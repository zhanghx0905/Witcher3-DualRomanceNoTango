# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
"""Separate dual-romance epilogue staging on the existing third tavern stool.

The original single-romance inputs, sections and community timetable remain
intact. Scene copies remap both ordinary references and buffered timeline IDs.
"""
from __future__ import annotations
import copy
import math
import struct
import uuid
from redio import Chunk, Property, encode_properties, read_properties, read_vlq, read_ws_string, u32, ws_string
from manor_layout import append_entity, fields, field, inline_array, encode_array

TAVERN_AP = r'levels\prolog_village_winter\quests\q504_ciri_empress\tavern\actionpoints\in_tavern.w2l'
TAVERN_SCENE = r'quests\epilogues\quest_files\q504_ciri_empress\scenes\q504_01_ciri_start.w2scene'
TAVERN_ANCHOR = r'levels\prolog_village_winter\quests\q504_ciri_empress\tavern\dialogsets\tavern.w2l'
TAVERN_STOOLS = r'levels\prolog_village_winter\village\tavern\decorations_ns.w2l'
DUAL_PHASE = 'dr_q504_triss_at_shared_table'
DUAL_AP = 'dr_q504_ap_triss_at_shared_table'
DUAL_INPUT = 'dr_dual_lovers'
DUAL_DIALOGSET = 'dr_with_both'
DUAL_CAMERA = 'dr_three_at_shared_table'

# Native, already placed furniture; coordinates were read from winter layers.
OLD_TRISS_STOOL = (44.249629974365234, 2.6747989654541016, 2.2829959392547607)
YEN_STOOL = (49.70884323120117, -0.6504124402999878, 2.368649959564209)
SHARED_STOOL = (48.74702453613281, -2.1616556644439697, 2.2829959392547607)
SHARED_YAW = 305.0
SCENE_ORIGIN = (45.930503845214844, -2.5115160942077637, 2.413947820663452)
SCENE_YAW = 7.119987487792969


def name(r, raw):
    return r.names[int.from_bytes(raw, 'little')]


def set_or_add(r, obj, key, kind, data):
    props, end = read_properties(r.chunk(obj).data, 1)
    found = next((p for p in props if r.names[p.name] == key), None)
    if found:
        found.data = data
    else:
        props.append(Property(r.name_id(key), r.name_id(kind), data))
    r.chunk(obj).data = b'\0' + encode_properties(props) + r.chunk(obj).data[end:]


def point_to_world(point):
    cs, sn = math.cos(math.radians(SCENE_YAW)), math.sin(math.radians(SCENE_YAW))
    return (SCENE_ORIGIN[0] + cs * point[0] - sn * point[1],
            SCENE_ORIGIN[1] + sn * point[0] + cs * point[1], SCENE_ORIGIN[2] + point[2])


def point_to_local(point):
    x, y, z = (v - o for v, o in zip(point, SCENE_ORIGIN))
    cs, sn = math.cos(math.radians(SCENE_YAW)), math.sin(math.radians(SCENE_YAW))
    return (cs*x + sn*y, -sn*x + cs*y, z)


def move_seated_root(point, old_stool, old_yaw):
    dx, dy = point[0]-old_stool[0], point[1]-old_stool[1]
    cs, sn = math.cos(math.radians(SHARED_YAW-old_yaw)), math.sin(math.radians(SHARED_YAW-old_yaw))
    return (SHARED_STOOL[0]+cs*dx-sn*dy, SHARED_STOOL[1]+sn*dx+cs*dy,
            SHARED_STOOL[2]+point[2]-old_stool[2])


def timeline_events(r, obj):
    raw = r.chunk(obj).data
    _, end = read_properties(raw, 1)
    count = struct.unpack_from('<I', raw, end)[0]
    pos, result = end+4, []
    for _ in range(count):
        size, kind = struct.unpack_from('<IH', raw, pos)
        props = fields(r, raw[pos+6:pos+size])
        result.append((kind, props))
        pos += size
    assert pos == len(raw)
    return end, result


def set_timeline(r, obj, events):
    _, end = read_properties(r.chunk(obj).data, 1)
    tail = bytearray(u32(len(events)))
    for kind, props in events:
        body = b'\0'+encode_properties(props)
        tail += struct.pack('<IH', len(body)+6, kind)+body
    r.chunk(obj).data = r.chunk(obj).data[:end]+bytes(tail)


def _nested_props(kind, raw):
    if kind.startswith('array:2,0,') and not kind.startswith('array:2,0,ptr:'):
        try:
            return 'array', inline_array(raw)
        except (AssertionError, struct.error, IndexError):
            return None, []
    if raw[:1] == b'\0' and kind not in ['String', 'CGUID', 'TagList']:
        try:
            return 'struct', [fields(None, raw)]
        except (AssertionError, struct.error, IndexError):
            return None, []
    return None, []


def clone_scene_tree(r, obj, label):
    """Clone scene-owned chunks including buffered event and variant references."""
    owned, queue = [], [obj]
    while queue:
        parent = queue.pop(0)
        if parent in owned:
            continue
        owned.append(parent)
        queue.extend(i for i, chunk in enumerate(r.chunks, 1) if chunk.parent == parent)
        if parent == obj and r.kind(obj) == 'CStorySceneSection':
            # Retail sections reference several objects parented to the scene
            # root, rather than to the section. Copy this explicit closure too.
            for key in ['variants', 'sceneElements', 'eventsInfo']:
                raw = r.prop(obj, key).data
                count = struct.unpack_from('<I', raw)[0]
                queue.extend(struct.unpack_from('<'+'I'*count, raw, 4))
    mapping = {old: len(r.chunks)+index+1 for index, old in enumerate(owned)}
    guids, element_ids = {}, {}

    def collect(props):
        for prop in props:
            kind = r.names[prop.kind]
            if kind == 'CGUID' and prop.data != b'\0'*16:
                guids[prop.data] = uuid.uuid5(uuid.NAMESPACE_URL, f'dualromance/{label}/{prop.data.hex()}').bytes_le
            _, nested = _nested_props(kind, prop.data)
            for item in nested:
                collect(item)

    for old in owned:
        collect(r.props(old))
        for prop in r.props(old):
            if r.names[prop.name] == 'elementID':
                value = read_ws_string(prop.data)
                element_ids[value] = 'dr_dual_'+value
        if r.kind(old) == 'CStorySceneSection':
            for _, props in timeline_events(r, old)[1]:
                collect(props)

    def remap(props):
        for prop in props:
            kind = r.names[prop.kind]
            if kind == 'CGUID':
                prop.data = guids.get(prop.data, prop.data)
            elif kind == 'String':
                value = read_ws_string(prop.data)
                if value in element_ids:
                    prop.data = ws_string(element_ids[value])
            elif kind.startswith('ptr:') and len(prop.data) == 4:
                value = int.from_bytes(prop.data, 'little', signed=True)
                if value in mapping:
                    prop.data = u32(mapping[value])
            elif kind.startswith('array:2,0,ptr:'):
                count = struct.unpack_from('<I', prop.data)[0]
                values = struct.unpack_from('<'+'I'*count, prop.data, 4)
                prop.data = u32(count)+b''.join(u32(mapping.get(v,v)) for v in values)
            elif kind == 'array:2,0,CGUID':
                count = struct.unpack_from('<I', prop.data)[0]
                prop.data = u32(count)+b''.join(guids.get(prop.data[4+i*16:20+i*16],prop.data[4+i*16:20+i*16]) for i in range(count))
            else:
                mode, nested = _nested_props(kind, prop.data)
                for item in nested:
                    remap(item)
                if mode == 'array':
                    prop.data = encode_array(nested)
                elif mode == 'struct':
                    prop.data = b'\0'+encode_properties(nested[0])

    for old in owned:
        chunk = copy.deepcopy(r.chunk(old))
        chunk.parent = mapping.get(chunk.parent, chunk.parent)
        props, end = read_properties(chunk.data, 1)
        remap(props)
        chunk.data = b'\0'+encode_properties(props)+chunk.data[end:]
        r.chunks.append(chunk)
        if r.kind(old) == 'CStorySceneSection':
            events = copy.deepcopy(timeline_events(r, old)[1])
            for _, fields_ in events:
                remap(fields_)
            set_timeline(r, mapping[old], events)
    return mapping[obj], mapping


def patch_tavern_actionpoint(r, notes):
    new = r.clone_owned(15, 'q504-triss-same-table-actionpoint')
    component = next(i for i,c in enumerate(r.chunks,1) if c.parent == new and r.kind(i)=='CActionPointComponent')
    original = r.prop(15,'transform').data
    old_position = struct.unpack_from('<3f',original,1)
    old_yaw = struct.unpack_from('<3f',original,13)[2]
    position = move_seated_root(old_position, OLD_TRISS_STOOL, old_yaw)
    r.set(new,'transform',b'\x03'+struct.pack('<6f',*position,0,0,SHARED_YAW))
    r.set(new,'tags',b'\1'+struct.pack('<H',r.name_id(DUAL_AP)))
    chunk = r.chunk(new)
    _,end = read_properties(chunk.data,1)
    tail = bytearray(chunk.data[end:])
    assert tail[:8] == b'\0'*8
    count,pos = read_vlq(tail,8)
    assert count == 1 and struct.unpack_from('<I',tail,pos)[0] == 16
    struct.pack_into('<I',tail,pos,component)
    chunk.data = chunk.data[:end]+bytes(tail)
    append_entity(r,new)
    notes.append('Q504 dual romance: independent Triss actionpoint at the existing third stool of Geralt/Yen table; native furniture and other actionpoints untouched.')


def patch_triss_dual_phase(r, notes):
    entries = inline_array(r.prop(1,'storyPhaseTimetable').data)
    original = next(entry for entry in entries if name(r,field(r,entry,'name').data)=='q504_in_tavern')
    duplicate = copy.deepcopy(original)
    field(r,duplicate,'name').data = struct.pack('<H',r.name_id(DUAL_PHASE))
    categories = field(r,duplicate,'actionCategies')
    marker = struct.pack('<HHI',r.name_id('apTags'),r.name_id('TagList'),7)+b'\1'+struct.pack('<H',r.name_id('q504_ap_sorc_sitting_table'))
    replacement = marker[:-2]+struct.pack('<H',r.name_id(DUAL_AP))
    assert categories.data.count(marker)==1
    categories.data = categories.data.replace(marker,replacement)
    r.set(1,'storyPhaseTimetable',encode_array(entries+[duplicate]))

    table = inline_array(r.prop(1,'communityTable').data)
    additions = 0
    for row in table:
        story_phases = next((p for p in row if r.names[p.name]=='storyPhases'),None)
        if not story_phases:
            continue
        phases = inline_array(story_phases.data)
        added=[]
        for phase in phases:
            timetable = next((p for p in phase if r.names[p.name]=='timetableName'),None)
            if not timetable or name(r,timetable.data)!='q504_in_tavern':
                continue
            clone = copy.deepcopy(phase)
            field(r,clone,'guid').data = uuid.uuid5(uuid.NAMESPACE_URL,'dualromance/q504/dual-community-phase').bytes_le
            field(r,clone,'timetableName').data = struct.pack('<H',r.name_id(DUAL_PHASE))
            phase_names = fields(r,field(r,clone,'storyPhaseName').data)
            field(r,phase_names,'tags').data = b'\1'+struct.pack('<H',r.name_id(DUAL_PHASE))
            field(r,clone,'storyPhaseName').data = b'\0'+encode_properties(phase_names)
            added.append(clone)
        additions += len(added)
        story_phases.data = encode_array(phases+added)
    assert additions==1
    r.set(1,'communityTable',encode_array(table))
    notes.append('Q504 Triss community: added a dual-only phase/timetable; original single-romance phase remains unchanged.')


def patch_tavern_scene(r, notes):
    new_input,input_map = clone_scene_tree(r,121,'q504-dual-input')
    section,section_map = clone_scene_tree(r,120,'q504-dual-dialogue')
    dialogset,slot_map = clone_scene_tree(r,355,'q504-dual-dialogset')
    r.set(new_input,'inputName',ws_string(DUAL_INPUT))
    r.set_name(new_input,'dialogsetInstanceName',DUAL_DIALOGSET)
    r.set_int(new_input,'nextLinkElement',section)
    mappings = inline_array(r.prop(new_input,'voicetagMappings').data)
    template = copy.deepcopy(next(row for row in mappings if any(r.names[p.name]=='voicetag' and name(r,p.data)=='YENNEFER' for p in row)))
    field(r,template,'voicetag').data = struct.pack('<H',r.name_id('TRISS'))
    r.set(new_input,'voicetagMappings',encode_array(mappings+[template]))
    r.set(section,'linkedElements',u32(1)+u32(new_input))
    r.set(section,'sectionName',ws_string('q504_01_morons_dual_romance'))
    r.set_int(section,'nextLinkElement',5)
    original_counter = int.from_bytes(r.prop(1,'sectionIDCounter').data,'little')
    r.set_int(section,'sectionId',original_counter+1)
    r.set_int(1,'sectionIDCounter',original_counter+1)
    element_count = sum(any(r.names[p.name]=='elementID' for p in r.props(obj)) for obj in section_map.values())
    r.set_int(1,'elementIDCounter',int.from_bytes(r.prop(1,'elementIDCounter').data,'little')+element_count)
    r.set_name(dialogset,'name',DUAL_DIALOGSET)

    triss_slot = slot_map[358]
    # Use the native sorceress seated pose, calibrated to another existing stool.
    source = copy.deepcopy(r.props(357))
    for p in source:
        key = r.names[p.name]
        if key == 'slotNumber':p.data=u32(3)
        elif key == 'slotName':p.data=struct.pack('<H',r.name_id('slot3'))
        elif key == 'actorName':p.data=struct.pack('<H',r.name_id('TRISS'))
        elif key == 'ID':p.data=uuid.uuid5(uuid.NAMESPACE_URL,'dualromance/q504/triss-scene-slot').bytes_le
        elif key == 'slotPlacement':
            old_local=struct.unpack_from('<3f',p.data,1)
            old_angle=struct.unpack_from('<3f',p.data,13)[2]+SCENE_YAW
            point=move_seated_root(point_to_world(old_local),YEN_STOOL,old_angle)
            p.data=b'\x03'+struct.pack('<6f',*point_to_local(point),0,0,SHARED_YAW-SCENE_YAW)
    r.chunk(triss_slot).data=b'\0'+encode_properties(source)

    cameras=inline_array(r.prop(1,'cameraDefinitions').data)
    new_camera=copy.deepcopy(next(row for row in cameras if name(r,field(r,row,'cameraName').data)=='g_sit_w_girl'))
    field(r,new_camera,'cameraName').data=struct.pack('<H',r.name_id(DUAL_CAMERA))
    field(r,new_camera,'cameraTransform').data=b'\x03'+struct.pack('<6f',3.3,3.1,1.4,0,-6,188)
    field(r,new_camera,'cameraFov').data=struct.pack('<f',50)
    new_camera[:]=[p for p in new_camera if r.names[p.name] not in ['genParam','cameraZoom']]
    field(r,new_camera,'dofIntensity').data=struct.pack('<f',0)
    r.set(1,'cameraDefinitions',encode_array(cameras+[new_camera]))
    _,events=timeline_events(r,section)
    replacements=0
    for kind,props in events:
        if r.names[kind]!='CStorySceneEventCustomCameraInstance':continue
        camera=field(r,props,'customCameraName')
        if name(r,camera.data)=='g_sit_w_girl':
            camera.data=struct.pack('<H',r.name_id(DUAL_CAMERA));replacements+=1
    assert replacements>=1
    set_timeline(r,section,events)
    for key,added in [('controlParts',[new_input,section]),('sections',[section]),('dialogsetInstances',[dialogset])]:
        raw=r.prop(1,key).data;count=struct.unpack_from('<I',raw)[0]
        r.set(1,key,u32(count+len(added))+raw[4:]+b''.join(u32(i) for i in added))
    raw=r.prop(5,'linkedElements').data
    r.set(5,'linkedElements',u32(struct.unpack_from('<I',raw)[0]+1)+raw[4:]+u32(section))
    notes.append('Q504 opening: dual-only input/dialogset with Geralt, Yen and Triss at the same table; native Yen lines retained; one dedicated three-person overview replaces the two-person shot. Single-romance inputs/timelines remain native.')
