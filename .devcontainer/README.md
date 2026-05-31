# EFW Codespaces Devcontainer

这个目录是 Codespaces 里运行 PyQt 可视化工具的远程桌面环境，当前内容已经合并为一套闭环：

- `Dockerfile`：安装 C/CMake/Python/PyQt6、XFCE、TigerVNC、noVNC、websockify，以及 `fonts-noto-cjk` 等中文字体。
- `devcontainer.json`：声明 Codespaces 端口、启动脚本和 VS Code 配置。
- `start-vnc.sh`：启动 XFCE + TigerVNC + noVNC，并把桌面暴露到 6080。
- `check-vnc.sh`：检查 `vncserver`、`websockify`、Noto CJK 字体、PyQt6 import、5901/6080 监听和 noVNC 页面。
- `post-create.sh`：容器创建后安装 Python 依赖并做一次 CMake smoke build。

如果 VNC 里中文显示为空格/方块，优先运行：

```bash
fc-match "Noto Sans CJK SC"
bash .devcontainer/check-vnc.sh --quick
```

如果不是在 devcontainer 内运行，`check-vnc.sh --quick` 可能会因为宿主机没有 `vncserver` 而失败，这是预期的；完整检查应在 Codespaces 容器内执行。
