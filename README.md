# Dual Romance / No Tango

**Hexiao Zhang · 0.1.5-experimental · BSD-3-Clause**

《巫师3：狂猎 — Remastered》双恋爱实验模组：保留 Triss 与 Yennefer 的恋爱状态，绕过“三人探戈”陷阱，调整结局及白鸦庄园的双人常驻流程。

0.1.5 将女皇结局酒馆开场的 Triss 安排到杰洛特、Yen 同桌旁原有的第三张凳子，并为双恋爱分支新增三人全景。保留原生 Yen 台词和其他特写，没有新增 Triss 台词；单恋爱分支使用原生座位和演出。庄园沿用 0.1.4 的独立躺椅、对话区域与客房床位。

目标版本：**Steam build 25773555 / CR2W 164 / bundle 5 / metadata 7**。27 项离线检查和 5 项庄园配置审计通过。酒馆坐姿、遮挡与镜头衔接仍待游戏内验收，离线投影不能代替实机画面。

## 安装、更新与回退

预构建文件在 `release/payload/Mods/modDualRomanceNoTango`。保存并退出游戏后，在仓库根目录执行：

```powershell
# 首次安装；替换为自己的游戏路径。
& .\scripts\Install-DualRomance.ps1 -GamePath 'C:\Games\The Witcher 3' -Action Install
# 从已知 0.1.4 更新。
& .\scripts\Install-DualRomance.ps1 -GamePath 'C:\Games\The Witcher 3' -Action Update
# 仅核对安装文件。
& .\scripts\Install-DualRomance.ps1 -GamePath 'C:\Games\The Witcher 3' -Action Verify
```

安装器核对游戏构建和文件哈希，更新前备份到游戏目录下的 `ModBackups/DualRomanceNoTango/时间戳/content`；遇到未知改动会停止。回退时退出游戏，将对应备份的 `content` 目录恢复到 `Mods/modDualRomanceNoTango/content`。`-Action Disable` / `Enable` 可停用或启用模组。

重测酒馆开场需要读取开场之前的存档并重新经过女皇结局转场；已经站在酒馆外的存档不会重播。仓库不包含个人存档。

## 构建与检查

需要 PowerShell 5.1+、Python 3.10+，以及包含 Blood and Wine 的目标游戏。Python 只使用标准库。

```powershell
# 不需要游戏：检查预构建文件、资源结构、源码指纹与许可证。
python .\scripts\check_release.py
# 需要游戏：重建、运行 27 项检查与 5 项审计、生成发行 ZIP。
& .\scripts\Build.ps1 -GamePath 'C:\Games\The Witcher 3'
# 需要游戏：只重跑资源与逻辑检查。
& .\scripts\Test.ps1 -GamePath 'C:\Games\The Witcher 3'
```

构建输出和报告位于 Git 忽略的 `build/`，不安装模组或启动游戏。CI 只核对已有发布文件，不执行实机测试。

## 文件与维护

- `src/`：资源读写、任务补丁、庄园与酒馆布局、验证。
- `scripts/`：安装、构建、测试和打包。
- `release/`：可安装内容、兼容信息及当前/前版哈希。
- [开发说明](docs/DEVELOPMENT.md)：格式约束、升级步骤与实机验收要点。
- [变更记录](CHANGELOG.md)、[许可证](LICENSE)、[署名范围](NOTICE.md)、[第三方声明](THIRD_PARTY.md)。

原创工具和文档按 BSD-3-Clause 发布，再分发须保留 Hexiao Zhang 的版权声明。游戏资源权利归原权利人。本仓库不是 REDkit 项目，尚未验证或上传创意工坊。
