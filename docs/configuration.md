# 配置开屏动画

## 文件夹与排序规则

默认运行时目录为 `~/.local/share/codex-startup-animation/animations/`，首次创建时包含 `00-default.mp4`。安装后的目录与源码仓库的 `animations/` 不同。

| 状态 | 行为 |
| --- | --- |
| 一个 MP4 | 播放它，结束后打开应用 |
| 多个 MP4 | 按文件名排序，只播放第一个 |
| 没有 MP4 | 直接打开应用 |
| 文件夹缺失 / 不可读取 | 直接打开应用 |
| 动画开关关闭 | 直接打开应用 |
| 第一个 MP4 无法播放 | 记录错误后打开应用，不尝试第二个 |

每次启动重新扫描。支持 `.mp4` / `.MP4` 等大小写组合，只读取第一层文件，忽略目录和其他格式。

排序先忽略大小写，再按原文件名打破平局；数字按文本排序，建议 `01-`、`02-`、`03-` 前缀。

## 更换视频

1. 打开设置窗口，点击“打开动画文件夹”。
2. 把自己的 MP4 放进去。
3. 移走默认 `00-default.mp4`，它的名字排序通常靠前。
4. 用 `01-your-intro.mp4`、`02-other.mp4` 命名。
5. 点击“预览”确认；下次图标启动自动扫描新的文件。

要播放另一个视频，把它重命名到更靠前的位置，或移走在它之前的文件。移走全部 MP4 即跳过动画；重新安装不会把删空的文件夹再次填满。

## 图形界面选项

打开应用图标右键操作“开屏动画设置”，或搜索独立设置菜单项，也可执行：

```sh
/usr/bin/python3 ~/.local/share/codex-startup-animation/manage.py gui
```

- **启用开屏动画**：关闭后直接打开应用，不必删视频。
- **选择文件夹**：指定保存 MP4 的文件夹。
- **全屏播放**：默认开启；关闭时使用 960×540 窗口。
- **静音**：默认关闭，允许播放视频内音轨；无音轨视频没有声音。
- **异常超时（秒）**：默认 300 秒，允许 1–3600 秒；正常播放按结束事件退出。
- **保存 / 安装**：安装入口或保存选项，下次启动生效。
- **预览**：使用当前界面的文件夹、开关、全屏、静音，只播放动画，不启动应用。预览不代替保存。
- **恢复原启动方式**：恢复应用原入口。

文件内容变化自动生效；界面选项变化需要保存。

## 命令行配置

以下命令在下载项目文件夹运行，也可把 `manage.py` 换为安装后的完整路径。

选择自己的文件夹：

```sh
/usr/bin/python3 manage.py configure --video-dir "$HOME/Videos/codex-intro"
```

首次安装直接使用自己的目录：

```sh
/usr/bin/python3 manage.py install --video-dir "$HOME/Videos/codex-intro"
```

自选目录不复制演示视频，空文件夹合法。

改变全屏和声音：

```sh
/usr/bin/python3 manage.py configure --windowed --mute
/usr/bin/python3 manage.py configure --fullscreen --no-mute
```

关闭和重新开启：

```sh
/usr/bin/python3 manage.py configure --no-enabled
/usr/bin/python3 manage.py configure --enabled
```

调整异常超时：

```sh
/usr/bin/python3 manage.py configure --timeout 60
```

若视频长于上限，会在上限到达时停止播放并进入应用。

导入单个文件的兼容命令：

```sh
/usr/bin/python3 manage.py install --video "$HOME/Videos/my-intro.mp4"
```

它把视频复制到当前动画目录，不清空其他文件；仍按文件名排序播放。可用 `status` 查看实际选择的文件。

## 手动编辑配置

默认配置路径是 `~/.config/codex-startup-animation/config.json`：

```json
{
  "schema_version": 2,
  "video_dir": "/home/YOUR_USER/.local/share/codex-startup-animation/animations",
  "enabled": true,
  "fullscreen": true,
  "mute": false,
  "timeout_seconds": 300,
  "app_command": ["/usr/bin/chatgpt"]
}
```

替换 `YOUR_USER`，更推荐用设置窗口或命令生成真实路径。`app_command` 从原桌面入口推导，必须保持数组，不是 shell 字符串。旧版 `video` 单文件配置仍可读取，更新后使用 `video_dir`。

`status` 的 `selected_video` 为 `null` 时表示当前不播放动画。
