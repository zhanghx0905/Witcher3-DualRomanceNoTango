# Dual Romance / No Tango

**作者：Hexiao Zhang · 0.1.4-experimental · 源码许可：BSD-3-Clause**

《巫师3：狂猎 — Remastered》的双恋爱实验模组：保留 Triss 与 Yennefer 的恋爱状态，绕过“三人探戈”陷阱，并调整结局及白鸦庄园的双人常驻流程。

本仓库是原 0.1.4 的源码与发布整理版，游戏内容没有改版。当前目标为 **Steam build 25773555 / CR2W 164 / bundle 5 / metadata 7**。不支持直接用于 1.32 或 4.04；其他 Remastered 构建需要重新核对输入资源。

## 功能与状态

- 绕过会触发“三人探戈”陷阱的邀请分支，保留正常主线后续。
- 双恋爱结局依次播放 Yen 与 Triss 的结局短片；包含女帝结局酒馆的双角色分支调整。
- 庄园欢迎依次进行，完成后启动两人的常驻活动。
- Triss 使用独立躺椅及配套物件，位于 Yen 西北侧约 4.1 米处；对话锚点、触发区和路径起点同步移动，夜间使用独立客房床位。

**版本仍为实验版。** 23 项离线检查及 5 项共存配置审计通过；这不代表家具、寻路、昼夜和存读档已全部完成实机验收。历史用户反馈与待验证项见 [验证状态](docs/VALIDATION.md)。

## 直接使用已构建版本

`release/payload/Mods/modDualRomanceNoTango` 是原 0.1.4 的预构建内容；两份二进制文件保持原哈希。保存并退出游戏后，可以运行：

```powershell
& .\scripts\Install-DualRomance.ps1 -GamePath 'C:\Games\The Witcher 3' -Action Install
```

已有 0.1.3 使用 `-Action Update`；核对安装使用 `-Action Verify`。安装器会核对已知内容，更新前备份旧文件。完整说明见 [安装与回退](docs/INSTALL.zh-CN.md)。

## 从本机游戏重新构建

需要 Windows PowerShell 5.1+ 或 PowerShell 7、Python 3.10+、已拥有的目标游戏及 Blood and Wine 资源。Python 部分只使用标准库，没有 pip 依赖。

```powershell
& .\scripts\Build.ps1 -GamePath 'C:\Games\The Witcher 3' -PythonExecutable python
```

构建会执行 23 项检查、5 项配置审计，并核对结果是否与 0.1.4 基准二进制一致。产物和 ZIP 写入被 Git 忽略的 `build/`。它不会安装模组或启动游戏。

只核对仓库已有发布内容，不需要游戏：

```powershell
python .\scripts\check_release.py
```

重新检查游戏相关逻辑：

```powershell
& .\scripts\Test.ps1 -GamePath 'C:\Games\The Witcher 3'
```

## 创意工坊发布

已准备标题、说明、署名、封面和上传前说明，见 [发布指南](docs/WORKSHOP.md) 与 `workshop/`。**尚未上传，也不是已经由 REDkit 测试或发布的项目。** 本仓库使用 Python 修改 cooked 资源；没有伪造 `.w3modproj` 或声称可直接导入 REDkit。

官方流程要求在 REDkit 中验证、设置发布信息并 cooking，再选择 Steam Workshop 发布。详见 [CDPR 发布教程](https://cdprojektred.atlassian.net/wiki/spaces/W3REDkit/pages/6328254/Publishing+mods)。本次整理没有安装 REDkit。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `src/` | 资源读取、补丁、布局和验证源码 |
| `scripts/` | 构建、测试、安装、发布完整性核对 |
| `release/payload/` | 保持原哈希的 0.1.4 二进制 |
| `release/metadata/` | 输入/输出哈希、兼容性和前版信息 |
| `reports/v0.1.4/` | 原版本的离线审计与选址证据 |
| `docs/` | 安装、验证、发布和开发说明 |
| `workshop/` | 发布文案、封面、发布信息草案 |

仓库仅包含 0.1.4；存档、个人配置、游戏原始资源库和另行开发的房间演出原型未纳入。

源码和工具的再分发须保留 **Hexiao Zhang** 的版权声明，见 [LICENSE](LICENSE)。游戏资源及第三方权利另见 [NOTICE](NOTICE.md) 和 [THIRD_PARTY](THIRD_PARTY.md)。
