# 开发与版本维护

只从自己的目标游戏安装读取资源。补丁输入必须匹配 `src/supported-sources.json`，不要为了通过构建而直接删除哈希校验。游戏更新后先重新评估资源布局及任务图，再建立新基准。

`src/build.py` 生成 12 个改动后的资源及 bundle/metadata；`src/manor_layout.py` 处理空间布局；`src/verify.py` 执行游戏相关检查；`src/audit_coexistence.py` 检查常驻与对话配置。Python 无外部运行依赖。

`scripts/Build.ps1` 按唯一输出目录构建，执行检查后，用 `scripts/package_release.py` 对照本版本基准哈希并打包。构建文件不应替换 `release/payload/`，除非在制作一个已审阅的新版本；基准不一致会报错。

版本升级时同步 `project.json`、`src/build.py`、兼容性/前版数据、发布说明和验收报告；不要把新版本包装为 0.1.4。二进制为本版本的小型发布内容，已纳入 Git；完整游戏、depot、存档和本地临时文件必须保持在忽略目录中。

## Git 起步

```powershell
git status
git add .
git commit -m 'Prepare 0.1.4 experimental source and release'
# 用自己的真实仓库地址添加 remote，再推送。
```

不要把用户名、账号邮箱、Steam 凭据、发布 token 或本地存档写进版本库。
