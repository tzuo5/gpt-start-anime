#!/usr/bin/python3
"""Install/configure a reversible per-user desktop startup extension."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from launcher import APP_ID, VERSION, config_path, data_path, default_video_dir, read_config, select_video

SYSTEM_DESKTOP = Path("/usr/share/applications/chatgpt.desktop")
SETTINGS_ID = "codex-startup-animation-settings.desktop"


def atomic_write(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        temporary.write_bytes(content)
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def paths():
    return data_path(), data_path().parent / "applications/chatgpt.desktop"


def digest(content):
    return hashlib.sha256(content).hexdigest()


def desktop_quote(value):
    # Desktop Entry quoting is not shell quoting. Escape its reserved characters.
    return '"' + str(value).replace("\\", "\\\\\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%") + '"'


def desktop_entry(original, launcher, settings=None):
    lines = original.splitlines()
    main_section = False
    replaced = False
    output = []
    for line in lines:
        if line.startswith("["):
            if main_section:
                output.append("X-CodexStartupAnimation=true")
            main_section = line == "[Desktop Entry]"
        if main_section and line.startswith("Exec="):
            line = f"Exec=/usr/bin/python3 {desktop_quote(launcher)} -- %U"
            replaced = True
        if main_section and line.startswith("DBusActivatable="):
            line = "DBusActivatable=false"
        if main_section and settings and line.startswith("Actions="):
            actions = [a for a in line[8:].split(";") if a and a != "StartupAnimationSettings"]
            line = "Actions=" + ";".join(actions + ["StartupAnimationSettings"]) + ";"
        if main_section and line.startswith("X-CodexStartupAnimation="):
            continue
        output.append(line)
    if main_section:
        output.append("X-CodexStartupAnimation=true")
    if not replaced:
        raise ValueError("原始桌面入口没有 Exec 字段")
    if settings:
        if not any(line.startswith("Actions=") for line in output):
            index = output.index("[Desktop Entry]") + 1
            output.insert(index, "Actions=StartupAnimationSettings;")
        output.extend(["", "[Desktop Action StartupAnimationSettings]", "Name=Startup animation settings",
                       "Name[zh_CN]=开屏动画设置", "Name[zh_TW]=開屏動畫設定",
                       f"Exec=/usr/bin/python3 {desktop_quote(settings)} gui"])
    return ("\n".join(output) + "\n").encode()


def doctor(desktop_file=None):
    if not Path(desktop_file or SYSTEM_DESKTOP).is_file():
        raise RuntimeError("未发现 chatgpt.desktop；可用 install --desktop-file 指定应用桌面文件")
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)
    required = ["playbin", "videoconvert", "videoscale", "appsink", "qtdemux", "avdec_h264"]
    missing = [name for name in required if not Gst.ElementFactory.find(name)]
    if missing:
        raise RuntimeError("缺少 GStreamer 组件：" + ", ".join(missing))
    return "GTK / GStreamer / H.264 解码器 / 桌面应用入口已就绪"


def app_command_from_desktop(original):
    import gi
    from gi.repository import GLib
    keyfile = GLib.KeyFile()
    keyfile.load_from_data(original.decode(), len(original), GLib.KeyFileFlags.NONE)
    _, command = GLib.shell_parse_argv(keyfile.get_string("Desktop Entry", "Exec"))
    # Exec is not a shell command; file/URL args are forwarded by our launcher.
    result = [part.replace("%%", "%") for part in command if part not in ("%U", "%u", "%F", "%f")]
    if any("%" in part.replace("%%", "") for part in command if part not in ("%U", "%u", "%F", "%f")):
        raise ValueError("桌面 Exec 含不支持的字段；当前支持 %U / %u / %F / %f")
    executable = shutil.which(result[0]) if result else None
    if not executable:
        raise ValueError("桌面入口引用的可执行程序不存在")
    result[0] = executable
    return result


def settings_entry(root):
    return ("[Desktop Entry]\nType=Application\nName=Codex Startup Animation Settings\n"
            "Name[zh_CN]=Codex 开屏动画设置\nName[zh_TW]=Codex 開屏動畫設定\n"
            "Comment=Choose the intro video folder, fullscreen, and sound\nIcon=preferences-desktop-theme\n"
            f"Exec=/usr/bin/python3 {desktop_quote(root / 'manage.py')} gui\n"
            "Categories=Settings;\nX-CodexStartupAnimation=true\n").encode()


def bundled_video_dir():
    return Path(__file__).parent / "animations"


def install(video=None, fullscreen=None, mute=None, timeout=None, *, video_dir=None, enabled=None, desktop_file=None):
    if video is not None and video_dir is not None:
        raise ValueError("--video 和 --video-dir 不能同时使用")
    if desktop_file is not None:
        desktop_file = Path(desktop_file).expanduser().resolve(strict=True)
    doctor(desktop_file)
    if video is not None:
        video = Path(video).expanduser().resolve(strict=True)
        if not video.is_file() or video.suffix.lower() != ".mp4":
            raise ValueError("请选择一个有效的 MP4 文件")
    root, desktop = paths()
    state_file = root / "install-state.json"
    existing_config = read_config(config_path()) if config_path().is_file() else {}
    fullscreen = existing_config.get("fullscreen", True) if fullscreen is None else fullscreen
    mute = existing_config.get("mute", False) if mute is None else mute
    enabled = existing_config.get("enabled", True) if enabled is None else enabled
    timeout = existing_config.get("timeout_seconds", 300) if timeout is None else timeout
    if not 1 <= timeout <= 3600:
        raise ValueError("超时必须在 1 到 3600 秒之间")
    state = json.loads(state_file.read_text()) if state_file.exists() else None
    if state and "desktop_name" in state:
        desktop = desktop.with_name(state["desktop_name"])
    elif desktop_file:
        desktop = desktop.with_name(Path(desktop_file).name)
    if desktop.is_symlink():
        raise RuntimeError("桌面入口是符号链接，请先确认其用途")
    if state is not None:
        if desktop_file and Path(desktop_file).name != desktop.name:
            raise ValueError("更换目标应用前，请先 uninstall 恢复原入口")
        if not desktop.is_file() or digest(desktop.read_bytes()) != state["installed_sha256"]:
            raise RuntimeError("桌面入口在安装后被其他程序更改；请先检查，避免覆盖你的修改")
        original = base64.b64decode(state["source"])
    else:
        local_exists = desktop.exists()
        source = desktop if local_exists else Path(desktop_file or SYSTEM_DESKTOP)
        original = source.read_bytes()
        state = {
            "had_local_entry": local_exists,
            "source": base64.b64encode(original).decode(),
            "original_mode": source.stat().st_mode & 0o777,
            "desktop_name": desktop.name,
        }
    state.setdefault("desktop_name", desktop.name)
    app_command = app_command_from_desktop(original)
    settings_desktop = desktop.with_name(SETTINGS_ID)
    if settings_desktop.exists() and b"X-CodexStartupAnimation=true" not in settings_desktop.read_bytes():
        raise RuntimeError("设置入口已被其他程序占用")
    folder = Path(video_dir or existing_config.get("video_dir") or default_video_dir()).expanduser().resolve()
    folder_new = not folder.exists()
    folder.mkdir(parents=True, exist_ok=True)
    if video is not None:
        destination = folder / video.name
        if video != destination:
            shutil.copy2(video, destination)
    elif video_dir is None and folder_new and "video_dir" not in existing_config:
        # Seed only a newly created default folder. Never refill an emptied one.
        bundled = bundled_video_dir()
        if bundled.is_dir():
            for clip in bundled.iterdir():
                if clip.is_file() and clip.suffix.lower() == ".mp4":
                    shutil.copy2(clip, folder / clip.name)
    rendered = desktop_entry(original.decode(), root / "launcher.py", root / "manage.py")
    if shutil.which("desktop-file-validate"):
        # Validate a staging file before changing the actual desktop entry.
        staging = root / "staging.desktop"
        atomic_write(staging, rendered)
        try:
            subprocess.run(["desktop-file-validate", str(staging)], check=True, capture_output=True)
        finally:
            staging.unlink(missing_ok=True)
    for name in ("launcher.py", "player.py", "manage.py"):
        atomic_write(root / name, Path(__file__).with_name(name).read_bytes(), 0o755)
    atomic_write(config_path(), json.dumps({
        "schema_version": 2, "video_dir": str(folder), "enabled": enabled,
        "fullscreen": fullscreen, "mute": mute,
        "timeout_seconds": timeout, "app_command": app_command,
    }, ensure_ascii=False, indent=2).encode())
    state["installed_sha256"] = digest(rendered)
    # Store recovery data before replacing the desktop entry.
    atomic_write(state_file, json.dumps(state, indent=2).encode())
    atomic_write(desktop, rendered, 0o644)
    atomic_write(settings_desktop, settings_entry(root), 0o644)
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(desktop.parent)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    selected = select_video(read_config(config_path()))
    return f"已保存启动动画配置。文件夹：{folder}\n当前视频：{selected or '无（直接打开应用）'}\n可从应用图标右键菜单打开开屏动画设置。"


def uninstall():
    root, desktop = paths()
    state_file = root / "install-state.json"
    if not state_file.exists():
        return "启动动画尚未安装。"
    state = json.loads(state_file.read_text())
    desktop = desktop.with_name(state.get("desktop_name", desktop.name))
    if desktop.is_symlink() or not desktop.is_file() or digest(desktop.read_bytes()) != state["installed_sha256"]:
        raise RuntimeError("桌面入口已被其他程序更改；未执行恢复，请保留 install-state.json 并检查入口")
    if state["had_local_entry"]:
        atomic_write(desktop, base64.b64decode(state["source"]), state["original_mode"])
    else:
        desktop.unlink()
    settings_desktop = desktop.with_name(SETTINGS_ID)
    if settings_desktop.is_file() and b"X-CodexStartupAnimation=true" in settings_desktop.read_bytes():
        settings_desktop.unlink()
    state_file.unlink()
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(desktop.parent)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "已恢复原来的应用启动方式。视频、配置和设置工具已保留，可以重新启用。"


def status():
    root, desktop = paths()
    state_file = root / "install-state.json"
    if state_file.is_file():
        desktop = desktop.with_name(json.loads(state_file.read_text()).get("desktop_name", desktop.name))
    installed = state_file.is_file() and desktop.is_file()
    intact = installed and digest(desktop.read_bytes()) == json.loads(state_file.read_text())["installed_sha256"]
    config = read_config(config_path()) if config_path().is_file() else None
    return {"version": VERSION, "installed": installed, "entry_intact": intact, "config": config,
            "selected_video": str(select_video(config)) if config and select_video(config) else None,
            "desktop_entry": str(desktop)}


def configure(**changes):
    config = read_config(config_path())
    config.update({key: value for key, value in changes.items() if value is not None})
    if changes.get("video_dir") is not None:
        folder = Path(changes["video_dir"]).expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        config["video_dir"] = str(folder)
        config.pop("video", None)
    # Validate before replacing the live configuration.
    temporary = config_path().with_name("validate-config.json")
    atomic_write(temporary, json.dumps(config).encode())
    try:
        read_config(temporary)
    finally:
        temporary.unlink(missing_ok=True)
    atomic_write(config_path(), json.dumps(config, ensure_ascii=False, indent=2).encode())
    return "配置已保存，下次启动生效。"


def open_folder():
    config = read_config(config_path()) if config_path().is_file() else {}
    folder = Path(config.get("video_dir", str(default_video_dir()))).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(["xdg-open", str(folder)])
    return f"动画文件夹：{folder}"


def gui():
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    window = Gtk.Window(title="Codex 启动动画 · 外观设置")
    window.set_default_size(700, 420)
    window.set_position(Gtk.WindowPosition.CENTER)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    box.set_border_width(24)
    window.add(box)
    box.pack_start(Gtk.Label(label="开屏动画\n文件夹中有多个 MP4 时，按文件名排序播放第一个；没有 MP4 时直接打开应用。", xalign=0), False, False, 0)
    enabled = Gtk.CheckButton(label="启用开屏动画")
    enabled.set_active(True)
    box.pack_start(enabled, False, False, 0)
    row = Gtk.Box(spacing=10)
    folder_entry = Gtk.Entry()
    folder_entry.set_text(str(default_video_dir()))
    row.pack_start(folder_entry, True, True, 0)
    browse = Gtk.Button(label="选择文件夹")
    row.pack_start(browse, False, False, 0)
    box.pack_start(row, False, False, 0)
    full = Gtk.CheckButton(label="全屏播放")
    full.set_active(True)
    mute = Gtk.CheckButton(label="静音")
    box.pack_start(full, False, False, 0)
    box.pack_start(mute, False, False, 0)
    timeout_spin = Gtk.SpinButton.new_with_range(1, 3600, 1)
    timeout_spin.set_value(300)
    timeout_row = Gtk.Box(spacing=10)
    timeout_row.pack_start(Gtk.Label(label="异常超时（秒）"), False, False, 0)
    timeout_row.pack_start(timeout_spin, False, False, 0)
    box.pack_start(timeout_row, False, False, 0)
    message = Gtk.Label(xalign=0)
    message.set_line_wrap(True)
    box.pack_start(message, True, True, 0)
    if config_path().exists():
        config = read_config(config_path())
        folder_entry.set_text(config.get("video_dir", str(default_video_dir())))
        enabled.set_active(config.get("enabled", True))
        full.set_active(config.get("fullscreen", True))
        mute.set_active(config.get("mute", False))
        timeout_spin.set_value(config.get("timeout_seconds", 300))
    buttons = Gtk.Box(spacing=12)
    box.pack_start(buttons, False, False, 0)

    def action(function):
        try:
            message.set_text(function())
        except Exception as exc:
            message.set_text(str(exc))

    def folder():
        if not folder_entry.get_text().strip():
            raise ValueError("请选择动画文件夹")
        return Path(folder_entry.get_text()).expanduser().resolve()

    def choose_folder(_):
        dialog = Gtk.FileChooserDialog(title="选择动画文件夹", parent=window,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("取消", Gtk.ResponseType.CANCEL, "选择", Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            folder_entry.set_text(dialog.get_filename())
        dialog.destroy()
    browse.connect("clicked", choose_folder)

    def preview():
        selected = select_video({"video_dir": str(folder()), "enabled": enabled.get_active()})
        if selected is None:
            return "动画已关闭或文件夹没有 MP4，下次启动会直接打开应用。"
        command = [sys.executable, str(Path(__file__).with_name("player.py")), "--video", str(selected)]
        if full.get_active():
            command.append("--fullscreen")
        if mute.get_active():
            command.append("--mute")
        subprocess.Popen(command)
        return "正在预览；按 Esc 可以跳过。"

    def save():
        changes = dict(video_dir=str(folder()), fullscreen=full.get_active(), mute=mute.get_active(),
                       enabled=enabled.get_active(), timeout_seconds=timeout_spin.get_value_as_int())
        if status()["installed"]:
            return configure(**changes)
        timeout = changes.pop("timeout_seconds")
        if folder() == default_video_dir().resolve():
            changes["video_dir"] = None
        return install(timeout=timeout, **changes)

    def show_folder():
        folder().mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(folder())])
        return "把 MP4 放进此文件夹即可；重新启动时自动扫描。"

    for label, callback in [
        ("预览", preview),
        ("保存 / 安装", save),
        ("打开动画文件夹", show_folder),
        ("恢复原启动方式", uninstall),
    ]:
        button = Gtk.Button(label=label)
        button.connect("clicked", lambda _, cb=callback: action(cb))
        buttons.pack_start(button, True, True, 0)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()


def main():
    parser = argparse.ArgumentParser(description="Codex 桌面启动动画扩展（Ubuntu）")
    commands = parser.add_subparsers(dest="action", required=True)
    install_parser = commands.add_parser("install", help="启用并接管用户桌面图标")
    video_group = install_parser.add_mutually_exclusive_group()
    video_group.add_argument("--video", type=Path, help="把一个 MP4 复制到动画文件夹")
    video_group.add_argument("--video-dir", type=Path, help="使用自选文件夹（不复制默认视频）")
    install_parser.add_argument("--desktop-file", type=Path, help="自定义目标应用的 .desktop 文件")
    configure_parser = commands.add_parser("configure", help="调整已安装扩展的外观配置")
    configure_parser.add_argument("--video-dir", type=Path)
    for target in (install_parser, configure_parser):
        screen = target.add_mutually_exclusive_group()
        screen.add_argument("--fullscreen", dest="fullscreen", action="store_const", const=True, default=None)
        screen.add_argument("--windowed", dest="fullscreen", action="store_const", const=False)
        target.add_argument("--mute", action=argparse.BooleanOptionalAction, default=None)
        target.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
        target.add_argument("--timeout", type=int)
    for name in ("gui", "status", "doctor", "uninstall", "preview", "open-folder"):
        commands.add_parser(name)
    args = parser.parse_args()
    try:
        if args.action == "install":
            print(install(args.video, args.fullscreen, args.mute, args.timeout,
                          video_dir=args.video_dir, enabled=args.enabled, desktop_file=args.desktop_file))
        elif args.action == "configure":
            print(configure(video_dir=str(args.video_dir) if args.video_dir else None, fullscreen=args.fullscreen,
                            mute=args.mute, enabled=args.enabled, timeout_seconds=args.timeout))
        elif args.action == "uninstall":
            print(uninstall())
        elif args.action == "status":
            print(json.dumps(status(), ensure_ascii=False, indent=2))
        elif args.action == "doctor":
            print(doctor())
        elif args.action == "open-folder":
            print(open_folder())
        elif args.action == "preview":
            return subprocess.call([sys.executable, str(Path(__file__).with_name("launcher.py")), "--preview"])
        else:
            gui()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
