# EFW Runtime SDK

这个包面向把 EFW 集成进真实嵌入式工程的开发者。

包含内容：

- `include/`：公开头文件
- `src/`：运行时源码
- `CMakeLists.txt`：主机侧 CMake 构建入口
- `README.md`：项目总览与接入说明
- `docs/api_reference.md`：API 参考
- `docs/design.md`：设计说明

推荐接入方式：

1. 把 `include/` 加入头文件搜索路径。
2. 推荐只加入 `src/efw_all.c`；或按需把 `src/` 中对应模块源码加入你的 IDE/工程。
3. 根据项目需要配置 `EFW_ENABLE_*` 宏。
4. 在系统启动后调用 `efw_init()`，再注册 HAL / COMM / SENSOR / MODULE / ALGORITHM 等对象。

主机侧验证示例：

```bash
cmake -S . -B build
cmake --build build
```

如果你使用的是 Keil、STM32CubeIDE、ESP-IDF 或其他嵌入式 IDE，优先参考：

- `用户文档/Runtime SDK使用说明.md`
- 仓库根目录 `README.md`
