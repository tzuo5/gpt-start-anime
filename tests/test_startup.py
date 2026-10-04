import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import launcher
import manage


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_STATE_HOME": str(self.root / "state"),
        })
        self.env.start()
        self.system_desktop = self.root / "chatgpt.desktop"
        self.system_desktop.write_text("[Desktop Entry]\nName=ChatGPT\nType=Application\nExec=/usr/bin/true %U\n")
        self.system = patch.object(manage, "SYSTEM_DESKTOP", self.system_desktop)
        self.system.start()
        self.video = self.root / 'video with spaces.mp4'
        self.video.write_bytes(b"placeholder")

    def tearDown(self):
        self.env.stop()
        self.system.stop()
        self.temp.cleanup()

    def test_existing_entry_restored_after_reconfiguration(self):
        _, desktop = manage.paths()
        desktop.parent.mkdir(parents=True)
        original = b"[Desktop Entry]\nName=ChatGPT\nType=Application\nExec=/usr/bin/true %U\nIcon=chatgpt\nDBusActivatable=true\n"
        desktop.write_bytes(original)
        desktop.chmod(0o640)
        with patch.object(manage, "doctor"):
            manage.install(self.video)
            manage.install(self.video, fullscreen=False, mute=True)
        status = manage.status()
        self.assertTrue(status["entry_intact"])
        self.assertTrue(status["config"]["mute"])
        self.assertIn("DBusActivatable=false", desktop.read_text())
        manage.uninstall()
        self.assertEqual(desktop.read_bytes(), original)
        self.assertEqual(desktop.stat().st_mode & 0o777, 0o640)

    def test_no_local_entry_removed_on_uninstall(self):
        with patch.object(manage, "doctor"):
            manage.install(self.video)
        _, desktop = manage.paths()
        self.assertTrue(desktop.is_file())
        manage.uninstall()
        self.assertFalse(desktop.exists())
        self.assertTrue(self.video.is_file())

    def test_changed_entry_is_never_overwritten(self):
        with patch.object(manage, "doctor"):
            manage.install(self.video)
        _, desktop = manage.paths()
        desktop.write_text("another program changed this")
        with self.assertRaises(RuntimeError):
            manage.uninstall()
        with patch.object(manage, "doctor"), self.assertRaises(RuntimeError):
            manage.install(self.video)
        self.assertEqual(desktop.read_text(), "another program changed this")

    def test_invalid_video_does_not_change_entry(self):
        with patch.object(manage, "doctor"), self.assertRaises(FileNotFoundError):
            manage.install(self.root / "missing.mp4")
        self.assertFalse(manage.paths()[1].exists())

    def test_malformed_config_rejected(self):
        path = self.root / "broken.json"
        for value in ([], {"video": []}, {"video_dir": []}, {"enabled": "false"},
                      {"app_command": "chatgpt"}, {"timeout_seconds": 0}):
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                launcher.read_config(path)

    def test_default_seed_only_once_and_empty_folder_stays_empty(self):
        bundled = self.root / "bundled"
        bundled.mkdir()
        (bundled / "00-default.mp4").write_bytes(b"default")
        with patch.object(manage, "doctor"), patch.object(manage, "bundled_video_dir", return_value=bundled):
            manage.install()
            config = launcher.read_config(launcher.config_path())
            chosen = launcher.select_video(config)
            self.assertEqual(chosen.name, "00-default.mp4")
            chosen.unlink()
            manage.install()
            # Deleting the directory also keeps animation disabled on upgrade.
            Path(config["video_dir"]).rmdir()
            manage.install()
        self.assertIsNone(manage.status()["selected_video"])

    def test_custom_empty_folder_never_seeded(self):
        folder = self.root / "custom"
        with patch.object(manage, "doctor"):
            manage.install(video_dir=folder)
        self.assertTrue(folder.is_dir())
        self.assertEqual(list(folder.iterdir()), [])
        self.assertIsNone(manage.status()["selected_video"])

    def test_configure_disables_without_replacing_desktop(self):
        with patch.object(manage, "doctor"):
            manage.install(self.video)
        original = manage.paths()[1].read_bytes()
        manage.configure(enabled=False, mute=True, fullscreen=False)
        self.assertIsNone(manage.status()["selected_video"])
        self.assertEqual(manage.paths()[1].read_bytes(), original)
        manage.configure(enabled=True)
        self.assertIsNotNone(manage.status()["selected_video"])

    def test_custom_desktop_and_settings_action_are_restored(self):
        custom = self.root / "codex.desktop"
        custom.write_text('[Desktop Entry]\nName=Codex\nType=Application\nExec=/usr/bin/true --some-flag %U\nActions=Original;\n\n[Desktop Action Original]\nName=Original\nExec=/usr/bin/true\n')
        with patch.object(manage, "doctor"):
            manage.install(video_dir=self.root / "clips", desktop_file=custom)
        state = manage.status()
        self.assertEqual(state["config"]["app_command"], ["/usr/bin/true", "--some-flag"])
        installed = Path(state["desktop_entry"])
        self.assertIn("Actions=Original;StartupAnimationSettings;", installed.read_text())
        settings = installed.with_name(manage.SETTINGS_ID)
        self.assertTrue(settings.is_file())
        manage.uninstall()
        self.assertFalse(installed.exists())
        self.assertFalse(settings.exists())


class SelectionTests(unittest.TestCase):
    def test_first_mp4_sorted_by_filename_and_rescanned(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name in ["02-second.mp4", "01-FIRST.MP4", "readme.txt"]:
                (folder / name).write_text("sample")
            (folder / "00-subdir.mp4").mkdir()
            (folder / "nested").mkdir()
            (folder / "nested/00-nested.mp4").write_text("sample")
            config = {"video_dir": str(folder), "video": str(folder / "02-second.mp4")}
            self.assertEqual(launcher.select_video(config).name, "01-FIRST.MP4")
            (folder / "01-FIRST.MP4").unlink()
            self.assertEqual(launcher.select_video(config).name, "02-second.mp4")
            (folder / "02-second.mp4").unlink()
            self.assertIsNone(launcher.select_video(config))

    def test_missing_or_disabled_folder_skips_animation(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "intro.mp4").write_text("sample")
            self.assertIsNone(launcher.select_video({"video_dir": str(folder), "enabled": False}))
            self.assertIsNone(launcher.select_video({"video_dir": str(folder / "missing")}))


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, XDG_STATE_HOME=str(self.root / "state"))
        (self.root / "launcher.py").write_bytes(Path(launcher.__file__).read_bytes())
        self.events = self.root / "events.jsonl"
        self.video = self.root / "movie.mp4"
        self.video.write_bytes(b"placeholder")
        self.app = self.root / "app.py"
        self.app.write_text(
            "import json, pathlib, sys\n"
            f"with pathlib.Path({str(self.events)!r}).open('a') as f:\n"
            " f.write(json.dumps({'event': 'app', 'args': sys.argv[1:]}) + '\\n')\n"
        )
        self.config = self.root / "config.json"
        self.write_config()

    def tearDown(self):
        self.temp.cleanup()

    def write_config(self, video=None, timeout=10):
        self.config.write_text(json.dumps({"video": str(video or self.video), "timeout_seconds": timeout,
                                           "app_command": [sys.executable, str(self.app)]}))

    def player(self, delay=0.15, code=0):
        (self.root / "player.py").write_text(
            "import json, pathlib, time, sys\n"
            f"p=pathlib.Path({str(self.events)!r})\n"
            "with p.open('a') as f: f.write(json.dumps({'event': 'play'}) + '\\n')\n"
            f"time.sleep({delay})\n"
            "with p.open('a') as f: f.write(json.dumps({'event': 'end'}) + '\\n')\n"
            f"sys.exit({code})\n"
        )

    def start(self, args=(), preview=False):
        command = [sys.executable, str(self.root / "launcher.py"), "--config", str(self.config)]
        if preview:
            command.append("--preview")
        return subprocess.Popen(command + ["--", *args], env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def wait_events(self, count):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            events = [json.loads(line) for line in self.events.read_text().splitlines()] if self.events.exists() else []
            if len(events) >= count:
                return events
            time.sleep(0.02)
        self.fail(f"Expected {count} events; got {events}")

    def assert_success(self, process):
        out, error = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, (out, error))

    def test_end_precedes_app_and_arguments_are_literal(self):
        self.player()
        args = ["codex://threads/example", "a file with spaces", '$(touch SHOULD_NOT_EXIST); "quoted"']
        self.assert_success(self.start(args))
        events = self.wait_events(3)
        self.assertEqual([event["event"] for event in events], ["play", "end", "app"])
        self.assertEqual(events[-1]["args"], args)

    def test_preview_never_launches_app(self):
        self.player()
        self.assert_success(self.start(preview=True))
        self.assertEqual([event["event"] for event in self.wait_events(2)], ["play", "end"])

    def test_failure_still_launches_app(self):
        self.player(code=1)
        self.assert_success(self.start())
        self.assertEqual(self.wait_events(3)[-1]["event"], "app")

    def test_missing_video_still_launches_app(self):
        self.write_config(video=self.root / "missing.mp4")
        self.assert_success(self.start())
        self.assertEqual(self.wait_events(1)[0]["event"], "app")

    def test_empty_folder_starts_app_without_player(self):
        self.player()
        folder = self.root / "empty"
        folder.mkdir()
        config = json.loads(self.config.read_text())
        config["video_dir"] = str(folder)
        self.config.write_text(json.dumps(config))
        self.assert_success(self.start())
        self.assertEqual(self.wait_events(1)[0]["event"], "app")

    def test_timeout_kills_player_then_launches_app(self):
        self.player(delay=5)
        self.write_config(timeout=1)
        self.assert_success(self.start())
        self.assertEqual([event["event"] for event in self.wait_events(2)], ["play", "app"])

    def test_overlapping_launches_share_one_intro(self):
        self.player(delay=0.5)
        first = self.start(["one"])
        self.wait_events(1)
        second = self.start(["two"])
        self.assert_success(first)
        self.assert_success(second)
        events = self.wait_events(4)
        self.assertEqual(sum(event["event"] == "play" for event in events), 1)
        self.assertEqual(events[1]["event"], "end")
        self.assertEqual(sorted(event["args"] for event in events if event["event"] == "app"), [["one"], ["two"]])


if __name__ == "__main__":
    unittest.main()
