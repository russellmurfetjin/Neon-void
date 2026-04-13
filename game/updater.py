"""
Auto-updater for NEON VOID.

How to set up updates:
1. Host your game files somewhere (GitHub repo, web server, etc.)
2. Put a version.json at the update URL with: {"version": "1.1.0", "build": 2, "files": {...}}
3. Set UPDATE_URL below to point to your hosted version.json
4. When players click "Check for Updates", it compares versions and patches.

For GitHub: create a repo, push your game files, then set UPDATE_URL to:
    https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/version.json

The version.json on the server should include a "files" dict mapping
file paths to their download URLs. Example:
{
    "version": "1.1.0",
    "build": 2,
    "files": {
        "main.py": "https://raw.githubusercontent.com/user/repo/main/main.py",
        "game/world.py": "https://raw.githubusercontent.com/user/repo/main/game/world.py"
    }
}
"""
import json
import os
import urllib.request
import threading
from typing import Optional, Tuple

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_VERSION_FILE = os.path.join(GAME_DIR, "version.json")
UPDATE_CONFIG_FILE = os.path.join(GAME_DIR, "update_config.json")

# Default update URL — points to your GitHub repo
DEFAULT_UPDATE_URL = "https://raw.githubusercontent.com/russellmurfetjin/Neon-void/main/version.json"


def get_update_url() -> str:
    """Get the update URL from config file or default."""
    if os.path.exists(UPDATE_CONFIG_FILE):
        try:
            with open(UPDATE_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get("update_url", DEFAULT_UPDATE_URL)
        except Exception:
            pass
    return DEFAULT_UPDATE_URL


def set_update_url(url: str):
    """Save the update URL to config."""
    config = {}
    if os.path.exists(UPDATE_CONFIG_FILE):
        try:
            with open(UPDATE_CONFIG_FILE, 'r') as f:
                config = json.load(f)
        except Exception:
            pass
    config["update_url"] = url
    with open(UPDATE_CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def get_local_version() -> Tuple[str, int]:
    """Returns (version_string, build_number)."""
    try:
        with open(LOCAL_VERSION_FILE, 'r') as f:
            data = json.load(f)
            return data.get("version", "0.0.0"), data.get("build", 0)
    except Exception:
        return "0.0.0", 0


def check_for_update() -> Optional[dict]:
    """
    Check remote server for a newer version.
    Returns remote version info dict if update available, None otherwise.
    """
    url = get_update_url()
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'NeonVoid-Updater'})
        with urllib.request.urlopen(req, timeout=10) as response:
            remote = json.loads(response.read().decode('utf-8'))
        local_ver, local_build = get_local_version()
        remote_build = remote.get("build", 0)
        if remote_build > local_build:
            return remote
        return None
    except Exception as e:
        return {"error": str(e)}


def download_update(remote_info, progress_callback=None) -> Tuple[bool, str]:
    """
    Download and apply an update.
    progress_callback(current, total, filename) is called for each file.
    Returns (success, message).
    """
    files = remote_info.get("files", {})
    if not files:
        return False, "No files in update"

    total = len(files)
    downloaded = 0
    errors = []

    for filepath, file_url in files.items():
        try:
            if progress_callback:
                progress_callback(downloaded, total, filepath)

            # Sanitize path — prevent directory traversal
            clean_path = filepath.replace('\\', '/').lstrip('/')
            if '..' in clean_path:
                continue
            full_path = os.path.join(GAME_DIR, clean_path)

            # Create directories if needed
            dir_path = os.path.dirname(full_path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)

            # Download file
            req = urllib.request.Request(file_url, headers={'User-Agent': 'NeonVoid-Updater'})
            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read()

            # Write file
            with open(full_path, 'wb') as f:
                f.write(content)

            downloaded += 1
        except Exception as e:
            errors.append(f"{filepath}: {e}")

    # Update local version.json
    try:
        new_version = {
            "version": remote_info.get("version", "?"),
            "build": remote_info.get("build", 0),
        }
        with open(LOCAL_VERSION_FILE, 'w') as f:
            json.dump(new_version, f, indent=2)
    except Exception:
        pass

    if errors:
        return downloaded > 0, f"Updated {downloaded}/{total} files. Errors: {'; '.join(errors[:3])}"
    return True, f"Updated {downloaded} files to v{remote_info.get('version', '?')}. Restart the game!"


class AsyncUpdater:
    """Non-blocking update checker/downloader."""
    def __init__(self):
        self.checking = False
        self.downloading = False
        self.result = None  # None, dict with update info, or {"error": ...}
        self.download_result = None  # (success, message)
        self.progress = (0, 0, "")  # (current, total, filename)
        self.thread = None

    def check(self):
        """Start async update check."""
        if self.checking:
            return
        self.checking = True
        self.result = None
        self.thread = threading.Thread(target=self._do_check, daemon=True)
        self.thread.start()

    def _do_check(self):
        self.result = check_for_update()
        self.checking = False

    def download(self, remote_info):
        """Start async download."""
        if self.downloading:
            return
        self.downloading = True
        self.download_result = None
        self.thread = threading.Thread(target=self._do_download, args=(remote_info,), daemon=True)
        self.thread.start()

    def _do_download(self, remote_info):
        def on_progress(current, total, filename):
            self.progress = (current, total, filename)
        success, msg = download_update(remote_info, on_progress)
        self.download_result = (success, msg)
        self.downloading = False
