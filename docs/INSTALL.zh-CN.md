# 安装、更新与回退

版本：0.1.4-experimental。需要已核对的 Steam Remastered build 25773555，以及 Blood and Wine 的资源；该模组不会替你补写未达成的恋爱条件。

## 安装

保存并退出游戏。在仓库根目录执行，替换示例游戏目录：

```powershell
& .\scripts\Install-DualRomance.ps1 -GamePath 'C:\Games\The Witcher 3' -Action Install
```

发行 ZIP 中的安装器位于包的根目录，执行 `& .\Install-DualRomance.ps1 -GamePath 'C:\Games\The Witcher 3' -Action Install`。

也可手动把 `release/payload/Mods/modDualRomanceNoTango` 放进游戏的 `Mods`。请保留随包的许可与署名文件。不要同时安装手动副本和相同创意工坊副本。

## 更新、核对和禁用

```powershell
& .\scripts\Install-DualRomance.ps1 -GamePath 'C:\Games\The Witcher 3' -Action Update
& .\scripts\Install-DualRomance.ps1 -GamePath 'C:\Games\The Witcher 3' -Action Verify
& .\scripts\Install-DualRomance.ps1 -GamePath 'C:\Games\The Witcher 3' -Action Disable
```

自动更新只接受包内记录的 0.1.3；若发现未知内容会停止。旧内容备份到游戏 `ModBackups/DualRomanceNoTango/<时间>/content`。禁用不会还原已经写入存档的任务状态；回到原剧情应读取安装前的备份存档。

手动恢复备份时，退出游戏，用对应备份中的 `content` 恢复模组目录，并避免保留第二份同名或同功能模组。

## 存档与复测

- 新流程最好使用会触发女术士邀请之前的独立存档；已执行的任务节点不保证会重跑。
- 庄园欢迎已结束的存档，更新后重启游戏，完整切换另一张地图再返回，使关卡和社区活动重新加载。不用重做欢迎。
- 分别与两人重复对话，检查 Triss 对话后的位置、夜间床位、次日活动以及存读档后的行为。
- 手动模组不一定出现在游戏内 mod.io 已安装列表；应结合文件核对和实际行为判断。

该版本直接覆盖 12 个资源路径。与其他改动这些剧情、角色社区、庄园场景或相同关卡资源的模组可能发生覆盖；仅做脚本合并不能解决所有二进制资源冲突。
