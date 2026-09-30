# Tools Structure

`tools/` 是 EFW 的工具层。用户 CLI 和 Studio 都应通过 `tools.api` 使用底层能力。

```text
tools/
  efw.py                 # CLI 主入口，薄适配层
  api/                   # 稳定 API 门面，CLI/Studio 共同入口
    capabilities.py      # capability registry，区分 CLI/Studio/Internal 可见性
    project.py           # 项目生命周期、项目描述操作
    graph.py             # Graph 读取、校验、导出、格式化、内部结构化编辑
    board.py             # Board Profile API
    build.py             # build/simulate/flash API
    device.py            # 真实设备调试 API
    svd.py               # SVD API
  project/               # 项目底层实现和 project CLI adapter
  codegen/               # Graph -> application 生成器
  studio/                # Studio，可视化前端
  board/                 # Board CLI adapter
  debug/                 # 真实设备调试底层工具
  compiler/              # 编译器和构建底层工具
  firmware/              # 固件包管理
  hw/                    # 硬件配置底层工具
  mcu/                   # MCU 数据导入
  simulator/             # MCU 仿真器实现
  svd/                   # SVD 导入、启动文件和链接脚本生成
```

## Command Mapping

| 用户命令 | API 层 | 底层实现 |
| --- | --- | --- |
| `project create/list/info` | `tools.api.project` | `tools.project.core` |
| `project validate/generate/debug` | `tools.api.project`, `tools.api.graph` | `tools.codegen` |
| `project build/simulate/flash` | `tools.api.build` | `tools.compiler`, `tools.simulator`, `tools.efw.cmd_flash` |
| `project device` | `tools.api.device` | `tools.debug` |
| `board list/info/import/set` | `tools.api.board` | board profile data + project descriptor |
| `svd import/list/linker/startup` | `tools.api.svd` | `tools.svd` |

`design` 和 `develop` 是旧兼容入口，不再作为推荐架构的主流程。
