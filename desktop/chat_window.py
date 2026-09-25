import subprocess
import threading
import os
from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango
import requests


CSS = """
#chat-window {
    background-color: #f0f0f0;
}

#header-bar {
    background-color: #2c3e50;
    color: white;
    padding: 8px 12px;
}

#header-label {
    color: white;
    font-size: 16px;
    font-weight: bold;
}

#message-area {
    background-color: #f0f0f0;
}

#parent-message {
    background-color: #3498db;
    color: white;
    border-radius: 12px;
    padding: 8px 12px;
    margin: 4px 60px 4px 8px;
}

#child-message {
    background-color: #2ecc71;
    color: white;
    border-radius: 12px;
    padding: 8px 12px;
    margin: 4px 8px 4px 60px;
}

#timestamp-label {
    color: #999999;
    font-size: 10px;
    padding: 0px 12px 2px 12px;
}

#input-area {
    background-color: #ffffff;
    padding: 8px;
}

#message-entry {
    border-radius: 20px;
    padding: 8px 12px;
    font-size: 14px;
}

#send-button {
    border-radius: 20px;
    background-color: #3498db;
    color: white;
    padding: 8px 16px;
    font-weight: bold;
}
"""


def _apply_css():
    """Load and apply the CSS provider."""
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


def _play_notification_sound():
    """Play a notification sound using available system tools."""
    sound_paths = [
        "/usr/share/sounds/freedesktop/stereo/message-new-instant.oga",
        "/usr/share/sounds/gnome/default/alerts/drip.ogg",
        "/usr/share/sounds/ubuntu/stereo/message-new-instant.ogg",
        "/usr/share/sounds/freedesktop/stereo/bell.oga",
        "/usr/share/sounds/sound-icons/percussion-10.wav",
    ]

    sound_file = None
    for path in sound_paths:
        if os.path.isfile(path):
            sound_file = path
            break

    if sound_file:
        for player in ["paplay", "aplay", "play"]:
            try:
                subprocess.Popen(
                    [player, sound_file],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except FileNotFoundError:
                continue

    # Last resort: terminal bell
    try:
        subprocess.Popen(
            ["bash", "-c", "echo -e '\\a'"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _set_x11_above(window):
    """Try to set _NET_WM_STATE_ABOVE via X11 for maximum compatibility."""
    try:
        gdk_window = window.get_window()
        if gdk_window is None:
            return
        gi.require_version("GdkX11", "3.0")
        from gi.repository import GdkX11

        if isinstance(gdk_window, GdkX11.X11Window):
            display = gdk_window.get_display()
            xid = gdk_window.get_xid()
            try:
                subprocess.Popen(
                    ["xdotool", "windowactivate", "--sync", str(xid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                pass
    except Exception:
        pass


class ChatWindow(Gtk.Window):
    """Chat popup window that appears over fullscreen applications."""

    def __init__(self, config):
        super().__init__(title="ParentChat")
        self._config = config

        _apply_css()

        self.set_name("chat-window")
        self.set_default_size(400, 500)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.stick()
        self.set_urgency_hint(True)
        self.set_skip_taskbar_hint(False)
        self.set_decorated(True)

        # Position at top-right of screen
        screen = Gdk.Screen.get_default()
        monitor_geo = screen.get_monitor_geometry(screen.get_primary_monitor())
        x = monitor_geo.x + monitor_geo.width - 420
        y = monitor_geo.y + 20
        self.move(x, y)

        # Main vertical layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Header bar
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header.set_name("header-bar")
        header_label = Gtk.Label(label="ParentChat")
        header_label.set_name("header-label")
        header_label.set_halign(Gtk.Align.START)
        header_label.set_margin_start(8)
        header_label.set_margin_top(6)
        header_label.set_margin_bottom(6)
        header.pack_start(header_label, True, True, 0)
        main_box.pack_start(header, False, False, 0)

        # Scrollable message area
        self._scrolled = Gtk.ScrolledWindow()
        self._scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scrolled.set_vexpand(True)

        self._message_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._message_box.set_name("message-area")
        self._message_box.set_margin_top(8)
        self._message_box.set_margin_bottom(8)
        self._scrolled.add(self._message_box)
        main_box.pack_start(self._scrolled, True, True, 0)

        # Input area
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        input_box.set_name("input-area")
        input_box.set_margin_start(8)
        input_box.set_margin_end(8)
        input_box.set_margin_top(6)
        input_box.set_margin_bottom(6)

        self._entry = Gtk.Entry()
        self._entry.set_name("message-entry")
        self._entry.set_placeholder_text("Type a message...")
        self._entry.set_hexpand(True)
        self._entry.connect("activate", self._on_send)
        input_box.pack_start(self._entry, True, True, 0)

        send_button = Gtk.Button(label="Send")
        send_button.set_name("send-button")
        send_button.connect("clicked", self._on_send)
        input_box.pack_end(send_button, False, False, 0)

        main_box.pack_start(input_box, False, False, 0)

        self.add(main_box)

        # Hide instead of destroy on close
        self.connect("delete-event", self._on_delete)

    def _on_delete(self, widget, event):
        self.hide()
        return True

    def add_message(self, sender_type, content, timestamp=None):
        """Add a message bubble to the chat area.

        Args:
            sender_type: 'parent' or 'child'
            content: message text
            timestamp: ISO timestamp string or None
        """
        # Message label
        label = Gtk.Label(label=content)
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(35)
        label.set_xalign(0)
        label.set_selectable(True)

        if sender_type == "parent":
            label.set_name("parent-message")
            label.set_halign(Gtk.Align.START)
        else:
            label.set_name("child-message")
            label.set_halign(Gtk.Align.END)

        self._message_box.pack_start(label, False, False, 0)

        # Timestamp
        if timestamp:
            try:
                if isinstance(timestamp, str):
                    # Strip UUID suffix: "2026-03-09T17:16:08+00:00_uuid" -> ISO part
                    import re
                    iso_str = re.sub(r'_[0-9a-f-]+$', '', timestamp)
                    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
                    ts_text = dt.strftime("%I:%M %p")
                else:
                    ts_text = str(timestamp)
            except Exception:
                ts_text = ""

            ts_label = Gtk.Label(label=ts_text)
            ts_label.set_name("timestamp-label")
            if sender_type == "parent":
                ts_label.set_halign(Gtk.Align.START)
            else:
                ts_label.set_halign(Gtk.Align.END)
            self._message_box.pack_start(ts_label, False, False, 0)

        self._message_box.show_all()
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        """Scroll message area to the bottom."""

        def _do_scroll():
            adj = self._scrolled.get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())
            return False

        GLib.timeout_add(50, _do_scroll)

    def show_with_notification(self):
        """Show the chat window and play a notification sound."""
        self.show_all()
        self.present_with_time(Gdk.CURRENT_TIME)
        self.set_keep_above(True)

        # Try to set X11 above state after the window is mapped
        GLib.idle_add(_set_x11_above, self)

        # Play notification sound in background thread
        threading.Thread(target=_play_notification_sound, daemon=True).start()

    def _on_send(self, widget):
        """Handle send button click or Enter key press."""
        text = self._entry.get_text().strip()
        if not text:
            return

        self._entry.set_text("")
        self._entry.set_sensitive(False)

        # Add message to UI immediately
        self.add_message("child", text, datetime.now().isoformat())

        # Send in background
        thread = threading.Thread(
            target=self._do_send, args=(text,), daemon=True
        )
        thread.start()

    def _do_send(self, text):
        """Send message to server in a background thread."""
        try:
            url = f"{self._config.server_url}/api/messages"
            headers = {"X-Child-Token": self._config.auth_token}
            payload = {
                "content": text,
            }
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code != 200 and response.status_code != 201:
                GLib.idle_add(self._show_send_error, f"Server returned {response.status_code}")
        except requests.ConnectionError:
            GLib.idle_add(self._show_send_error, "Could not connect to server.")
        except requests.Timeout:
            GLib.idle_add(self._show_send_error, "Request timed out.")
        except Exception as e:
            GLib.idle_add(self._show_send_error, str(e))
        finally:
            GLib.idle_add(self._entry.set_sensitive, True)
            GLib.idle_add(self._entry.grab_focus)

    def _show_send_error(self, message):
        """Show a brief error message for a failed send."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Send Failed",
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()
