# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
"""Read-only release audit, including risks that branch traversal cannot prove away."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

from build import HOUSE, TRISS_HOME
from redio import BundleCatalog, Resource, encode_properties
from manor_dual import DUAL_LAYER_SOURCES, DUAL_PHASES
from manor_layout import inline_array, field


def tags(resource, raw):
    return [resource.names[i] for i in struct.unpack_from('<' + 'H' * raw[0], raw, 1)]


def cname(resource, obj, prop):
    return resource.names[int.from_bytes(resource.prop(obj, prop).data, 'little')]


def main(game, output, content=None):
    native = BundleCatalog(game / 'content/content0/bundles')
    content = content or game / 'Mods/modDualRomanceNoTango/content'
    installed = BundleCatalog(content)
    manifest_path = content.parents[2] / 'build-manifest.json'
    version = json.loads(manifest_path.read_text(encoding='utf-8'))['version'] if manifest_path.exists() else 'installed-content-see-sha256'
    wanted = {'q705_swp_yen_default', 'q705_swp_triss_default',
              'q705_ap_yen_house', 'q705_ap_triss_house', 'q705_ap_ciri_house',
              'q705_ap_sleep_sorceress', 'q705_ap_sleep_guest'}
    anchors = {}
    dual_paths = {source:path for path,source in DUAL_LAYER_SOURCES.items()}
    for path in native.items:
        if 'q705_epilog' not in path or not path.endswith('.w2l'):
            continue
        active_path = dual_paths.get(path,path)
        if active_path in installed.items:
            path = active_path
        raw = installed.extract(path) if path in installed.items else native.extract(path)
        if not any(tag.encode() in raw for tag in wanted):
            continue
        resource = Resource(raw)
        for obj in range(1, len(resource.chunks) + 1):
            props = {resource.names[p.name]: p.data for p in resource.props(obj)}
            if 'tags' not in props or 'transform' not in props:
                continue
            for tag in set(tags(resource, props['tags'])) & wanted:
                transform = props['transform']
                assert transform[0] & 1
                anchors[tag] = dict(path=path, object=obj,
                                    position=list(struct.unpack_from('<3f', transform, 1)), overridden=path in installed.items)
    assert wanted <= set(anchors), wanted - set(anchors)

    scenes = {}
    prefix = 'dlc\\bob\\data\\quests\\main_quests\\quest_files\\q705_epilog\\scenes\\'
    for actor, filename in [('yen', 'q705_20a_yen_visit_vineyard.w2scene'),
                            ('triss', 'q705_20b_triss_visit_vineyard.w2scene')]:
        path = prefix + filename
        raw = installed.extract(path) if path in installed.items else native.extract(path)
        resource = Resource(raw)
        tag = f'q705_swp_{actor}_default'
        instance = next(i for i in range(1, len(resource.chunks) + 1)
                        if resource.kind(i) == 'CStorySceneDialogsetInstance'
                        and tag in tags(resource, resource.prop(i, 'placementTag').data))
        slots = resource.prop(instance, 'slots').data
        count = struct.unpack_from('<I', slots)[0]
        ids = struct.unpack_from('<' + 'I' * count, slots, 4)
        slot = next(i for i in ids if cname(resource, i, 'actorName') != 'GERALT')
        scenes[actor] = dict(path=path, overridden=path in installed.items,
                             anchor=tag, anchor_position=anchors[tag]['position'],
                             actor_pose=[cname(resource, slot, p) for p in
                                         ['actorStatus', 'actorEmotionalState', 'actorPoseName']],
                             slot_transform=resource.prop(slot, 'slotPlacement').data.hex())
    separation = math.dist(scenes['yen']['anchor_position'], scenes['triss']['anchor_position'])
    scene_conflict = (separation < 0.1
                      and scenes['yen']['slot_transform'] == scenes['triss']['slot_transform'])
    home = Resource(installed.extract(TRISS_HOME))
    rows = inline_array(home.prop(1,'storyPhaseTimetable').data)
    dual_rows = [row for row in rows if home.names[int.from_bytes(field(home,row,'name').data,'little')] in DUAL_PHASES.values()]
    timetable = b''.join(encode_properties(row) for row in dual_rows) if dual_rows else home.prop(1,'storyPhaseTimetable').data
    # These are the exact serialized TagList properties, not arbitrary name-table matches.
    def tag_count(tag):
        if tag not in home.names:
            return 0
        header = struct.pack('<HHI', home.names.index('apTags'), home.names.index('TagList'), 7)
        return timetable.count(header + b'\x01' + struct.pack('<H', home.names.index(tag)))
    timetable_counts = {name: tag_count(name) for name in
                        ['q705_ap_triss_house', 'q705_ap_ciri_house', 'q705_ap_sleep_guest']}
    house = Resource(installed.extract(HOUSE))
    cycles = next(targets for socket, targets in house.connections(125) if socket == 'True')
    checks = [
        dict(name='independent_daytime_actionpoints', passed=math.dist(anchors['q705_ap_triss_house']['position'],
             anchors['q705_ap_yen_house']['position']) > 2.5 and timetable_counts['q705_ap_triss_house'] == 2),
        dict(name='independent_beds', passed=anchors['q705_ap_sleep_guest']['position']
             != anchors['q705_ap_sleep_sorceress']['position'] and timetable_counts['q705_ap_sleep_guest'] == 1),
        dict(name='native_visit_and_residence_job_ap_retained', passed=timetable_counts['q705_ap_triss_house'] == 2
             and timetable_counts['q705_ap_ciri_house'] == 0),
        dict(name='both_daily_cycles_enabled', passed=sorted(cycles) == [(22, 'In'), (52, 'In')]),
        dict(name='independent_repeat_dialogue_staging', passed=not scene_conflict),
    ]
    result = dict(version=version, release_gate='requires_runtime_validation' if all(c['passed'] for c in checks) else 'blocked', runtime_validated=False,
                  checks=checks, anchors=anchors, scenes=scenes, timetable_counts=timetable_counts,
                  repeat_dialogue_anchor_separation_meters=separation,
                  blockers=['Repeat dialogues still share identical world and actor placement.'
                            if scene_conflict else 'Furniture physics and native AI path following remain unverified in game.',
                            'Both actors, repeated conversations, day/night, travel and reload remain unverified.'],
                  installed_bundle_sha256=hashlib.sha256(
                      (content / 'blob0.bundle').read_bytes()).hexdigest())
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(checks=len(checks), passed=sum(c['passed'] for c in checks),
                          release_gate=result['release_gate'], runtime_validated=False)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--content', type=Path)
    args = parser.parse_args()
    main(args.game, args.out, args.content)
