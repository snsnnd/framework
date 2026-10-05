# Electron 壳

- `main.mjs`：以 stdio 启动 Python 服务（开发时 `python -m studio_core.server`，打包后用
  `resources/backend-bin/efw-backend`），把 JSON Lines 转成 IPC；渲染进程只经白名单方法调用。
- `preload.cjs`：`contextIsolation` 下的唯一桥，暴露 `efw.call` / `efw.pickDirectory` /
  `efw.pickFile` / `efw.onEvent`。
- 开发：`EFW_DEV_URL=http://127.0.0.1:5173 npm start`（先跑 `npm run dev`）。
- 打包：`npm run package` = 前端构建 + `scripts/package_backend.py` + `electron-builder --dir`。
- 打包后把 `runtime/`、`docs/`、`examples/` 作为 `extraResources` 一起分发，生成器通过
  `EFW_RUNTIME` 找到 C 运行库。
