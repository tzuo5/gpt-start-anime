#!/usr/bin/python3
"""GTK/GStreamer splash player; does not import or modify the target app."""
import argparse
import json
from pathlib import Path
import sys
import threading


def play(video, fullscreen=False, mute=False):
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    gi.require_version("Gst", "1.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gst, Gtk

    Gst.init(None)
    if not Gtk.init_check()[0]:
        raise RuntimeError("无法连接图形桌面")
    window = Gtk.Window(title="Codex · 启动动画")
    window.set_default_size(960, 540)
    window.set_position(Gtk.WindowPosition.CENTER)
    window.set_decorated(False)
    window.set_keep_above(True)
    css = Gtk.CssProvider()
    css.load_from_data(b"window { background: #000; } button { margin: 20px; padding: 8px 16px; }")
    Gtk.StyleContext.add_provider_for_screen(window.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    overlay = Gtk.Overlay()
    image = Gtk.Image()
    overlay.add(image)
    skip = Gtk.Button(label="跳过  Esc")
    skip.set_halign(Gtk.Align.END)
    skip.set_valign(Gtk.Align.END)
    overlay.add_overlay(skip)
    window.add(overlay)
    monitor = window.get_screen().get_display().get_primary_monitor()
    if monitor is None:
        monitor = window.get_screen().get_display().get_monitor(0)
    geometry = monitor.get_geometry()
    width, height = (geometry.width, geometry.height) if fullscreen else (960, 540)
    scale = min(1.0, 1280 / width, 720 / height)
    width, height = int(width * scale) // 2 * 2, int(height * scale) // 2 * 2

    playbin = Gst.ElementFactory.make("playbin", "intro")
    sink = Gst.parse_bin_from_description(
        f"videoconvert ! videoscale add-borders=true ! video/x-raw,format=RGB,width={width},height={height},pixel-aspect-ratio=1/1 "
        "! appsink name=frames emit-signals=true max-buffers=1 drop=true sync=true", True)
    if playbin is None or sink is None:
        raise RuntimeError("缺少 GStreamer 播放组件")
    frames = sink.get_by_name("frames")
    playbin.set_property("video-sink", sink)
    playbin.set_property("uri", video.resolve().as_uri())
    if mute:
        playbin.set_property("audio-sink", Gst.ElementFactory.make("fakesink", "silent"))
    result = {"reason": "error", "frames": 0}
    pending = {"frame": None, "scheduled": False, "closed": False}
    guard = threading.Lock()

    def show_frame():
        with guard:
            frame = pending["frame"]
            pending["frame"] = None
            pending["scheduled"] = False
            if pending["closed"] or frame is None:
                return False
        data, rowstride = frame
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(data), GdkPixbuf.Colorspace.RGB,
                                                False, 8, width, height, rowstride)
        # Fit to the monitor without changing the video's aspect ratio.
        allocation = overlay.get_allocation()
        if allocation.width > 1 and allocation.height > 1:
            ratio = min(allocation.width / width, allocation.height / height)
            pixbuf = pixbuf.scale_simple(max(1, int(width * ratio)), max(1, int(height * ratio)),
                                        GdkPixbuf.InterpType.BILINEAR)
        image.set_from_pixbuf(pixbuf)
        result["frames"] += 1
        return False

    def on_sample(appsink):
        sample = appsink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.EOS
        buffer = sample.get_buffer()
        pixels = buffer.extract_dup(0, buffer.get_size())
        with guard:
            if pending["closed"]:
                return Gst.FlowReturn.FLUSHING
            pending["frame"] = (pixels, ((width * 3 + 3) // 4) * 4)
            if not pending["scheduled"]:
                pending["scheduled"] = True
                GLib.idle_add(show_frame)
        return Gst.FlowReturn.OK

    def finish(reason, error=None):
        with guard:
            if pending["closed"]:
                return
            pending["closed"] = True
        result["reason"] = reason
        if error:
            print(error, file=sys.stderr)
        Gtk.main_quit()

    def on_message(bus, message):
        if message.type == Gst.MessageType.EOS:
            finish("eos")
        elif message.type == Gst.MessageType.ERROR:
            error, detail = message.parse_error()
            finish("error", str(error))

    def on_key(widget, event):
        if event.keyval in (Gdk.KEY_Escape, Gdk.KEY_space):
            finish("skip")
            return True
        return False

    frames.connect("new-sample", on_sample)
    bus = playbin.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_message)
    skip.connect("clicked", lambda _: finish("skip"))
    window.connect("delete-event", lambda *_: finish("skip") or True)
    window.connect("key-press-event", on_key)
    window.show_all()
    if fullscreen:
        window.fullscreen()
    if playbin.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
        playbin.set_state(Gst.State.NULL)
        window.destroy()
        raise RuntimeError("无法开始播放")
    # A file that cannot produce a video frame must not leave a black splash.
    def check_first_frame():
        if result["frames"] == 0:
            finish("error", "10 秒内未解码出视频画面")
        return False
    watchdog = GLib.timeout_add_seconds(10, check_first_frame)
    try:
        Gtk.main()
    finally:
        with guard:
            pending["closed"] = True
        source = GLib.MainContext.default().find_source_by_id(watchdog)
        if source is not None:
            source.destroy()
        playbin.set_state(Gst.State.NULL)
        bus.remove_signal_watch()
        window.destroy()
    print(json.dumps(result))
    return 0 if result["reason"] in ("eos", "skip") and (result["frames"] or result["reason"] == "skip") else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--mute", action="store_true")
    args = parser.parse_args()
    try:
        return play(args.video, args.fullscreen, args.mute)
    except Exception as exc:
        print(f"动画播放失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
