# EFW CLI Project-First Workflow

EFW CLI 现在以项目为中心。`design` / `develop` 仍保留为兼容入口，但新流程应使用 `project` 子命令。

## 推荐流程

```bash
python3 tools/efw.py project create demo --chip STM32F407VGT6 --board Discovery_F407
python3 tools/efw.py project validate demo
python3 tools/efw.py project generate demo --dry-run
python3 tools/efw.py project generate demo
python3 tools/efw.py project build demo --generate
python3 tools/efw.py project simulate demo --duration 1000
python3 tools/efw.py project device demo snapshot --port /dev/ttyUSB0
python3 tools/efw.py project flash demo --bin path/to/app.bin --tool stlink
```

## Graph 职责边界

- `graph.json` 是项目定义源文件。
- Studio 是主要 Graph 可视化编辑器。
- 用户也可以直接编辑 JSON。
- CLI 只读取、校验、导出和格式化 Graph，不提供逐字段写 Graph 的用户命令。
- Studio 和自动化可通过 `tools.api.graph` 调用结构化写 API。

## 常用命令

```bash
python3 tools/efw.py project list
python3 tools/efw.py project info demo
python3 tools/efw.py project graph demo info
python3 tools/efw.py project graph demo path
python3 tools/efw.py project graph demo export -o graph.backup.json
python3 tools/efw.py board list
python3 tools/efw.py svd list
python3 tools/efw.py studio
```

## API-First 分层

```text
CLI / Studio
  -> tools.api.*
    -> tools.project / tools.codegen / tools.debug / tools.compiler / tools.simulator / tools.svd
```

CLI 和 Studio 都应通过 `tools.api` 使用工具能力。底层模块可以重构，API 层负责保持稳定契约。
