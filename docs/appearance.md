# 外观设置与原生 Appearance

本项目提供独立的 **Codex 启动动画 · 外观设置** 窗口，可调整开关、文件夹、全屏、声音和异常超时。

安装后的入口：

- 应用菜单中 ChatGPT / Codex 图标的右键“开屏动画设置”；Dock 支持桌面操作菜单时，也能显示。
- 应用菜单中的 **Codex 开屏动画设置** 独立图标。
- `/usr/bin/python3 ~/.local/share/codex-startup-animation/manage.py gui`。

截至 2026-10-03，核对的[官方设置文档](https://learn.chatgpt.com/docs/reference/settings)列出了主题、颜色、字体等 Appearance 项；[插件扩展文档](https://developers.openai.com/plugins/build/extensions)没有提供向该页面注入第三方控件的已文档化接口。本机 Appearance 设置模块也未发现用于本项目的注册入口。

因此此版本**尚未嵌入原生 `Settings → Appearance`**，采用独立设置窗口与桌面右键菜单。该窗口已支持本工具的全部开屏设置。

开屏播放器需早于主窗口启动；[SessionStart 钩子](https://learn.chatgpt.com/docs/hooks)针对会话生命周期，不是本项目所需的桌面主窗口启动前入口。安装器不修改应用的 `app.asar` 或系统二进制。

如果将来提供正式设置扩展接口，可以围绕当前同一份配置文件增加集成。
