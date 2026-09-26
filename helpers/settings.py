#!/usr/bin/env python3
"""Read/write hero-notifications plugin settings.

Security model:
  - Settings live under `$XDG_STATE_HOME/hero-notifications/settings.json`
    (falls back to `~/.local/state`), never inside Omarchy's own state dir.
  - The settings directory is created 0700 and must be owned by the current
    user and not a symlink; `set` refuses to write otherwise.
  - Reads are bounded (at most MAX_READ_BYTES) via an O_NOFOLLOW open plus
    an fstat regular/owner check, so a swapped or oversized file cannot be
    parsed as trusted settings.
  - Writes are atomic: write to a private mkstemp() file in the same
    directory (mode 0600), fsync, then os.replace() into place.
"""
import json
import os
import stat
import sys
import tempfile

MAX_READ_BYTES = 4 * 1024
DEFAULT_SETTINGS = {"splitScreenshots": True}


def _state_home():
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return xdg
    home = os.environ.get("HOME", "")
    return os.path.join(home, ".local", "state")


def _settings_dir():
    return os.path.join(_state_home(), "hero-notifications")


def _settings_path():
    return os.path.join(_settings_dir(), "settings.json")


def _ensure_settings_dir():
    d = _settings_dir()
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"cannot create settings dir: {e}")

    try:
        st = os.lstat(d)
    except OSError as e:
        raise RuntimeError(f"cannot stat settings dir: {e}")

    if stat.S_ISLNK(st.st_mode):
        raise RuntimeError("settings directory must not be a symlink")
    if not stat.S_ISDIR(st.st_mode):
        raise RuntimeError("settings path is not a directory")
    if st.st_uid != os.getuid():
        raise RuntimeError("settings directory is not owned by the current user")

    # Tighten permissions if they were looser than expected (e.g. pre-existing dir).
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def _legacy_settings_path():
    # Location used by versions before the settings move; read-only fallback.
    return os.path.join(_state_home(), "omarchy", "notifications", "hero_settings.json")


def _read_settings_file(path):
    """Return the bounded, validated settings dict at `path`, or None."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        return None

    try:
        try:
            st = os.fstat(fd)
        except OSError:
            return None
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
            return None

        chunks = []
        remaining = MAX_READ_BYTES
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    finally:
        os.close(fd)

    try:
        parsed = json.loads(data.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("splitScreenshots"), bool):
        return {"splitScreenshots": parsed["splitScreenshots"]}
    return None


def get_settings():
    """Current settings: the plugin's own file, else the legacy one, else defaults."""
    for path in (_settings_path(), _legacy_settings_path()):
        found = _read_settings_file(path)
        if found is not None:
            return found
    return dict(DEFAULT_SETTINGS)


def set_split_screenshots(value):
    d = _ensure_settings_dir()
    payload = json.dumps({"splitScreenshots": value}).encode("utf-8")

    fd, tmp_path = tempfile.mkstemp(prefix=".settings-", dir=d)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, os.path.join(d, "settings.json"))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main():
    args = sys.argv[1:]
    if not args:
        print("[]")
        return 1

    action = args[0]
    if action == "get":
        try:
            print(json.dumps(get_settings()))
        except Exception:
            print(json.dumps(DEFAULT_SETTINGS))
        return 0

    if action == "set":
        if len(args) < 2 or args[1] not in ("true", "false"):
            sys.stderr.write("usage: settings.py set true|false\n")
            return 1
        try:
            set_split_screenshots(args[1] == "true")
        except RuntimeError as e:
            sys.stderr.write(str(e) + "\n")
            return 1
        return 0

    sys.stderr.write("usage: settings.py get|set true|false\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
