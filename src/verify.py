# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
"""Structural/integration checks. These do not replace in-game playtesting."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest

from build import (BOARDS, BOB_FIX, HOUSE, LODGE, PATHS, Q310, Q504, TRISS_HOME,
                   TRISS_MAIN, build, integer)
from redio import (BundleCatalog, Metadata, Resource, fnv32_name, fnv64_path, encode_properties, read_properties,
                   read_ws_string, read_vlq)
from manor_layout import (AP_LAYER as NATIVE_AP_LAYER, ANCHOR_LAYER as NATIVE_ANCHOR_LAYER,
                          TRIGGER_LAYER as NATIVE_TRIGGER_LAYER, DECO_LAYER as NATIVE_DECO_LAYER, BED_TEMPLATE,
                          OFFSET, TRISS_PATH, TRISS_TRIGGER, fields, field,
                          inline_array, path_world_points, sector_objects)
from manor_dual import (DUAL_AP_LAYER as AP_LAYER, DUAL_ANCHOR_LAYER as ANCHOR_LAYER,
                        DUAL_TRIGGER_LAYER as TRIGGER_LAYER, DUAL_DECO_LAYER as DECO_LAYER,
                        DUAL_LAYER_SOURCES, DUAL_GROUP, DUAL_PHASES, YEN_HOME, WORLD,
                        NATIVE_SPATIAL_GROUPS, NATIVE_DECO_GROUP, YEN_PATH, YEN_TRIGGER,
                        NATIVE_PATH, NATIVE_TRIGGER, group_tail)
from tavern_layout import (TAVERN_AP, TAVERN_SCENE, DUAL_PHASE, DUAL_AP, DUAL_INPUT,
                            DUAL_DIALOGSET, DUAL_CAMERA, SHARED_STOOL, YEN_STOOL,
                            SHARED_YAW, SCENE_YAW, point_to_world, timeline_events)


def fact_condition(r, obj, facts):
    props = {r.names[p.name]: p for p in r.props(obj)}
    key = read_ws_string(props['factId'].data)
    value = facts.get(key, 0)
    expected = int.from_bytes(props['value'].data, 'little', signed=True) if 'value' in props else 0
    compare = r.names[int.from_bytes(props['compareFunc'].data, 'little')] if 'compareFunc' in props else 'CF_Equal'
    if 'queryFact' in props and r.names[int.from_bytes(props['queryFact'].data, 'little')] == 'QF_DoesExist':
        value = int(key in facts)
    operations = {'CF_Equal': lambda: value == expected, 'CF_NotEqual': lambda: value != expected,
                  'CF_Greater': lambda: value > expected, 'CF_GreaterEqual': lambda: value >= expected,
                  'CF_Less': lambda: value < expected, 'CF_LessEqual': lambda: value <= expected}
    return operations[compare]()


def walk_quest(r, start, facts, stop):
    queue, visited, steps = [start], [], 0
    while queue:
        obj = queue.pop(0)
        visited.append(obj)
        steps += 1
        assert steps < 100, 'Unexpected quest loop'
        if obj in stop:
            continue
        connections = r.connections(obj)
        if r.kind(obj) == 'CQuestConditionBlock':
            decision = fact_condition(r, integer(r, obj, 'questCondition'), facts)
            connections = [(s, t) for s, t in connections if s == ('True' if decision else 'False')]
        assert len(connections) <= 1, (obj, connections)
        if connections:
            queue.extend(target for target, _ in connections[0][1])
    return visited


def boards(r, facts):
    obj, videos, visited = 11, [], set()
    while obj != 7:
        assert obj not in visited, 'Ending scene loop'
        visited.add(obj)
        kind = r.kind(obj)
        if kind == 'CStorySceneFlowCondition':
            decision = fact_condition(r, integer(r, obj, 'questCondition'), facts)
            obj = integer(r, obj, 'trueLink' if decision else 'falseLink')
        else:
            if kind == 'CStorySceneVideoSection':
                videos.append(read_ws_string(r.prop(obj, 'videoFileName').data))
            obj = integer(r, obj, 'nextLinkElement')
    return videos


def romance(triss, yen):
    return {key: 1 for key, enabled in [('q309_triss_lover', triss), ('q309_triss_stayed', triss),
                                       ('sq202_yen_girlfriend', yen)] if enabled}


class ModChecks(unittest.TestCase):
    resources = {}
    originals = {}
    output = None

    def resource(self, name):
        return Resource(self.resources[name])

    def properties_except(self, resource, obj, exclude=('guid',)):
        return {resource.names[p.name]:p.data for p in resource.props(obj)
                if resource.names[p.name] not in exclude}

    def test_all_inputs_roundtrip_without_changes(self):
        for name, raw in self.originals.items():
            with self.subTest(path=name):
                self.assertEqual(Resource(raw).build(), raw)

    def test_all_outputs_have_valid_crcs_and_names(self):
        for name, raw in self.resources.items():
            with self.subTest(path=name):
                r = Resource(raw)
                self.assertEqual(r.build(), raw)
                for i, text in enumerate(r.names):
                    stored = struct.unpack_from('<I', r.table_data[1], i * 8 + 4)[0]
                    self.assertEqual(fnv32_name(text), stored)

    def test_package_metadata_matches_bundle_and_native_layout(self):
        directory = self.output / 'Mods/modDualRomanceNoTango/content'
        catalog = BundleCatalog(directory)
        metadata = Metadata((directory / 'metadata.store').read_bytes())
        self.assertEqual(set(catalog.items), set(PATHS))
        self.assertEqual(set(metadata.by_path) - {''}, set(PATHS))
        hashes = [struct.unpack_from('<Q', row)[0] for row in metadata.sections[6]]
        self.assertEqual(hashes, sorted(hashes))
        for name in PATHS:
            with self.subTest(path=name):
                fi = struct.unpack('<8I', metadata.sections[0][metadata.by_path[name]])
                _, _, offset, unpacked, packed, _, comp = catalog.items[name]
                self.assertEqual(fi[2:4], (packed, unpacked))
                self.assertEqual(fi[5:8], (0, 0, comp))
                entry = struct.unpack('<Q4I', metadata.sections[1][fi[4]])
                self.assertEqual(entry, (offset, packed, 0, metadata.by_path[name], 1))
                self.assertEqual(catalog.extract(name), self.resources[name])

    def test_native_metadata_compression_layout_is_confirmed(self):
        m = Metadata((self.game / 'content/metadata.store').read_bytes())
        c = BundleCatalog(self.game / 'content/content0/bundles')
        for name in PATHS:
            name = DUAL_LAYER_SOURCES.get(name,name)
            fi = struct.unpack('<8I', m.sections[0][m.by_path[name]])
            self.assertEqual(fi[7], c.items[name][-1])
            self.assertEqual(fi[6], 0)

    def test_new_quest_nodes_are_registered_and_guid_distinct(self):
        for name in (Q310, HOUSE, Q504, BOB_FIX):
            r = self.resource(name)
            old_count = len(Resource(self.originals[name]).chunks)
            original_guids = set()
            added_guids = set()
            for obj, chunk in enumerate(r.chunks, 1):
                for p in r.props(obj):
                    if r.names[p.name] == 'guid':
                        if obj <= old_count:
                            original_guids.add(p.data)
                        else:
                            self.assertNotIn(p.data, original_guids | added_guids)
                            added_guids.add(p.data)
                if obj > old_count and r.kind(chunk.parent) == 'CQuestGraph':
                    raw = r.prop(chunk.parent, 'graphBlocks').data
                    self.assertIn(obj, struct.unpack_from('<' + 'I' * struct.unpack_from('<I', raw)[0], raw, 4))
                if any(r.names[p.name] == 'cachedConnections' for p in r.props(obj)):
                    for _, targets in r.connections(obj):
                        for target, _ in targets:
                            self.assertGreater(target, 0)
                            self.assertLessEqual(target, len(r.chunks))

    def test_quest_connections_keep_unmodified_bytes(self):
        # Re-encoding representative native connection records must match
        # byte-for-byte before relying on this codec to build new fan-outs.
        for name, ids in [(Q310, [192, 238]), (HOUSE, [125, 157, 244])]:
            r = Resource(self.originals[name])
            for obj in ids:
                original = r.prop(obj, 'cachedConnections').data
                r.set_connections(obj, r.connections(obj))
                self.assertEqual(original, r.prop(obj, 'cachedConnections').data)

    def test_tango_setup_and_door_lock_unreachable(self):
        r = self.resource(Q310)
        for triss in (False, True):
            for yen in (False, True):
                with self.subTest(triss=triss, yen=yen):
                    facts = romance(triss, yen)
                    for completed in (False, True):
                        state = dict(facts)
                        if completed:
                            state['q311_completed'] = 1
                        path = walk_quest(r, 191, state, {69})
                        self.assertIn(69, path)
                        self.assertNotIn(189, path)
                        self.assertNotIn(109, path)
                    path = walk_quest(r, 237, facts, {227})
                    self.assertIn(227, path)
                    self.assertNotIn(239, path)

    def test_both_lodge_invitations_bypassed(self):
        r = self.resource(LODGE)
        original = Resource(self.originals[LODGE])
        for obj in (9, 684):
            true_link = integer(r, obj, 'trueLink')
            false_link = integer(r, obj, 'falseLink')
            self.assertEqual(integer(r, true_link, 'nextLinkElement'), integer(r, false_link, 'nextLinkElement'))
            self.assertNotEqual(integer(original, true_link, 'nextLinkElement'), integer(r, true_link, 'nextLinkElement'))

    def test_all_four_ending_board_outcomes(self):
        r = self.resource(BOARDS)
        expected = {(False, False): ['fb_5c.usm'], (True, False): ['fb_5b.usm'],
                    (False, True): ['fb_5a.usm'], (True, True): ['fb_5a.usm', 'fb_5b.usm']}
        for choices, result in expected.items():
            with self.subTest(choices=choices):
                self.assertEqual([v.split('\\')[-1] for v in boards(r, romance(*choices))], result)

    def test_scene_forward_reverse_links_agree(self):
        for name in (LODGE, BOARDS):
            r = self.resource(name)
            old = Resource(self.originals[name])
            for obj, chunk in enumerate(r.chunks, 1):
                if obj <= len(old.chunks) and old.chunk(obj).data == chunk.data:
                    continue
                props = {r.names[p.name]: p for p in r.props(obj)}
                if 'nextLinkElement' not in props:
                    continue
                target = integer(r, obj, 'nextLinkElement')
                incoming = r.prop(target, 'linkedElements').data
                count = struct.unpack_from('<I', incoming)[0]
                self.assertIn(obj, struct.unpack_from('<' + 'I' * count, incoming, 4))

    def test_manor_intros_serial_and_quest_completes_once(self):
        r = self.resource(HOUSE)
        for triss, yen, expected in [(False, True, [244]), (True, False, [252]), (True, True, [244, 252])]:
            with self.subTest(triss=triss, yen=yen):
                path = walk_quest(r, 214, romance(triss, yen), {5})
                self.assertEqual([obj for obj in path if obj in (244, 252)], expected)
                self.assertEqual(path.count(5), 1)
                self.assertNotIn(216, path)
        path = walk_quest(r, 214, {}, {216})
        self.assertIn(216, path)

    def test_manor_yen_deactivation_has_a_hard_community_import(self):
        r = self.resource(HOUSE)
        # Follow the actual transition after Yen's scene to its despawn action.
        check = r.connections(244)[0][1][0][0]
        remove = next(targets[0][0] for socket, targets in r.connections(check) if socket == 'True')
        action = next(i for i, chunk in enumerate(r.chunks, 1)
                      if chunk.parent == remove and r.kind(i) == 'CDeactivateSpawnset')
        handle = integer(r, action, 'spawnset')
        self.assertLess(handle, 0)
        path_offset, kind, flags = struct.unpack_from('<IHH', r.table_data[2], (-handle - 1) * 8)
        self.assertEqual(flags, 0, 'A CHandle cannot use a soft-only import (flag 4)')
        self.assertEqual(r.names[kind], 'CCommunity')
        strings = r.table_data[0]
        path = strings[path_offset:strings.index(b'\0', path_offset)].decode('utf-8')
        self.assertTrue(path.endswith('q705_yennefer.w2comm'))
        soft = struct.unpack_from('<IHH', r.table_data[2], 8 * 8)
        self.assertEqual(soft[:2], (path_offset, kind))
        self.assertEqual(soft[2], 4, 'The original soft activation reference must remain soft')

    def test_manor_dual_residents_and_both_dialog_cycles(self):
        r = self.resource(HOUSE)
        path = walk_quest(r, 15, romance(True, True), {20})
        self.assertEqual(path.count(20), 1)
        self.assertNotIn(156, path, 'Despawned Yen cannot satisfy a distance-to-Yen pause')
        phases = [r.names[int.from_bytes(r.prop(i,'phase').data,'little')]
                  for obj in path for i,c in enumerate(r.chunks,1)
                  if c.parent==obj and r.kind(i)=='CActivateStoryPhase']
        self.assertEqual(phases,[DUAL_PHASES['q705_cycle']]*2)
        spawn_actions = [p.data for obj in path for p in r.props(obj) if r.names[p.name] == 'spawnsets']
        self.assertEqual(len(spawn_actions), 2)
        for triss, yen, targets in [(True, True, [22, 52]), (True, False, [22]), (False, True, [52])]:
            path = walk_quest(r, 130, romance(triss, yen), {22, 52})
            self.assertEqual([i for i in path if i in (22, 52)], targets)

    def test_dual_empress_tavern_contains_both_companions(self):
        r = self.resource(Q504)
        for triss, yen in [(True, True), (False, True), (True, False), (False, False)]:
            with self.subTest(triss=triss, yen=yen):
                path = walk_quest(r, 558, romance(triss, yen), {561})
                self.assertEqual(path.count(561), 1)
                spawned = [obj for obj in path if r.kind(obj) == 'CQuestStoryPhaseSetterBlock']
                self.assertEqual(len(spawned), int(triss) + int(yen))
                self.assertEqual(560 in path, not (triss or yen))
                source = path[-2]
                socket = next(input_name for _,targets in r.connections(source) for target,input_name in targets if target == 561)
                expected = DUAL_INPUT if triss and yen else 'triss_lover' if triss else 'yen_lover' if yen else 'no_lover'
                self.assertEqual(socket, expected)
                triss_phases=[]
                for obj in spawned:
                    for child,chunk in enumerate(r.chunks,1):
                        if chunk.parent == obj and r.kind(child)=='CActivateStoryPhase':
                            phase=r.names[int.from_bytes(r.prop(child,'phase').data,'little')]
                            if 'triss' in phase or phase=='q504_in_tavern':triss_phases.append(phase)
                if triss and yen:self.assertIn(DUAL_PHASE,triss_phases)

    def test_q504_single_romance_scene_and_timetable_remain_native(self):
        scene,original=self.resource(TAVERN_SCENE),Resource(self.originals[TAVERN_SCENE])
        for obj in range(2,len(original.chunks)+1):
            if obj!=5:self.assertEqual(scene.chunk(obj).data,original.chunk(obj).data)
        community=self.resource(TRISS_MAIN);old=Resource(self.originals[TRISS_MAIN])
        before=inline_array(old.prop(1,'storyPhaseTimetable').data)
        after=inline_array(community.prop(1,'storyPhaseTimetable').data)
        self.assertEqual(len(after),len(before)+1)
        for a,b in zip(before,after):self.assertEqual(b'\0'+__import__('redio').encode_properties(a),b'\0'+__import__('redio').encode_properties(b))
        self.assertEqual(community.names[int.from_bytes(field(community,after[-1],'name').data,'little')],DUAL_PHASE)

    def test_q504_shared_table_actionpoint_and_scene_use_existing_third_stool(self):
        ap,original=self.resource(TAVERN_AP),Resource(self.originals[TAVERN_AP])
        for obj in range(2,len(original.chunks)+1):self.assertEqual(ap.chunk(obj).data,original.chunk(obj).data)
        actor=next(i for i in range(1,len(ap.chunks)+1) if any(ap.names[p.name]=='tags' and p.data==b'\1'+struct.pack('<H',ap.names.index(DUAL_AP)) for p in ap.props(i)))
        position=struct.unpack_from('<3f',ap.prop(actor,'transform').data,1)
        self.assertLess(math.dist(position,SHARED_STOOL),.5)
        component=next(i for i,c in enumerate(ap.chunks,1) if c.parent==actor and ap.kind(i)=='CActionPointComponent')
        self.assertEqual(ap.prop(component,'jobTreeRes').data,original.prop(16,'jobTreeRes').data)
        _,end=read_properties(ap.chunk(actor).data,1);tail=ap.chunk(actor).data[end:]
        count,pos=read_vlq(tail,8);self.assertEqual(count,1);self.assertEqual(struct.unpack_from('<I',tail,pos)[0],component)
        scene=self.resource(TAVERN_SCENE)
        dialogset=next(i for i in range(1,len(scene.chunks)+1) if scene.kind(i)=='CStorySceneDialogsetInstance' and scene.names[int.from_bytes(scene.prop(i,'name').data,'little')]==DUAL_DIALOGSET)
        raw=scene.prop(dialogset,'slots').data
        slots=struct.unpack_from('<'+'I'*struct.unpack_from('<I',raw)[0],raw,4)
        positions={}
        for slot in slots:
            props={scene.names[p.name]:p for p in scene.props(slot)}
            if 'actorName' in props:positions[scene.names[int.from_bytes(props['actorName'].data,'little')]]=point_to_world(struct.unpack_from('<3f',props['slotPlacement'].data,1))
        self.assertTrue({'TRISS','YENNEFER','GERALT'}<=positions.keys())
        for actor_name in ['GERALT','YENNEFER']:
            self.assertGreater(math.dist(positions['TRISS'],positions[actor_name]),.65)
            self.assertLess(math.dist(positions['TRISS'],positions[actor_name]),2.1)
        self.assertLess(math.dist(positions['TRISS'],SHARED_STOOL),.4)

    def test_q504_cloned_timeline_remaps_event_guids_and_element_references(self):
        scene=self.resource(TAVERN_SCENE)
        original=Resource(self.originals[TAVERN_SCENE])
        section=next(i for i in range(1,len(scene.chunks)+1) if scene.kind(i)=='CStorySceneSection' and read_ws_string(scene.prop(i,'sectionName').data)=='q504_01_morons_dual_romance')
        events=timeline_events(scene,section)[1]
        guids={field(scene,props,'GUID').data for _,props in events}
        old_guids={field(original,props,'GUID').data for _,props in timeline_events(original,120)[1]}
        self.assertFalse(guids & old_guids)
        raw=scene.prop(section,'eventsInfo').data
        ids=struct.unpack_from('<'+'I'*struct.unpack_from('<I',raw)[0],raw,4)
        elements_raw=scene.prop(section,'sceneElements').data
        element_ids=set(struct.unpack_from('<'+'I'*struct.unpack_from('<I',elements_raw)[0],elements_raw,4))
        self.assertEqual(len(ids),len(events))
        for event_id,(_,props) in zip(ids,events):
            self.assertEqual(scene.prop(event_id,'eventGuid').data,field(scene,props,'GUID').data)
            for p in props:
                key,kind=scene.names[p.name],scene.names[p.kind]
                if key=='sceneElement':self.assertIn(int.from_bytes(p.data,'little'),element_ids)
                if key in ['linkParentGUID','interpolationEventGUID'] and p.data!=b'\0'*16:self.assertIn(p.data,guids)
        old_raw=original.prop(120,'sceneElements').data
        old_ids=struct.unpack_from('<'+'I'*struct.unpack_from('<I',old_raw)[0],old_raw,4)
        original_lines=[original.chunk(i).data for i in old_ids if original.kind(i)=='CStorySceneLine']
        copied_lines=[scene.chunk(i).data for i in sorted(element_ids) if scene.kind(i)=='CStorySceneLine']
        self.assertGreater(len(original_lines),0)
        self.assertEqual(len(original_lines),len(copied_lines))
        for old_raw,new_raw in zip(original_lines,copied_lines):
            a={original.names[p.name]:p.data for p in read_properties(old_raw,1)[0] if original.names[p.kind]=='LocalizedString'}
            b={scene.names[p.name]:p.data for p in read_properties(new_raw,1)[0] if scene.names[p.kind]=='LocalizedString'}
            self.assertEqual(a,b)

    def test_q504_three_person_overview_contains_seated_heads_and_shoulders(self):
        scene=self.resource(TAVERN_SCENE)
        camera=next(row for row in inline_array(scene.prop(1,'cameraDefinitions').data) if scene.names[int.from_bytes(field(scene,row,'cameraName').data,'little')]==DUAL_CAMERA)
        transform=field(scene,camera,'cameraTransform').data
        position=struct.unpack_from('<3f',transform,1);_,pitch,yaw=struct.unpack_from('<3f',transform,13)
        pitch,yaw=map(math.radians,[pitch,yaw])
        forward=(-math.sin(yaw)*math.cos(pitch),math.cos(yaw)*math.cos(pitch),math.sin(pitch))
        right=(math.cos(yaw),math.sin(yaw),0)
        up=(right[1]*forward[2],-right[0]*forward[2],right[0]*forward[1]-right[1]*forward[0])
        tangent=math.tan(math.radians(struct.unpack('<f',field(scene,camera,'cameraFov').data)[0])/2)
        dialogset=next(i for i in range(1,len(scene.chunks)+1) if scene.kind(i)=='CStorySceneDialogsetInstance' and scene.names[int.from_bytes(scene.prop(i,'name').data,'little')]==DUAL_DIALOGSET)
        raw=scene.prop(dialogset,'slots').data;slots=struct.unpack_from('<'+'I'*struct.unpack_from('<I',raw)[0],raw,4)
        checked=[]
        for slot in slots:
            props={scene.names[p.name]:p for p in scene.props(slot)}
            actor_name=scene.names[int.from_bytes(props['actorName'].data,'little')] if 'actorName' in props else ''
            if actor_name not in ['TRISS','YENNEFER','GERALT']:continue
            origin=struct.unpack_from('<3f',props['slotPlacement'].data,1)
            for dx in [-.3,.3]:
                for dy in [-.15,.15]:
                    for dz in [.8,1.25]:
                        delta=[origin[0]+dx-position[0],origin[1]+dy-position[1],origin[2]+dz-position[2]]
                        depth=sum(a*b for a,b in zip(delta,forward));self.assertGreater(depth,1)
                        screen_x=sum(a*b for a,b in zip(delta,right))/(depth*tangent)
                        screen_y=sum(a*b for a,b in zip(delta,up))/(depth*tangent/(16/9))
                        self.assertLess(abs(screen_x),1.0,actor_name)
                        self.assertLess(abs(screen_y),1.0,actor_name)
            checked.append(actor_name)
        self.assertEqual(set(checked),{'TRISS','YENNEFER','GERALT'})

    def test_activity_points_and_movement_paths_separated(self):
        r = self.resource(TRISS_HOME)
        self.assertIn('q705_ap_sleep_guest', r.names)
        house = self.resource(HOUSE)
        for obj in (29, 37):
            self.assertEqual(house.names[int.from_bytes(house.prop(obj, 'pathTag').data, 'little')], NATIVE_PATH)
        for obj in (47, 48):
            self.assertEqual(house.names[int.from_bytes(house.prop(obj, 'triggerTag').data, 'little')], NATIVE_TRIGGER)
        for obj in (59,67):
            self.assertEqual(house.names[integer(house,obj,'pathTag')],YEN_PATH)
        for obj in (76,77):
            self.assertEqual(house.names[integer(house,obj,'triggerTag')],YEN_TRIGGER)
        self.assertEqual(house.connections(283)[0], ('True', []))
        self.assertEqual(self.resource(BOB_FIX).connections(442)[0], ('True', [(439, ' ')]))

    def test_repeated_dialogue_world_staging_has_a_separate_matching_actionpoint(self):
        ap, scene = self.resource(AP_LAYER), self.resource(ANCHOR_LAYER)
        old_ap, old_scene = Resource(self.originals[AP_LAYER]), Resource(self.originals[ANCHOR_LAYER])
        def position(resource, obj):
            return struct.unpack_from('<3f', resource.prop(obj, 'transform').data, 1)
        # This catches the actual 0.1.2 failure: two differently named anchors
        # at the same place despite different daytime AP tags.
        self.assertGreater(math.dist(position(scene, 12), position(scene, 16)), 2.5)
        self.assertGreater(math.dist(position(ap, 13), position(ap, 15)), 2.5)
        for axis in range(3):
            ap_shift = position(ap, 15)[axis] - position(old_ap, 15)[axis]
            scene_shift = position(scene, 16)[axis] - position(old_scene, 16)[axis]
            self.assertAlmostEqual(ap_shift, scene_shift, delta=0.0001)
        for obj in (8, 13, 14):
            self.assertEqual(self.properties_except(ap,obj),self.properties_except(old_ap,obj))
        for obj in range(1, len(old_scene.chunks) + 1):
            if obj != 16:
                self.assertEqual(self.properties_except(scene,obj),self.properties_except(old_scene,obj))

    def test_native_triss_voice_actor_and_scene_events_are_not_replaced(self):
        native = BundleCatalog(self.game / 'content/content0/bundles')
        path = r'dlc\bob\data\quests\main_quests\quest_files\q705_epilog\scenes\q705_20b_triss_visit_vineyard.w2scene'
        self.assertNotIn(path, self.resources)
        scene = Resource(native.extract(path))
        self.assertEqual(scene.names[integer(scene, 605, 'id')], 'TRISS')
        tags = scene.prop(605, 'actorTags').data
        self.assertEqual([scene.names[i] for i in struct.unpack_from('<'+'H'*tags[0], tags, 1)], ['q705_triss'])
        phase = Resource(native.extract(r'dlc\bob\data\quests\bob_quest_npc_default_dialogues.w2phase'))
        tags = phase.prop(194, 'actorTags').data
        self.assertEqual([phase.names[i] for i in struct.unpack_from('<'+'H'*tags[0], tags, 1)], ['q705_triss'])

    def test_streamed_second_furniture_matches_native_scene_relative_placement(self):
        r, old = self.resource(DECO_LAYER), Resource(self.originals[DECO_LAYER])
        self.assertEqual(r.chunk(3).data, old.chunk(3).data, 'Yen baked sector must remain unchanged')
        self.assertEqual(self.properties_except(r,2),self.properties_except(old,2))
        self.assertEqual(len(r.chunks), len(old.chunks) + 4)
        raw, meshes, objects, start = sector_objects(old)
        metadata = Metadata((self.game / 'content/metadata.store').read_bytes())
        hashes = {struct.unpack('<qQ', row)[0] & 0xffffffffffffffff: struct.unpack('<qQ', row)[1]
                  for row in metadata.sections[6]}
        original_anchor = Resource(self.originals[ANCHOR_LAYER])
        new_anchor = self.resource(ANCHOR_LAYER)
        p0 = struct.unpack_from('<3f', original_anchor.prop(16, 'transform').data, 1)
        p1 = struct.unpack_from('<3f', new_anchor.prop(16, 'transform').data, 1)
        shift = [b-a for a,b in zip(p0,p1)]
        def mesh_corners(index):
            off = start + objects[index][3]
            basis = struct.unpack_from('<9f',raw,off)
            origin = struct.unpack_from('<3f',raw,off+36)
            bounds = meshes[struct.unpack_from('<H',raw,off+56)[0]][:6]
            return [tuple(origin[a]+sum(v[i]*basis[i*3+a] for i in range(3)) for a in range(3))
                    for v in [(x,y,z) for x in (bounds[0],bounds[3]) for y in (bounds[1],bounds[4]) for z in (bounds[2],bounds[5])]]
        old_chair = mesh_corners(1)
        new_chair = [tuple(p[a]+shift[a] for a in range(3)) for p in old_chair]
        self.assertTrue(any(max(p[a] for p in old_chair)<min(p[a] for p in new_chair)
                            or max(p[a] for p in new_chair)<min(p[a] for p in old_chair) for a in range(3)),
                        'Chair world-space bounds must not overlap')
        inner_guids = set()
        for entity, source_index in zip(range(4,8), (1,3,5,6)):
            self.assertEqual(r.kind(entity), 'CEntity')
            t = r.prop(entity, 'transform').data
            position = struct.unpack_from('<3f', t, 1)
            descriptor = objects[source_index]
            source_offset = start + descriptor[3]
            old_position = struct.unpack_from('<3f', raw, source_offset+36)
            for axis in range(3):
                self.assertAlmostEqual(position[axis]-old_position[axis], shift[axis], delta=0.0001)
            # Independent streamed entities do not belong to the baked sector.
            # Native world CLayerInfo 6696 has no bounding box; this quest layer
            # is loaded explicitly. Keep the furniture local to the native site.
            self.assertLess(math.dist(position, old_position), 7.0)
            self.assertTrue(all(math.isfinite(v) for v in position))
            # Reconstruct the runtime entity's basis independently and compare
            # it to the cooked source, including the table/jug's native scale.
            rx,ry,rz = map(math.radians, struct.unpack_from('<3f', t, 13))
            sx,sy,sz = struct.unpack_from('<3f', t, 25)
            cx,cy,cz,snx,sny,snz = math.cos(rx),math.cos(ry),math.cos(rz),math.sin(rx),math.sin(ry),math.sin(rz)
            basis = [cy*cz*sx, cy*snz*sx, -sny*sx,
                     (snx*sny*cz-cx*snz)*sy,(snx*sny*snz+cx*cz)*sy,snx*cy*sy,
                     (cx*sny*cz+snx*snz)*sz,(cx*sny*snz-snx*cz)*sz,cx*cy*sz]
            for actual,expected in zip(basis,struct.unpack_from('<9f',raw,source_offset)):
                self.assertAlmostEqual(actual,expected,delta=0.00001)
            data = r.prop(entity, 'streamingDataBuffer').data
            self.assertEqual(struct.unpack_from('<I',data)[0],len(data)-4)
            inner = Resource(data[4:]);self.assertEqual(inner.build(),data[4:])
            self.assertEqual(len(inner.chunks),1)
            self.assertEqual(inner.kind(1),'CStaticMeshComponent')
            self.assertEqual(integer(inner,1,'mesh'),-1)
            path_offset,kind,flags = struct.unpack('<IHH',inner.table_data[2])
            path = inner.table_data[0][path_offset:inner.table_data[0].index(b'\0',path_offset)].decode()
            mesh_index = struct.unpack_from('<H',raw,source_offset+56)[0]
            fid = hashes[meshes[mesh_index][6]]
            self.assertEqual(path,metadata.string(struct.unpack_from('<I',metadata.sections[0][fid])[0]))
            self.assertEqual((inner.names[kind],flags),('CMesh',0))
            guid = inner.prop(1,'guid').data
            self.assertNotIn(guid,inner_guids);inner_guids.add(guid)
            self.assertEqual(inner.prop(1,'transform').data,b'\x01'+struct.pack('<3f',0,0,0))
            flags = inner.prop(1,'drawableFlags').data
            flag_names = {inner.names[i] for i in struct.unpack('<'+'H'*(len(flags)//2),flags)}
            self.assertTrue({'DF_IsVisible','DF_CastShadows'} <= flag_names)
            self.assertEqual(inner.names[integer(inner,1,'pathLibCollisionType')],'PLC_Dynamic')

    def test_layer_component_references_and_guids_resolve_after_entity_cloning(self):
        for path in (AP_LAYER,TRIGGER_LAYER,DECO_LAYER,NATIVE_AP_LAYER,NATIVE_TRIGGER_LAYER):
            r,old = self.resource(path),Resource(self.originals[path])
            guid_set = {p.data for obj in range(1,len(old.chunks)+1) for p in old.props(obj) if old.names[p.name]=='guid'}
            entities = r.prop(1,'entities').data
            listed = struct.unpack_from('<'+'I'*struct.unpack_from('<I',entities)[0],entities,4)
            for obj in range(len(old.chunks)+1,len(r.chunks)+1):
                for prop in r.props(obj):
                    if r.names[prop.name]=='guid':
                        self.assertNotIn(prop.data,guid_set);guid_set.add(prop.data)
                if r.chunk(obj).parent!=1:continue
                self.assertIn(obj,listed)
                _,end = read_properties(r.chunk(obj).data,1)
                tail = r.chunk(obj).data[end:]
                self.assertEqual(tail[:8],b'\0'*8)
                count,pos = read_vlq(tail,8)
                for i in range(count):
                    target = struct.unpack_from('<I',tail,pos+i*4)[0]
                    self.assertGreater(target,len(old.chunks))
                    self.assertEqual(r.chunk(target).parent,obj)

    def test_triss_bed_route_uses_native_guest_stairs_without_changing_yen_or_ciri(self):
        r,old = self.resource(AP_LAYER),Resource(self.originals[AP_LAYER])
        for obj in (11,12,17,18):
            excluded = ('guid','tags') if obj == 17 else ('guid',)
            self.assertEqual(self.properties_except(r,obj,excluded),self.properties_except(old,obj,excluded))
        points = path_world_points(r,21,22)
        guest_position = struct.unpack_from('<3f',r.prop(6,'transform').data,1)
        chair_position = struct.unpack_from('<3f',r.prop(15,'transform').data,1)
        self.assertLess(math.dist(points[-1],guest_position),1.0)
        self.assertLess(math.dist(points[0],chair_position),2.0)
        ciri = path_world_points(old,11,12)
        sorceress = path_world_points(old,17,18)
        self.assertEqual(len(points),1+17+len(ciri[25:]))
        for actual,expected in zip(points[1:18],sorceress[:17]):
            self.assertLess(math.dist(actual,expected),0.0001)
        for actual,expected in zip(points[18:],ciri[25:]):
            self.assertLess(math.dist(actual,expected),0.0001)

    def test_triss_own_dialogue_trigger_has_consistent_world_polygon_and_bounds(self):
        r,old = self.resource(TRIGGER_LAYER),Resource(self.originals[TRIGGER_LAYER])
        for obj in range(2,len(old.chunks)+1):
            excluded = ('guid','tags') if obj == 8 else ('guid',)
            self.assertEqual(self.properties_except(r,obj,excluded),self.properties_except(old,obj,excluded))
        tag = r.prop(14,'tags').data
        self.assertEqual(r.names[struct.unpack_from('<H',tag,1)[0]],TRISS_TRIGGER)
        self.assertEqual(r.prop(15,'localPoints').data,old.prop(9,'localPoints').data)
        old_points = inline_array(old.prop(9,'worldPoints').data)
        new_points = inline_array(r.prop(15,'worldPoints').data)
        for old_point,new_point in zip(old_points,new_points):
            for axis,delta in zip(['X','Y','Z'],OFFSET):
                before = struct.unpack('<f',field(old,old_point,axis).data)[0]
                after = struct.unpack('<f',field(r,new_point,axis).data)[0]
                self.assertAlmostEqual(after-before,delta,delta=0.0001)
        old_box = fields(old,old.prop(9,'boundingBox').data)
        new_box = fields(r,r.prop(15,'boundingBox').data)
        for before,after in zip(old_box,new_box):
            for axis,delta in zip(['X','Y','Z'],OFFSET):
                v0 = struct.unpack('<f',field(old,fields(old,before.data),axis).data)[0]
                v1 = struct.unpack('<f',field(r,fields(r,after.data),axis).data)[0]
                self.assertAlmostEqual(v1-v0,delta,delta=0.0001)

    def test_new_chair_avoids_native_flower_beds(self):
        native = BundleCatalog(self.game / 'content/content0/bundles')
        furniture = self.resource(DECO_LAYER)
        x, y, z = struct.unpack_from('<3f', furniture.prop(4, 'transform').data, 1)
        clearance, instances = math.inf, 0
        for cell_x in (-448, -384, -320):
            for cell_y in (-832, -768):
                path = rf'dlc\bob\data\levels\bob\source_foliage\foliage_{cell_x:.2f}_{cell_y:.2f}.flyr'
                resource = Resource(native.extract(path))
                raw = resource.chunk(1).data
                _, pos = read_properties(raw, 1)
                for radius in (2.2, .8):
                    groups, pos = read_vlq(raw, pos)
                    for _ in range(groups):
                        handle = struct.unpack_from('<i', raw, pos)[0]; pos += 4
                        self.assertLess(handle, 0)
                        offset = struct.unpack_from('<I', resource.table_data[2], (-handle-1)*8)[0]
                        name = resource.table_data[0][offset:resource.table_data[0].index(b'\0', offset)].decode('utf-8')
                        count, pos = read_vlq(raw, pos)
                        for _ in range(count):
                            px, py, pz, _, _, _ = struct.unpack_from('<6f', raw, pos); pos += 24
                            if 'green_low' in name or abs(pz-z)>2.5 or math.hypot(px-x, py-y)>10:
                                continue
                            instances += 1
                            vx, vy = px-x, py-y
                            lx, ly = vx*.62866765-vy*.77767408, vx*.77767408+vy*.62866765
                            gap = math.hypot(max(abs(lx)-1.15, 0), max(abs(ly)-.55, 0))-radius
                            clearance = min(clearance, gap)
                self.assertEqual(pos, len(raw))
        self.assertGreater(instances, 20)
        self.assertGreater(clearance, .5, 'Chair footprint overlaps native shrub/flower exclusion zones')

    def test_single_romance_native_communities_and_triss_cycle_are_retained(self):
        for path in [TRISS_HOME,YEN_HOME]:
            r,old = self.resource(path),Resource(self.originals[path])
            before = inline_array(old.prop(1,'storyPhaseTimetable').data)
            after = inline_array(r.prop(1,'storyPhaseTimetable').data)
            self.assertGreaterEqual(len(after),len(before))
            for native,current in zip(before,after):
                self.assertEqual(encode_properties(native),encode_properties(current))
            old_table = inline_array(old.prop(1,'communityTable').data)
            new_table = inline_array(r.prop(1,'communityTable').data)
            for native,current in zip(old_table,new_table):
                old_phases = inline_array(field(old,native,'storyPhases').data)
                new_phases = inline_array(field(r,current,'storyPhases').data)
                for a,b in zip(old_phases,new_phases):
                    self.assertEqual(encode_properties(a),encode_properties(b))
        house,old = self.resource(HOUSE),Resource(self.originals[HOUSE])
        # This includes both native bed-route parameter objects with parent=0.
        for obj in list(range(22,52))+[158,165,246,254]:
            self.assertEqual(house.chunk(obj).data,old.chunk(obj).data,obj)
        for triss,yen in [(True,False),(False,True)]:
            facts = romance(triss,yen)
            native_path = walk_quest(old,214,facts,{5})
            current_path = walk_quest(house,214,facts,{5})
            kinds = {'CQuestStoryPhaseSetterBlock','CQuestSceneBlock'}
            self.assertEqual([i for i in current_path if house.kind(i) in kinds],
                             [i for i in native_path if old.kind(i) in kinds])

    def test_single_manor_objects_furniture_and_route_geometry_remain_native(self):
        self.assertFalse(NATIVE_ANCHOR_LAYER in self.resources,'Native manor dialogset layer must not be overridden')
        self.assertFalse(NATIVE_DECO_LAYER in self.resources,'Native garden furniture layer must not be overridden')
        for path in [NATIVE_AP_LAYER,NATIVE_TRIGGER_LAYER]:
            r,old = self.resource(path),Resource(self.originals[path])
            for obj in range(2,len(old.chunks)+1):
                self.assertEqual(r.chunk(obj).data,old.chunk(obj).data,(path,obj))
        ap = self.resource(NATIVE_AP_LAYER)
        for entity,component in [(21,22),(23,24)]:
            self.assertEqual(path_world_points(ap,entity,component),path_world_points(ap,17,18))
        trigger = self.resource(NATIVE_TRIGGER_LAYER)
        for component in [15,17]:
            for key in ['localPoints','worldPoints','boundingBox']:
                self.assertEqual(trigger.prop(component,key).data,trigger.prop(9,key).data)

    def test_dual_community_phases_target_only_the_dual_layer_and_guest_bed(self):
        for path in [TRISS_HOME,YEN_HOME]:
            r = self.resource(path)
            rows = inline_array(r.prop(1,'storyPhaseTimetable').data)
            native_rows = {r.names[int.from_bytes(field(r,row,'name').data,'little')]:row
                           for row in rows if r.names[int.from_bytes(field(r,row,'name').data,'little')] in DUAL_PHASES}
            dual_rows = {r.names[int.from_bytes(field(r,row,'name').data,'little')]:row
                         for row in rows if r.names[int.from_bytes(field(r,row,'name').data,'little')] in DUAL_PHASES.values()}
            self.assertEqual(set(dual_rows),set(DUAL_PHASES.values()))
            native_layer = next(name for name in r.names if 'geralt_house' in name and ';' in name)
            dual_layer = next(name for name in r.names if 'dual_manor' in name and ';' in name)
            native_id = struct.pack('<H',r.names.index(native_layer))
            dual_id = struct.pack('<H',r.names.index(dual_layer))
            for phase,row in dual_rows.items():
                raw = encode_properties(row)
                # Match the complete CName field header, rather than arbitrary
                # two-byte sequences inside a serialized timetable.
                header = struct.pack('<HHI',r.names.index('layerName'),r.names.index('CName'),6)
                self.assertIn(header+dual_id,raw)
                self.assertNotIn(header+native_id,raw)
            native_cycle = encode_properties(native_rows['q705_cycle'])
            dual_cycle = encode_properties(dual_rows[DUAL_PHASES['q705_cycle']])
            header = struct.pack('<HHI',r.names.index('apTags'),r.names.index('TagList'),7)+b'\1'
            self.assertIn(header+struct.pack('<H',r.names.index('q705_ap_sleep_sorceress')),native_cycle)
            expected = 'q705_ap_sleep_guest' if path == TRISS_HOME else 'q705_ap_sleep_sorceress'
            self.assertIn(header+struct.pack('<H',r.names.index(expected)),dual_cycle)

    def test_manor_layout_selection_is_gated_by_both_romances_on_entry_and_reload(self):
        def layer_names(data):
            count = struct.unpack_from('<I',data)[0]
            pos,result = 4,[]
            for _ in range(count):
                length,start = read_vlq(data,pos)
                self.assertLessEqual(length,0)
                pos = start-length
                result.append(data[start:pos].decode('utf-8'))
            self.assertEqual(pos,len(data))
            return result
        for path,start,stop in [(HOUSE,16,20),(BOB_FIX,440,439)]:
            r = self.resource(path)
            for triss,yen in [(False,False),(True,False),(False,True),(True,True)]:
                with self.subTest(path=path,triss=triss,yen=yen):
                    facts=romance(triss,yen)|{'q705_triss_house_met':1,'q705_yen_first_met':1}
                    walked = walk_quest(r,start,facts,{stop})
                    state = {}
                    for obj in walked:
                        if r.kind(obj) != 'CQuestLayersHiderBlock':
                            continue
                        props = {r.names[p.name]:p.data for p in r.props(obj)}
                        shown = layer_names(props['layersToShow']) if 'layersToShow' in props else []
                        hidden = layer_names(props['layersToHide']) if 'layersToHide' in props else []
                        if DUAL_GROUP in shown+hidden:
                            self.assertEqual(props['syncOperation'],b'\1')
                        state.update({name:True for name in shown})
                        state.update({name:False for name in hidden})
                    if path==HOUSE and not(triss and yen):
                        self.assertFalse(state.get(DUAL_GROUP,False))
                        continue
                    self.assertEqual(state.get(DUAL_GROUP),triss and yen)
                    for group in NATIVE_SPATIAL_GROUPS:
                        self.assertEqual(state.get(group),not(triss and yen))
                    if triss and yen:
                        self.assertFalse(state[NATIVE_DECO_GROUP])

    def test_reload_reselects_native_or_dual_community_phases_for_existing_saves(self):
        r = self.resource(BOB_FIX)
        for triss,yen in [(False,False),(True,False),(False,True),(True,True)]:
            facts=romance(triss,yen)|{'q705_triss_house_met':1,'q705_yen_first_met':1}
            path = walk_quest(r,440,facts,{439})
            phases = {}
            for block in path:
                for obj,c in enumerate(r.chunks,1):
                    if c.parent != block or r.kind(obj) != 'CActivateStoryPhase':
                        continue
                    index = int.from_bytes(r.prop(obj,'spawnset').data,'little')-1
                    offset,kind,flags = struct.unpack_from('<IHH',r.table_data[2],index*8)
                    self.assertEqual((r.names[kind],flags),('CCommunity',4))
                    strings = r.table_data[0]
                    depot = strings[offset:strings.index(b'\0',offset)].decode('utf-8')
                    phases[depot] = r.names[integer(r,obj,'phase')]
            expected_phase = DUAL_PHASES['q705_cycle'] if triss and yen else 'q705_cycle'
            self.assertEqual(phases,{actor:expected_phase for actor,enabled in [(TRISS_HOME,triss),(YEN_HOME,yen)] if enabled})

    def test_dual_world_group_is_registered_hidden_and_preserves_other_world_data(self):
        r,old = self.resource(WORLD),Resource(self.originals[WORLD])
        group = next(i for i in range(1,len(r.chunks)+1) if r.kind(i)=='CLayerGroup'
                     and read_ws_string(r.prop(i,'name').data)=='dual_manor')
        self.assertEqual(r.prop(group,'isVisibleOnStart').data,b'\0')
        world,parent,children,infos = group_tail(r,group)
        self.assertEqual((world,children,len(infos)),(1,[],4))
        before = group_tail(old,parent)
        after = group_tail(r,parent)
        self.assertEqual(after,(before[0],before[1],before[2]+[group],before[3]))
        paths = set()
        for obj in infos:
            paths.add(read_ws_string(r.prop(obj,'depotFilePath').data))
            _,end = read_properties(r.chunk(obj).data,1)
            self.assertEqual(r.chunk(obj).data[end:],struct.pack('<I',group))
        self.assertEqual(paths,set(DUAL_LAYER_SOURCES))
        for obj in range(1,len(old.chunks)+1):
            if obj != parent:
                self.assertEqual(r.chunk(obj).data,old.chunk(obj).data,obj)

    def test_existing_save_migration_replaces_the_native_terminal_pause(self):
        r,old = self.resource(BOB_FIX),Resource(self.originals[BOB_FIX])
        self.assertEqual(old.kind(10),'CQuestPauseConditionBlock')
        self.assertEqual(r.kind(10),'CQuestDeletionMarkerBlock')
        guid = old.prop(10,'guid').data
        marker_guids=r.prop(10,'guids').data
        self.assertEqual(struct.unpack_from('<I',marker_guids)[0],2)
        self.assertIn(guid,[marker_guids[4:20],marker_guids[20:36]])
        self.assertFalse(any(p.data==guid for i in range(1,len(r.chunks)+1) for p in r.props(i)
                             if r.names[p.name]=='guid'))
        targets = r.connections(10)[0][1]
        self.assertEqual(len(targets),2)
        stub = next(obj for obj,_ in targets if r.kind(obj)=='CQuestPauseConditionBlock')
        self.assertEqual(read_ws_string(r.prop(stub,'name').data),read_ws_string(old.prop(10,'name').data))
        entered = next(obj for obj,_ in targets if r.kind(obj)=='CQuestFactsDBChangingBlock')
        self.assertEqual(read_ws_string(r.prop(entered,'factID').data),'dr_manor_layout_split_v2')
        phase = r.connections(entered)[0][1][0][0]
        self.assertEqual(r.kind(phase),'CQuestPhaseBlock')
        graph = integer(r,phase,'embeddedGraph')
        start = next(i for i,c in enumerate(r.chunks,1) if c.parent==graph and r.kind(i)=='CQuestPhaseInputBlock')
        end = next(i for i,c in enumerate(r.chunks,1) if c.parent==graph and r.kind(i)=='CQuestPhaseOutputBlock')
        for triss,yen in [(False,False),(True,False),(False,True),(True,True)]:
            facts=romance(triss,yen)|{'q705_triss_house_met':1,'q705_yen_first_met':1}
            path = walk_quest(r,start,facts,{end})
            self.assertIn(end,path)
            self.assertTrue(all(r.chunk(obj).parent==graph for obj in path))
            actions = [obj for obj in path if r.kind(obj)=='CQuestStoryPhaseSetterBlock']
            self.assertEqual(len(actions),int(triss or yen))

    def test_manor_migration_waits_for_the_corresponding_welcome_before_residency(self):
        r=self.resource(BOB_FIX)
        for triss,yen in [(False,False),(True,False),(False,True),(True,True)]:
            for triss_met,yen_met in [(0,0),(1,0),(0,1),(1,1)]:
                with self.subTest(triss=triss,yen=yen,triss_met=triss_met,yen_met=yen_met):
                    facts=romance(triss,yen)|{'q705_triss_house_met':triss_met,'q705_yen_first_met':yen_met,
                                              'q705_completed':1,'witcher3_game_finished':1}
                    path=walk_quest(r,440,facts,{439})
                    spawns=[obj for obj in path if r.kind(obj)=='CQuestStoryPhaseSetterBlock']
                    ready=(triss_met and yen_met) if triss and yen else triss_met if triss else yen_met if yen else False
                    self.assertEqual(len(spawns),int(bool(ready)))
                    shown=[obj for obj in path if any(r.names[p.name]=='layersToShow' and DUAL_GROUP.encode() in p.data for p in r.props(obj))]
                    self.assertEqual(bool(shown),bool(triss and yen and triss_met and yen_met))

    def test_welcomes_keep_native_layers_and_spawn_phases_until_the_offscreen_residency_transition(self):
        r,old=self.resource(HOUSE),Resource(self.originals[HOUSE])
        self.assertEqual(r.connections(199),[('Out',[(200,'Input')])])
        self.assertEqual(r.prop(199,'layersToShow').data,old.prop(199,'layersToShow').data)
        self.assertEqual(r.prop(199,'layersToHide').data,struct.pack('<I',1)+__import__('redio').ws_string(DUAL_GROUP))
        for triss,yen in [(True,True),(True,False),(False,True)]:
            path=walk_quest(r,214,romance(triss,yen),{5})
            actions=[i for block in path for i,c in enumerate(r.chunks,1)
                     if c.parent==block and r.kind(i)=='CActivateStoryPhase']
            self.assertEqual(len(actions),int(triss)+int(yen))
            self.assertEqual([r.names[integer(r,i,'phase')] for i in actions],['q705_house']*len(actions))
            self.assertFalse(any(DUAL_GROUP.encode() in p.data for obj in path for p in r.props(obj)
                                 if r.names[p.name] in ['layersToShow','layersToHide']))
        path=walk_quest(r,16,romance(True,True),{20})
        wait=next(obj for obj in path if r.kind(obj)=='CQuestPauseConditionBlock')
        layout=next(obj for obj in path if any(r.names[p.name]=='layersToShow' and DUAL_GROUP.encode() in p.data for p in r.props(obj)))
        spawn=next(obj for obj in path if r.kind(obj)=='CQuestStoryPhaseSetterBlock')
        self.assertLess(path.index(wait),path.index(layout))
        self.assertLess(path.index(layout),path.index(spawn))

    def test_derived_layers_have_distinct_guids_and_consistent_path_hashes(self):
        metadata = Metadata((self.output/'Mods/modDualRomanceNoTango/content/metadata.store').read_bytes())
        for path in DUAL_LAYER_SOURCES:
            r,old = self.resource(path),Resource(self.originals[path])
            def guids(resource):
                return [p.data for obj in range(1,len(resource.chunks)+1) for p in resource.props(obj)
                        if resource.names[p.kind]=='CGUID']
            ids = guids(r)
            self.assertEqual(len(ids),len(set(ids)))
            self.assertFalse(set(ids)&set(guids(old)))
            fid = metadata.by_path[path]
            self.assertEqual(metadata.hashes[fid]&0xffffffffffffffff,fnv64_path(path))
        native = Metadata((self.game/'content/metadata.store').read_bytes())
        for path in [WORLD,HOUSE,TRISS_HOME]:
            self.assertEqual(native.hashes[native.by_path[path]]&0xffffffffffffffff,fnv64_path(path))

    def test_romance_fact_mutations_are_unchanged(self):
        # No cheat that periodically erases/re-adds a romance, no automatic
        # backfill of failed choices, and no new deletion of romance facts.
        for name in PATHS:
            r = self.resource(name)
            old = Resource(self.originals[name])
            def mutations(resource):
                result = []
                for obj in range(1, len(resource.chunks) + 1):
                    if resource.kind(obj) == 'CQuestFactsDBChangingBlock':
                        fact = read_ws_string(resource.prop(obj, 'factID').data)
                        if fact in ('q309_triss_lover', 'q309_triss_stayed', 'sq202_yen_girlfriend'):
                            result.append((fact, integer(resource, obj, 'value')))
                return sorted(result)
            self.assertEqual(mutations(r), mutations(old))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='dual-romance-', dir=Path(__file__).resolve().parent.parent) as temporary:
        output = Path(temporary)
        resources, originals, _ = build(args.game, output)
        ModChecks.resources, ModChecks.originals = resources, originals
        ModChecks.game, ModChecks.output = Path(args.game), output
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ModChecks))
        report = dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                      passed=result.wasSuccessful(), runtime_validated=False,
                      scope='Native resource roundtrip, CRC, container/index, branch traversal, scene links and activities')
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        raise SystemExit(0 if result.wasSuccessful() else 1)
