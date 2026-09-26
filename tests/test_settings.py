import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(REPO_ROOT, "helpers", "settings.py")


def run_helper(args, env):
    proc = subprocess.run(
        [sys.executable, HELPER] + args,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return proc


def env_with_state(state_home):
    env = dict(os.environ)
    env["XDG_STATE_HOME"] = state_home
    return env


class SettingsTests(unittest.TestCase):
    def test_get_default_when_missing(self):
        with tempfile.TemporaryDirectory() as state_home:
            proc = run_helper(["get"], env_with_state(state_home))
            out = json.loads(proc.stdout)
            self.assertEqual(out, {"splitScreenshots": True})

    def test_set_then_get_roundtrip(self):
        with tempfile.TemporaryDirectory() as state_home:
            env = env_with_state(state_home)
            run_helper(["set", "false"], env)
            proc = run_helper(["get"], env)
            out = json.loads(proc.stdout)
            self.assertEqual(out, {"splitScreenshots": False})

    def test_write_is_atomic_and_mode_0600(self):
        with tempfile.TemporaryDirectory() as state_home:
            env = env_with_state(state_home)
            run_helper(["set", "true"], env)
            settings_path = os.path.join(state_home, "hero-notifications", "settings.json")
            self.assertTrue(os.path.exists(settings_path))
            mode = stat.S_IMODE(os.stat(settings_path).st_mode)
            self.assertEqual(mode, 0o600)

    def test_dir_created_mode_0700(self):
        with tempfile.TemporaryDirectory() as state_home:
            env = env_with_state(state_home)
            run_helper(["set", "true"], env)
            dir_path = os.path.join(state_home, "hero-notifications")
            mode = stat.S_IMODE(os.stat(dir_path).st_mode)
            self.assertEqual(mode, 0o700)

    def test_symlinked_state_dir_refused(self):
        with tempfile.TemporaryDirectory() as state_home, tempfile.TemporaryDirectory() as outside:
            link_path = os.path.join(state_home, "hero-notifications")
            os.symlink(outside, link_path)
            env = env_with_state(state_home)
            proc = run_helper(["set", "true"], env)
            self.assertNotEqual(proc.returncode, 0)
            # Nothing should have been written into the symlink target.
            self.assertFalse(os.path.exists(os.path.join(outside, "settings.json")))

    def test_bounded_read_ignores_oversized_file(self):
        with tempfile.TemporaryDirectory() as state_home:
            dir_path = os.path.join(state_home, "hero-notifications")
            os.makedirs(dir_path, mode=0o700)
            settings_path = os.path.join(dir_path, "settings.json")
            with open(settings_path, "w") as f:
                f.write('{"splitScreenshots": true, "padding": "' + ("x" * 8192) + '"}')
            env = env_with_state(state_home)
            proc = run_helper(["get"], env)
            out = json.loads(proc.stdout)
            self.assertEqual(out, {"splitScreenshots": True})

    def test_settings_file_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as state_home, tempfile.TemporaryDirectory() as outside:
            dir_path = os.path.join(state_home, "hero-notifications")
            os.makedirs(dir_path, mode=0o700)
            secret = os.path.join(outside, "secret.json")
            with open(secret, "w") as f:
                json.dump({"splitScreenshots": False}, f)
            link_path = os.path.join(dir_path, "settings.json")
            os.symlink(secret, link_path)
            env = env_with_state(state_home)
            proc = run_helper(["get"], env)
            out = json.loads(proc.stdout)
            self.assertEqual(out, {"splitScreenshots": True})

    def test_invalid_value_rejected(self):
        with tempfile.TemporaryDirectory() as state_home:
            env = env_with_state(state_home)
            proc = run_helper(["set", "maybe"], env)
            self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
