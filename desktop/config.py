import json
import os


class Config:
    """Configuration manager for ParentChat desktop client."""

    DEFAULT_CONFIG = {
        "child_id": None,
        "auth_token": None,
        "parent_id": None,
        "display_name": None,
        "server_url": "http://localhost:8080",
        "last_message_timestamp": None,
    }

    def __init__(self, config_dir=None, server_url=None):
        if config_dir is None:
            config_dir = os.path.join(os.path.expanduser("~"), ".parentchat")
        self._config_dir = config_dir
        self._config_file = os.path.join(self._config_dir, "config.json")
        self._data = dict(self.DEFAULT_CONFIG)
        if server_url is not None:
            self._data["server_url"] = server_url
        self.load()

    def _ensure_config_dir(self):
        """Create config directory if it doesn't exist."""
        if not os.path.isdir(self._config_dir):
            os.makedirs(self._config_dir, mode=0o700, exist_ok=True)

    def load(self):
        """Load configuration from disk. Handles missing or corrupt files gracefully."""
        self._ensure_config_dir()
        if not os.path.isfile(self._config_file):
            return
        try:
            with open(self._config_file, "r") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                for key in self.DEFAULT_CONFIG:
                    if key in stored:
                        self._data[key] = stored[key]
        except (json.JSONDecodeError, IOError, OSError) as e:
            print(f"[config] Warning: could not load config ({e}), using defaults")

    def save(self):
        """Persist current configuration to disk."""
        self._ensure_config_dir()
        try:
            with open(self._config_file, "w") as f:
                json.dump(self._data, f, indent=2)
        except (IOError, OSError) as e:
            print(f"[config] Warning: could not save config ({e})")

    def is_registered(self):
        """Return True if the client has a child_id and auth_token."""
        return bool(self._data.get("child_id")) and bool(self._data.get("auth_token"))

    @property
    def child_id(self):
        return self._data.get("child_id")

    @child_id.setter
    def child_id(self, value):
        self._data["child_id"] = value

    @property
    def auth_token(self):
        return self._data.get("auth_token")

    @auth_token.setter
    def auth_token(self, value):
        self._data["auth_token"] = value

    @property
    def server_url(self):
        return self._data.get("server_url", "http://localhost:8080")

    @server_url.setter
    def server_url(self, value):
        self._data["server_url"] = value

    @property
    def parent_id(self):
        return self._data.get("parent_id")

    @parent_id.setter
    def parent_id(self, value):
        self._data["parent_id"] = value

    @property
    def display_name(self):
        return self._data.get("display_name")

    @display_name.setter
    def display_name(self, value):
        self._data["display_name"] = value

    @property
    def last_message_timestamp(self):
        return self._data.get("last_message_timestamp")

    @last_message_timestamp.setter
    def last_message_timestamp(self, value):
        self._data["last_message_timestamp"] = value
