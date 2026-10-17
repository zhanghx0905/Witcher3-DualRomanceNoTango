# 创意工坊发布准备

此仓库已完成源码和手动发布内容整理，**尚未上传 Steam Workshop**。

## 已备材料

- `workshop/item.json`：标题、版本、作者及目标应用信息草案。
- `workshop/description.zh-CN.bbcode` 和英文说明：可复制到工坊页面。
- `workshop/preview.png`：原创文字封面；可替换为自己拍摄的实际游戏截图。
- `release/payload/Mods/modDualRomanceNoTango`：已校验的 0.1.4 cooked bundle 和索引。
- `LICENSE`、`NOTICE.md`、`THIRD_PARTY.md`、`licenses/`：随发布保留的署名与许可。

## 官方发布流程与本仓库的边界

CDPR 的 [Publishing mods](https://cdprojektred.atlassian.net/wiki/spaces/W3REDkit/pages/6328254/Publishing+mods) 说明：先在 REDkit 中验证项目，再进入 Publish，填写名称、版本、描述和缩略图，完成 cooking，最后选择语言、可见性及 Steam Workshop 发布。

本仓库通过 Python 直接修改已安装游戏的 cooked 资源，**不是已创建的 REDkit 项目**。普通 Git 仓库、手工 ZIP 和 REDkit 的可发布项目不能直接等同。这里没有提供未经验证的 SteamCMD 上传命令，也没有虚构项目文件。

如果后续走官方 REDkit 流程，需要在已初始化且兼容当前游戏版本的编辑器中建立项目，将相应改动迁移/重新构建并预览、验证，然后使用其实际生成的发布结构。可以用 `scripts/Export-Resources.ps1` 导出此包内 12 个 cooked 资源作对照；导出文件不是完成 uncook 的 depot，不能当作可直接打开的项目承诺。

当前未安装 REDkit。此限制不影响手动安装包的构建，但 **Workshop 导入、cooking 与上传尚未验证**。首次验证可以选择非公开可见性，成功订阅加载、测试并补齐兼容性说明后再公开。

## 说明和署名

发布标题保留实验版标识，兼容性写清 Steam build 25773555、Blood and Wine、已知资源冲突和存档条件。不要把离线通过写成全部实机通过。

作者：**Hexiao Zhang**。源码/工具采用 BSD-3-Clause；源码和二进制再分发均须保留版权声明、条款及免责声明，且未经许可不能用作者名为衍生产品背书。见 [BSD-3-Clause 原文](https://opensource.org/license/bsd-3-clause)。游戏及第三方内容不由该源码许可证重新授权。

提交到 Git 远端、创建工坊项目和公开发布均由发布者自行执行。本次没有连接远端或建立线上条目。
