#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
"""Export patched cooked CR2W files for inspection; not an uncooker."""
from pathlib import Path
import argparse,sys,json
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
from redio import BundleCatalog
parser=argparse.ArgumentParser();parser.add_argument('--out',required=True,type=Path);args=parser.parse_args()
out=args.out.resolve();assert not out.exists(),'Export directory already exists'
content=ROOT/'release/payload/Mods/modDualRomanceNoTango/content'
catalog=BundleCatalog(content)
for path in catalog.items:
    target=out/Path(*path.split('\\'));target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(catalog.extract(path))
(out/'EXPORT-NOTICE.txt').write_text('Cooked resource export for inspection. This is not an uncooked REDkit depot or a publishable project.\n',encoding='utf-8')
print(json.dumps(dict(files=len(catalog.items),output=str(out),uncooked=False)))
