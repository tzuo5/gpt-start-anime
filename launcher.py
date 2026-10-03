#!/usr/bin/python3
"""Play the intro in a separate process, then hand off to the desktop app."""
import argparse
import fcntl
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

APP_ID = "codex-startup-animation"
VERSION = "1.0.0"


def data_path():
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / APP_ID


def default_video_dir():
    return data_path() / "animations"


def config_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / APP_ID / "config.json"


def read_config(path):
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("配置必须是 JSON 对象")
    if not isinstance(data.get("video", ""), str):
        raise ValueError("video 必须是路径字符串")
    if "video_dir" in data and (not isinstance(data["video_dir"], str) or not data["video_dir"]):
        raise ValueError("video_dir 必须是非空路径字符串")
    for key in ("enabled", "fullscreen", "mute"):
        if key in data and not isinstance(data[key], bool):
            raise ValueError(f"{key} 必须是 true 或 false")
    command = data.get("app_command", ["/usr/bin/chatgpt"])
    if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
        raise ValueError("app_command 必须是非空字符串数组")
    timeout = float(data.get("timeout_seconds", 300))
    if not 1 <= timeout <= 3600:
        raise ValueError("timeout_seconds 必须在 1 到 3600 之间")
    data["app_command"] = command
    data["timeout_seconds"] = timeout
    return data


def select_video(config):
    """Rescan each launch. Directory mode takes precedence over legacy video."""
    if not config.get("enabled", True):
        return None
    if "video_dir" in config:
        folder = Path(config["video_dir"]).expanduser()
        try:
            videos = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".mp4"),
                            key=lambda p: (p.name.casefold(), p.name))
        except OSError:
            return None
        return videos[0] if videos else None
    video = Path(config.get("video", "")).expanduser()
    return video if video.is_file() else None


def play_intro(config, player):
    video = select_video(config)
    if video is None:
        logging.info("动画关闭或文件夹没有 MP4，直接打开应用")
        return
    command = [sys.executable, str(player), "--video", str(video.resolve())]
    if config.get("fullscreen", True):
        command.append("--fullscreen")
    if config.get("mute", False):
        command.append("--mute")
    try:
        result = subprocess.run(command, timeout=config["timeout_seconds"], capture_output=True, text=True,
                                errors="replace")
        logging.info("播放器结果：%s", result.stdout.strip())
        if result.returncode:
            logging.warning("播放失败：%s", result.stderr[-2000:])
    except (OSError, subprocess.TimeoutExpired) as exc:
        logging.warning("播放器不可用或超时，继续打开应用：%s", exc)


def main(argv=None):
    parser = argparse.ArgumentParser(description="先播放 MP4，再打开 Codex 桌面应用")
    parser.add_argument("--config", type=Path, default=config_path())
    parser.add_argument("--preview", action="store_true", help="仅播放，不打开应用")
    parser.add_argument("app_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    forwarded = args.app_args
    if forwarded[:1] == ["--"]:
        forwarded = forwarded[1:]
    state_dir = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / APP_ID
    state_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=state_dir / "launcher.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = read_config(args.config)
    except (OSError, ValueError, TypeError) as exc:
        logging.warning("无法读取配置，使用原始启动命令：%s", exc)
        config = {"app_command": ["/usr/bin/chatgpt"], "timeout_seconds": 300}
    with (state_dir / "launch.lock").open("a") as lock:
        overlapping = False
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            overlapping = True
            # Wait for the first intro to end; preserve this invocation's URLs.
            fcntl.flock(lock, fcntl.LOCK_EX)
        if not overlapping:
            play_intro(config, Path(__file__).with_name("player.py"))
        if args.preview:
            return 0
        command = config["app_command"] + forwarded
        logging.info("动画结束，启动应用")
        try:
            subprocess.Popen(command, start_new_session=True, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            logging.error("无法启动应用：%s", exc)
            print(f"无法启动应用：{exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
