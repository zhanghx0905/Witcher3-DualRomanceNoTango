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
    assert validation['passed'] and validation['tests_run']==27
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

从 0.1.4 更新使用 -Action Update，核对安装使用 -Action Verify。更新前自动备份到游戏目录的 ModBackups/DualRomanceNoTango；回退时退出游戏，将备份 content 恢复到 Mods/modDualRomanceNoTango/content。

0.1.5 将女皇结局酒馆开场的 Triss 调整到同桌第三张原有凳子，并使用专用三人全景；原生单恋爱分支保持原样。需要读取酒馆开场前的存档重播。

27 项离线检查和 5 项庄园配置审计通过。实际坐姿、遮挡和镜头衔接仍待游戏内验收，报告见 validation.json 和 coexistence-audit.json。

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
