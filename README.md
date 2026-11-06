<p align="center">
  <img src="icon.jpg" alt="NeoCatCraftLauncher" width="160">
</p>

# NeoCatCraftLauncher

一个采用 Electron + Vue 3 + Python FastAPI 构建的 Minecraft Java 版启动器。

NeoCatCraftLauncher 将 Minecraft 版本安装、模组加载器、多实例、玩家账户、Java 运行时、模组与整合包下载集中在同一个桌面界面中，并通过本地 FastAPI 边车（sidecar）调用 `minecraft-launcher-lib` 完成游戏安装与启动。

当前版本：`0.2.2`

## 功能特色

### 多实例与游戏启动

- 创建多个相互隔离的 Minecraft 实例。
- 支持原版、Fabric、Forge、Quilt 和 NeoForge。
- 每个实例可单独配置内存、Java、JVM 参数、分辨率、图标和备注。
- 支持复制实例、修复游戏文件和打开实例目录。
- 展示最近游玩时间、已安装模组数量、Java 状态和运行状态。
- 支持停止当前启动器拉起的游戏进程。

### 版本与加载器

- 获取 Mojang 版本清单。
- 按正式版、快照版、愚人节版和远古版本分类。
- 自动安装对应 Minecraft 版本。
- 枚举并安装 Fabric、Forge、Quilt、NeoForge。
- 支持导入本地加载器安装器 `.jar`。

### 账户登录

- Microsoft OAuth 设备代码登录。
- 离线账户登录。
- 支持第三方 Yggdrasil/LittleSkin 风格的认证服务。
- 支持统一认证（Unified Auth）配置。
- 支持正版皮肤与披风预览。

### Java 运行时

- 根据 Minecraft 版本自动匹配所需 Java 主版本。
- 下载和管理 Azul Zulu JDK。
- 自动检测系统 Java 与 Minecraft 内置 Java。
- 下载过程包含大小检查、SHA-256 校验和解压进度。
- Java 下载采用整体安装进度，避免 ZIP 下载完成后长时间停在 100%。

### 模组与内容

- 扫描实例 `mods` 目录并解析 JAR 元数据。
- 识别 Fabric、Quilt、Forge 和 NeoForge 模组。
- 搜索、筛选和下载 Modrinth / CurseForge 项目。
- 显示必需前置依赖的安装状态。
- 管理资源包、光影包和数据包。
- 支持下载、启用、停用和删除本地内容。

### 整合包

- 搜索并安装 Modrinth `.mrpack` 整合包。
- 支持 CurseForge 整合包。
- 导入本地 `.mrpack`、`.zip` 整合包。
- 自动安装整合包所需的 Minecraft 与加载器环境。
- 在后台下载缺失的模组和配置文件。

### 下载与界面

- 支持官方下载源和 BMCLAPI 国内镜像。
- 镜像请求失败时自动回退到官方源。
- 后台任务统一展示下载、安装和错误状态。
- 使用 SSE 实时同步任务与游戏状态。
- 支持浅色、深色和跟随系统模式。
- 提供天空蓝、草方块绿、暖阳橙、紫水晶和樱花粉五种主题色。
- 支持窗口关闭动画和系统“减少动态效果”设置。

## 技术架构

```text
┌──────────────────────────────────────────────┐
│ Electron                                     │
│  主进程：窗口、IPC、本地后端生命周期          │
│  渲染进程：Vue 3 + Vite                      │
└───────────────────┬──────────────────────────┘
                    │ HTTP / SSE
┌───────────────────▼──────────────────────────┐
│ FastAPI 本地后端（默认 127.0.0.1:47821）      │
│  实例、版本、账户、Java、模组、整合包、任务调度 │
└───────────────────┬──────────────────────────┘
                    │
      ┌─────────────┼──────────────┬──────────────┐
      ▼             ▼              ▼              ▼
 Mojang        Modrinth       CurseForge     Azul Zulu
 minecraft-launcher-lib 负责游戏安装、构建启动命令和管理游戏进程。
```

## 系统要求

开发和打包流程主要面向 Windows 10/11 x64：

- Node.js `^20.19.0` 或 `>=22.12.0`
- npm
- PowerShell 5.1 或更高版本
- 能够访问 npm、PyPI、Mojang 和相关下载源
- 首次启动游戏前需要对应主版本的 Java

Python 不需要提前安装。`npm run setup` 会下载项目专用的便携式 Python 3.12 环境。

## 快速开始

进入项目目录后执行：

```powershell
# 1. 安装前端和 Electron 依赖
npm install

# 2. 准备便携式 Python 与后端依赖
npm run setup

# 3. 构建前端并启动 Electron
npm start
```

Electron 启动时会自动寻找可用端口，并拉起 Python 后端。默认后端地址为：

```text
http://127.0.0.1:47821
```

如果端口已被占用，启动器会自动尝试后续端口。

## 常用命令

| 命令 | 说明 |
| --- | --- |
| `npm start` | 构建前端并启动完整启动器 |
| `npm run dev` | 以开发参数启动 Electron |
| `npm run frontend:dev` | 启动 Vite 开发服务器 |
| `npm run frontend:build` | 构建 Vue 前端到 `frontend/dist` |
| `npm run backend` | 单独启动 FastAPI 后端 |
| `npm run backend:test` | 运行后端单元测试 |
| `npm run dist` | 构建 Windows 分发目录和 NSIS 安装包 |

只调试后端时：

```powershell
npm run backend
```

然后访问：

- API 文档：<http://127.0.0.1:47821/docs>
- 健康检查：<http://127.0.0.1:47821/api/health>

## 目录结构

```text
Neocatcraftlaucher/
├── electron/
│   ├── main.js                 # Electron 主进程、后端进程管理与 IPC
│   └── preload.js              # contextBridge 安全接口
├── frontend-vue/
│   ├── src/App.vue             # Vue 应用外壳
│   ├── src/components/         # 对话框、任务栏、账户与实例组件
│   ├── src/views/              # 实例、下载、Java、设置页面
│   ├── src/composables/        # REST、SSE 与全局状态
│   └── vite.config.mjs         # Vite 配置
├── frontend/dist/              # 前端构建产物
├── backend/
│   ├── main.py                 # FastAPI 路由与应用入口
│   ├── requirements.txt        # Python 依赖
│   ├── neo/
│   │   ├── config.py           # 设置、账户和目录管理
│   │   ├── instances.py        # 多实例持久化
│   │   ├── launcher.py         # 游戏和加载器安装、启动
│   │   ├── java_manager.py     # Java 检测与 Zulu 下载
│   │   ├── auth.py             # 账户与认证服务
│   │   ├── content.py          # 资源包、光影与数据包
│   │   ├── modpacks.py         # 整合包安装
│   │   ├── mirror.py           # BMCLAPI 下载镜像
│   │   ├── tasks.py            # 后台任务状态
│   │   ├── events.py           # SSE 事件总线
│   │   └── mods/               # 模组扫描、搜索与下载
│   └── tests/                  # 后端测试
├── scripts/
│   ├── setup-backend.ps1       # 准备便携式 Python 和后端依赖
│   ├── run-backend.ps1         # 单独启动后端
│   ├── build-windows.ps1       # Windows 打包脚本
│   └── installer.nsi           # NSIS 安装器模板
├── .runtime/                   # 脚本生成的便携式 Python，不提交到仓库
├── build/                      # 打包时生成的图标和安装器脚本
├── dist/                       # 打包后的便携目录
└── release/                    # 最终安装包
```

## 数据目录

默认配置目录：

```text
%APPDATA%\NeoCatCraftLauncher
```

其中可能包含：

| 路径 | 内容 |
| --- | --- |
| `settings.json` | 启动器设置 |
| `accounts.json` | 本地玩家账户数据 |
| `instances.json` | 实例列表与实例配置 |
| `javas/` | 启动器管理的 Java 运行时 |
| `loader-installers/` | 缓存的加载器安装器 |

Minecraft 默认目录由 `minecraft-launcher-lib` 决定，通常为：

```text
%APPDATA%\.minecraft
```

隔离实例默认位于：

```text
%APPDATA%\.minecraft\instances\<实例 ID>
```

可以在设置页修改 Minecraft 目录、Java 目录和全局 Java 路径。

> `accounts.json` 可能包含登录凭据。请勿将配置目录或该文件上传到公共仓库。

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `NEO_PYTHON` | 指定 Electron 后端使用的 Python 解释器 |
| `NEO_PORT` | 指定后端端口，默认 `47821` |
| `NEO_CONFIG_DIR` | 覆盖启动器配置目录 |
| `NEO_MS_CLIENT_ID` | Microsoft OAuth 应用 Client ID |
| `NEO_CURSEFORGE_API_KEY` | CurseForge API Key |
| `NEO_LOG_LEVEL` | 后端日志级别，默认 `warning` |
| `NEO_SERVE_FRONTEND` | 设置后由 FastAPI 直接托管构建后的前端 |

示例：

```powershell
$env:NEO_PORT = "47822"
$env:NEO_CURSEFORGE_API_KEY = "你的 API Key"
npm start
```

## 下载镜像

在设置页将 Minecraft 下载源切换为 **BMCLAPI 镜像**后，以下地址会优先使用镜像：

- Mojang 版本清单与版本 JSON
- Minecraft 资源索引和资源文件
- Minecraft 库文件
- Fabric、Forge、Quilt、NeoForge 的可镜像文件

镜像请求发生连接错误、限流或服务端错误时，会自动回退到官方源。

Modrinth 和 CurseForge 项目文件仍从其官方 CDN 下载，不经过 BMCLAPI。

## 后端接口概览

### 基础与应用

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查与目录信息 |
| GET | `/api/app/bootstrap` | 启动器初始数据 |
| GET/PUT | `/api/settings` | 读取或更新设置 |
| GET | `/api/tasks` | 当前后台任务 |
| GET | `/api/events` | SSE 事件流 |

### 实例与游戏

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/instances` | 列出或创建实例 |
| GET/PATCH/DELETE | `/api/instances/{id}` | 读取、修改或删除实例 |
| POST | `/api/instances/{id}/duplicate` | 复制实例 |
| POST | `/api/instances/{id}/repair` | 修复实例 |
| GET | `/api/instances/{id}/saves` | 列表存档 |
| GET | `/api/instances/{id}/logs` | 列表日志 |
| POST | `/api/launch` | 启动游戏 |
| POST | `/api/launch/stop` | 停止游戏 |

### 版本与 Java

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/versions` | 可用与已安装版本 |
| POST | `/api/versions/install` | 安装 Minecraft 版本 |
| GET | `/api/loaders` | 支持的模组加载器 |
| GET | `/api/loaders/{loader}/versions` | 加载器版本列表 |
| POST | `/api/loaders/install` | 安装加载器 |
| GET | `/api/java` | Java 运行时列表 |
| POST | `/api/java/install` | 下载并安装 Zulu Java |
| GET | `/api/java/resolve` | 按游戏版本解析 Java |

### 账户、模组与整合包

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/auth/accounts` | 账户列表 |
| POST | `/api/auth/microsoft/device/start` | 开始 Microsoft 设备登录 |
| POST | `/api/auth/microsoft/device/poll` | 查询 Microsoft 登录状态 |
| POST | `/api/auth/offline` | 离线登录 |
| GET | `/api/mods` | 扫描本地模组 |
| GET | `/api/mods/search` | 搜索模组 |
| POST | `/api/mods/install` | 安装模组 |
| GET | `/api/content/search` | 搜索资源包、光影或数据包 |
| POST | `/api/content/install` | 安装内容 |
| GET | `/api/modpacks/search` | 搜索整合包 |
| POST | `/api/modpacks/install` | 安装整合包 |
| POST | `/api/modpacks/import` | 导入本地整合包 |

完整接口与请求结构可在 FastAPI 的 `/docs` 页面查看。

## 核心实现说明

### 进程与通信

- Electron 主进程负责端口探测、窗口管理、打开外部链接和后端进程生命周期。
- `preload.js` 通过 `contextBridge` 暴露有限的桌面能力，不直接向页面开放 Node.js。
- Vue 前端通过 HTTP 调用本地 FastAPI 接口，通过 SSE 接收任务、日志和游戏状态。

### 多实例

- 实例元数据保存在 `instances.json`。
- 隔离实例拥有独立的 `mods`、`saves`、`resourcepacks`、`shaderpacks`、`config` 和 `logs` 目录。
- 每个实例可以覆盖全局内存、Java、JVM 参数和分辨率配置。

### 模组解析

启动器按以下文件识别模组元数据：

| 元数据文件 | 加载器 |
| --- | --- |
| `fabric.mod.json` | Fabric / Quilt |
| `META-INF/neoforge.mods.toml` | NeoForge |
| `META-INF/mods.toml` | Forge |
| `mcmod.info` | 旧版 Forge |

损坏或无法识别的 JAR 不会中断整份模组列表。

### Java 安装

Java 安装任务使用整体进度：

1. `0%–85%`：下载 ZIP。
2. `85%–90%`：检查大小并校验 SHA-256。
3. `90%–99%`：逐个文件解压 JDK。
4. `100%`：验证 `java.exe` 并完成安装。

下载、校验、解压或临时目录清理失败时，后台任务会进入错误状态并显示原因。

## 打包 Windows 应用

```powershell
npm run dist
```

构建完成后：

- 便携目录：`dist/NeoCatCraftLauncher-win32-x64`
- 安装包：`release/NeoCatCraftLauncher-Setup-0.2.2-x64.exe`

打包脚本会复制 Electron、前端构建产物、后端和便携式 Python，并调用本地 NSIS 工具生成安装包。

## 测试

运行全部后端测试：

```powershell
npm run backend:test
```

仅运行 Java 下载与安装测试：

```powershell
.runtime\python\python.exe -m unittest discover -s backend\tests -t backend -p test_java_manager.py -v
```

当前测试覆盖实例与整合包安装、加载器 JAR 解析、皮肤缓存、Java 下载校验与解压等逻辑。

## 常见问题

### 启动器显示“等待本地服务”

1. 确认 `.runtime\python\python.exe` 存在。
2. 重新执行 `npm run setup`。
3. 检查端口是否被占用，或设置 `NEO_PORT`。
4. 运行 `npm run backend` 查看后端错误日志。

### Java 下载较长或进度停止

- 下载阶段最高显示 `85%`，剩余进度用于校验和解压，这是正常现象。
- 进度消息会显示已下载大小、SHA-256 校验和解压文件数量。
- 如果长时间没有变化，请检查网络、代理和磁盘剩余空间。
- 安装完成后，受管运行时位于配置目录的 `javas` 子目录。

### CurseForge 无法搜索或下载

- 在设置页填写 CurseForge API Key，或设置 `NEO_CURSEFORGE_API_KEY`。
- 未配置 Key 时，Modrinth 功能仍可正常使用。

### Microsoft 登录失败

- 在设置页填写有效的 Microsoft OAuth Client ID，或设置 `NEO_MS_CLIENT_ID`。
- 确认应用的公开客户端配置允许本地回调。
- 无法完成微软登录时，可以临时使用离线账户。

### 游戏提示 Java 版本不匹配

常见对应关系：

| Minecraft 版本 | Java |
| --- | --- |
| 1.17–1.20.4 | Java 17 |
| 1.20.5 及更高版本 | Java 21 |
| 较旧的 1.16 及以下版本 | Java 8 |

实际要求仍以对应 Minecraft 版本 JSON 和模组加载器说明为准。

### 下载镜像不可用

在设置页切回 Mojang 官方源，或检查 BMCLAPI 地址。启动器会在镜像请求失败时自动尝试官方源。

## 开发注意事项

- Electron 渲染进程不能直接访问 Node.js；新增桌面能力应通过 `preload.js` 暴露。
- 后端任务应通过 `TaskManager` 更新状态，避免长时间阻塞 HTTP 请求。
- 下载文件应先写临时文件，校验完成后再原子重命名。
- 修改前端后需要重新执行 `npm run frontend:build`，Electron 加载的是 `frontend/dist`。
- 修改后端后需要重启启动器，使 Python 边车重新加载代码。

## 许可证

`package.json` 中声明的项目许可证为 MIT。
