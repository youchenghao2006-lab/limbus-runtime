# Third-party components / 第三方组件

`LICENSE` applies to the original launcher source, scripts, tests and documentation in this source release. It does **not** relicense downloaded runtimes, libraries, Steam, Limbus Company, their assets, names or trademarks.

| Component | Source / provenance | Relationship to this project |
| --- | --- | --- |
| Sikarugir Wine engine | [Engines](https://github.com/Sikarugir-App/Engines/releases/tag/v1.0), `WS12WineSikarugir11.0_1.tar.xz` | External runtime, downloaded only by explicit local setup |
| Sikarugir wrapper template | [Template](https://github.com/Sikarugir-App/Template/releases/tag/v1.0), `Template-1.0.21.tar.xz` | External bundle containing multiple components with separate notices |
| Wine | [Wine license information](https://www.winehq.org/license) | Upstream Wine licensing does not establish the license of every bundled component |
| DXMT | [DXMT upstream](https://github.com/3Shain/dxmt) | Used by Steam's graphics path through the external template |
| Apple D3DMetal | License distributed with the template at `Contents/Frameworks/renderer/d3dmetal/License.rtf` | Separately licensed Apple component used by the game graphics path; not covered by this project's MIT license |
| GStreamer and other template libraries | Notices distributed within the upstream engine/template | Runtime dependencies; preserve their bundled notices |
| Steam | [Valve installer](https://cdn.akamai.steamstatic.com/client/installer/SteamSetup.exe), [Steam Subscriber Agreement](https://store.steampowered.com/subscriber_agreement/) | Proprietary external client; user signs in directly |
| Limbus Company | [Steam store page](https://store.steampowered.com/app/1973530/Limbus_Company/) | Separate game acquired through Steam; no game assets or binaries in this repository |

## Download provenance

The engine and template names, byte sizes and SHA-256 values are pinned in `runtime-sources.json`. The values match the upstream release metadata retained with the original prototype. Hash checking ensures downloaded bytes match those pins; it is not a review of every embedded component or its permissions. Upstream release assets can become unavailable, in which case setup should fail rather than silently select another version.

The Steam installer URL is mutable and has no pinned hash. It is an explicit optional HTTPS download and is not executed by the preparation script. Do not describe its integrity as equivalent to the pinned archives.

## Publication boundary

This release contains only launcher source. Initialization preserves upstream license files and places all external binaries outside the source tree by default. The setup consent flag records the user's deliberate choice to use external components; it does not replace the upstream agreements or establish redistribution permission.

No permission to redistribute the entire engine/template bundle, D3DMetal, Steam or game content is asserted here. A future bundled binary distribution requires component-by-component review, preservation of notices, and any applicable corresponding-source or other obligations. Do not mirror those archives or include an initialized prefix as a project release.

中文说明：项目自身采用 MIT，不意味着依赖组件也都采用 MIT，或都可以打包分发。当前交付范围限定为启动器源码。用户自行获取并按各组件许可使用依赖；完整运行环境不能直接作为本项目的 MIT 产物发布。
