#!/usr/bin/env python3
"""ParentChat Desktop Client - main entry point."""

import argparse
import os
import sys
import signal

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from config import Config
from registration import RegistrationWindow
from chat_window import ChatWindow
from polling_service import PollingService
from tray_icon import TrayIcon


def main():
    parser = argparse.ArgumentParser(description="ParentChat Desktop Client")
    parser.add_argument(
        "--server-url",
        default="http://localhost:8080",
        help="Server URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--config-dir",
        default=os.path.join(os.path.expanduser("~"), ".parentchat"),
        help="Config directory (default: ~/.parentchat)",
    )
    parser.add_argument(
        "--allow-quit",
        action="store_true",
        help="Allow quitting the app (for development only)",
    )
    args = parser.parse_args()

    if not args.allow_quit:
        # Prevent child from terminating the process via signals
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        signal.signal(signal.SIGQUIT, signal.SIG_IGN)
    else:
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    config = Config(config_dir=args.config_dir, server_url=args.server_url)

    allow_quit = args.allow_quit

    if not config.is_registered():
        def on_registered():
            _start_app(config, allow_quit)

        reg_window = RegistrationWindow(config, on_registered=on_registered)
        reg_window.show_all()
        Gtk.main()
    else:
        _start_app(config, allow_quit)
        Gtk.main()


def _start_app(config, allow_quit=False):
    """Initialize and start the main application components."""
    chat_window = ChatWindow(config)
    polling_service = None

    def on_open_chat():
        chat_window.show_with_notification()
        tray.set_has_unread(False)

    on_quit = None
    if allow_quit:
        def on_quit():
            if polling_service is not None:
                polling_service.stop()
            Gtk.main_quit()

    tray = TrayIcon(on_open_chat=on_open_chat, on_quit=on_quit)

    def on_new_messages(messages):
        if not messages:
            return
        for msg in messages:
            sender_type = msg.get("senderType", "parent")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp") or msg.get("createdAt")
            chat_window.add_message(sender_type, content, timestamp)

        # Only show notification for parent messages
        has_parent_msg = any(
            msg.get("senderType") == "parent" for msg in messages
        )
        if has_parent_msg:
            chat_window.show_with_notification()
            tray.set_has_unread(True)

    polling_service = PollingService(config, on_new_messages=on_new_messages)
    polling_service.start()

    print("[main] ParentChat desktop client running")


if __name__ == "__main__":
    main()
