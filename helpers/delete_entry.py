#!/usr/bin/env python3
"""Delete one notification history entry safely.

Usage: delete_entry.py <timestamp> <originalId> [historyDir]

Security model:
  - timestamp and originalId are validated against the same strict
    patterns used by read_history.py before being used to build a
    filename.
  - The history directory is opened once with O_DIRECTORY|O_NOFOLLOW and
    checked to be owned by the current user.
  - The target is stat()-ed relative to that directory descriptor with
    follow_symlinks=False and must be a regular file owned by the current
    user before it is unlinked, also relative to the directory
    descriptor, so a symlink swap cannot redirect the deletion.
"""
import os
import re
import stat
import sys

TIMESTAMP_RE = re.compile(r"^\d{1,20}$")
ORIGINAL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

DEFAULT_HISTORY_DIR = os.path.join(
    os.environ.get("HOME", ""), ".local/state/omarchy/notifications/history"
)


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        sys.stderr.write("usage: delete_entry.py <timestamp> <originalId> [historyDir]\n")
        return 1

    timestamp, original_id = args[0], args[1]
    history_dir = args[2] if len(args) > 2 else DEFAULT_HISTORY_DIR

    if not TIMESTAMP_RE.match(timestamp) or not ORIGINAL_ID_RE.match(original_id):
        sys.stderr.write("invalid timestamp or originalId\n")
        return 1

    name = f"{timestamp}-{original_id}.json"

    try:
        dirfd = os.open(
            history_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
    except OSError as e:
        sys.stderr.write(f"cannot open history dir: {e}\n")
        return 1

    try:
        dst = os.fstat(dirfd)
        if not stat.S_ISDIR(dst.st_mode) or dst.st_uid != os.getuid():
            sys.stderr.write("history dir is not an owner-appropriate directory\n")
            return 1

        try:
            st = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
        except OSError as e:
            sys.stderr.write(f"entry not found: {e}\n")
            return 1

        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
            sys.stderr.write("refusing to delete a non-regular or foreign-owned entry\n")
            return 1

        try:
            os.unlink(name, dir_fd=dirfd)
        except OSError as e:
            sys.stderr.write(f"delete failed: {e}\n")
            return 1
    finally:
        os.close(dirfd)

    return 0


if __name__ == "__main__":
    sys.exit(main())
