#!/usr/bin/env python3
"""Read and sanitize Omarchy notification history entries.

Security model (marketplace review):
  - The history directory and every candidate file are opened once with
    O_NOFOLLOW so a symlink swap cannot redirect us outside the directory.
  - Each opened file descriptor is validated with fstat() to be a regular
    file owned by the current user before any bytes are read.
  - Reads happen on that same descriptor, bounded by both a per-file cap
    and a remaining-aggregate cap, using the actual number of bytes read
    (never a size reported by a separate stat/getsize call) so a file that
    grows or is replaced between checks cannot bypass the limits.
  - Output fields are whitelisted and length-capped before being emitted.
"""
import json
import os
import re
import stat
import sys

MAX_FILES = 100
MAX_FILE_BYTES = 50 * 1024  # 50 KiB per file
MAX_TOTAL_BYTES = 2 * 1024 * 1024  # 2 MiB aggregate
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MiB

NAME_RE = re.compile(r"^(\d{1,20})-([A-Za-z0-9_-]{1,64})\.json$")

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")

FIELD_CAPS = {
    "app": 64,
    "appIcon": 128,
    "summary": 256,
    "body": 1024,
    "execArgv": 4096,
    "image": 1024,
    "glyph": 8,
    "timestamp": 20,
    "originalId": 64,
}

TIMESTAMP_RE = re.compile(r"^\d+$")
ORIGINAL_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _open_dir_nofollow(path):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
    except OSError:
        os.close(fd)
        raise
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        os.close(fd)
        raise ValueError("history directory is not an owner-appropriate directory")
    return fd


def _list_candidate_names(dirfd):
    names = []
    for name in os.listdir(dirfd):
        m = NAME_RE.match(name)
        if not m:
            continue
        names.append((int(m.group(1)), name))
    names.sort(key=lambda item: item[0], reverse=True)
    return [name for _, name in names[:MAX_FILES]]


def _read_bounded_from_fd(fd, limit):
    """Read at most `limit` bytes from fd, returning (data, truncated)."""
    chunks = []
    remaining = limit + 1
    while remaining > 0:
        chunk = os.read(fd, min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    truncated = len(data) > limit
    if truncated:
        data = data[:limit]
    return data, truncated


def _open_file_nofollow(dirfd, name):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    return os.open(name, flags, dir_fd=dirfd)


def _read_history_entry(dirfd, name, remaining_aggregate):
    fd = None
    try:
        fd = _open_file_nofollow(dirfd, name)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
            return None, 0
        per_file_limit = min(MAX_FILE_BYTES, remaining_aggregate)
        data, truncated = _read_bounded_from_fd(fd, per_file_limit)
        actual_bytes = len(data)
        if truncated:
            # File exceeds either the per-file cap or the remaining
            # aggregate budget; reject it rather than parsing a partial
            # document, but still count the bytes actually read.
            return None, actual_bytes
        try:
            text = data.decode("utf-8", errors="strict")
            parsed = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, actual_bytes
        if not isinstance(parsed, dict):
            return None, actual_bytes
        return parsed, actual_bytes
    except OSError:
        return None, 0
    finally:
        if fd is not None:
            os.close(fd)


def _cap_str(value, limit):
    return str(value)[:limit]


def _sanitize_entry(raw):
    out = {}
    for field, limit in FIELD_CAPS.items():
        value = raw.get(field)
        if value is None:
            out[field] = ""
            continue
        out[field] = _cap_str(value, limit)
    if out["timestamp"] and not TIMESTAMP_RE.match(out["timestamp"]):
        out["timestamp"] = ""
    if out["originalId"] and not ORIGINAL_ID_RE.match(out["originalId"]):
        out["originalId"] = ""
    return out


def _allowed_image_roots():
    """Return (spelled, canonical) pairs for the directories images may live in.

    The spelled form is how paths usually appear in notifications (for example
    $HOME/Pictures even if Pictures is a symlink); the canonical form is where
    the component walk starts.
    """
    screenshot_dir = os.environ.get("OMARCHY_SCREENSHOT_DIR")
    if not screenshot_dir:
        pictures_dir = os.environ.get("XDG_PICTURES_DIR")
        home = os.environ.get("HOME", "")
        screenshot_dir = pictures_dir or os.path.join(home, "Pictures")
    images_dir = os.environ.get("HERO_NOTIFICATIONS_IMAGES_DIR")
    if not images_dir:
        home = os.environ.get("HOME", "")
        images_dir = os.path.join(home, ".local/state/omarchy/notifications/images")
    roots = []
    for d in (screenshot_dir, images_dir):
        if not d or not os.path.isabs(d):
            continue
        spelled = os.path.normpath(d)
        roots.append((spelled, os.path.realpath(spelled)))
    return roots


def _relative_components(path, root):
    """Split `path` below `root` into components, or None if not below it."""
    prefix = root.rstrip(os.sep) + os.sep
    if not path.startswith(prefix):
        return None
    parts = path[len(prefix):].split(os.sep)
    if not parts or any(p in ("", ".", "..") for p in parts):
        return None
    return parts


def _open_image_nofollow(canonical_root, parts):
    """Walk from the canonical root without following any symlink.

    Every intermediate component is opened relative to its parent with
    O_DIRECTORY | O_NOFOLLOW, and the final one with O_NOFOLLOW, so a link
    anywhere below the root (or one swapped in mid-walk) fails the open.
    Returns an fd for the image file; the caller closes it.
    """
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(canonical_root, dir_flags)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, dir_flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        return os.open(parts[-1], file_flags, dir_fd=fd)
    finally:
        os.close(fd)


def _validate_image_path(candidate):
    """Return the canonical path of a trusted image, or "" if it fails.

    Accepted only when the path is absolute, has no "." / ".." components,
    lies below an allowed root, contains no symlink below that root, and
    ends in a regular, user-owned .png/.jpg/.jpeg file of at most 20 MiB.
    The returned path is the verified canonical one, never the raw input.
    """
    if not candidate:
        return ""
    path = candidate[len("file://"):] if candidate.startswith("file://") else candidate
    if not path or not os.path.isabs(path):
        return ""
    if os.path.splitext(path)[1].lower() not in IMAGE_EXTENSIONS:
        return ""

    for spelled, canonical in _allowed_image_roots():
        parts = _relative_components(path, spelled)
        if parts is None and canonical != spelled:
            parts = _relative_components(path, canonical)
        if parts is None:
            continue
        try:
            fd = _open_image_nofollow(canonical, parts)
        except OSError:
            return ""
        try:
            st = os.fstat(fd)
        finally:
            os.close(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
            return ""
        if st.st_size > MAX_IMAGE_BYTES:
            return ""
        return os.path.join(canonical, *parts)
    return ""


def _derive_omarchy_action_image(entry):
    exec_argv_raw = entry.get("execArgv") or ""
    try:
        args = json.loads(exec_argv_raw)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(args, list) or len(args) < 2:
        return ""
    if not all(isinstance(a, str) for a in args):
        return ""
    return args[-1]


def _apply_image_validation(entry):
    candidate = entry.get("image") or ""
    if not candidate and entry.get("app") == "omarchy-action":
        candidate = _derive_omarchy_action_image(entry)
    try:
        entry["image"] = _validate_image_path(candidate)
    except Exception:
        # A failure on one image only blanks that thumbnail.
        entry["image"] = ""
    return entry


def main():
    if len(sys.argv) < 2:
        print("[]")
        return

    history_dir = sys.argv[1]

    try:
        dirfd = _open_dir_nofollow(history_dir)
    except (OSError, ValueError):
        print("[]")
        return

    try:
        try:
            names = _list_candidate_names(dirfd)
        except OSError:
            print("[]")
            return

        results = []
        remaining_aggregate = MAX_TOTAL_BYTES
        for name in names:
            if remaining_aggregate <= 0:
                break
            raw, bytes_read = _read_history_entry(dirfd, name, remaining_aggregate)
            remaining_aggregate -= bytes_read
            if raw is None:
                continue
            entry = _sanitize_entry(raw)
            entry = _apply_image_validation(entry)
            results.append(entry)

        print(json.dumps(results))
    except Exception:
        print("[]")
    finally:
        os.close(dirfd)


if __name__ == "__main__":
    main()
