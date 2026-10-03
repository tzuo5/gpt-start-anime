# 默认动画模板

`00-default.mp4` 是 15.5 秒演示视频，首次安装复制到 `~/.local/share/codex-startup-animation/animations/`。

安装后在**用户运行时文件夹**更换 MP4。仓库这个目录是分发模板；若希望直接读取源码目录，可显式配置：

```sh
/usr/bin/python3 manage.py configure --video-dir "$PWD/animations"
```

此时需要保留源码目录。多个 MP4 按文件名排序播放第一个；没有 MP4 直接打开应用。
