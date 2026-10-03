# 常见问题与排错

## 点击图标没有动画

运行：

```sh
/usr/bin/python3 ~/.local/share/codex-startup-animation/manage.py status
```

检查 `installed`、`entry_intact`、`config.enabled` 是否为 `true`；`selected_video` 应指向目标 MP4。为 `null` 时检查开关与运行时文件夹。

注意运行时文件夹不同于下载项目的 `animations/`。从原应用二进制或其他自建快捷方式启动会绕过动画。Dock 缓存旧入口时，可取消收藏再从应用菜单重新添加。

## 动画期间仍看到应用窗口

本工具延后调用启动命令，不隐藏已有窗口。使用应用的退出菜单正常退出后再点击图标测试。此版本没有实现 Wayland 下隐藏其他应用窗口的功能。

## 缺少 gi、GTK 或 GStreamer

按 README 安装系统依赖，用 `/usr/bin/python3` 执行；虚拟环境、Conda 或用户自装 Python 可能看不到系统模块。

## 黑屏、解码错误

确认安装 `gstreamer1.0-libav` 和 `gstreamer1.0-plugins-good`。推荐 H.264 编码的 MP4；MP4 是容器，播放能力取决于具体编码及系统解码器。

```sh
/usr/bin/python3 ~/.local/share/codex-startup-animation/manage.py doctor
/usr/bin/python3 ~/.local/share/codex-startup-animation/manage.py preview
```

10 秒内没有解码出画面时，播放器退出。发生播放错误或达到异常超时后，启动器继续打开应用。

## 多个视频没有播放最新加入的那个

按文件名排序，不按修改时间。移走默认 `00-default.mp4`，使用 `01-`、`02-` 前缀，查看 `selected_video`。

## 没声音 / 想静音

无音轨视频不会发声。检查设置中的“静音”；勾选并保存即可关闭视频声音。

## 清空文件夹后升级会恢复视频吗

不会。默认视频只在首次创建默认目录时复制。自选目录不会自动导入演示文件。

## 原生 Appearance 中没有选项

此版本使用独立设置窗口，见[外观说明](appearance.md)。若右键菜单不展示操作，可搜索独立设置菜单项或执行 `manage.py gui`；不同桌面对桌面操作菜单的支持不同。

## 桌面入口被其他程序修改

安装器在摘要不匹配时停止更新与恢复。保留安装目录的 `install-state.json`，检查 `~/.local/share/applications/chatgpt.desktop`（自定义目标对应自己的文件名）。状态文件包含原入口恢复信息，不要直接删除它来强行重装。

## 更换了应用安装路径

先恢复原入口，再用新的 `.desktop` 运行 `install --desktop-file ...`。启动命令从原文件的 `Exec` 推导。

## 查看日志

`~/.local/state/codex-startup-animation/launcher.log` 记录视频选择、播放器结果与失败信息。报告问题时提供系统版本、桌面环境、状态和相关日志片段。
