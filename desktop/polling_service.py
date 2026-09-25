import threading

import requests

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib

from screenshot_handler import handle_screenshot_request


class PollingService:
    """Background service that polls the server for new messages and screenshot requests."""

    def __init__(self, config, on_new_messages=None):
        """
        Args:
            config: Config instance.
            on_new_messages: Callback receiving a list of message dicts.
        """
        self._config = config
        self._on_new_messages = on_new_messages
        self._running = False
        self._message_timer_id = None
        self._screenshot_timer_id = None

    def start(self):
        """Start polling timers on the GLib main loop."""
        self._running = True
        self._message_timer_id = GLib.timeout_add_seconds(3, self._poll_messages_tick)
        self._screenshot_timer_id = GLib.timeout_add_seconds(10, self._poll_screenshots_tick)
        print("[polling] Service started")

    def stop(self):
        """Stop all polling."""
        self._running = False
        if self._message_timer_id is not None:
            GLib.source_remove(self._message_timer_id)
            self._message_timer_id = None
        if self._screenshot_timer_id is not None:
            GLib.source_remove(self._screenshot_timer_id)
            self._screenshot_timer_id = None
        print("[polling] Service stopped")

    def _poll_messages_tick(self):
        """GLib timeout callback for message polling. Returns True to keep running."""
        if not self._running:
            return False
        thread = threading.Thread(target=self._poll_messages, daemon=True)
        thread.start()
        return True

    def _poll_screenshots_tick(self):
        """GLib timeout callback for screenshot polling. Returns True to keep running."""
        if not self._running:
            return False
        thread = threading.Thread(target=self._poll_screenshots, daemon=True)
        thread.start()
        return True

    def _poll_messages(self):
        """Fetch new messages from the server (runs in background thread)."""
        try:
            url = f"{self._config.server_url}/api/messages"
            headers = {"X-Child-Token": self._config.auth_token}
            params = {"childId": self._config.child_id}
            if self._config.last_message_timestamp:
                params["since"] = self._config.last_message_timestamp

            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"[polling] Message poll failed ({response.status_code})")
                return

            data = response.json()
            messages = data if isinstance(data, list) else data.get("messages", [])

            if not messages:
                return

            # Update since cursor to just past the latest message to avoid re-fetch
            latest_ts = None
            for msg in messages:
                ts = msg.get("timestamp") or msg.get("createdAt")
                if ts and (latest_ts is None or ts > latest_ts):
                    latest_ts = ts

            if latest_ts:
                # Append ~ so next gte query excludes this exact timestamp
                self._config.last_message_timestamp = latest_ts + "~"
                self._config.save()

            # Filter out child's own messages — already shown locally when sent
            parent_messages = [
                m for m in messages if m.get("senderType") != "child"
            ]
            if parent_messages and self._on_new_messages:
                GLib.idle_add(self._on_new_messages, parent_messages)

        except requests.ConnectionError:
            print("[polling] Message poll: connection error")
        except requests.Timeout:
            print("[polling] Message poll: timeout")
        except Exception as e:
            print(f"[polling] Message poll error: {e}")

    def _poll_screenshots(self):
        """Check for pending screenshot requests (runs in background thread)."""
        try:
            url = f"{self._config.server_url}/api/screenshots/pending"
            headers = {"X-Child-Token": self._config.auth_token}
            params = {"childId": self._config.child_id}

            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"[polling] Screenshot poll failed ({response.status_code})")
                return

            data = response.json()
            requests_list = data if isinstance(data, list) else data.get("requests", [])

            for req in requests_list:
                request_id = req.get("requestId") or req.get("id")
                if request_id:
                    print(f"[polling] Processing screenshot request: {request_id}")
                    handle_screenshot_request(self._config, request_id)

        except requests.ConnectionError:
            print("[polling] Screenshot poll: connection error")
        except requests.Timeout:
            print("[polling] Screenshot poll: timeout")
        except Exception as e:
            print(f"[polling] Screenshot poll error: {e}")
