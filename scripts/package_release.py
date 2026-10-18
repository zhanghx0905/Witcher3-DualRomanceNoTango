#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
"""Package the current reproducible release with its attribution and sources."""
from pathlib import Path
import argparse,hashlib,json,shutil,sys,zipfile
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
from check_release import check

def package(stage):
    check(ROOT)
    stage=Path(stage).resolve()
    assert ROOT/'build' in stage.parents,'Stage must stay in this repository build directory'
    project=json.loads((ROOT/'project.json').read_text(encoding='utf-8'))
    reference=json.loads((ROOT/'release/metadata/build-manifest.json').read_text(encoding='utf-8'))
    actual=json.loads((stage/'build-manifest.json').read_text(encoding='utf-8'))
    validation=json.loads((stage/'validation.json').read_text(encoding='utf-8'))
    audit=json.loads((stage/'coexistence-audit.json').read_text(encoding='utf-8'))
    assert actual['version']==project['version']==reference['version']
    assert validation['passed'] and validation['tests_run']==37
    assert all(row['passed'] for row in audit['checks']) and len(audit['checks'])==5
    for key in ['bundle_sha256','metadata_sha256']:assert actual[key]==reference[key],f'Non-reproducible {project["version"]}: {key}'
    for name in ['compatibility.json','previous-version.json']:
        shutil.copyfile(ROOT/'release/metadata'/name,stage/name)
    for name in ['LICENSE','NOTICE.md','THIRD_PARTY.md']:
        shutil.copyfile(ROOT/name,stage/name)
    shutil.copytree(ROOT/'licenses',stage/'licenses')
    shutil.copyfile(ROOT/'scripts/Install-DualRomance.ps1',stage/'Install-DualRomance.ps1')
    readme=f'''# Dual Romance / No Tango {project['version']}

作者 Hexiao Zhang。原创工具与文档采用 BSD-3-Clause；游戏资源权利归原权利人。

保存并退出游戏，在本目录执行，替换为自己的游戏路径：

```powershell
& .\\Install-DualRomance.ps1 -GamePath 'C:\\Games\\The Witcher 3' -Action Install
```

从安装器支持的前版更新使用 -Action Update，核对安装使用 -Action Verify。更新前自动备份到游戏目录的 ModBackups/DualRomanceNoTango；回退时退出游戏，将备份 content 恢复到 Mods/modDualRomanceNoTango/content。

双恋爱时，两位伴侣在女皇结局酒馆中同桌出场，在白鸦庄园使用各自的休息位置和床位。单恋爱时，庄园使用原有家具、床位与活动路线。

更新庄园布景后请重新启动游戏，跨地图后返回庄园，让图层和活动安排重新加载。重测酒馆演出需要读取开场前的存档。

37 项离线检查和 5 项庄园配置审计通过。用户实测确认双恋爱欢迎正常读取，后续日常流程正常。两段欢迎使用原版图层和生成阶段，双人布局推迟到欢迎后的常驻阶段启用。

已知问题：欢迎结束后、日常流程触发前，后出场的特莉丝会顶替叶奈法，此时不会显示两个躺椅。该过渡阶段尚未修正。其他分支、旧档迁移和全部镜头仍需分别验收；validation.json 和 coexistence-audit.json 只记录离线检查结果。

src 内包含可重建源码，只需 Python 3.10+ 标准库和目标游戏：

```powershell
python .\\src\\build.py --game 'C:\\Games\\The Witcher 3' --out 'C:\\Temp\\DualRomanceBuild'
python .\\src\\verify.py --game 'C:\\Games\\The Witcher 3' --report 'C:\\Temp\\DualRomanceValidation.json'
```
'''
    (stage/'README-中文.md').write_text(readme,encoding='utf-8')
    shutil.copytree(ROOT/'src',stage/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    # Fixed timestamps make identical inputs produce identical ZIP bytes.
    archive=stage.parent/(stage.name+'.zip')
    assert not archive.exists(),archive
    files=sorted(p for p in stage.rglob('*') if p.is_file())
    sums=''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(stage).as_posix()}\n' for p in files)
    (stage/'SHA256SUMS.txt').write_text(sums,encoding='utf-8');files.append(stage/'SHA256SUMS.txt')
    date=tuple(map(int,project['release_date'].split('-')))+(0,0,0)
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as output:
        for path in sorted(files):
            info=zipfile.ZipInfo(stage.name+'/'+path.relative_to(stage).as_posix(),date)
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
            output.writestr(info,path.read_bytes(),compresslevel=9)
    with zipfile.ZipFile(archive) as output:
        assert output.testzip() is None
        for path in files:assert output.read(stage.name+'/'+path.relative_to(stage).as_posix())==path.read_bytes()
    sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    (archive.parent/(archive.name+'.sha256')).write_text(f'{sha}  {archive.name}\n',encoding='utf-8')
    print(json.dumps(dict(package=str(archive),sha256=sha,reproduces_version=project['version'],runtime_validated=False)))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',required=True,type=Path)
    package(parser.parse_args().stage)
