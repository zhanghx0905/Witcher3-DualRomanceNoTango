# 安装与开发

## 适用环境

目标游戏为包含 Blood and Wine 的 Remastered 安装，Steam build 25773555，资源格式为 CR2W 164 / bundle 5 / metadata 7。兼容信息见 `release/metadata/compatibility.json`，源码要求的输入指纹见 `src/supported-sources.json`。

离线检查覆盖资源结构、任务分支、布景坐标和镜头投影。双恋爱欢迎读取与后续日常流程已获用户实测确认；具体范围和已知问题见下方实机记录。

## 安装、更新与回退

预构建文件在 `release/payload/Mods/modDualRomanceNoTango`。保存并退出游戏后，在仓库根目录执行：

```powershell
# 首次安装；替换为自己的游戏路径。
& .\scripts\Install-DualRomance.ps1 -GamePath 'C:\Games\The Witcher 3' -Action Install
# 从安装器支持的前版更新。
& .\scripts\Install-DualRomance.ps1 -GamePath 'C:\Games\The Witcher 3' -Action Update
# 仅核对安装文件。
& .\scripts\Install-DualRomance.ps1 -GamePath 'C:\Games\The Witcher 3' -Action Verify
```

安装器核对游戏构建和文件哈希，支持的前版记录在 `release/metadata/previous-version.json`；更新前备份到游戏目录下的 `ModBackups/DualRomanceNoTango/时间戳/content`；遇到未知改动会停止。回退时退出游戏，将对应备份的 `content` 目录恢复到 `Mods/modDualRomanceNoTango/content`。`-Action Disable` / `Enable` 可停用或启用模组。

重测酒馆开场需要读取开场之前的存档并重新经过女皇结局转场；已经站在酒馆外的存档不会重播。仓库不包含个人存档。

## 构建与检查

需要 PowerShell 5.1+、Python 3.10+，以及包含 Blood and Wine 的目标游戏。Python 只使用标准库。

```powershell
# 不需要游戏：检查预构建文件、资源结构、源码指纹与许可证。
python .\scripts\check_release.py
# 需要游戏：重建、运行资源检查与配置审计、生成发行 ZIP。
& .\scripts\Build.ps1 -GamePath 'C:\Games\The Witcher 3'
# 需要游戏：只重跑资源与逻辑检查。
& .\scripts\Test.ps1 -GamePath 'C:\Games\The Witcher 3'
```

构建输出和报告位于 Git 忽略的 `build/`，不安装模组或启动游戏。CI 只核对已有发布文件，不执行实机测试。

## 维护约束

Python 只使用标准库。补丁输入必须匹配 `src/supported-sources.json`；游戏升级后先检查资源格式、任务图和原生坐标，再建立新指纹，不要删除校验来跳过不兼容问题。

## 代码入口

- `redio.py`：CR2W、bundle、metadata 读取与打包，保留原生格式及校验。
- `build.py`：18 项资源输出与任务分支修改，派生资源通过 `source_path` 记录原生模板。
- `manor_layout.py`：庄园独立动作点、家具、触发区和到客房的路径。
- `manor_dual.py`：双恋爱专用图层、社区阶段、原版路线别名和旧存档迁移入口。
- `tavern_layout.py`：女皇结局双恋爱专用社区阶段、动作点、对话布景和三人全景。
- `verify.py`：38 项结构与逻辑检查；`audit_coexistence.py`：5 项庄园配置审计。

## 庄园分支隔离

双恋爱常驻使用隐藏的 `quests\main_quests\q705_epilog\dual_manor` 图层组，包含独立的动作点、对话锚点、触发区和家具。两段欢迎始终使用原版图层和 `q705_house` 角色生成阶段。第二段欢迎输出后立即加载双人专用图层，并为两人激活 `dr_q705_house` 休息阶段，填补欢迎后的空档。玩家离开特莉丝 60 米后，再按原流程启用 `dr_q705_cycle` 昼夜日常。旧存档迁移只有在两人的恋爱事实及欢迎完成事实都满足时才启用双人布局，其余情况沿用原版图层。

两人的原生社区阶段与时间表保留。专用的 `dr_q705_house` 仅在两段欢迎结束后供双人休息使用，`dr_q705_cycle` 用于之后的双人昼夜日常；欢迎场景本身不选择专用阶段。特莉丝的原生昼夜脚本和路径参数保持原样；对应标签在原版图层中指向原路线，在双恋爱图层中指向独立躺椅与客房。叶奈法使用与原路线、触发区几何一致的别名，避免两人共用标签指向不同位置。

单恋爱图层只追加不可见的路径和触发区别名，保留原有实体数据。原版对话锚点和花园家具文件不再被覆盖。专用图层中的实体使用独立 GUID，避免与已保存的原版实体混淆。

原版庄园图层修复任务可能已经在存档里结束。迁移入口使用 `bob_bugfix_phase` 的原生 deletion marker 机制接续其末端等待节点，为旧存档启动新的布景选择流程；入口事实为 `dr_manor_layout_split_v3`。后续升级该入口时，需要保留对旧等待节点 GUID 的迁移关系。

新图层需要覆盖 `bob.w2w` 的图层登记；同时覆盖该文件的其他模组需要合并。离线检查核对登记、父子引用和默认隐藏状态。双恋爱后续日常流程已获实测确认；不同剧情进度的旧档迁移仍需单独验证。

## 实机验证与已知问题

2026-10-18，用户在 `0.1.7-experimental` 中实测确认：双恋爱欢迎流程正常读取，后续日常流程正常。

`0.1.7` 的欢迎后过渡阶段存在叶奈法被特莉丝顶替、两套躺椅未同时显示的问题。`0.1.8` 增加欢迎结束后的双人休息衔接，并接续前两版迁移入口。2026-10-18，用户实机复测后接受该修正，此问题已关闭。

本次反馈不代表其他分支及场景均已完成验收。单恋爱、无恋爱、旧档迁移、日夜切换、跨地图重载与全部镜头仍需分别确认。自动生成报告中的 `runtime_validated: false` 表示离线检查不能代替完整实机验收，不能据此否定上述已确认结果。

## 酒馆修改约束

双恋爱使用 `dr_q504_triss_at_shared_table` 社区阶段和 `dr_dual_lovers` 场景入口。Triss 使用原有第三张凳子，世界坐标约为 `(48.7470, -2.1617, 2.2830)`，朝向 305°。动作点与对话布景分别按各自原生坐姿偏移校准；原有凳子、单恋爱入口与时间表保持原样。

复制场景时必须同时处理普通属性与缓冲时间线。台词、事件信息和变体可能挂在场景根节点，不能只沿 section 的 parent 复制。事件 GUID、eventInfo、sceneElement、插值引用和 elementID 必须一致重映射，并保留原生语音 ID。

三人全景的场景局部位置为 `(3.3, 3.1, 1.4)`，pitch -6°、yaw 188°、FOV 50。检查使用 16:9 上半身包围盒投影；实际 FOV 解释、遮挡、坐姿及镜头衔接必须进游戏确认。

## 修改与发布

`Build.ps1` 创建独立输出目录，依次构建、验证、审计和打包，并要求结果与当前预构建文件哈希一致。仅修改文档或工具时不要改动游戏二进制基准。

修改补丁并准备新版本时，同步 `project.json`、`src/build.py` 的版本，以及 `release/metadata/` 的当前清单、兼容性和前版哈希；经审阅后更新 `release/payload/`。版本升级应记录在 CHANGELOG，保持预构建核对与完整构建通过。

生成的报告、ZIP、depot、个人存档与临时研究文件不纳入 Git。提交前运行 `git diff --check` 和与修改相关的检查。保留源代码与发行包的版权声明、LICENSE、NOTICE 和第三方声明。

实机验收应包括双恋爱、单 Triss、单 Yen、无恋爱四种入口，酒馆三人坐姿及镜头、离开演出后的衔接，以及庄园常驻、日夜切换、对话、跨地图与重载。当前版本仍未完成这些场景的全面实机验收。

常驻恢复必须等待对应欢迎事实达到 1：特莉丝为 `q705_triss_house_met`，叶奈法为 `q705_yen_first_met`；双恋爱需两者都完成。`q705_completed` 只代表前面的血与酒结局已完成，不能据此提前启动常驻活动。迁移标记同时接续原版及前两版修复入口的末端等待 GUID。
