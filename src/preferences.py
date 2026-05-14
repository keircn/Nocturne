# preferences.py

from gi.repository import Gtk, Adw, GLib, Gst, Gio, GObject, Gdk

from .integrations import get_current_integration, secret
from .constants import SIDEBAR_MENU, BITRATE_OPTIONS
import threading

@Gtk.Template(resource_path='/com/jeffser/Nocturne/preferences.ui')
class NocturnePreferences(Adw.PreferencesDialog):
    __gtype_name__ = 'NocturnePreferencesDialog'

    # General
    ## Behavior
    restore_el = Gtk.Template.Child()
    hide_on_close_el = Gtk.Template.Child()
    simulate_wbwl_el = Gtk.Template.Child()
    default_page_el = Gtk.Template.Child()
    bitrate_el = Gtk.Template.Child()

    ## Session
    session_group_el = Gtk.Template.Child()
    listenbrainz_stack_el = Gtk.Template.Child()
    instance_avatar_el = Gtk.Template.Child()
    instance_icon_el = Gtk.Template.Child()
    instance_el = Gtk.Template.Child()
    discord_rpc_el = Gtk.Template.Child()
    discord_rpc_client_id_el = Gtk.Template.Child()
    discord_rpc_public_url_el = Gtk.Template.Child()

    # Customization
    ## Interface
    context_button_el = Gtk.Template.Child()
    context_label_el = Gtk.Template.Child()
    show_playlists_sidebar_el = Gtk.Template.Child()
    footer_big_mode_el = Gtk.Template.Child()
    translucent_player_el = Gtk.Template.Child()
    use_sidebar_player_el = Gtk.Template.Child()

    ## Dynamic Background
    global_dynamic_bg_el = Gtk.Template.Child()
    player_dynamic_bg_el = Gtk.Template.Child()
    popout_dynamic_bg_el = Gtk.Template.Child()
    dynamic_accent_el = Gtk.Template.Child()

    ## Homepage
    hp_songs_el = Gtk.Template.Child()
    hp_albums_el = Gtk.Template.Child()
    hp_artists_el = Gtk.Template.Child()
    hp_playlists_el = Gtk.Template.Child()

    # Visualizer
    ## Preferences
    visualizer_el = Gtk.Template.Child()

    ## Appearance
    visualizer_bar_n_el = Gtk.Template.Child()
    visualizer_type_el = Gtk.Template.Child()
    visualizer_fill_el = Gtk.Template.Child()

    ## Color
    visualizer_auto_color_el = Gtk.Template.Child()
    visualizer_invert_auto_color_el = Gtk.Template.Child()
    visualizer_manual_color_el = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        settings = Gio.Settings(schema_id="com.jeffser.Nocturne")
        integration = get_current_integration()

        # General
        ## Behavior
        settings.bind(
            "restore-session",
            self.restore_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "hide-on-close",
            self.hide_on_close_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "simulate-word-by-word-lyrics",
            self.simulate_wbwl_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )
        self.default_page_dict = {}
        selected_page = settings.get_value('default-page-tag').unpack()
        for section in SIDEBAR_MENU:
            for item in section.get('items', []):
                if section.get('title') and item.get('page-tag') != "radios":
                    title = '{} ({})'.format(section.get('title'), item.get('title'))
                else:
                    title = item.get('title')
                self.default_page_dict[title] = item.get('page-tag')
                self.default_page_el.get_model().append(title)
                if item.get('page-tag') == selected_page:
                    self.default_page_el.set_selected(len(self.default_page_dict) - 1)
        self.max_bitrate_dict = {}
        selected_bitrate = settings.get_value('max-bitrate').unpack()
        for title, kbps in BITRATE_OPTIONS.items():
            if kbps != 0:
                title = title.format('{} kbps'.format(kbps))
            self.max_bitrate_dict[title] = kbps
            self.bitrate_el.get_model().append(title)
            if kbps == selected_bitrate:
                self.bitrate_el.set_selected(len(self.max_bitrate_dict) - 1)
        if integration:
            self.bitrate_el.set_visible('no-max-bitrate' not in integration.limitations)
        else:
            self.bitrate_el.set_visible(False)

        ## Session
        settings.bind(
            "discord-rpc-enabled",
            self.discord_rpc_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "discord-rpc-client-id",
            self.discord_rpc_client_id_el,
            "text",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "discord-rpc-public-url",
            self.discord_rpc_public_url_el,
            "text",
            Gio.SettingsBindFlags.DEFAULT
        )

        self.listenbrainz_stack_el.set_visible_child_name("unlink" if secret.get_plain_password(schema_type="listenbrainz") else "link")
        if integration:
            data = integration.getServerInformation()
            self.instance_el.set_title(data.get('username', ""))

            self.instance_el.set_subtitle(data.get('title', ""))

            self.instance_el.set_tooltip_text(data.get('link'))
            self.instance_el.set_action_target_value(GLib.Variant('s', data.get('link', '')))
            self.instance_icon_el.set_visible(data.get('link'))
            self.instance_el.set_activatable(data.get('link'))

            self.instance_avatar_el.set_custom_image(data.get('picture'))
            self.instance_avatar_el.set_text(data.get('username', ''))
            self.instance_el.set_visible(len(data) > 0)
            self.session_group_el.set_visible(True)
        else:
            self.session_group_el.set_visible(False)

        # Customization
        ## Interface
        settings.bind(
            "show-context-button",
            self.context_button_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "show-context-button-label",
            self.context_label_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "show-playlists-in-sidebar",
            self.show_playlists_sidebar_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "use-big-footer",
            self.footer_big_mode_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "player-blur-bg",
            self.translucent_player_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "use-sidebar-player",
            self.use_sidebar_player_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )

        ## Dynamic Background
        settings.bind(
            "global-dynamic-bg-mode",
            self.global_dynamic_bg_el,
            "active-name",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "player-dynamic-bg-mode",
            self.player_dynamic_bg_el,
            "active-name",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "popout-dynamic-bg-mode",
            self.popout_dynamic_bg_el,
            "active-name",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "use-dynamic-accent",
            self.dynamic_accent_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )

        ## Homepage
        settings.bind(
            "n-songs-home",
            self.hp_songs_el,
            "value",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "n-albums-home",
            self.hp_albums_el,
            "value",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "n-artists-home",
            self.hp_artists_el,
            "value",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "n-playlists-home",
            self.hp_playlists_el,
            "value",
            Gio.SettingsBindFlags.DEFAULT
        )

        # Visualizer
        ## Preferences
        settings.bind(
            "show-visualizer",
            self.visualizer_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )

        ## Appearance
        settings.bind(
            "visualizer-bar-n",
            self.visualizer_bar_n_el,
            "value",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "visualizer-type",
            self.visualizer_type_el,
            "active-name",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "visualizer-fill-mode",
            self.visualizer_fill_el,
            "active-name",
            Gio.SettingsBindFlags.DEFAULT
        )

        ## Color
        settings.bind(
            "visualizer-auto-color",
            self.visualizer_auto_color_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )
        settings.bind(
            "visualizer-auto-color-invert",
            self.visualizer_invert_auto_color_el,
            "active",
            Gio.SettingsBindFlags.DEFAULT
        )
        try:
            rgb_str = settings.get_value('visualizer-manual-color').unpack()
            rgb_list = [float(c) for c in rgb_str.split(',')]
        except:
            rgb_list = [0.11, 0.44, 0.85]
        self.visualizer_manual_color_el.set_rgba(Gdk.RGBA(
            red=rgb_list[0],
            green=rgb_list[1],
            blue=rgb_list[2],
            alpha=1
        ))

    @Gtk.Template.Callback()
    def default_page_changed(self, combo_row, ud):
        page_tag = self.default_page_dict.get(combo_row.get_selected_item().get_string(), 'home')
        Gio.Settings(schema_id="com.jeffser.Nocturne").set_string('default-page-tag', page_tag)

    @Gtk.Template.Callback()
    def max_bitrate_changed(self, combo_row, ud):
        bitrate = self.max_bitrate_dict.get(combo_row.get_selected_item().get_string(), 0)
        Gio.Settings(schema_id="com.jeffser.Nocturne").set_int('max-bitrate', bitrate)

    @Gtk.Template.Callback()
    def visualizer_manual_color_changed(self, btn, ud):
        rgb = ','.join([str(round(c, 3)) for c in list(btn.get_rgba())[:-1]])
        Gio.Settings(schema_id="com.jeffser.Nocturne").set_string('visualizer-manual-color', rgb)

    @Gtk.Template.Callback()
    def listenbrainz_link_requested(self, button):
        def on_response(dialog, result, token_entry_el):
            response = dialog.choose_finish(result)
            if response == "save":
                if token := token_entry_el.get_text():
                    secret.store_password(
                        token,
                        schema_type="listenbrainz"
                    )
                    self.listenbrainz_stack_el.set_visible_child_name("unlink")

        container = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10
        )
        container.append(Gtk.LinkButton(
            label=_("Settings Page"),
            uri="https://listenbrainz.org/settings/"
        ))
        token_el = Gtk.Entry(placeholder_text=_("User Token"))
        container.append(token_el)

        dialog = Adw.AlertDialog(
            heading=_("Link ListenBrainz"),
            body=_("Connect your ListenBrainz account with a user token"),
            extra_child=container
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("save", _("Save"))
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        dialog.choose(
            self.get_root(),
            None,
            on_response,
            token_el
        )

    @Gtk.Template.Callback()
    def listenbrainz_unlink_requested(self, button):
        secret.remove_password(
            schema_type="listenbrainz",
            callback=lambda: self.listenbrainz_stack_el.set_visible_child_name("link")
        )
