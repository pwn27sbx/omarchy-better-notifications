import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(REPO_ROOT, "helpers", "delete_entry.py")


def run_helper(args):
    return subprocess.run(
        [sys.executable, HELPER] + args,
        capture_output=True,
        text=True,
        timeout=10,
    )


class DeleteEntryTests(unittest.TestCase):
    def test_deletes_valid_entry(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "100-1.json")
            with open(path, "w") as f:
                json.dump({}, f)
            proc = run_helper(["100", "1", d])
            self.assertEqual(proc.returncode, 0)
            self.assertFalse(os.path.exists(path))

    def test_refuses_invalid_timestamp(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "100-1.json")
            with open(path, "w") as f:
                json.dump({}, f)
            proc = run_helper(["100; rm -rf /", "1", d])
            self.assertNotEqual(proc.returncode, 0)
            self.assertTrue(os.path.exists(path))

    def test_refuses_invalid_original_id(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "100-1.json")
            with open(path, "w") as f:
                json.dump({}, f)
            proc = run_helper(["100", "../../etc/passwd", d])
            self.assertNotEqual(proc.returncode, 0)
            self.assertTrue(os.path.exists(path))

    def test_refuses_symlinked_target(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            victim = os.path.join(outside, "victim.txt")
            with open(victim, "w") as f:
                f.write("keep me")
            link_path = os.path.join(d, "100-1.json")
            os.symlink(victim, link_path)
            proc = run_helper(["100", "1", d])
            self.assertNotEqual(proc.returncode, 0)
            self.assertTrue(os.path.exists(victim))

    def test_refuses_symlinked_history_dir(self):
        with tempfile.TemporaryDirectory() as real_dir:
            path = os.path.join(real_dir, "100-1.json")
            with open(path, "w") as f:
                json.dump({}, f)
            with tempfile.TemporaryDirectory() as parent:
                link_dir = os.path.join(parent, "history_link")
                os.symlink(real_dir, link_dir)
                proc = run_helper(["100", "1", link_dir])
                self.assertNotEqual(proc.returncode, 0)
                self.assertTrue(os.path.exists(path))

    def test_missing_entry_is_not_fatal_error(self):
        with tempfile.TemporaryDirectory() as d:
            proc = run_helper(["999", "notthere", d])
            # Should not crash, but should not succeed either (nothing deleted).
            self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
