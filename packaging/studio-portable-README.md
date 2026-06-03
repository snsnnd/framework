# EFW Studio Portable for Windows

这个包面向最终用户，目标是解压后直接运行，不需要额外安装 Python、PyQt 或配置环境变量。

## 包内主要内容

- `start_studio.bat`：启动 EFW Studio 工作台
- `start_codegen_demo.bat`：命令行示例，生成 demo application
- `.venv/`：随包携带的 Windows Python 运行环境与 PyQt
- `tools/`：Studio、codegen 和统一入口
- `examples/`：示例 graph、示例项目与 board profile
- `include/`、`src/`：EFW runtime 源码，供模板扫描、说明和生成逻辑参考
- `docs/`：介绍文档与操作手册

## 最短使用方式

1. 解压整个目录到任意可写位置，例如 `D:\EFW-Studio-Portable`。
2. 双击 `start_studio.bat`。
3. 在 Studio 中直接打开 `examples/projects/generic_embedded_app.efw_project.json`。

## 注意事项

- 请不要只拷贝某几个文件，必须保留整个目录结构。
- 第一次运行如果被 Windows SmartScreen 提示，需要手动允许。
- `examples/`、`tools/`、`include/`、`src/` 都被 Studio/codegen 使用，不建议删除。
- 生成的 application 默认写到你在项目中选择的输出目录；建议使用当前包目录下的 `application/`。

## 如果启动失败

优先检查：

1. 是否解压完整目录，而不是在压缩包预览里直接运行。
2. `.venv/Scripts/python.exe` 是否存在。
3. `tools/efw.py` 是否存在。
4. 是否把整个目录放到了有写权限的位置。

更多说明见 `docs/studio_intro.md` 和 `docs/studio_user_guide.md`。
