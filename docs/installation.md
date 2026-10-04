# 下载、安装、更新和卸载

## 系统要求

Linux 图形桌面、Python 3.10 或更新版本、PyGObject、GTK 3、GStreamer。已在 Ubuntu 26.04 的 GNOME Wayland 上验证；本版本不支持 Windows / macOS。

应用本身需已经安装。默认从 `/usr/share/applications/chatgpt.desktop` 的 `Exec` 推导启动命令，不依赖作者的用户名或源码路径，也不会把 Codex CLI 当成图形应用。

## 下载方式 A：Git

尚未安装 Git 时，可用 `sudo apt install git` 安装。

```sh
git clone https://github.com/tzuo5/gpt-start-anime.git
cd gpt-start-anime
```

## 下载方式 B：ZIP

1. 打开 [GitHub 仓库](https://github.com/tzuo5/gpt-start-anime)。
2. 点击绿色 **Code**，选择 **Download ZIP**；或[直接下载](https://github.com/tzuo5/gpt-start-anime/archive/refs/heads/main.zip)。
3. 解压，进入 `gpt-start-anime-main`。
4. 在空白处右键选择“在终端打开”。

ZIP 包包含源码与默认视频，无需 Git 或 GitHub 账号。

## 安装依赖

```sh
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-3.0 gir1.2-gstreamer-1.0 \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-libav \
  desktop-file-utils xdg-utils
```

用 apt 安装系统库，运行时用 `/usr/bin/python3`。虚拟环境、Conda 或用户自装 Python 可能无法读取这些系统模块。

## 默认安装

在源码文件夹运行：

```sh
/usr/bin/python3 manage.py doctor
/usr/bin/python3 manage.py install
/usr/bin/python3 manage.py status
```

按用户安装，不需要 sudo。程序复制到 `~/.local/share/codex-startup-animation/`，配置写入 `~/.config/codex-startup-animation/config.json`，原入口备份写入安装目录的 `install-state.json`。覆盖的是用户级桌面入口，系统文件不修改。

首次**新建**默认动画目录时，复制 `animations/00-default.mp4`。若首次安装前已创建该目录，安装器尊重已有内容，不自动复制视频；需要时手动复制仓库的视频即可。

图形方式：`/usr/bin/python3 manage.py gui` 或 `sh setup.sh`，保留默认文件夹，点击“保存 / 安装”。安装完成后打开动画文件夹与预览。

## 指定不同的桌面应用入口

如果安装提供的是 `codex.desktop`，可以这样运行：

```sh
/usr/bin/python3 manage.py install --desktop-file /usr/share/applications/codex.desktop
```

把路径替换为自己的真实 `.desktop`。安装器保留它的桌面 ID 和应用命令。当前支持 `Exec` 中 `%U`、`%u`、`%F`、`%f` 文件 / URL 字段；其他字段会报错，不猜测。更换目标前先运行 `uninstall`。

## 验证完整启动

1. 用 `manage.py preview` 测试视频。
2. 使用应用的退出菜单正常退出，关闭窗口可能仍保留后台进程。
3. 点击原应用菜单 / Dock 图标。
4. 应先出现动画，结束后打开应用；Esc、空格和“跳过”可提前结束。

Dock 缓存旧入口时，可取消收藏，再从应用菜单重新添加到收藏。

## 更新

Git 下载者：

```sh
git pull --ff-only
/usr/bin/python3 manage.py install
```

ZIP 下载者下载新版本，在新目录运行同样的安装命令。已有文件夹、开关、全屏、静音、超时保留。默认文件夹清空后不会被重新填入视频。更新不会把动画入口当成原应用备份。

## 恢复原启动方式

```sh
/usr/bin/python3 ~/.local/share/codex-startup-animation/manage.py uninstall
```

也可在设置页点击“恢复原启动方式”。安装前有用户级入口时恢复其内容和权限；原来只有系统入口时删除本工具的用户入口。独立设置快捷方式也会移除。

视频、配置、日志和工具保留，可以重新安装。入口后来被其他程序修改时，会停止恢复与更新并提示，避免覆盖你的修改；此时保留 `install-state.json` 并检查入口差异。

如果安装过原生 Appearance 集成，恢复命令还会关闭集成并删除未运行的副本。副本仍运行时需正常退出后再次执行 `native uninstall`。专用 AppArmor 规则要单独卸载，见[原生集成教程](appearance.md)。

## 完整清理

确认恢复成功、所有副本已退出且专用 AppArmor 规则已卸载后，可删除以下三个项目专用目录，移除保留的数据：

```text
~/.local/share/codex-startup-animation/
~/.config/codex-startup-animation/
~/.local/state/codex-startup-animation/
```

自选文件夹在这些目录外时，不会被工具删除。

## 自定义 XDG 路径

支持 `XDG_DATA_HOME`、`XDG_CONFIG_HOME`、`XDG_STATE_HOME`。设置这些变量时，它们替换教程的 `.local/share`、`.config`、`.local/state` 默认目录。用 `status` 查看实际目标与配置。
