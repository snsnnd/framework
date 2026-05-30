# EFW 开发与可视化工具环境需求

## 基础构建环境

- Python 3.10 或更新版本：运行 `tools/efw_codegen.py`、`tools/efw_visual_editor.py` 和 `tools/efw_project_manager.py`。
- CMake 3.15 或更新版本：主机侧构建验证。
- C99 编译器：例如 GCC/Clang；嵌入式 IDE 可使用 Keil、STM32CubeIDE、ESP-IDF、MSPM0 SDK 工程等。

## Python 依赖

代码生成器本身只依赖 Python 标准库，不需要额外安装包。

PyQt 可视化工具需要 Qt 绑定：

```bash
python3 -m pip install -r tools/requirements-visual.txt
```

默认推荐 PyQt6。源码也会检测 PyQt5，如果你的环境只能安装 PyQt5，可以手动安装：

```bash
python3 -m pip install "PyQt5>=5.15"
```

## 工具入口

```bash
# 项目管理界面：管理 graph、输出目录、板级 profile 和 notes
python3 tools/efw_project_manager.py

# 蓝图编辑器：编辑卡片、连线、Graph JSON 和 custom_files
python3 tools/efw_visual_editor.py

# CLI 生成器：不启动 UI，直接从 Graph JSON 生成 application/
python3 tools/efw_codegen.py examples/graphs/generic_embedded_app.json \
  -o application/generated_generic_embedded_app \
  --force
```

## 推荐工作流

1. 用 `tools/efw_project_manager.py` 打开或创建 `.efw_project.json` 项目文件。
2. 点击 **Open Graph Editor** 编辑卡片、连线和自定义代码。
3. 点击 **Validate Graph** 做结构、回调函数、签名、周期和 ID 校验。
4. 点击 **Generate** 输出 `application/`。
5. 在真实工程中引入 `include/` 和 `src/efw_all.c`，并把芯片相关 glue 放进 Graph 的 `board_adapters` 或生成后的平台适配文件。

## GitHub Codespaces / VNC 可视化 Qt

仓库已经包含 `.devcontainer/`，在 GitHub Codespaces 中打开仓库时会自动构建带 XFCE、TigerVNC、noVNC、PyQt6、CMake 和 GCC 的开发容器。容器启动后会自动运行 VNC 桌面：

1. 在 Codespaces 的 **Ports** 面板打开 `6080`，浏览器会进入 noVNC。
2. VNC 默认密码是 `codespaces`；如需修改，可在 Codespaces Secrets 或环境变量里设置 `VNC_PASSWORD`。
3. 如果 VNC 页面打不开，先在 Codespaces 终端运行 `bash .devcontainer/check-vnc.sh` 查看 TigerVNC/noVNC/PyQt 自检结果。
4. 进入桌面后打开终端，运行：

```bash
python3 tools/efw_project_manager.py
```

如果只需要命令行生成，不需要 VNC 桌面，可以直接在 Codespaces 终端运行 `tools/efw_codegen.py`。`start-vnc.sh` 每次容器启动都会运行 `check-vnc.sh --quick`，确保 5901/6080 端口已经监听且 noVNC 页面能返回。

## 主机侧验证

```bash
cmake -S . -B build -DEFW_BUILD_APPLICATIONS=ON
cmake --build build
./build/efw_app_simple_blink
./build/efw_app_smart_environment_controller
./build/efw_app_line_tracking_car
```


## 中文字体

Codespaces devcontainer 会安装 `fonts-noto-cjk`、`fonts-noto-color-emoji`、`fonts-dejavu-core` 和 `fontconfig`，并在 PyQt 工作台里优先使用 `Noto Sans CJK SC`。如果 VNC 里中文显示成空格、方块或乱码，先在容器内运行：

```bash
fc-match "Noto Sans CJK SC"
bash .devcontainer/check-vnc.sh --quick
```

`check-vnc.sh` 会检查 `fc-match`、Noto CJK 字体、TigerVNC、noVNC 和 PyQt6。
