# EFW Studio Tool

这个包面向使用可视化工作台建模、校验并生成 application 的开发者。

包含内容：

- `tools/`：Studio、codegen 和统一入口
- `examples/graphs/`：Graph 示例
- `examples/projects/`：项目示例
- `examples/board_profiles/`：板卡配置数据库
- `include/`、`src/`：供模板扫描、文档提示和生成逻辑参考的 EFW runtime 源码
- `CMakeLists.txt`：主机侧 runtime 构建入口
- `README.md`：项目总览
- `docs/codegen.md`：Studio / codegen 说明
- `docs/environment.md`：环境准备说明

启动方式：

```bash
python3 -m pip install -r tools/requirements-visual.txt
python3 tools/efw.py studio
```

只使用命令行生成器时：

```bash
python3 tools/efw.py codegen examples/graphs/generic_embedded_app.json \
  -o application/generated_generic_embedded_app \
  --force
```

建议第一次使用时直接打开 `examples/projects/generic_embedded_app.efw_project.json`。
