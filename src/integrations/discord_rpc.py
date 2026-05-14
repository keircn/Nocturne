# discord_rpc.py

import ipaddress, json, os, socket, struct, threading, time, uuid
from gi.repository import GLib, Gst
from urllib.parse import urlparse, urlunparse

from . import get_current_integration


class DiscordRPC:
    MAX_FIELD_LENGTH = 127

    def __init__(self, player):
        self.player = player
        self.socket = None
        self.client_id = ""
        self.state_lock = threading.Lock()
        self.socket_lock = threading.Lock()
        self.pending = None
        self.worker_running = False
        self.generation = 0
        self.update_source_id = None

    def close(self):
        with self.state_lock:
            self.generation += 1
            self.pending = None
            if self.update_source_id:
                GLib.source_remove(self.update_source_id)
                self.update_source_id = None
        with self.socket_lock:
            self._clear()
            if self.socket:
                try:
                    self.socket.close()
                except OSError:
                    pass
                self.socket = None
            self.client_id = ""

    def update(self):
        if not self.player.settings.get_value("discord-rpc-enabled").unpack():
            self.close()
            return

        client_id = self.player.settings.get_value("discord-rpc-client-id").unpack().strip()
        if not client_id:
            self.close()
            return

        with self.state_lock:
            if self.update_source_id:
                GLib.source_remove(self.update_source_id)
            self.update_source_id = GLib.timeout_add(500, self._queue_update, client_id)

    def _queue_update(self, client_id):
        activity = self._get_activity()
        with self.state_lock:
            self.update_source_id = None
            self.generation += 1
            self.pending = (self.generation, client_id, activity)
            if self.worker_running:
                return GLib.SOURCE_REMOVE
            self.worker_running = True
        threading.Thread(target=self._run, daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _run(self):
        while True:
            with self.state_lock:
                if not self.pending:
                    self.worker_running = False
                    return
                generation, client_id, activity = self.pending
                self.pending = None

            with self.socket_lock:
                with self.state_lock:
                    if generation != self.generation:
                        continue
                if self.client_id != client_id:
                    self._disconnect()
                if not self.socket and not self._connect(client_id):
                    continue
                with self.state_lock:
                    if self.pending or generation != self.generation:
                        continue
                if not self._set_activity(activity):
                    self._disconnect()

    def _set_activity(self, activity):
        return self._send(1, {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": os.getpid(),
                "activity": activity
            },
            "nonce": uuid.uuid4().hex
        })

    def _get_activity(self):
        integration = get_current_integration()
        if not integration:
            return None

        current_song = integration.loaded_models.get("currentSong")
        song_id = current_song.get_property("songId")
        if not song_id:
            return None

        song = integration.loaded_models.get(song_id)
        success, state, pending = self.player.gst.get_state(0)
        if current_song.get_property("buttonState") == "play" and pending != Gst.State.PLAYING:
            return {
                "details": _("Browsing Nocturne"),
                "type": 0,
                "assets": {
                    "large_image": "logo",
                    "large_text": "Nocturne"
                }
            }

        if song and song.get_property("isRadio"):
            title = current_song.get_property("displaySongTitle") or song.get_property("title")
            artist = current_song.get_property("displaySongArtist") or song.get_property("artist")
        else:
            title = song.get_property("title") if song else current_song.get_property("displaySongTitle")
            if song and song.get_property("artists"):
                artist = ", ".join([a.get("name") for a in song.get_property("artists")])
            else:
                artist = song.get_property("artist") if song else current_song.get_property("displaySongArtist")
        activity = {
            "details": self._truncate(title or _("Listening to music")),
            "state": self._truncate(artist) if artist else None,
            "type": 2,
            "assets": {
                "large_text": self._truncate(song.get_property("album") if song else "Nocturne")
            }
        }
        if song and (cover_url := integration.getCoverArtUrl(song_id, big=True)):
            cover_url = self._with_public_base_url(cover_url)
            activity["assets"]["large_image"] = cover_url if self._is_discord_accessible_url(cover_url) else "logo"
        else:
            activity["assets"]["large_image"] = "logo"

        if song and song.get_property("duration") > 0:
            position = max(current_song.get_property("positionSeconds"), 0)
            started_at = int(time.time() - position)
            activity["timestamps"] = {
                "start": started_at,
                "end": started_at + song.get_property("duration")
            }

        return activity

    def _connect(self, client_id):
        for path in self._get_socket_paths():
            try:
                rpc_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                rpc_socket.settimeout(2)
                rpc_socket.connect(path)
                self.socket = rpc_socket
                self.client_id = client_id
                if self._send(0, {"v": 1, "client_id": client_id}):
                    self._receive()
                    return True
            except OSError:
                self._disconnect()
        return False

    def _get_socket_paths(self):
        dirs = [
            os.environ.get("XDG_RUNTIME_DIR"),
            os.environ.get("TMPDIR"),
            "/tmp",
        ]
        return [
            os.path.join(directory, "discord-ipc-{}".format(index))
            for directory in dirs
            if directory
            for index in range(10)
        ]

    def _truncate(self, field):
        return field if len(field) <= self.MAX_FIELD_LENGTH else field[:self.MAX_FIELD_LENGTH - 1] + "..."

    def _with_public_base_url(self, url):
        public_url = self.player.settings.get_value("discord-rpc-public-url").unpack().strip().rstrip("/")
        if not public_url:
            return url

        if "://" not in public_url:
            public_url = "https://{}".format(public_url)

        parsed_url = urlparse(url)
        parsed_public_url = urlparse(public_url)
        if not parsed_url.scheme or not parsed_url.netloc or not parsed_public_url.scheme or not parsed_public_url.netloc:
            return url

        public_path = parsed_public_url.path.rstrip("/")
        path = "{}{}".format(public_path, parsed_url.path) if public_path else parsed_url.path
        return urlunparse(parsed_url._replace(
            scheme=parsed_public_url.scheme,
            netloc=parsed_public_url.netloc,
            path=path
        ))

    def _is_discord_accessible_url(self, url):
        parsed_url = urlparse(url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.hostname:
            return False
        if parsed_url.hostname == "localhost":
            return False
        try:
            ip = ipaddress.ip_address(parsed_url.hostname)
            return not (ip.is_private or ip.is_loopback or ip.is_link_local)
        except ValueError:
            return True

    def _send(self, op, payload):
        try:
            data = json.dumps(payload).encode("utf-8")
            self.socket.sendall(struct.pack("<II", op, len(data)) + data)
            return True
        except OSError:
            return False

    def _receive(self):
        try:
            header = self.socket.recv(8)
            if len(header) != 8:
                return None
            op, length = struct.unpack("<II", header)
            return json.loads(self.socket.recv(length).decode("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _clear(self):
        if self.socket:
            self._set_activity(None)

    def _disconnect(self):
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
        self.socket = None
        self.client_id = ""
