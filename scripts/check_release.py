#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
"""Validate the versioned cooked payload without requiring a game install."""
from pathlib import Path
import argparse,hashlib,json,struct,sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
from redio import BundleCatalog,Metadata,Resource

def check(root=ROOT):
    root=Path(root)
    project=json.loads((root/'project.json').read_text(encoding='utf-8'))
    manifest=json.loads((root/'release/metadata/build-manifest.json').read_text(encoding='utf-8'))
    compatibility=json.loads((root/'release/metadata/compatibility.json').read_text(encoding='utf-8'))
    assert project['version']==manifest['version']
    assert project['steam_build_id']==compatibility['steam_build_id']
    assert project['author']=='Hexiao Zhang'
    content=root/'release/payload/Mods'/project['mod_directory']/'content'
    for filename,key in [('blob0.bundle','bundle_sha256'),('metadata.store','metadata_sha256')]:
        assert hashlib.sha256((content/filename).read_bytes()).hexdigest()==manifest[key],filename
    catalog=BundleCatalog(content);metadata=Metadata((content/'metadata.store').read_bytes())
    expected={r['path']:r for r in manifest['resources']}
    assert set(catalog.items)==set(expected)==set(metadata.by_path)-{''}
    for path,record in expected.items():
        raw=catalog.extract(path)
        assert len(raw)==record['patched_bytes'],path
        assert hashlib.sha256(raw).hexdigest()==record['patched_sha256'],path
        resource=Resource(raw)
        assert len(resource.chunks)==record['patched_objects'],path
        assert resource.build()==raw,path
    hashes=[struct.unpack_from('<Q',row)[0] for row in metadata.sections[6]]
    assert hashes==sorted(hashes) and len(set(hashes))==len(hashes)
    pinned=json.loads((root/'src/supported-sources.json').read_text(encoding='utf-8'))
    for row in manifest['resources']:assert pinned[row['path']]==row['source_sha256']
    for row in manifest['support_resources']:assert pinned[row['path']]==row['sha256']
    for filename in ['LICENSE','NOTICE.md','THIRD_PARTY.md','licenses/w3edit-BSD-2-Clause.txt']:
        assert (root/filename).is_file(),filename
    return dict(passed=True,version=project['version'],resources_checked=len(expected),
                scope='Prebuilt payload integrity; not in-game or native-source tests',runtime_validated=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--report',type=Path)
    args=parser.parse_args();result=check(args.root)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
