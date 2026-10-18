# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
"""Load a separate manor layout only when both romances are present.

Single-romance communities, actionpoints, scenes and scripted cycles use their
retail data. A hidden world layer group supplies the dual layout under the same
actor/placement tags, with the original spatial layers hidden while it is active.
"""
from __future__ import annotations

import copy
import struct
import uuid

from redio import (Chunk, Property, encode_properties, read_properties, read_vlq,
                   read_ws_string, u32, vlq, ws_string)
from manor_layout import (AP_LAYER, ANCHOR_LAYER, TRIGGER_LAYER, DECO_LAYER,
                          TRISS_PATH, TRISS_TRIGGER, append_entity,
                          field, fields, inline_array, encode_array)

WORLD = r'dlc\bob\data\levels\bob\bob.w2w'
YEN_HOME = r'dlc\bob\data\quests\main_quests\quest_files\q705_epilog\spawnsets\q705_yennefer.w2comm'
DUAL_GROUP = r'quests\main_quests\q705_epilog\dual_manor'
DUAL_DEPOT = r'dlc\bob\data\levels\bob' + '\\' + DUAL_GROUP + '\\'
DUAL_AP_LAYER = DUAL_DEPOT + 'guests.w2l'
DUAL_ANCHOR_LAYER = DUAL_DEPOT + 'dialogsets.w2l'
DUAL_TRIGGER_LAYER = DUAL_DEPOT + 'triggers.w2l'
DUAL_DECO_LAYER = DUAL_DEPOT + 'decor.w2l'
DUAL_LAYER_SOURCES = dict(zip(
    [DUAL_AP_LAYER, DUAL_ANCHOR_LAYER, DUAL_TRIGGER_LAYER, DUAL_DECO_LAYER],
    [AP_LAYER, ANCHOR_LAYER, TRIGGER_LAYER, DECO_LAYER]))
NATIVE_SPATIAL_GROUPS = [r'quests\main_quests\q705_epilog\geralt_house' + '\\' + name
                         for name in ['actionpoints', 'dialogsets', 'triggers']]
NATIVE_DECO_GROUP = r'locations\vineyards\east\corvo_bianco\q705_epilog\garden_chair'
DUAL_PHASES = {'q705_house': 'dr_q705_house', 'q705_cycle': 'dr_q705_cycle'}
YEN_PATH = 'dr_q705_yen_native_path'
YEN_TRIGGER = 'dr_q705_yen_native_trigger'
NATIVE_PATH = 'q705_path_sorc_from_szez'
NATIVE_TRIGGER = 'q705_tr_szezlong'


def name(r, data):
    return r.names[int.from_bytes(data, 'little')]


def clone_entity(r,obj,label,tag):
    children = [i for i,c in enumerate(r.chunks,1) if c.parent == obj]
    new = r.clone_owned(obj,label)
    new_children = [i for i,c in enumerate(r.chunks,1) if c.parent == new]
    mapping = dict(zip(children,new_children))
    chunk = r.chunk(new)
    _,end = read_properties(chunk.data,1)
    tail = bytearray(chunk.data[end:])
    assert tail[:8] == b'\0'*8
    count,pos = read_vlq(tail,8)
    assert count == len(children)
    for index in range(count):
        old = struct.unpack_from('<I',tail,pos+4*index)[0]
        struct.pack_into('<I',tail,pos+4*index,mapping[old])
    chunk.data = chunk.data[:end]+tail
    r.set(new,'tags',b'\1'+struct.pack('<H',r.name_id(tag)))
    append_entity(r,new)
    return new


def patch_native_actionpoints(r,notes):
    # Invisible aliases retain native geometry. The legacy Triss tag also lets
    # an AI action saved under the previous release finish on the native route.
    for tag in [YEN_PATH,TRISS_PATH]:
        clone_entity(r,17,'native-path-alias/'+tag,tag)
    notes.append('Single romances: native manor APs and routes retained, with geometry-identical path aliases for saved actions.')


def patch_native_triggers(r,notes):
    for tag in [YEN_TRIGGER,TRISS_TRIGGER]:
        clone_entity(r,8,'native-trigger-alias/'+tag,tag)
    notes.append('Single romances: native dialogue trigger retained, with matching aliases for saved conditions.')


def patch_dual_actionpoint_tags(r):
    r.set(17,'tags',b'\1'+struct.pack('<H',r.name_id(YEN_PATH)))
    clone_entity(r,21,'dual-triss-native-path-name',NATIVE_PATH)


def patch_dual_trigger_tags(r):
    r.set(8,'tags',b'\1'+struct.pack('<H',r.name_id(YEN_TRIGGER)))
    marker = b'\1'+struct.pack('<H',r.name_id(TRISS_TRIGGER))
    shifted = next(i for i in range(1,len(r.chunks)+1)
                   if any(r.names[p.name]=='tags' and p.data==marker for p in r.props(i)))
    clone_entity(r,shifted,'dual-triss-native-trigger-name',NATIVE_TRIGGER)


def rekey_layer(r,path):
    for obj in range(1,len(r.chunks)+1):
        for p in r.props(obj):
            if r.names[p.kind] == 'CGUID':
                key = path+'/'+str(obj)+'/'+r.names[p.name]+'/'+p.data.hex()
                r.set(obj,r.names[p.name],uuid.uuid5(uuid.NAMESPACE_URL,key).bytes_le)


def patch_dual_community(r, notes, actor):
    """Append phases; preserve every retail phase and timetable byte for byte."""
    original = inline_array(r.prop(1, 'storyPhaseTimetable').data)
    additions = []
    canonical = r'quests\main_quests\q705_epilog\geralt_house\actionpoints\guests;dlc\bob\data\levels\bob\bob'
    old_layer = next(value for value in r.names if value.replace('\\\\','\\') == canonical)
    new_layer = DUAL_GROUP + r'\guests;dlc\bob\data\levels\bob\bob'
    if '\\\\' in old_layer:
        new_layer = new_layer.replace('\\','\\\\')

    def replace_names(props):
        for p in props:
            kind = r.names[p.kind]
            if kind == 'CName' and name(r,p.data) == old_layer:
                p.data = struct.pack('<H',r.name_id(new_layer))
            elif kind == 'TagList' and actor == 'triss':
                before = b'\1'+struct.pack('<H',r.name_id('q705_ap_sleep_sorceress'))
                if p.data == before:
                    p.data = b'\1'+struct.pack('<H',r.name_id('q705_ap_sleep_guest'))
            elif kind.startswith('array:2,0,'):
                try:
                    rows = inline_array(p.data)
                except (AssertionError, IndexError, struct.error):
                    continue
                for row in rows:
                    replace_names(row)
                p.data = encode_array(rows)
            elif kind == 'CSLayerName':
                nested = fields(r,p.data)
                replace_names(nested)
                p.data = b'\0'+encode_properties(nested)

    for row in original:
        phase = name(r,field(r,row,'name').data)
        if phase not in DUAL_PHASES:
            continue
        clone = copy.deepcopy(row)
        field(r,clone,'name').data = struct.pack('<H',r.name_id(DUAL_PHASES[phase]))
        replace_names(clone)
        additions.append(clone)
    assert len(additions) == 2
    r.set(1,'storyPhaseTimetable',encode_array(original+additions))
    table = inline_array(r.prop(1,'communityTable').data)
    phases_added = 0
    for row in table:
        phases_prop = next((p for p in row if r.names[p.name]=='storyPhases'),None)
        if phases_prop is None:
            continue
        phases = inline_array(phases_prop.data)
        extra = []
        for phase in phases:
            timetable = name(r,field(r,phase,'timetableName').data)
            if timetable not in DUAL_PHASES:
                continue
            clone = copy.deepcopy(phase)
            field(r,clone,'guid').data = uuid.uuid5(uuid.NAMESPACE_URL,'dualromance/manor/'+actor+'/'+timetable).bytes_le
            field(r,clone,'timetableName').data = struct.pack('<H',r.name_id(DUAL_PHASES[timetable]))
            phase_names = fields(r,field(r,clone,'storyPhaseName').data)
            field(r,phase_names,'tags').data = b'\1'+struct.pack('<H',r.name_id(DUAL_PHASES[timetable]))
            field(r,clone,'storyPhaseName').data = b'\0'+encode_properties(phase_names)
            extra.append(clone)
        phases_added += len(extra)
        phases_prop.data = encode_array(phases+extra)
    assert phases_added == 2
    r.set(1,'communityTable',encode_array(table))
    notes.append(f'Manor {actor}: native welcomes and single-romance phases retained; dual post-welcome resting and daily phases select the dual layout.')


def group_tail(r, obj):
    raw = r.chunk(obj).data
    _, pos = read_properties(raw,1)
    world, parent = struct.unpack_from('<II',raw,pos)
    pos += 8
    groups_count,pos = read_vlq(raw,pos)
    groups = list(struct.unpack_from('<'+'I'*groups_count,raw,pos));pos += 4*groups_count
    infos_count,pos = read_vlq(raw,pos)
    infos = list(struct.unpack_from('<'+'I'*infos_count,raw,pos));pos += 4*infos_count
    assert pos == len(raw)
    return world,parent,groups,infos


def set_group_tail(r,obj,world,parent,groups,infos):
    _,end = read_properties(r.chunk(obj).data,1)
    r.chunk(obj).data = (r.chunk(obj).data[:end]+u32(world)+u32(parent)+vlq(len(groups))
                         +b''.join(u32(v) for v in groups)+vlq(len(infos))+b''.join(u32(v) for v in infos))


def patch_world(r,notes):
    source_group = 9061
    assert read_ws_string(r.prop(source_group,'name').data) == 'geralt_house'
    world,parent,_,_ = group_tail(r,source_group)
    new_group = r.clone_owned(source_group,'dual-manor-world-group')
    r.set(new_group,'name',ws_string('dual_manor'))
    r.set(new_group,'depotPath',ws_string(DUAL_DEPOT))
    r.set(new_group,'isVisibleOnStart',b'\0')
    # idHash is a persistent group identity. Give the new group a unique,
    # deterministic identity instead of reusing the retail group's saved state.
    identity = uuid.uuid5(uuid.NAMESPACE_URL,'dualromance/'+DUAL_GROUP).bytes_le[:8]
    assert all(r.prop(i,'idHash').data != identity for i in range(1,len(r.chunks)+1)
               if r.kind(i)=='CLayerGroup' and i != new_group)
    r.set(new_group,'idHash',identity)
    new_infos = []
    for source,path in zip([9063,9065,9071,6696],DUAL_LAYER_SOURCES):
        obj = r.clone_owned(source,'dual-manor-world-info/'+path)
        r.set(obj,'depotFilePath',ws_string(path))
        r.set(obj,'shortName',ws_string(path.rsplit('\\',1)[-1][:-4]))
        _,end = read_properties(r.chunk(obj).data,1)
        assert len(r.chunk(obj).data)-end == 4
        r.chunk(obj).data = r.chunk(obj).data[:end]+u32(new_group)
        new_infos.append(obj)
    set_group_tail(r,new_group,world,parent,[],new_infos)
    pw,pp,groups,infos = group_tail(r,parent)
    set_group_tail(r,parent,pw,pp,groups+[new_group],infos)
    notes.append('Manor: hidden dual-only world layer group; native spatial/furniture layers remain retail for single romances.')


def strings(values):
    return u32(len(values))+b''.join(ws_string(v) for v in values)


def set_property(r,obj,key,kind,data):
    props,end = read_properties(r.chunk(obj).data,1)
    existing = next((p for p in props if r.names[p.name] == key),None)
    if existing is None:
        props.append(Property(r.name_id(key),r.name_id(kind),data))
    else:
        existing.data = data
    r.chunk(obj).data = b'\0'+encode_properties(props)+r.chunk(obj).data[end:]


def soft_community(r,path):
    for index in range(len(r.table_data[2])//8):
        offset,kind,flags = struct.unpack_from('<IHH',r.table_data[2],index*8)
        value = r.table_data[0][offset:r.table_data[0].index(b'\0',offset)].decode('utf-8')
        if value == path and r.names[kind] == 'CCommunity' and flags == 4:
            return index+1
    offset = len(r.table_data[0])
    r.table_data[0] += path.encode('utf-8')+b'\0'
    r.table_data[2] += struct.pack('<IHH',offset,r.name_id('CCommunity'),4)
    return len(r.table_data[2])//8


def add_phase_setter(r,graph,entries,label,continuation):
    template = next(i for i in range(1,len(r.chunks)+1) if r.kind(i)=='CQuestStoryPhaseSetterBlock')
    action_template = next(i for i in range(1,len(r.chunks)+1) if r.kind(i)=='CActivateStoryPhase')
    def p(key,kind,value):
        return Property(r.name_id(key),r.name_id(kind),value)
    block = len(r.chunks)+1
    actions = list(range(block+1,block+1+len(entries)))
    props = [p('name','String',ws_string(label)),
             p('guid','CGUID',uuid.uuid5(uuid.NAMESPACE_URL,'dualromance/'+label).bytes_le),
             p('cachedConnections','array:2,0,SCachedConnections',u32(0)),
             p('spawnsets','array:2,0,ptr:IQuestSpawnsetAction',u32(len(actions))+b''.join(u32(i) for i in actions))]
    r.chunks.append(Chunk(r.name_id('CQuestStoryPhaseSetterBlock'),r.chunk(template).flags,graph,0,b'\0'+encode_properties(props)))
    for path,phase in entries:
        props = [p('spawnset','soft:CCommunity',struct.pack('<H',soft_community(r,path))),
                 p('phase','CName',struct.pack('<H',r.name_id(phase)))]
        r.chunks.append(Chunk(r.name_id('CActivateStoryPhase'),r.chunk(action_template).flags,block,0,b'\0'+encode_properties(props)))
    r.register(graph,block)
    r.set_connections(block,[('Out',continuation)])
    return block


def add_saved_quest_migration(r,notes):
    """Use the retail bugfix phase's deletion-marker upgrade entry.

    Its terminal pause deliberately stays active in existing saves. Replacing
    that pause with a marker for its old GUID starts a fresh copy of the fix,
    even when the original q705 layer-restoration phase already completed.
    """
    old_pause_guid = r.prop(10,'guid').data
    previous_stub_guids=[uuid.uuid5(uuid.NAMESPACE_URL,'dualromance/manor-layout-v'+str(version)+'-migration-stub/'+old_pause_guid.hex()).bytes_le
                         for version in [1,2]]
    stub = r.clone_owned(10,'manor-layout-v3-migration-stub')
    r.register(2,stub)
    owned = [437]
    for obj in owned:
        owned.extend(i for i,c in enumerate(r.chunks,1) if c.parent == obj)
    before = len(r.chunks)
    phase = r.clone_owned(437,'manor-layout-v3-migration-phase')
    r.register(2,phase)
    mapping = {old:before+index+1 for index,old in enumerate(owned)}
    for old,new in mapping.items():
        if any(r.names[p.name]=='cachedConnections' for p in r.props(old)):
            r.set_connections(new,[(socket,[(mapping.get(target,target),input_name) for target,input_name in targets])
                                   for socket,targets in r.connections(old)])
    r.set(phase,'name',ws_string('Romance-specific manor layout compatibility'))
    entered = r.clone_owned(477,'manor-layout-v3-migration-entered')
    r.register(2,entered)
    r.set(entered,'name',ws_string('Dual manor compatibility entry'))
    r.set(entered,'factID',ws_string('dr_manor_layout_split_v3'))
    set_property(r,entered,'setExactValue','Bool',b'\1')
    r.route(entered,'Out',[(phase,'In')])
    r.chunks[9] = copy.deepcopy(r.chunk(9))
    r.set(10,'guid',uuid.uuid5(uuid.NAMESPACE_URL,'dualromance/manor-layout-v3-marker').bytes_le)
    r.set(10,'guids',u32(3)+old_pause_guid+b''.join(previous_stub_guids))
    r.set_connections(10,[('Out',[(entered,'In'),(stub,'In')])])
    notes.append('Existing-save migration: native terminal-pause deletion marker starts a fresh gated manor fix, including already-completed q705 saves.')


def add_layout_switch(r, graph, source, socket, continuation, yen_test, triss_test, layer_block, label, require_welcomes=False):
    """Use native fact conditions and synchronous layer visibility actions."""
    def clone(obj,suffix):
        result = r.clone_owned(obj,label+'/'+suffix)
        r.register(graph,result)
        return result
    yen = clone(yen_test,'check-yen')
    triss = clone(triss_test,'check-triss')
    dual = clone(layer_block,'dual-layout')
    single = clone(layer_block,'native-layout')
    set_property(r,dual,'layersToShow','array:2,0,String',strings([DUAL_GROUP]))
    set_property(r,dual,'layersToHide','array:2,0,String',strings(NATIVE_SPATIAL_GROUPS+[NATIVE_DECO_GROUP]))
    set_property(r,single,'layersToShow','array:2,0,String',strings(NATIVE_SPATIAL_GROUPS))
    set_property(r,single,'layersToHide','array:2,0,String',strings([DUAL_GROUP]))
    for obj in [dual,single]:
        set_property(r,obj,'syncOperation','Bool',b'\1')
    r.set_connections(yen,[('True',[(triss,'In')]),('False',[(single,'In')])])
    dual_entry = dual
    if require_welcomes:
        for fact in ['q705_triss_house_met','q705_yen_first_met']:
            gate = clone(triss_test,'welcomed/'+fact)
            condition = next(i for i,c in enumerate(r.chunks,1)
                             if c.parent==gate and r.kind(i)=='CQuestFactsDBCondition')
            r.set(gate,'name',ws_string(fact))
            r.set(condition,'factId',ws_string(fact))
            r.set_name(condition,'queryFact','QF_Sum')
            r.set_name(condition,'compareFunc','CF_GreaterEqual')
            r.set_int(condition,'value',1)
            r.set_connections(gate,[('True',[(dual_entry,'In')]),('False',[(single,'In')])])
            dual_entry = gate
    r.set_connections(triss,[('True',[(dual_entry,'In')]),('False',[(single,'In')])])
    r.set_connections(dual,[('Out',continuation)])
    r.set_connections(single,[('Out',continuation)])
    r.route(source,socket,[(yen,'In')])
    return dual,single
