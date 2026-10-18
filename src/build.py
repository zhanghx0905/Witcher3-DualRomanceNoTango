# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
"""Build Dual Romance from the user's own Remastered installation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from redio import BundleCatalog, Metadata, Resource, read_ws_string, u32, ws_string
from manor_layout import (AP_LAYER, ANCHOR_LAYER, BED_TEMPLATE, DECO_LAYER, TRIGGER_LAYER,
                          patch_actionpoints, patch_anchors,
                          patch_decor, patch_triggers)
from tavern_layout import (TAVERN_AP, TAVERN_SCENE, TAVERN_ANCHOR, TAVERN_STOOLS, DUAL_PHASE, DUAL_INPUT,
                           patch_tavern_actionpoint, patch_tavern_scene, patch_triss_dual_phase)
from manor_dual import (WORLD, YEN_HOME, DUAL_LAYER_SOURCES, DUAL_AP_LAYER,
                        DUAL_ANCHOR_LAYER, DUAL_TRIGGER_LAYER, DUAL_DECO_LAYER,
                        DUAL_PHASES, YEN_PATH, YEN_TRIGGER, patch_dual_community,
                        patch_world, patch_native_actionpoints, patch_native_triggers,
                        patch_dual_actionpoint_tags, patch_dual_trigger_tags,
                        rekey_layer, add_layout_switch, add_phase_setter, add_saved_quest_migration)
from manor_dual import set_property, strings, DUAL_GROUP

MOD_NAME = 'modDualRomanceNoTango'
Q310 = r'quests\part_3\q310_pregeels_new.w2phase'
LODGE = r'quests\part_3\quest_files\q310_pregeels\scenes\q310_44_wait_for_lodge.w2scene'
BOARDS = r'quests\videos_scenes\ending_boards_scene.w2scene'
HOUSE = r'dlc\bob\data\quests\main_quests\quest_files\q705_epilog\phases\q705_house.w2phase'
TRISS_HOME = r'dlc\bob\data\quests\main_quests\quest_files\q705_epilog\spawnsets\q705_triss.w2comm'
BOB_FIX = r'dlc\bob\data\quests\bob_bugfix_phase.w2phase'
Q504 = r'quests\epilogues\q504_ciri_empress.w2phase'
TRISS_MAIN = r'quests\main_npcs\community_files\triss.w2comm'
PATHS = [Q310, LODGE, BOARDS, HOUSE, TRISS_HOME, BOB_FIX, Q504, TRISS_MAIN,
         AP_LAYER, TRIGGER_LAYER, TAVERN_AP, TAVERN_SCENE, WORLD, YEN_HOME,
         *DUAL_LAYER_SOURCES]


def integer(resource, obj, name):
    return int.from_bytes(resource.prop(obj, name).data, 'little', signed=True)


def append_ref(resource, obj, name, target):
    raw = resource.prop(obj, name).data
    count = struct.unpack_from('<I', raw)[0]
    assert len(raw) == 4 + 4 * count
    vals = list(struct.unpack_from('<' + 'I' * count, raw, 4))
    assert target not in vals
    resource.set(obj, name, u32(count + 1) + raw[4:] + u32(target))


def change_scene_next(resource, obj, target):
    """Update runtime scene links and their reverse links together."""
    previous = integer(resource, obj, 'nextLinkElement')
    if previous == target:
        return
    for node, adding in [(previous, False), (target, True)]:
        if not node:
            continue
        raw = resource.prop(node, 'linkedElements').data
        count = struct.unpack_from('<I', raw)[0]
        values = list(struct.unpack_from('<' + 'I' * count, raw, 4))
        if adding:
            if obj not in values:
                values.append(obj)
        else:
            assert obj in values, (node, obj)
            values.remove(obj)
        resource.set(node, 'linkedElements', u32(len(values)) + b''.join(u32(i) for i in values))
    resource.set_int(obj, 'nextLinkElement', target)


def clone_block(resource, original, label, graph):
    cloned = resource.clone_owned(original, label)
    resource.register(graph, cloned)
    return cloned


def sole_owned(resource, obj, kind):
    return next(i for i, c in enumerate(resource.chunks, 1)
                if c.parent == obj and resource.kind(i) == kind)


def hard_community_reference(resource, soft_import):
    # CActivateStoryPhase stores a soft import, whereas CDeactivateSpawnset
    # requires a loaded CHandle. A soft-only import (flag 4) cannot supply it.
    path, kind, flags = struct.unpack_from('<IHH', resource.table_data[2], (soft_import - 1) * 8)
    assert resource.names[kind] == 'CCommunity' and flags == 4
    record = struct.pack('<IHH', path, kind, 0)
    for offset in range(0, len(resource.table_data[2]), 8):
        if resource.table_data[2][offset:offset + 8] == record:
            return -(offset // 8 + 1)
    resource.table_data[2] += record
    return -(len(resource.table_data[2]) // 8)


def patch_q310(r, notes):
    # Girl Talk and lodge resolution have independent gates. Keep their normal
    # continuation nodes so Final Preparations can still finish without Tango.
    assert r.kind(192) == r.kind(238) == 'CQuestConditionBlock'
    assert r.connections(192)[0] == ('True', [(189, 'In')])
    assert r.connections(238)[0] == ('True', [(239, 'In')])
    r.route(192, 'True', [(66, 'In')])
    r.route(238, 'True', [(240, 'In')])
    notes.append('q310: Girl Talk bypasses trap setup; resolution bypasses trap-door lock.')


def patch_lodge(r, notes):
    # Both versions of the lodge conversation can invite Geralt upstairs.
    for flow in (9, 684):
        true_link = integer(r, flow, 'trueLink')
        false_link = integer(r, flow, 'falseLink')
        change_scene_next(r, true_link, integer(r, false_link, 'nextLinkElement'))
    notes.append('q310 lodge scene: bypass revenge invitation in both conversation entry paths.')


def patch_boards(r, notes):
    # A dual romance takes Yen's board, then a fresh Triss condition. Singles
    # remain singles; no-romance remains the original solitary board.
    clone = r.clone_owned(9, 'ending-check-triss-after-yen')
    assert r.kind(clone) == 'CStorySceneFlowCondition'
    true_link = integer(r, clone, 'trueLink')
    false_link = integer(r, clone, 'falseLink')
    # Clone-owned copies the old reverse link lists; establish the new ones.
    r.set(clone, 'linkedElements', u32(1) + u32(93))
    change_scene_next(r, 87, 93)
    # Register cloned link elements at their targets before rerouting, since
    # the original scene's reverse lists cannot yet contain new object IDs.
    for link in (true_link, false_link):
        append_ref(r, integer(r, link, 'nextLinkElement'), 'linkedElements', link)
    change_scene_next(r, false_link, 7)
    change_scene_next(r, 93, clone)
    append_ref(r, 1, 'controlParts', clone)
    notes.append('Ending boards: dual plays Yen then Triss; original single/none selection preserved.')


def patch_house(r, notes):
    # Existing visitor scenes use the same lounge space. Serialize them and
    # temporarily remove Yen while Triss's introductory scene owns that space.
    check_triss = clone_block(r, 248, 'house-intro-check-triss', 2)
    remove_yen = clone_block(r, 137, 'house-intro-remove-yen', 2)
    wait_yen = clone_block(r, 138, 'house-intro-wait-yen-despawn', 2)
    # Visits require the retail scene anchors and start-in-AP spawn phases.
    # Keep both introductions on that path. Only after the second scene has
    # returned may the shared staging be replaced by separate resting places.
    r.route(215, 'True', [(241, 'In')])
    r.route(244, 'Output', [(check_triss, 'In')])
    r.route(check_triss, 'True', [(remove_yen, 'In')])
    r.route(check_triss, 'False', [(5, 'Success')])
    r.set(remove_yen, 'name', ws_string('Dual romance: clear shared intro space'))
    action = sole_owned(r, remove_yen, 'CDeactivateSpawnset')
    assert r.prop(246, 'spawnset').data == b'\x09\0'
    r.set_int(action, 'spawnset', hard_community_reference(r, 9))
    r.route(remove_yen, 'Out', [(wait_yen, 'In')])
    cond = sole_owned(r, wait_yen, 'W3QuestCond_ActorIsDespawned')
    r.set_name(cond, 'actorTag', 'q705_yen')
    r.route(wait_yen, '', [(249, 'In')])

    # The ordinary post-visit residence branch starts Triss, then Yen, and
    # enters the dialogue cycle exactly once, after both are present.
    wait_triss = clone_block(r, 163, 'house-resident-wait-triss', 2)
    spawn_triss = clone_block(r, 164, 'house-resident-spawn-triss', 2)
    spawn_yen = clone_block(r,157,'house-resident-spawn-yen-dual',2)
    for obj in [spawn_triss,spawn_yen]:
        r.set_name(sole_owned(r,obj,'CActivateStoryPhase'),'phase',DUAL_PHASES['q705_cycle'])
    r.route(16, 'True', [(wait_triss, 'In')])
    add_layout_switch(r,2,wait_triss,'',[(spawn_triss,'In')],214,215,9,'house-residency-layout')
    # Yen was explicitly despawned between the two introductions. The stock
    # distance-to-Yen pause at 156 needs her actor to exist, so it cannot be
    # used here. Triss's distance pause already provides the offscreen boundary.
    r.route(spawn_triss, 'Out', [(spawn_yen, 'In')])
    r.route(125, 'True', [(22, 'In'), (52, 'In')])
    # The original Triss cycle stays byte-identical, including existing saved
    # quest-node GUIDs. Its tags resolve to native geometry for a single romance
    # and the guest-room route in the dual layer. Yen uses equivalent aliases.
    for obj in (59,67):
        r.set_name(obj,'pathTag',YEN_PATH)
    for obj in (76,77):
        r.set_name(obj,'triggerTag',YEN_TRIGGER)
    set_property(r,199,'layersToHide','array:2,0,String',strings([DUAL_GROUP]))
    set_property(r,199,'syncOperation','Bool',b'\1')
    # Do not leave Yen absent until the later 60 m residency trigger. Both
    # actors use the dual visit/rest timetable in this interim stage; their
    # normal day/night schedules still start through the existing branch.
    dual,_ = add_layout_switch(r,2,252,'Output',[(5,'Success')],214,215,9,'house-after-welcomes-layout')
    resting = add_phase_setter(r,2,[(TRISS_HOME,DUAL_PHASES['q705_house']),
        (YEN_HOME,DUAL_PHASES['q705_house'])],'house-after-welcomes-resting',[(5,'Success')])
    r.route(dual,'Out',[(resting,'In')])
    notes.append('House: Yen intro then Triss intro; shared scene space is serialized; dual residents spawn together.')
    notes.append('House hotfix: Yen deactivation uses a hard-loaded community import, separate from the soft spawn reference.')
    notes.append('House residency hotfix: after leaving Triss behind, activate Yen directly; do not wait for distance to a despawned actor.')
    notes.append('House: both welcomes use retail layers and spawn phases; after Triss scene output, load dual furniture and restore both resting companions immediately. The native offscreen gate still starts daily residency later.')


def patch_triss_home(r, notes):
    patch_dual_community(r,notes,'triss')


def patch_bob_fix(r, notes):
    dual,single = add_layout_switch(r,438,440,'Out',[(441,'In')],441,442,440,'manor-reload-layout',require_welcomes=True)
    dual_spawn = add_phase_setter(r,438,[(TRISS_HOME,DUAL_PHASES['q705_cycle']),
        (YEN_HOME,DUAL_PHASES['q705_cycle'])],'reload-dual-residents',[(441,'In')])
    def after_welcome(fact,target,label):
        block=clone_block(r,442,label,438)
        condition=sole_owned(r,block,'CQuestFactsDBCondition')
        r.set(block,'name',ws_string(fact))
        r.set(condition,'factId',ws_string(fact))
        r.set_name(condition,'queryFact','QF_Sum')
        r.set_name(condition,'compareFunc','CF_GreaterEqual')
        r.set_int(condition,'value',1)
        r.set_connections(block,[('True',[(target,'In')]),('False',[(441,'In')])])
        return block
    dual_triss_met=after_welcome('q705_triss_house_met',dual_spawn,'reload-dual-triss-welcomed')
    dual_yen_met=after_welcome('q705_yen_first_met',dual_triss_met,'reload-dual-yen-welcomed')
    r.route(dual,'Out',[(dual_yen_met,'In')])
    yen_check = clone_block(r,441,'reload-single-yen',438)
    triss_check = clone_block(r,442,'reload-single-triss',438)
    yen_spawn = add_phase_setter(r,438,[(YEN_HOME,'q705_cycle')],'reload-native-yen',[(441,'In')])
    triss_spawn = add_phase_setter(r,438,[(TRISS_HOME,'q705_cycle')],'reload-native-triss',[(441,'In')])
    yen_met=after_welcome('q705_yen_first_met',yen_spawn,'reload-single-yen-welcomed')
    triss_met=after_welcome('q705_triss_house_met',triss_spawn,'reload-single-triss-welcomed')
    # The native-layout path also handles partially completed dual welcomes.
    # Those saves must not activate a single-Yen cycle between the two visits.
    pending_dual=clone_block(r,442,'reload-native-check-pending-dual',438)
    r.set_connections(pending_dual,[('True',[(441,'In')]),('False',[(yen_met,'In')])])
    r.route(single,'Out',[(yen_check,'In')])
    r.set_connections(yen_check,[('True',[(pending_dual,'In')]),('False',[(triss_check,'In')])])
    r.set_connections(triss_check,[('True',[(triss_met,'In')]),('False',[(441,'In')])])
    add_saved_quest_migration(r,notes)
    notes.append('Manor reload: choose dual/native layers and community phases from both romance facts; retain native single-romance furniture selection.')


def patch_q504(r, notes):
    # The empress epilogue has physical companions in the tavern. A dual save
    # uses Yen's original conversation while also spawning Triss nearby.
    check_triss = clone_block(r, 579, 'q504-check-second-companion', 551)
    stop_triss = clone_block(r, 581, 'q504-stop-triss-default', 551)
    spawn_triss = clone_block(r, 582, 'q504-spawn-second-companion', 551)
    spawn_yen_dual = clone_block(r, 574, 'q504-spawn-yen-dual', 551)
    wait_yen_dual = clone_block(r, 575, 'q504-wait-yen-dual', 551)
    r.set_name(sole_owned(r, spawn_triss, 'CActivateStoryPhase'), 'phase', DUAL_PHASE)
    r.route(559, 'True', [(572, 'In')])
    r.route(573, 'Out', [(check_triss, 'In')])
    r.route(check_triss, 'True', [(stop_triss, 'In')])
    r.route(check_triss, 'False', [(574, 'In')])
    r.route(stop_triss, 'Out', [(spawn_triss, 'In')])
    r.route(spawn_triss, 'Out', [(spawn_yen_dual, 'In')])
    r.route(spawn_yen_dual, 'Out', [(wait_yen_dual, 'In')])
    r.route(wait_yen_dual, '', [(561, DUAL_INPUT)])
    notes.append('Ciri empress tavern: dual-only community/input/dialogue branch seats both companions at Geralt table; original single-romance branches retained.')


def patch_triss_main(r, notes):
    patch_triss_dual_phase(r, notes)


PATCHERS = {Q310:patch_q310,LODGE:patch_lodge,BOARDS:patch_boards,HOUSE:patch_house,
            TRISS_HOME:patch_triss_home,BOB_FIX:patch_bob_fix,Q504:patch_q504,TRISS_MAIN:patch_triss_main,
            AP_LAYER:patch_native_actionpoints,TRIGGER_LAYER:patch_native_triggers,
            TAVERN_AP:patch_tavern_actionpoint,TAVERN_SCENE:patch_tavern_scene,WORLD:patch_world,
            YEN_HOME:lambda r,n:patch_dual_community(r,n,'yen'),
            DUAL_AP_LAYER:patch_actionpoints,DUAL_ANCHOR_LAYER:patch_anchors,
            DUAL_TRIGGER_LAYER:patch_triggers}


def build(game, destination):
    from redio import pack_mod
    game, destination = Path(game).resolve(), Path(destination).resolve()
    assert destination != game and game not in destination.parents, 'Build outside the game directory'
    catalog = BundleCatalog(game / 'content/content0/bundles')
    metadata = Metadata((game / 'content/metadata.store').read_bytes())
    support_path = Path(__file__).with_name('supported-sources.json')
    supported = json.loads(support_path.read_text(encoding='utf-8')) if support_path.exists() else None
    template_bytes = catalog.extract(BED_TEMPLATE)
    support_resources = {path: catalog.extract(path) for path in [BED_TEMPLATE, TAVERN_ANCHOR, TAVERN_STOOLS]}
    if supported is not None:
        for path, data in support_resources.items():
            assert hashlib.sha256(data).hexdigest() == supported[path], ('Support resource changed; rebase required', path)
    resources, originals, notes, manifest = {}, {}, [], []
    for path in PATHS:
        source_path = DUAL_LAYER_SOURCES.get(path,path)
        original = catalog.extract(source_path)
        if supported is not None:
            assert hashlib.sha256(original).hexdigest() == supported[source_path], ('Game resources changed; rebase required', source_path)
        resource = Resource(original)
        assert resource.build() == original, ('Lossless roundtrip failed', path)
        if path == DUAL_DECO_LAYER:
            patch_decor(resource, notes, template_bytes, metadata)
        else:
            PATCHERS[path](resource, notes)
        if path == DUAL_AP_LAYER:
            patch_dual_actionpoint_tags(resource)
        elif path == DUAL_TRIGGER_LAYER:
            patch_dual_trigger_tags(resource)
        if path in DUAL_LAYER_SOURCES:
            rekey_layer(resource,path)
        patched = resource.build()
        assert Resource(patched).build() == patched
        resources[path], originals[path] = patched, original
        manifest.append(dict(path=path, source_path=source_path, source_sha256=hashlib.sha256(original).hexdigest(),
                             patched_sha256=hashlib.sha256(patched).hexdigest(),
                             source_bytes=len(original), patched_bytes=len(patched),
                             source_objects=len(Resource(original).chunks), patched_objects=len(resource.chunks)))
    bundle, index = pack_mod(resources, catalog, metadata, DUAL_LAYER_SOURCES)
    content = destination / 'Mods' / MOD_NAME / 'content'
    content.mkdir(parents=True, exist_ok=True)
    (content / 'blob0.bundle').write_bytes(bundle)
    (content / 'metadata.store').write_bytes(index)
    # Check the actual packed artifacts, including table CRCs and resource data.
    packed_catalog = BundleCatalog(content)
    packed_metadata = Metadata(index)
    assert set(packed_catalog.items) == set(resources)
    for path, raw in resources.items():
        assert packed_catalog.extract(path) == raw
        assert path in packed_metadata.by_path
    report = dict(name='Dual Romance / No Tango', version='0.1.8-experimental',
                  target='Local Steam Remastered resources, CR2W 164 / bundle 5 / metadata 7',
                  runtime_validated=False, resources=manifest, changes=notes,
                  support_resources=[dict(path=path, sha256=hashlib.sha256(data).hexdigest()) for path,data in support_resources.items()],
                  bundle_sha256=hashlib.sha256(bundle).hexdigest(),
                  metadata_sha256=hashlib.sha256(index).hexdigest())
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'build-manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return resources, originals, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    _, _, result = build(args.game, args.out)
    print(json.dumps({'status': 'built', 'version': result['version'],
                      'resource_count': len(result['resources']), 'runtime_validated': False}, indent=2))
