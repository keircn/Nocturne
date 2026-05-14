# main.py
#
# Copyright 2026 Jeffry Samuel
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import sys, pathlib, threading
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Secret', '1')
gi.require_version('Gst', '1.0')

from gi.repository import Gtk, Gdk, Gio, Adw, GLib
from .window import NocturneWindow
from .preferences import NocturnePreferences
from .constants import get_song_info_from_file, TRANSLATORS, DEFAULT_MUSIC_DIR, set_version
from .integrations import get_current_integration, set_current_integration, get_available_integrations, models
from .widgets.playing import Player
from .widgets.pages import LoginDialog
from . import widgets as Widgets

GLib.set_prgname('com.jeffser.Nocturne')
GLib.set_application_name("Nocturne")

class NocturneApplication(Adw.Application):
    __gtype_name__ = 'NocturneApplication'
    """The main application singleton class."""

    def __init__(self, version):
        self.version = version
        self.external_songs = []
        self.main_window = None
        self.popout_window = None
        self.player = None
        self.inhibit_cookie = None
        self.dbus_registration_id = None
        self.pending_miniplayer_present = False
        self.idle_inhibit_cookie = None
        self.css_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        super().__init__(application_id='com.jeffser.Nocturne',
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS | Gio.ApplicationFlags.HANDLES_OPEN,
                         resource_base_path='/com/jeffser/Nocturne')
        self.create_action('quit', lambda *_: self.quit(), ['<control>q'])
        self.create_action('about', self.on_about_action)
        self.create_action('preferences', self.on_preferences_action, ['<control>comma'])
        self.create_action('toggle-miniplayer', self.on_toggle_miniplayer_action)

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.register_dbus_interface()

    def do_shutdown(self):
        if self.dbus_registration_id:
            self.get_dbus_connection().unregister_object(self.dbus_registration_id)
            self.dbus_registration_id = None
        Adw.Application.do_shutdown(self)

    def register_dbus_interface(self):
        introspection = Gio.DBusNodeInfo.new_for_xml("""
            <node>
              <interface name="com.jeffser.Nocturne">
                <method name="ToggleMiniplayer"/>
              </interface>
            </node>
        """)
        interface = introspection.interfaces[0]
        self.dbus_registration_id = self.get_dbus_connection().register_object(
            '/com/jeffser/Nocturne',
            interface,
            self.on_dbus_method_call,
            None,
            None
        )

    def on_dbus_method_call(
        self,
        connection,
        sender,
        object_path,
        interface_name,
        method_name,
        parameters,
        invocation
    ):
        if interface_name == 'com.jeffser.Nocturne' and method_name == 'ToggleMiniplayer':
            self.toggle_miniplayer()
            invocation.return_value(GLib.Variant('()', ()))
        else:
            invocation.return_dbus_error(
                'com.jeffser.Nocturne.Error.NotSupported',
                f"Unsupported method {interface_name}.{method_name}"
            )

    def inhibit_suspend(self):
        if self.inhibit_cookie is None:
            self.inhibit_cookie = self.inhibit(
                self.get_active_window(),
                Gtk.ApplicationInhibitFlags.SUSPEND,
                _("Music is Playing")
            )

    def uninhibit_suspend(self):
        if self.inhibit_cookie is not None:
            self.uninhibit(self.inhibit_cookie)
            self.inhibit_cookie = None

    def inhibit_idle(self, window=None):
        if self.idle_inhibit_cookie is None:
            self.idle_inhibit_cookie = self.inhibit(
                window or self.get_active_window(),
                Gtk.ApplicationInhibitFlags.IDLE,
                _("Fullscreen Player Active")
            )

    def uninhibit_idle(self):
        if self.idle_inhibit_cookie is not None:
            self.uninhibit(self.idle_inhibit_cookie)
            self.idle_inhibit_cookie = None

    def load_default_integration(self):
        settings = Gio.Settings(schema_id="com.jeffser.Nocturne")
        selected_local_folder = settings.get_value("integration-library-dir").unpack()
        if not selected_local_folder:
            settings.set_string("integration-library-dir", DEFAULT_MUSIC_DIR)

        if selected_instance := settings.get_value("selected-instance-type").unpack():
            if integration_type := get_available_integrations().get(selected_instance):
                integration = integration_type(
                    url=settings.get_value('integration-ip').unpack(),
                    user=settings.get_value('integration-user').unpack(),
                    trustServer=settings.get_value('integration-trust-server').unpack()
                )
                directory = settings.get_value('integration-library-dir').unpack()
                if Gio.File.new_for_path(directory).query_exists():
                    integration.set_property('libraryDir', directory)
                threading.Thread(target=self.try_login, args=(integration,), daemon=True).start()
                return
        self.main_window.main_stack.set_visible_child_name('welcome')

    def try_login(self, integration):
        # call on different thread
        if integration.ping():
            set_current_integration(integration)
            integration.on_login()
            GLib.idle_add(self.main_window.main_stack.set_visible_child_name, "content")
            GLib.idle_add(self.main_window.setup)
            if not self.player:
                self.player = Player(self)
            if self.pending_miniplayer_present:
                self.pending_miniplayer_present = False
                GLib.idle_add(self.show_miniplayer)
            settings = Gio.Settings(schema_id="com.jeffser.Nocturne")
            default_page = settings.get_value('default-page-tag').unpack() or 'home'
            self.main_window.activate_action("app.replace_root_page", GLib.Variant('s', default_page))
            GLib.idle_add(threading.Thread(target=self.main_window.update_playlist_section_of_sidebar, daemon=True).start)
            if settings.get_value("restore-session").unpack():
                threading.Thread(target=self.player.restore_play_queue, daemon=True).start()
            if dialog := self.main_window.get_visible_dialog():
                dialog.close()
        else:
            self.main_window.main_stack.set_visible_child_name('welcome')
            toast = Adw.Toast(title=_("Login Failed"))
            dialog = self.main_window.get_visible_dialog()
            if not isinstance(dialog, LoginDialog):
                dialog = LoginDialog(integration)
                GLib.idle_add(dialog.present, self.main_window)
            GLib.idle_add(dialog.toast_overlay.add_toast, toast)
            GLib.idle_add(dialog.login_button_el.set_sensitive, True)

    def do_activate(self):
        if not self.main_window:
            self.main_window = NocturneWindow(application=self)
            self.load_default_integration()
        self.main_window.present()

    def on_toggle_miniplayer_action(self, *args):
        self.toggle_miniplayer()

    def show_miniplayer(self, fullscreened=False):
        if not self.popout_window:
            integration = get_current_integration()
            if not integration or not integration.loaded_models.get('currentSong'):
                self.pending_miniplayer_present = True
                self.do_activate()
                return
            self.popout_window = Widgets.PopoutWindow(
                application=self,
                fullscreened=fullscreened
            )
            self.popout_window.set_name('miniplayer')
            self.popout_window.connect('destroy', self.on_popout_window_destroyed)

        self.popout_window.present()

    def toggle_miniplayer(self):
        if self.popout_window and self.popout_window.get_visible():
            self.popout_window.hide()
            return
        self.show_miniplayer()

    def on_popout_window_destroyed(self, popout_window):
        if self.popout_window == popout_window:
            self.popout_window = None

    def do_open(self, files, n_files=None, hint=None):
        self.external_songs = []
        integration = get_current_integration()
        for file in files:
            result_path = file.get_path()
            audio_info = get_song_info_from_file(result_path, is_external_file=True)
            audio_info['id'] = 'EXTERNAL_SONG:{}'.format(result_path)
            if audio_info:
                self.external_songs.append(models.Song(**audio_info))
                if integration:
                    integration.loaded_models[audio_info.get('id')] = self.external_songs[-1]

        if self.main_window and integration:
            target_value = GLib.Variant('as', [a.id for a in self.external_songs])
            self.main_window.activate_action('app.play_songs', target_value)
            self.external_songs = []
        else:
            self.do_activate()

    def on_about_action(self, *args):
        about = Adw.AboutDialog(
            application_icon="com.jeffser.Nocturne",
            application_name="Nocturne",
            copyright="© 2026 Jeffry Samuel",
            developer_name="Jeffry Samuel",
            issue_url="https://github.com/Jeffser/Nocturne/issues",
            license="GPL-3.0-or-later",
            support_url="https://github.com/Jeffser/Nocturne/discussions",
            version=self.version,
            website="https://jeffser.com/nocturne",
            developers=['Jeffser https://jeffser.com'],
            designers=['Jeffser https://jeffser.com'],
            translator_credits='\n'.join(TRANSLATORS)
        )
        about.present(self.props.active_window)

    def on_preferences_action(self, widget, _):
        NocturnePreferences().present(self.props.active_window)

    def create_action(self, name, callback, shortcuts=None, parameter_type=None):
        action = Gio.SimpleAction.new(name, parameter_type)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)


def main(version):
    """The application's entry point."""
    print("Nocturne version:", version)
    set_version(version)
    return NocturneApplication(version).run(sys.argv)
