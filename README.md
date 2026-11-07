# Limbus Runtime

[English](README.en.md) · **0.2.0 / 实验版** · 项目源码采用 [MIT](LICENSE)

面向 Apple Silicon Mac 的非官方《Limbus Company》启动器。SwiftUI 界面负责本机状态和启动操作，Python 后端管理独立的 Wine 环境，Steam 负责账号登录、游戏下载及更新。

这是启动器的源码项目，不是游戏源码，也不是完整开源的 Wine/图形运行时发行版。源码发布包不包含游戏资源、Steam 客户端、Wine、D3DMetal、账号资料或作者的本地运行环境。第三方组件按各自许可单独获取，见 [第三方说明](THIRD_PARTY_NOTICES.md)。

## 项目状态

开源不代表功能已完成。本项目以可阅读、可构建、可测试的实验版源码发布。

| 范围 | 状态 |
| --- | --- |
| 后端、初始化和源码打包 | 有离线自动化测试 |
| macOS 原生界面 | 支持从源码构建；构建不下载运行时 |
| Wine/模板初始化 | 已提供下载校验、独立目录和初始化流程；新机器完整安装仍需实测 |
| 游戏图形兼容性 | 原型曾在一台 M2 Mac 上确认启动及画面显示；不代表此版本在所有机器验证通过 |
| 战斗、长时间运行、后续 Steam/游戏更新 | 未完成验证 |
| Intel Mac、Windows、Linux 上运行游戏 | 不支持；部分离线测试可在 Linux 运行 |

这是社区项目，与 Project Moon、Valve、Apple 或 Sikarugir 没有官方隶属关系。名称仅用于说明兼容目标。

## 环境要求

- Apple Silicon Mac，macOS 14.6 或更高版本。
- Apple Command Line Tools 或 Xcode，提供 `swiftc` 和 `/usr/bin/python3`；Python 3.9 或更高。图形应用当前固定调用 `/usr/bin/python3`，仅安装 Homebrew Python 不足以替代它。
- Rosetta 2，用于 Windows x86-64 运行组件。请通过 macOS 官方提示安装并自行阅读适用许可。
- 初始化时需要联网访问上游 GitHub Release 和 Valve CDN；游戏由 Steam 下载。
- 预留足够的运行环境和游戏下载空间；实际占用随游戏更新而变化。

## 先检查、测试和构建

在解压后的项目目录中运行：

```sh
python3 -m unittest discover -s tests -v
python3 scripts/source_release.py --check
python3 scripts/prepare_runtime.py --check
python3 scripts/build.py
```

`--check` 只检查环境和已有安装包，不下载或启动 Wine。新机器显示缓存或运行环境缺失是预期结果。构建产物为 `dist/Limbus Runtime.app`，可以移动到“应用程序”目录，运行数据不会绑定源码目录。

构建产物使用本地临时签名，没有 Developer ID 签名或 Apple 公证。公开提供预编译应用需要单独处理签名、公证和相应依赖许可；本项目默认发布源码压缩包。

## 首次准备运行环境

先阅读 [第三方说明](THIRD_PARTY_NOTICES.md) 和相应上游许可。如果你同意这些组件适用的许可，再运行：

```sh
python3 scripts/prepare_runtime.py --download --accept-third-party-licenses --steam-installer
```

该命令下载固定版本的 Wine 引擎及模板，校验文件大小和 SHA-256，在独立目录中组装并初始化 Wine。Steam 安装包来自 Valve 官方 HTTPS 地址，其地址内容会更新，没有固定摘要；它不会被此步骤自动执行。

离线准备：将与 `runtime-sources.json` 匹配的两个归档放入数据目录的 `.cache`，然后运行 `python3 scripts/prepare_runtime.py --download --accept-third-party-licenses`。已缓存且验证通过的归档会跳过下载。离线时不加 `--steam-installer`；可自行从官方来源准备 `SteamSetup.exe` 并放入同一缓存目录。具体选项见 `--help`。

默认数据目录：

```text
~/Library/Application Support/Limbus Runtime/
├── .cache/                 下载的组件
├── runtime/LimbusRuntime.app/
│   └── Contents/SharedSupport/prefix/   Steam、游戏及账号数据
└── logs/                   本机运行日志
```

准备完成后打开 `Limbus Runtime.app`：

1. 点击“安装 Steam”，等待安装完成。
2. 点击“打开 Steam”，在 Steam 自己的窗口中登录。
3. 点击“安装游戏”，在 Steam 中完成安装。
4. 点击“启动游戏”。如果先打开了 Steam，等待登录和更新完成后再点击一次。

运行时默认让 Steam 使用 DXMT、游戏使用 D3DMetal。D3DMetal 是单独许可的组件，本项目的 MIT 许可证不授予它的使用或再分发权利。我们没有把 DXMT 单独渲染游戏标为功能等价的替代方案。

## 自定义目录及命令行

可以设置 `LIMBUS_RUNTIME_HOME`，或向后端/准备脚本传入 `--root`。两种方式都会将全部运行数据定向到所选目录；命令行 `--root` 优先。

```sh
export LIMBUS_RUNTIME_HOME="$HOME/Library/Application Support/Limbus Runtime"
python3 scripts/backend.py status
python3 scripts/backend.py install-steam
python3 scripts/backend.py open-steam
python3 scripts/backend.py install-game
python3 scripts/backend.py launch-game
```

终端的环境变量通常不会传给 Finder 双击启动的应用。使用自定义路径时，通过同一终端直接运行构建出的程序：

```sh
"dist/Limbus Runtime.app/Contents/MacOS/LimbusLauncher"
```

“修复环境”刷新 Wine 系统组件；“停止环境”会终止这个独立环境中的 Steam 和游戏。操作前保存进度。初始化脚本不会替换已有的完整运行环境；遇到不完整安装时按照错误提示处理，先备份已有数据，避免删除可能包含游戏或存档的目录。

## 隐私与已有安装

启动器不要求输入 Steam 密码，不提供遥测或自动日志上传。Steam 和游戏自身的联网、账号数据及隐私政策由相应厂商管理。提交问题前检查日志，移除用户名、路径、Steam ID 等信息。

旧个人原型的 `runtime/`、缓存、日志和安装标记不属于此仓库。此版本不会自动导入旧 Steam 登录资料或搬动原型游戏。可通过 `--root` 显式选择一个已有的兼容数据根目录，但旧环境升级和回滚需要用户自行验证。本仓库没有包含原型中硬编码路径、会移动游戏下载文件的复用脚本。

## 创建源码发布包

```sh
python3 scripts/source_release.py --check
python3 scripts/source_release.py
```

输出是 `dist/limbus-runtime-0.2.0-source.zip` 及校验文件。工具只收录 `release-files.json` 列出的源码、测试和文档，检查路径及明显的敏感内容，并拒绝将额外的已跟踪文件混入发布。新增公共文件时同时更新清单。检查器只能识别部分泄露模式，提交者仍需审阅变更。

不要将自己的数据目录、整个个人原型文件夹或已装好游戏的应用打包上传。`.gitignore` 只是辅助；发布使用明确的文件清单。

## 参与开发

参见 [贡献指南](CONTRIBUTING.md)、[安全说明](SECURITY.md) 和 [更新记录](CHANGELOG.md)。GitHub Actions 配置会运行离线测试、发布检查和 macOS 编译，不登录 Steam、不下载游戏，也不自动发布。
