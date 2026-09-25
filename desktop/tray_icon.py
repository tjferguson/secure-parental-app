import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

try:
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3

    HAS_APPINDICATOR = True
except (ValueError, ImportError):
    HAS_APPINDICATOR = False
    print(
        "[tray] AppIndicator3 not available. "
        "System tray icon will not be shown. "
        "Install gir1.2-appindicator3-0.1 for tray support."
    )


class TrayIcon:
    """System tray icon using AppIndicator3 with a fallback no-op."""

    ICON_NORMAL = "user-available"
    ICON_UNREAD = "mail-message-new"

    def __init__(self, on_open_chat=None, on_quit=None):
        """
        Args:
            on_open_chat: Callback when user clicks 'Open Chat'.
            on_quit: Callback when user clicks 'Quit'. If None, Quit menu item is hidden.
        """
        self._on_open_chat = on_open_chat
        self._on_quit = on_quit
        self._indicator = None
        self._status_item = None

        if not HAS_APPINDICATOR:
            return

        self._indicator = AppIndicator3.Indicator.new(
            "parentchat-indicator",
            self.ICON_NORMAL,
            AppIndicator3.IndicatorCategory.COMMUNICATIONS,
        )
        self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self._indicator.set_title("ParentChat")

        menu = Gtk.Menu()

        # Open Chat
        item_open = Gtk.MenuItem(label="Open Chat")
        item_open.connect("activate", self._on_open_chat_clicked)
        menu.append(item_open)

        menu.append(Gtk.SeparatorMenuItem())

        # Status label
        self._status_item = Gtk.MenuItem(label="Status: Connected")
        self._status_item.set_sensitive(False)
        menu.append(self._status_item)

        # Only show Quit option if a quit callback is provided (dev mode)
        if self._on_quit is not None:
            menu.append(Gtk.SeparatorMenuItem())
            item_quit = Gtk.MenuItem(label="Quit")
            item_quit.connect("activate", self._on_quit_clicked)
            menu.append(item_quit)

        menu.show_all()
        self._indicator.set_menu(menu)

    def _on_open_chat_clicked(self, widget):
        if self._on_open_chat:
            self._on_open_chat()

    def _on_quit_clicked(self, widget):
        if self._on_quit:
            self._on_quit()
        else:
            Gtk.main_quit()

    def set_has_unread(self, has_unread):
        """Update the tray icon to reflect unread message state.

        Args:
            has_unread: True to show unread indicator, False for normal.
        """
        if self._indicator is None:
            return

        if has_unread:
            self._indicator.set_icon_full(self.ICON_UNREAD, "New messages")
        else:
            self._indicator.set_icon_full(self.ICON_NORMAL, "ParentChat")

    def set_status(self, status_text):
        """Update the status label in the menu.

        Args:
            status_text: Text to display (e.g. 'Connected', 'Disconnected').
        """
        if self._status_item is not None:
            self._status_item.set_label(f"Status: {status_text}")
