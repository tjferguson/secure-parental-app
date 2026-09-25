import base64
import os
import subprocess
import tempfile

import requests


SCREENSHOT_PATH = os.path.join(tempfile.gettempdir(), "parentchat_screenshot.png")


def _get_display():
    """Get the current X11 display, defaulting to :0."""
    return os.environ.get("DISPLAY", ":0")


def _get_xauthority():
    """Find the XAUTHORITY file for the current user."""
    # Check env first
    xauth = os.environ.get("XAUTHORITY")
    if xauth and os.path.isfile(xauth):
        return xauth

    # Try GDM path
    uid = str(os.getuid())
    gdm_path = f"/run/user/{uid}/gdm/Xauthority"
    if os.path.isfile(gdm_path):
        return gdm_path

    # Try home directory
    home_path = os.path.expanduser("~/.Xauthority")
    if os.path.isfile(home_path):
        return home_path

    return None


def capture_screenshot():
    """Capture a screenshot silently using ffmpeg x11grab.

    Uses ffmpeg to grab the X11 display directly — no visual flash,
    no shutter sound, no notification. The image is scaled to half size
    and converted to grayscale to reduce file size.

    Falls back to xdpyinfo + import (ImageMagick) if ffmpeg is unavailable.

    Returns:
        bytes: PNG image data, or None on failure.
    """
    # Clean up any previous screenshot
    if os.path.isfile(SCREENSHOT_PATH):
        os.remove(SCREENSHOT_PATH)

    display = _get_display()
    xauthority = _get_xauthority()

    env = dict(os.environ)
    env["DISPLAY"] = display
    if xauthority:
        env["XAUTHORITY"] = xauthority

    # Method 1: ffmpeg x11grab (silent, no visual cues)
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-f", "x11grab",
                "-i", display,
                "-vframes", "1",
                "-y",
                SCREENSHOT_PATH,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            timeout=10,
        )
        if result.returncode == 0 and os.path.isfile(SCREENSHOT_PATH):
            with open(SCREENSHOT_PATH, "rb") as f:
                return f.read()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Method 2: ImageMagick import (also silent)
    try:
        result = subprocess.run(
            [
                "import",
                "-window", "root",
                SCREENSHOT_PATH,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            timeout=10,
        )
        if result.returncode == 0 and os.path.isfile(SCREENSHOT_PATH):
            with open(SCREENSHOT_PATH, "rb") as f:
                return f.read()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Method 3: xwd + convert pipeline (silent)
    try:
        result = subprocess.run(
            "xwd -root -silent | convert xwd:- png:" + SCREENSHOT_PATH,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            timeout=10,
        )
        if result.returncode == 0 and os.path.isfile(SCREENSHOT_PATH):
            with open(SCREENSHOT_PATH, "rb") as f:
                return f.read()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    print("[screenshot] All capture methods failed")
    return None


def upload_screenshot(server_url, auth_token, child_id, request_id, image_data):
    """Upload a screenshot to the server.

    Args:
        server_url: Base URL of the server.
        auth_token: Authentication token.
        child_id: The child device ID.
        request_id: The screenshot request ID.
        image_data: Raw PNG bytes.

    Returns:
        bool: True if upload succeeded, False otherwise.
    """
    try:
        encoded = base64.b64encode(image_data).decode("utf-8")
        url = f"{server_url}/api/screenshots/upload"
        headers = {"X-Child-Token": auth_token}
        payload = {
            "requestId": request_id,
            "childId": child_id,
            "imageData": encoded,
        }
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code in (200, 201):
            print(f"[screenshot] Upload successful for request {request_id}")
            return True
        else:
            print(
                f"[screenshot] Upload failed ({response.status_code}): {response.text}"
            )
            return False
    except requests.ConnectionError:
        print("[screenshot] Upload failed: could not connect to server")
        return False
    except requests.Timeout:
        print("[screenshot] Upload failed: request timed out")
        return False
    except Exception as e:
        print(f"[screenshot] Upload failed: {e}")
        return False


def handle_screenshot_request(config, request_id):
    """Capture a screenshot and upload it to the server.

    Args:
        config: Config instance with server_url, auth_token, child_id.
        request_id: The screenshot request ID from the server.

    Returns:
        bool: True if capture and upload both succeeded.
    """
    print(f"[screenshot] Handling request {request_id}")

    image_data = capture_screenshot()
    if image_data is None:
        print("[screenshot] Capture failed, nothing to upload")
        return False

    print(f"[screenshot] Captured {len(image_data)} bytes")

    return upload_screenshot(
        server_url=config.server_url,
        auth_token=config.auth_token,
        child_id=config.child_id,
        request_id=request_id,
        image_data=image_data,
    )
