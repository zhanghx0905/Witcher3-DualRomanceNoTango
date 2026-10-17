#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
"""Package an exact 0.1.4 rebuild, including attribution in every payload."""
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
    assert validation['passed'] and validation['tests_run']==23
    assert all(row['passed'] for row in audit['checks']) and len(audit['checks'])==5
    for key in ['bundle_sha256','metadata_sha256']:assert actual[key]==reference[key],f'Non-reproducible 0.1.4: {key}'
    for name in ['compatibility.json','previous-version.json']:
        shutil.copyfile(ROOT/'release/metadata'/name,stage/name)
    for name in ['LICENSE','NOTICE.md','THIRD_PARTY.md']:
        shutil.copyfile(ROOT/name,stage/name)
    shutil.copytree(ROOT/'licenses',stage/'licenses')
    shutil.copyfile(ROOT/'scripts/Install-DualRomance.ps1',stage/'Install-DualRomance.ps1')
    shutil.copyfile(ROOT/'docs/RELEASE_README.zh-CN.md',stage/'README-中文.md')
    for name in ['VALIDATION.md','INSTALL.zh-CN.md']:
        (stage/'docs').mkdir(exist_ok=True);shutil.copyfile(ROOT/'docs'/name,stage/'docs'/name)
    shutil.copytree(ROOT/'src',stage/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    payload=stage.parent/'workshop-payload'
    shutil.copytree(stage/'Mods',payload/'Mods')
    for name in ['LICENSE','NOTICE.md','THIRD_PARTY.md']:shutil.copyfile(ROOT/name,payload/name)
    shutil.copytree(ROOT/'licenses',payload/'licenses')
    shutil.copyfile(ROOT/'workshop/description.zh-CN.bbcode',payload/'DESCRIPTION.txt')
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
    print(json.dumps(dict(package=str(archive),sha256=sha,reproduces_v014=True,workshop_upload_validated=False)))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',required=True,type=Path)
    package(parser.parse_args().stage)
