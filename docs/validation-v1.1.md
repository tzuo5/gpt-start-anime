# v1.1 原生 Appearance 验证记录

验证日期：2026-10-03。环境：Ubuntu 26.04.1、Linux x86_64、GNOME 桌面，Codex `26.930.31730`、Electron `42.3.0`。

## 已通过

- 33 项 Python 单元及启动流程测试：视频选择、空目录、参数原样转发、并发、超时、桌面恢复、原生状态保存、版本变更回退、缺失副本、立即退出回退、磁盘不足和验证中断。
- Node.js IPC 测试：来源、主框架、调用参数限制、设置子进程复用、缺失程序及启动失败。
- GTK 设置窗口实际构建、显示并退出。
- 未修改的应用副本在独立配置目录中启动并显示界面。
- 修改后的真实桌面应用打开 `Settings → Appearance`，只显示一个新增入口。
- 按钮打开设置子进程，重复点击复用同一进程。
- 操作原生 Mode 控件切换亮色／暗色；新增入口分别使用对应文字和边框颜色。
- Tab 可以进入按钮，Enter 实际触发点击。
- 不可信页面调用专用桥接得到拒绝。
- 注入“设置程序缺失”故障时，Appearance 显示错误提示，主窗口保持可用；真实设置程序文件没有修改。
- 生产副本只修改三个原有打包成员，新增两个模块；测试钩子在验收后移除。
- 生产副本全部 **20,497** 个打包成员通过整文件及分块 SHA-256 校验。
- 系统原 `app.asar` SHA-256 保持 `03157e5af93b354e0814956a3881d77354e62adcbffab5c7e630c14d3b66178c`；副本 Electron 二进制与系统二进制内容一致。
- 再次执行原生安装复用已验证副本，不重复注入。
- 专用 AppArmor 规则通过本机解析器语法检查。

## 验收边界

测试使用临时 Electron 配置和临时 `CODEX_HOME`，清除调用方的 agent 身份、IPC 管道、CLI 路径及 API 凭据环境变量。设置界面使用合成的无效 API-key 标识及完成首次引导的本地测试状态。测试脚本不发起模型请求，不验证真实登录、聊天、API 或组织策略访问。

本机测试进程继承现有 Codex 的 AppArmor 权限，因此能验证真实应用副本。普通桌面图标启动仍需按教程安装并加载副本专用规则；本机 `sudo` 需要交互认证，规则不会由无权限安装器强行加载。未检测到规则时，启动器保留系统原版。

GitHub Actions 验证 Python、IPC、GTK 和默认 MP4 的解码、渲染、自然结束，不下载或分发 Codex 本体。原生应用测试由本机 `native install` 执行。

## 复现

```sh
/usr/bin/python3 -m unittest discover -s tests -v
node tests/test_bridge.cjs
/usr/bin/python3 manage.py native prepare-apparmor
# 检查并执行上一步打印的系统规则安装命令。
/usr/bin/python3 manage.py native install
/usr/bin/python3 manage.py native status
```

最后两步需要本机已安装支持的应用包和图形桌面。查看 `native/evidence/` 的 `raw.json`、`patched.json`、日志和两张主题截图；运行时数据目录详见 [原生集成教程](appearance.md)。
