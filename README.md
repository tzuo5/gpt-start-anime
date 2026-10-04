# Codex Startup Animation · 开屏动画

[![Tests](https://github.com/tzuo5/gpt-start-anime/actions/workflows/tests.yml/badge.svg)](https://github.com/tzuo5/gpt-start-anime/actions/workflows/tests.yml)

打开 Codex / ChatGPT 桌面应用时，先播放一个 MP4，结束后再打开应用窗口。

**平台：Linux 的 Ubuntu / Debian 系桌面。已在 Ubuntu 26.04 + GNOME Wayland 上验证。当前不支持 Windows、macOS，也不用于 Codex CLI 的终端启动。** 默认适配提供 `chatgpt.desktop` 的桌面应用，其他 Linux 安装可指定自己的 `.desktop` 文件。

这是通过用户桌面启动器实现的第三方开屏动画扩展。v1.1 提供可选的原生 Appearance 按钮：构建指定版本的用户目录应用副本，点击按钮打开动画设置。[原生集成安装教程](docs/appearance.md)包含支持范围、AppArmor 配置、升级与恢复步骤。

## 功能

- 随附 `animations/00-default.mp4`：15.5 秒的默认演示动画。
- 首次安装复制默认视频到自己的动画文件夹。
- 多个 MP4 按文件名排序播放第一个；没有 MP4 直接打开应用。
- 每次启动重新扫描，替换、删除、重命名视频无需重装。
- 可配置开关、文件夹、全屏 / 窗口、静音、异常超时。
- Esc、空格或“跳过”可以提前进入应用。
- 独立外观设置窗口、应用图标右键菜单入口。
- 可选的原生 `Settings → Appearance` 设置按钮，首次适配 Linux x86_64 的 `26.930.31730` 已核对应用包。
- 原应用更新时，原生集成自动回退系统原版，保留动画功能。
- 失败或超时后继续打开应用；可恢复原启动入口。

## 1. 下载

使用 Git：

```sh
git clone https://github.com/tzuo5/gpt-start-anime.git
cd gpt-start-anime
```

也可[下载 ZIP](https://github.com/tzuo5/gpt-start-anime/archive/refs/heads/main.zip)，解压后在 `gpt-start-anime-main` 文件夹打开终端，无需 GitHub 账号。详细步骤见[下载与安装教程](docs/installation.md)。

## 2. 安装依赖

先安装并确认目标桌面应用可以正常打开。本项目不会下载或安装 Codex 桌面应用。

Ubuntu / Debian 系统依赖：

```sh
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-3.0 gir1.2-gstreamer-1.0 \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-libav \
  desktop-file-utils xdg-utils
```

**扩展按用户安装，不要用 sudo 运行安装器。** 使用系统 `/usr/bin/python3`，不需要 pip 或虚拟环境。

## 3. 启用默认动画

在项目文件夹运行：

```sh
/usr/bin/python3 manage.py install
/usr/bin/python3 manage.py status
```

图形安装也可以运行 `/usr/bin/python3 manage.py gui` 或 `sh setup.sh`，然后点击“保存 / 安装”。

首次创建的默认运行时文件夹：

```text
~/.local/share/codex-startup-animation/animations/
└── 00-default.mp4
```

安装后程序和默认视频已有独立副本，下载的源码文件夹可以删除。自选视频文件夹按原路径引用，需要保留。

## 4. 预览与启动

```sh
/usr/bin/python3 manage.py preview
```

预览只播放视频。正常退出 Codex / ChatGPT 桌面应用后，从原来的应用菜单或 Dock 图标打开，验证完整启动效果。已经存在的窗口不会自动隐藏。

## 5. 更换自己的 MP4

设置窗口点击“打开动画文件夹”，把自己的 MP4 放进去，并移走默认 `00-default.mp4`：

```text
animations/
├── 01-my-intro.mp4    ← 播放这个
└── 02-another.mp4
```

关闭“启用开屏动画”或移走全部 MP4，即可直接打开应用。文件夹删空后，升级或重装不会重新填入默认视频。

**安装后读取用户动画文件夹，不是下载仓库中的 `animations/`。** 更改文件后，下次图标启动自动生效。详细规则与命令见[视频配置教程](docs/configuration.md)。

## 6. 打开外观设置

任选一种：

1. 右键应用菜单里的 ChatGPT / Codex 图标，选择“开屏动画设置”。Dock 支持桌面操作菜单时，也可在那里右键打开。
2. 在应用菜单搜索 **Codex 开屏动画设置** / **Codex Startup Animation Settings**。
3. 执行：

```sh
/usr/bin/python3 ~/.local/share/codex-startup-animation/manage.py gui
```

设置页提供开关、文件夹、全屏、静音、超时、预览与恢复原入口。要从原生 `Settings → Appearance` 打开它，按[原生集成教程](docs/appearance.md)先配置副本的 AppArmor 规则，再运行：

```sh
/usr/bin/python3 manage.py native install
/usr/bin/python3 manage.py native status
```

正常退出当前应用，再从原图标打开即可看到按钮。这是第三方应用副本补丁，按版本与 SHA-256 校验；不是官方插件设置扩展接口。

## 更新、卸载与排错

Git 下载者更新：

```sh
git pull --ff-only
/usr/bin/python3 manage.py install
```

ZIP 下载者下载新版本，解压后执行同样的安装命令。更新保留已有文件夹、配置和原入口备份。

恢复原启动方式：

```sh
/usr/bin/python3 ~/.local/share/codex-startup-animation/manage.py uninstall
```

恢复后移除设置快捷方式和未运行的应用副本，保留视频、配置和工具供重新启用。正在运行的副本需正常退出后再次移除，专用 AppArmor 规则需单独卸载。完整清理见[安装与卸载教程](docs/installation.md)和[原生集成教程](docs/appearance.md)。

检查状态和依赖：

```sh
/usr/bin/python3 ~/.local/share/codex-startup-animation/manage.py status
/usr/bin/python3 ~/.local/share/codex-startup-animation/manage.py doctor
```

日志：`~/.local/state/codex-startup-animation/launcher.log`。[常见问题与排错](docs/troubleshooting.md)包含图标缓存、黑屏、解码器、无声音、恢复冲突等处理。

## 行为和限制

- 保留原应用的桌面 ID、图标与文件 / URL 类型，只覆盖用户级启动入口。
- 可用 `install --desktop-file '/path/to/app.desktop'` 适配其他图形应用入口。
- 直接执行原应用二进制、应用内部新窗口、自建的其他快捷方式会绕过动画。
- 应用已打开时原窗口继续存在；正常退出后的图标启动才是完整开屏过程。
- 只扫描第一层 MP4，扩展名不区分大小写，不递归、不轮播、不随机。
- 排序先忽略大小写，再按原文件名打破平局；数字按文本排序，建议使用 `01-`、`02-` 前缀。
- 第一个视频损坏时，直接打开应用，不尝试播放第二个。
- 快速重复点击共用正在播放的动画，随后转交各次启动参数。

## 开发与验证

```sh
/usr/bin/python3 -m unittest discover -s tests -v
```

测试使用临时目录与模拟应用，不修改真实桌面入口。GitHub Actions 另外在虚拟显示器上播放默认视频，检查渲染和自然结束。

IPC 桥接测试使用 Node.js（仅开发测试需要）：

```sh
node tests/test_bridge.cjs
```

原生应用验收由 `native install` 在本机已安装的支持版本上执行；GitHub Actions 不下载、分发或运行 Codex 本体。

```text
gpt-start-anime/
├── animations/00-default.mp4
├── docs/
│   ├── installation.md
│   ├── configuration.md
│   ├── appearance.md
│   └── troubleshooting.md
├── launcher.py
├── player.py
├── manage.py
├── native.py
├── asar.py
├── native_assets/
├── setup.sh
├── tests/
├── .github/workflows/tests.yml
└── LICENSE
```

本项目是独立的第三方工具，与 OpenAI 无隶属关系，采用 [MIT 许可证](LICENSE)。
