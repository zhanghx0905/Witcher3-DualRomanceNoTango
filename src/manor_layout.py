# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
"""Keep native Triss dialogue/animation staging, with an independent chair.

The second furniture set uses ordinary streamed CStaticMeshComponents, following
the native mq7024 bed's entity/component serialization. It deliberately does not
reuse baked sector occlusion IDs from Yen's furniture. Path curves retain native
outdoor segments and the existing guest-room staircase approach.
"""
from __future__ import annotations

import copy
import math
import struct
import uuid

from redio import Chunk, Property, Resource, encode_properties, read_properties, read_vlq, u32, ws_string

AP_LAYER = r'dlc\bob\data\levels\bob\quests\main_quests\q705_epilog\geralt_house\actionpoints\guests.w2l'
ANCHOR_LAYER = r'dlc\bob\data\levels\bob\quests\main_quests\q705_epilog\geralt_house\dialogsets\house.w2l'
TRIGGER_LAYER = r'dlc\bob\data\levels\bob\quests\main_quests\q705_epilog\geralt_house\triggers\house.w2l'
DECO_LAYER = r'dlc\bob\data\levels\bob\locations\vineyards\east\corvo_bianco\q705_epilog\garden_chair\deco_exterior.w2l'
BED_TEMPLATE = r'dlc\bob\data\quests\minor_quests\quest_files\mq7024_home\entities\mq7024_witcher_bed_rich_collision.w2ent'
TRISS_PATH = 'q705_path_triss_from_own_chair'
TRISS_TRIGGER = 'q705_tr_triss_own_chair'
# Northwest of Yen, away from the native rhododendron bed. Terrain + native
# rock render samples span 6.53 cm across the approximate chair footprint.
# Foliage exclusion is checked independently; runtime QA is still required.
OFFSET = (-4.0, 1.0, -0.017419446013150264)


def fields(resource, raw):
    assert raw[0] == 0
    result, end = read_properties(raw, 1)
    assert end == len(raw)
    return result


def field(resource, props, name):
    return next(prop for prop in props if resource.names[prop.name] == name)


def inline_array(raw):
    result, pos = [], 4
    for _ in range(struct.unpack_from('<I', raw)[0]):
        assert raw[pos] == 0
        props, pos = read_properties(raw, pos + 1)
        result.append(props)
    assert pos == len(raw)
    return result


def encode_array(items):
    return u32(len(items)) + b''.join(b'\0' + encode_properties(props) for props in items)


def shift_transform(raw, delta=OFFSET):
    assert raw[0] & 1
    result = bytearray(raw)
    position = struct.unpack_from('<3f', raw, 1)
    struct.pack_into('<3f', result, 1, *(a + b for a, b in zip(position, delta)))
    return bytes(result)


def append_entity(resource, entity):
    raw = resource.prop(1, 'entities').data
    count = struct.unpack_from('<I', raw)[0]
    assert len(raw) == 4 + count * 4
    resource.set(1, 'entities', u32(count + 1) + raw[4:] + u32(entity))
    if any(resource.names[prop.name] == 'nameCount' for prop in resource.props(1)):
        counter = struct.unpack('<I', resource.prop(1, 'nameCount').data)[0]
        resource.set(1, 'nameCount', u32(counter + 1))


def path_world_points(resource, entity, component):
    curve = fields(resource, resource.prop(component, 'curve').data)
    coordinates = []
    for axis in inline_array(field(resource, curve, 'curves').data):
        entries = inline_array(field(resource, axis, 'Curve Values').data)
        coordinates.append([struct.unpack('<f', field(resource, entry, 'lue').data)[0] for entry in entries])
    assert len(coordinates) == 3 and len({len(axis) for axis in coordinates}) == 1
    transform = resource.prop(entity, 'transform').data
    position = struct.unpack_from('<3f', transform, 1)
    angle = struct.unpack_from('<3f', transform, 13)[2] if transform[0] & 2 else 0
    cs, sn = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    component_position = struct.unpack_from('<3f', resource.prop(component, 'transform').data, 1)
    result = []
    for values in zip(*coordinates):
        x, y, z = (a + b for a, b in zip(values, component_position))
        result.append((position[0] + cs * x - sn * y,
                       position[1] + sn * x + cs * y, position[2] + z))
    return result


def patch_actionpoints(resource, notes):
    # Reuse Triss's native chair AP/job tree. Both visit and residence point to
    # this AP; Ciri's AP and Yen's AP remain byte-for-byte untouched.
    resource.set(15, 'transform', shift_transform(resource.prop(15, 'transform').data))
    ciri = path_world_points(resource, 11, 12)
    sorceress = path_world_points(resource, 17, 18)
    points = [tuple(a + b for a, b in zip(sorceress[0], OFFSET))] + sorceress[:17] + ciri[25:]
    assert math.dist(sorceress[16], ciri[25]) < 3.0

    entity = resource.clone_owned(11, 'triss-own-chair-path')
    component = next(i for i, chunk in enumerate(resource.chunks, 1)
                     if chunk.parent == entity and resource.kind(i) == 'CPathComponent')
    # CEntity's component references live in its buffered tail, outside normal
    # properties. clone_owned intentionally only handles property references.
    chunk = resource.chunk(entity)
    _, end = read_properties(chunk.data, 1)
    tail = bytearray(chunk.data[end:])
    # Remastered v164 precedes the classic component list with eight zero
    # bytes. Preserve this native prefix rather than using the v162 layout.
    assert tail[:8] == b'\0' * 8
    count, pos = read_vlq(tail, 8)
    assert count == 1 and struct.unpack_from('<I', tail, pos)[0] == 12
    struct.pack_into('<I', tail, pos, component)
    chunk.data = chunk.data[:end] + bytes(tail)
    resource.set(entity, 'tags', b'\x01' + struct.pack('<H', resource.name_id(TRISS_PATH)))

    # The cloned entity retains Ciri's native world/local reference frames.
    # Express the spliced route in that unchanged local frame.
    origin = struct.unpack_from('<3f', resource.prop(entity, 'transform').data, 1)
    local_offset = struct.unpack_from('<3f', resource.prop(component, 'transform').data, 1)
    distances = [0.0]
    for previous, current in zip(points, points[1:]):
        distances.append(distances[-1] + math.dist(previous, current))
    curve = fields(resource, resource.prop(component, 'curve').data)
    axes = inline_array(field(resource, curve, 'curves').data)
    for axis, props in enumerate(axes):
        values = field(resource, props, 'Curve Values')
        template = inline_array(values.data)[1]
        assert any(resource.names[p.name] == 'me' for p in template)
        entries = []
        for point, distance in zip(points, distances):
            entry = copy.deepcopy(template)
            field(resource, entry, 'lue').data = struct.pack('<f', point[axis] - origin[axis] - local_offset[axis])
            field(resource, entry, 'me').data = struct.pack('<f', distance / distances[-1])
            entries.append(entry)
        values.data = encode_array(entries)
    field(resource, curve, 'curves').data = encode_array(axes)
    resource.set(component, 'curve', b'\0' + encode_properties(curve))
    append_entity(resource, entity)
    notes.append('Triss: native chair actionpoint and staging moved together; separate route joins native outdoor path to the guest-room staircase.')


def patch_anchors(resource, notes):
    # Camera and animation events remain native and scene-relative. Move only
    # the default Triss dialogset anchor; her front-door intro anchor stays put.
    resource.set(16, 'transform', shift_transform(resource.prop(16, 'transform').data))
    notes.append('Triss repeat dialogue: independent world anchor; original voices, choices, cameras, poses and animation events unchanged.')


def shift_vector(resource, raw):
    props = fields(resource, raw)
    for name, offset in zip(['X', 'Y', 'Z'], OFFSET):
        prop = field(resource, props, name)
        prop.data = struct.pack('<f', struct.unpack('<f', prop.data)[0] + offset)
    return b'\0' + encode_properties(props)


def patch_triggers(resource, notes):
    entity = resource.clone_owned(8, 'triss-own-chair-trigger')
    component = next(i for i, chunk in enumerate(resource.chunks, 1)
                     if chunk.parent == entity and resource.kind(i) == 'CTriggerAreaComponent')
    chunk = resource.chunk(entity)
    _, end = read_properties(chunk.data, 1)
    tail = bytearray(chunk.data[end:]);assert tail[:8] == b'\0' * 8
    count, pos = read_vlq(tail, 8)
    assert count == 1 and struct.unpack_from('<I', tail, pos)[0] == 9
    struct.pack_into('<I', tail, pos, component)
    chunk.data = chunk.data[:end] + bytes(tail)
    resource.set(entity, 'tags', b'\x01' + struct.pack('<H', resource.name_id(TRISS_TRIGGER)))
    resource.set(entity, 'transform', shift_transform(resource.prop(entity, 'transform').data))
    box = fields(resource, resource.prop(component, 'boundingBox').data)
    for prop in box:
        assert resource.names[prop.kind] == 'Vector'
        prop.data = shift_vector(resource, prop.data)
    resource.set(component, 'boundingBox', b'\0' + encode_properties(box))
    points = inline_array(resource.prop(component, 'worldPoints').data)
    for props in points:
        for name, offset in zip(['X', 'Y', 'Z'], OFFSET):
            prop = field(resource, props, name)
            prop.data = struct.pack('<f', struct.unpack('<f', prop.data)[0] + offset)
    resource.set(component, 'worldPoints', encode_array(points))
    append_entity(resource, entity)
    notes.append('Triss dialogue availability: independent translated trigger, including cached world polygon and bounds; Yen trigger unchanged.')


def sector_objects(resource):
    raw = resource.chunk(3).data
    assert raw[:4] == b'\0\0\0\x08'
    count, pos = read_vlq(raw, 8)
    resources = [struct.unpack_from('<6fQ', raw, pos + i * 32) for i in range(count)]
    pos += count * 32
    count, pos = read_vlq(raw, pos)
    objects = [struct.unpack_from('<BBHQfff', raw, pos + i * 24) for i in range(count)]
    pos += count * 24
    size, pos = read_vlq(raw, pos)
    assert pos + size == len(raw)
    return raw, resources, objects, pos


def matrix_transform(matrix, position):
    scale = tuple(math.sqrt(sum(matrix[i * 3 + j] ** 2 for j in range(3))) for i in range(3))
    roll = math.atan2(matrix[5] / scale[1], matrix[8] / scale[2])
    pitch = math.asin(max(-1, min(1, -matrix[2] / scale[0])))
    yaw = math.atan2(matrix[1] / scale[0], matrix[0] / scale[0])
    return b'\x07' + struct.pack('<9f', *(a + b for a, b in zip(position, OFFSET)),
                                *map(math.degrees, [roll, pitch, yaw]), *scale)


def patch_decor(resource, notes, template_bytes, metadata):
    prototype = Resource(template_bytes)
    original_buffer = prototype.prop(2, 'streamingDataBuffer').data
    assert struct.unpack_from('<I', original_buffer)[0] == len(original_buffer) - 4
    assert prototype.kind(2) == 'CEntity'
    _, end = read_properties(prototype.chunk(2).data, 1)
    entity_tail = prototype.chunk(2).data[end:]
    assert entity_tail == bytes.fromhex('0000000000000000800000')
    raw, meshes, objects, start = sector_objects(resource)
    hashes = {struct.unpack('<qQ', row)[0] & 0xffffffffffffffff: struct.unpack('<qQ', row)[1]
              for row in metadata.sections[6]}

    # Ordinary entity streaming lets the engine register render/physics objects
    # at their new positions, instead of copying somebody else's baked Umbra ID.
    for index in (1, 3, 5, 6):
        descriptor = objects[index]
        assert descriptor[0] == 1
        offset = start + descriptor[3]
        matrix = struct.unpack_from('<9f', raw, offset)
        position = struct.unpack_from('<3f', raw, offset + 36)
        mesh_index = struct.unpack_from('<H', raw, offset + 56)[0]
        mesh_id = hashes[meshes[mesh_index][6]]
        path = metadata.string(struct.unpack_from('<I', metadata.sections[0][mesh_id])[0])
        assert path.endswith('.w2mesh')

        inner = Resource(original_buffer[4:])
        assert [inner.kind(i) for i in range(1, len(inner.chunks) + 1)] == ['CStaticMeshComponent'] * 2
        inner.chunks = inner.chunks[:1]
        inner.table_data[2] = inner.table_data[2][:8]
        path_offset = len(inner.table_data[0])
        inner.table_data[0] += path.encode('utf-8') + b'\0'
        _, mesh_kind, flags = struct.unpack('<IHH', inner.table_data[2])
        assert inner.names[mesh_kind] == 'CMesh' and flags == 0
        inner.table_data[2] = struct.pack('<IHH', path_offset, mesh_kind, flags)
        inner.set(1, 'transform', b'\x01' + struct.pack('<3f', 0, 0, 0))
        inner.set(1, 'guid', uuid.uuid5(uuid.NAMESPACE_URL, f'dualromance/chair-component/{index}').bytes_le)
        inner.set(1, 'drawableFlags', b''.join(struct.pack('<H', inner.name_id(name)) for name in
                                             ['DF_IsVisible', 'DF_CastShadows', 'DF_NoDissolves', '']))
        buffer = inner.build()
        assert Resource(buffer).build() == buffer
        props = [
            Property(resource.name_id('transform'), resource.name_id('EngineTransform'), matrix_transform(matrix, position)),
            Property(resource.name_id('guid'), resource.name_id('CGUID'),
                     uuid.uuid5(uuid.NAMESPACE_URL, f'dualromance/chair-entity/{index}').bytes_le),
            Property(resource.name_id('streamingDataBuffer'), resource.name_id('SharedDataBuffer'), u32(len(buffer)) + buffer),
            Property(resource.name_id('streamingDistance'), resource.name_id('Uint8'), b'\0'),
        ]
        resource.chunks.append(Chunk(resource.name_id('CEntity'), prototype.chunk(2).flags, 1, 0,
                                     b'\0' + encode_properties(props) + entity_tail))
        append_entity(resource, len(resource.chunks))
    notes.append('Triss furniture: independent native lounge mesh, side table, jug and serving plate as streamed entities; original sector/furniture untouched.')
