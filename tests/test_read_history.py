import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(REPO_ROOT, "helpers", "read_history.py")

sys.path.insert(0, os.path.join(REPO_ROOT, "helpers"))
import read_history  # noqa: E402


def run_helper(history_dir):
    proc = subprocess.run(
        [sys.executable, HELPER, history_dir],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.stdout


def write_entry(history_dir, ts, original_id, payload):
    path = os.path.join(history_dir, f"{ts}-{original_id}.json")
    if isinstance(payload, dict):
        payload = dict(payload)
        payload.setdefault("originalId", original_id)
        payload.setdefault("timestamp", ts)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return path


def sample_payload(**overrides):
    payload = {
        "app": "some-app",
        "appIcon": "",
        "summary": "hello",
        "body": "world",
        "image": "",
        "glyph": "",
        "execArgv": "",
        "urgency": "2",
        "expireTimeout": "0",
    }
    payload.update(overrides)
    return payload


class ReadHistoryFunctionalTests(unittest.TestCase):
    def test_oversized_file_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            big_body = "x" * (60 * 1024)
            write_entry(d, "100", "1", sample_payload(body=big_body))
            write_entry(d, "200", "2", sample_payload(summary="fine"))
            out = json.loads(run_helper(d))
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["originalId"], "2")

    def test_aggregate_cap_uses_actual_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            # Each file is ~40KB, well under per-file cap but multiple files
            # should stop once the aggregate cap is reached using real bytes read.
            body = "y" * (40 * 1024)
            for i in range(60):
                write_entry(d, str(1000 + i), str(i), sample_payload(body=body))
            out = json.loads(run_helper(d))
            # 2 MiB aggregate / ~40KB per entry -> well under 60 entries
            self.assertLess(len(out), 60)

    def test_symlinked_file_not_followed(self):
        with tempfile.TemporaryDirectory() as d:
            outside_dir = tempfile.mkdtemp()
            try:
                target = os.path.join(outside_dir, "secret.json")
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(sample_payload(summary="secret"), f)
                link_path = os.path.join(d, "100-1.json")
                os.symlink(target, link_path)
                out = json.loads(run_helper(d))
                self.assertEqual(out, [])
            finally:
                import shutil
                shutil.rmtree(outside_dir, ignore_errors=True)

    def test_history_dir_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as real_dir:
            write_entry(real_dir, "100", "1", sample_payload())
            with tempfile.TemporaryDirectory() as parent:
                link_dir = os.path.join(parent, "history_link")
                os.symlink(real_dir, link_dir)
                out = json.loads(run_helper(link_dir))
                self.assertEqual(out, [])

    def test_fifo_not_followed_does_not_hang(self):
        with tempfile.TemporaryDirectory() as d:
            fifo_path = os.path.join(d, "100-1.json")
            os.mkfifo(fifo_path)
            try:
                out = json.loads(run_helper(d))
                self.assertEqual(out, [])
            finally:
                pass

    def test_growing_file_capped_at_limit(self):
        # Simulate a file that is larger than MAX_FILE_BYTES at read time;
        # the read must stop at the cap instead of reading to EOF.
        with tempfile.TemporaryDirectory() as d:
            huge = "{" + '"a":"' + ("z" * (100 * 1024)) + '"}'
            write_entry(d, "100", "1", None)
            path = os.path.join(d, "100-1.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write(huge)
            out = json.loads(run_helper(d))
            self.assertEqual(out, [])

    def test_bad_names_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "..%2Fx.json"), "w") as f:
                f.write("{}")
            with open(os.path.join(d, "$(id)-1.json"), "w") as f:
                f.write("{}")
            with open(os.path.join(d, "notanumber-1.json"), "w") as f:
                f.write("{}")
            write_entry(d, "100", "1", sample_payload())
            out = json.loads(run_helper(d))
            self.assertEqual(len(out), 1)

    def test_malformed_json_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "100-1.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{not valid json")
            out = json.loads(run_helper(d))
            self.assertEqual(out, [])

    def test_field_caps_and_whitelist(self):
        with tempfile.TemporaryDirectory() as d:
            write_entry(d, "100", "1", sample_payload(
                app="a" * 100,
                summary="s" * 500,
                body="b" * 2000,
                secretField="should not appear",
            ))
            out = json.loads(run_helper(d))
            self.assertEqual(len(out), 1)
            entry = out[0]
            self.assertNotIn("secretField", entry)
            self.assertLessEqual(len(entry["app"]), 64)
            self.assertLessEqual(len(entry["summary"]), 256)
            self.assertLessEqual(len(entry["body"]), 1024)

    def test_image_outside_allowed_dirs_rejected(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as screenshots, tempfile.TemporaryDirectory() as images:
            outside = tempfile.mkdtemp()
            try:
                bad_img = os.path.join(outside, "x.png")
                with open(bad_img, "wb") as f:
                    f.write(b"\x89PNG\r\n")
                write_entry(d, "100", "1", sample_payload(image=bad_img))
                env = dict(os.environ)
                env["OMARCHY_SCREENSHOT_DIR"] = screenshots
                env["HERO_NOTIFICATIONS_IMAGES_DIR"] = images
                proc = subprocess.run(
                    [sys.executable, HELPER, d], capture_output=True, text=True, env=env, timeout=10
                )
                out = json.loads(proc.stdout)
                self.assertEqual(out[0]["image"], "")
            finally:
                import shutil
                shutil.rmtree(outside, ignore_errors=True)

    def test_image_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as screenshots, tempfile.TemporaryDirectory() as images:
            outside = tempfile.mkdtemp()
            try:
                real_img = os.path.join(outside, "real.png")
                with open(real_img, "wb") as f:
                    f.write(b"\x89PNG\r\n")
                linked_img = os.path.join(screenshots, "link.png")
                os.symlink(real_img, linked_img)
                write_entry(d, "100", "1", sample_payload(image=linked_img))
                env = dict(os.environ)
                env["OMARCHY_SCREENSHOT_DIR"] = screenshots
                env["HERO_NOTIFICATIONS_IMAGES_DIR"] = images
                proc = subprocess.run(
                    [sys.executable, HELPER, d], capture_output=True, text=True, env=env, timeout=10
                )
                out = json.loads(proc.stdout)
                self.assertEqual(out[0]["image"], "")
            finally:
                import shutil
                shutil.rmtree(outside, ignore_errors=True)

    def test_image_allowed_accepted(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as screenshots, tempfile.TemporaryDirectory() as images:
            good_img = os.path.join(screenshots, "shot.png")
            with open(good_img, "wb") as f:
                f.write(b"\x89PNG\r\n")
            write_entry(d, "100", "1", sample_payload(image=good_img))
            env = dict(os.environ)
            env["OMARCHY_SCREENSHOT_DIR"] = screenshots
            env["HERO_NOTIFICATIONS_IMAGES_DIR"] = images
            proc = subprocess.run(
                [sys.executable, HELPER, d], capture_output=True, text=True, env=env, timeout=10
            )
            out = json.loads(proc.stdout)
            self.assertEqual(out[0]["image"], good_img)

    def test_omarchy_action_image_derived_from_exec_argv(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as screenshots, tempfile.TemporaryDirectory() as images:
            good_img = os.path.join(screenshots, "shot.png")
            with open(good_img, "wb") as f:
                f.write(b"\x89PNG\r\n")
            exec_argv = json.dumps(["tensaku-edit", good_img])
            write_entry(d, "100", "1", sample_payload(
                app="omarchy-action", image="", execArgv=exec_argv
            ))
            env = dict(os.environ)
            env["OMARCHY_SCREENSHOT_DIR"] = screenshots
            env["HERO_NOTIFICATIONS_IMAGES_DIR"] = images
            proc = subprocess.run(
                [sys.executable, HELPER, d], capture_output=True, text=True, env=env, timeout=10
            )
            out = json.loads(proc.stdout)
            self.assertEqual(out[0]["image"], good_img)

    def _run_with_roots(self, history_dir, screenshots, images):
        env = dict(os.environ)
        env["OMARCHY_SCREENSHOT_DIR"] = screenshots
        env["HERO_NOTIFICATIONS_IMAGES_DIR"] = images
        proc = subprocess.run(
            [sys.executable, HELPER, history_dir], capture_output=True, text=True, env=env, timeout=10
        )
        return json.loads(proc.stdout)

    def test_image_with_symlinked_intermediate_dir_rejected(self):
        # A symlinked directory inside an allowed root must not be traversed,
        # even when its target is also inside the root: validation walks every
        # component without following links.
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as screenshots, tempfile.TemporaryDirectory() as images:
            real_sub = os.path.join(screenshots, "real")
            os.mkdir(real_sub)
            with open(os.path.join(real_sub, "shot.png"), "wb") as f:
                f.write(b"\x89PNG\r\n")
            os.symlink(real_sub, os.path.join(screenshots, "link"))
            write_entry(d, "100", "1", sample_payload(image=os.path.join(screenshots, "link", "shot.png")))
            out = self._run_with_roots(d, screenshots, images)
            self.assertEqual(out[0]["image"], "")

    def test_image_with_dotdot_rejected(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as screenshots, tempfile.TemporaryDirectory() as images:
            sub = os.path.join(screenshots, "sub")
            os.mkdir(sub)
            with open(os.path.join(screenshots, "shot.png"), "wb") as f:
                f.write(b"\x89PNG\r\n")
            write_entry(d, "100", "1", sample_payload(image=os.path.join(sub, "..", "shot.png")))
            out = self._run_with_roots(d, screenshots, images)
            self.assertEqual(out[0]["image"], "")

    def test_image_output_is_canonical_path(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as screenshots, tempfile.TemporaryDirectory() as images:
            good_img = os.path.join(screenshots, "shot.png")
            with open(good_img, "wb") as f:
                f.write(b"\x89PNG\r\n")
            write_entry(d, "100", "1", sample_payload(image="file://" + good_img))
            out = self._run_with_roots(d, screenshots, images)
            self.assertEqual(out[0]["image"], good_img)

    def test_image_validation_error_does_not_drop_history(self):
        # An unexpected failure while validating one entry's image must only
        # blank that image, not discard the whole history.
        original = read_history._validate_image_path
        def boom(_candidate):
            raise RuntimeError("unexpected")
        read_history._validate_image_path = boom
        try:
            entry = read_history._apply_image_validation({"app": "x", "image": "/a.png", "execArgv": ""})
        finally:
            read_history._validate_image_path = original
        self.assertEqual(entry["image"], "")

    def test_sorted_newest_first_by_filename_timestamp(self):
        with tempfile.TemporaryDirectory() as d:
            write_entry(d, "100", "1", sample_payload())
            write_entry(d, "300", "2", sample_payload())
            write_entry(d, "200", "3", sample_payload())
            out = json.loads(run_helper(d))
            self.assertEqual([e["originalId"] for e in out], ["2", "3", "1"])

    def test_non_dict_json_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "100-1.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(["not", "a", "dict"], f)
            out = json.loads(run_helper(d))
            self.assertEqual(out, [])


class ReadHistoryUnitTests(unittest.TestCase):
    def test_name_regex_accepts_valid(self):
        self.assertIsNotNone(read_history.NAME_RE.match("1790441969950-14.json"))

    def test_name_regex_rejects_traversal(self):
        self.assertIsNone(read_history.NAME_RE.match("../x.json"))
        self.assertIsNone(read_history.NAME_RE.match("$(id)-1.json"))


if __name__ == "__main__":
    unittest.main()
