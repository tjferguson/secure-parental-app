import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
import requests


class RegistrationWindow(Gtk.Window):
    """Registration window that accepts a code and registers the child device."""

    def __init__(self, config, on_registered=None):
        super().__init__(title="ParentChat Registration")
        self._config = config
        self._on_registered = on_registered

        self.set_default_size(400, 200)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(False)
        self.set_border_width(20)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        vbox.set_halign(Gtk.Align.CENTER)
        vbox.set_valign(Gtk.Align.CENTER)

        label = Gtk.Label(label="Enter Registration Code")
        label.set_markup("<b><big>Enter Registration Code</big></b>")
        vbox.pack_start(label, False, False, 0)

        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text("Registration code")
        self._entry.set_width_chars(30)
        self._entry.connect("activate", self._on_register_clicked)
        vbox.pack_start(self._entry, False, False, 0)

        self._register_button = Gtk.Button(label="Register")
        self._register_button.connect("clicked", self._on_register_clicked)
        self._register_button.get_style_context().add_class("suggested-action")
        vbox.pack_start(self._register_button, False, False, 0)

        self._spinner = Gtk.Spinner()
        vbox.pack_start(self._spinner, False, False, 0)

        self.add(vbox)
        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, widget):
        if not self._config.is_registered():
            Gtk.main_quit()

    def _set_sensitive(self, sensitive):
        self._entry.set_sensitive(sensitive)
        self._register_button.set_sensitive(sensitive)
        if sensitive:
            self._spinner.stop()
        else:
            self._spinner.start()

    def _on_register_clicked(self, widget):
        code = self._entry.get_text().strip()
        if not code:
            self._show_error("Please enter a registration code.")
            return

        self._set_sensitive(False)
        thread = threading.Thread(target=self._do_register, args=(code,), daemon=True)
        thread.start()

    def _do_register(self, code):
        try:
            url = f"{self._config.server_url}/api/children/register"
            response = requests.post(url, json={"code": code}, timeout=15)
            if response.status_code == 200:
                data = response.json()
                child_id = data.get("childId")
                auth_token = data.get("authToken")
                if child_id and auth_token:
                    display_name = data.get("displayName", "")
                    parent_id = data.get("parentId", "")
                    GLib.idle_add(self._on_register_success, child_id, auth_token, parent_id, display_name)
                else:
                    GLib.idle_add(
                        self._on_register_error,
                        "Invalid server response: missing childId or authToken.",
                    )
            else:
                try:
                    err_data = response.json()
                    msg = err_data.get("error", response.text)
                except Exception:
                    msg = response.text
                GLib.idle_add(
                    self._on_register_error,
                    f"Registration failed ({response.status_code}): {msg}",
                )
        except requests.ConnectionError:
            GLib.idle_add(
                self._on_register_error,
                "Could not connect to server. Check the server URL and try again.",
            )
        except requests.Timeout:
            GLib.idle_add(self._on_register_error, "Request timed out. Try again.")
        except Exception as e:
            GLib.idle_add(self._on_register_error, f"Unexpected error: {e}")

    def _on_register_success(self, child_id, auth_token, parent_id="", display_name=""):
        self._config.child_id = child_id
        self._config.auth_token = auth_token
        self._config.parent_id = parent_id
        self._config.display_name = display_name
        self._config.save()

        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Registration Successful",
        )
        dialog.format_secondary_text("This device has been registered successfully.")
        dialog.run()
        dialog.destroy()

        if self._on_registered:
            self._on_registered()

        self.destroy()

    def _on_register_error(self, message):
        self._set_sensitive(True)
        self._show_error(message)

    def _show_error(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Registration Error",
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()
