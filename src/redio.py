# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Hexiao Zhang
"""Small, lossless readers/builders for the installed Remastered resources.

Format references: WolvenKit-7 and Systemcluster/w3edit (see THIRD_PARTY.md).
This module does not cook assets or convert between game versions.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import copy
import struct
import uuid
import zlib


def u32(value):
    return struct.pack('<I', value)


def vlq(value):
    negative = value <= 0
    value = abs(value)
    result = bytearray([(value & 63) | (128 if negative else 0)])
    value >>= 6
    if value:
        result[0] |= 64
    while value:
        part = value & 127
        value >>= 7
        result.append(part | (128 if value else 0))
    return bytes(result)


def read_vlq(data, pos):
    first = data[pos]
    pos += 1
    result, shift, more = first & 63, 6, first & 64
    while more:
        part = data[pos]
        pos += 1
        result |= (part & 127) << shift
        shift += 7
        more = part & 128
        assert shift <= 34, 'Invalid VLQ'
    return (-result if first & 128 else result), pos


def ws_string(value):
    encoded = value.encode('utf-8')
    return vlq(-len(encoded)) + encoded


def read_ws_string(data):
    count, start = read_vlq(data, 0)
    assert count <= 0, 'Expected narrow UTF-8 string'
    assert start - count == len(data)
    return data[start:].decode('utf-8')


def fnv32_name(name):
    if not name:
        return 0
    value = 0x811c9dc5
    for byte in name.encode('utf-8') + b'\0':
        value = ((value ^ byte) * 0x1000193) & 0xffffffff
    return value


@dataclass
class Property:
    name: int
    kind: int
    data: bytes

    def encode(self):
        return struct.pack('<HHI', self.name, self.kind, len(self.data) + 4) + self.data


def read_properties(data, pos=0):
    result = []
    while True:
        name = struct.unpack_from('<H', data, pos)[0]
        pos += 2
        if not name:
            return result, pos
        kind, size = struct.unpack_from('<HI', data, pos)
        pos += 6
        assert size >= 4 and pos + size - 4 <= len(data)
        result.append(Property(name, kind, bytes(data[pos:pos + size - 4])))
        pos += size - 4


def encode_properties(props):
    return b''.join(p.encode() for p in props) + b'\0\0'


@dataclass
class Chunk:
    class_id: int
    flags: int
    parent: int
    template: int
    data: bytes


class Resource:
    """Preserve all unknown bytes; append objects without renumbering originals."""
    TABLE_WIDTHS = [1, 8, 8, 16, 24, 24, 24, 0, 0, 0]

    def __init__(self, data):
        self.original = bytes(data)
        assert data[:4] == b'CR2W'
        assert struct.unpack_from('<I', data, 4)[0] == 164, 'Only retail Remastered v164 supported'
        self.header = bytes(data[:40])
        self.tables = [struct.unpack_from('<III', data, 40 + 12 * i) for i in range(10)]
        assert all(not count for _, count, _ in self.tables[5:]), 'External buffers unsupported'
        self.table_data = []
        for i, (offset, count, crc) in enumerate(self.tables):
            raw = bytes(data[offset:offset + count * self.TABLE_WIDTHS[i]]) if count else b''
            if count:
                assert zlib.crc32(raw) == crc, ('Table CRC', i)
            self.table_data.append(raw)
        strings = self.table_data[0]
        self.names = []
        for pos in range(0, len(self.table_data[1]), 8):
            offset, _ = struct.unpack_from('<II', self.table_data[1], pos)
            self.names.append(strings[offset:strings.index(b'\0', offset)].decode('utf-8'))
        self.chunks = []
        for pos in range(0, len(self.table_data[4]), 24):
            cid, flags, parent, size, offset, template, crc = struct.unpack_from('<HH5I', self.table_data[4], pos)
            raw = bytes(data[offset:offset + size])
            assert len(raw) == size and zlib.crc32(raw) == crc, ('Object CRC', pos // 24 + 1)
            self.chunks.append(Chunk(cid, flags, parent, template, raw))
        assert max(struct.unpack_from('<I', self.table_data[4], p + 12)[0] +
                   struct.unpack_from('<I', self.table_data[4], p + 8)[0]
                   for p in range(0, len(self.table_data[4]), 24)) == len(data), 'Unexpected resource trailer'

    def chunk(self, obj):
        return self.chunks[obj - 1]

    def kind(self, obj):
        return self.names[self.chunk(obj).class_id]

    def name_id(self, name):
        if name in self.names:
            return self.names.index(name)
        offset = len(self.table_data[0])
        self.table_data[0] += name.encode('utf-8') + b'\0'
        self.table_data[1] += struct.pack('<II', offset, fnv32_name(name))
        self.names.append(name)
        return len(self.names) - 1

    def props(self, obj):
        data = self.chunk(obj).data
        assert data[0] == 0, 'Unexpected object prefix'
        result, _ = read_properties(data, 1)
        return result

    def prop(self, obj, name):
        return next(p for p in self.props(obj) if self.names[p.name] == name)

    def set(self, obj, name, data):
        chunk = self.chunk(obj)
        props, end = read_properties(chunk.data, 1)
        for prop in props:
            if self.names[prop.name] == name:
                prop.data = bytes(data)
                chunk.data = b'\0' + encode_properties(props) + chunk.data[end:]
                return
        raise KeyError((obj, name))

    def set_int(self, obj, name, value):
        self.set(obj, name, struct.pack('<i', value))

    def set_name(self, obj, name, value):
        self.set(obj, name, struct.pack('<H', self.name_id(value)))

    def connections(self, obj):
        raw = self.prop(obj, 'cachedConnections').data
        count = struct.unpack_from('<I', raw)[0]
        pos, result = 4, []
        for _ in range(count):
            assert raw[pos] == 0
            fields, pos = read_properties(raw, pos + 1)
            socket, targets = '', []
            for prop in fields:
                name = self.names[prop.name]
                if name == 'socketId':
                    socket = self.names[int.from_bytes(prop.data, 'little')]
                elif name == 'blocks':
                    size = struct.unpack_from('<I', prop.data)[0]
                    inner = 4
                    for _ in range(size):
                        assert prop.data[inner] == 0
                        desc, inner = read_properties(prop.data, inner + 1)
                        record = {self.names[p.name]: p.data for p in desc}
                        targets.append((int.from_bytes(record['ock'], 'little'),
                                        self.names[int.from_bytes(record['putName'], 'little')]))
                    assert inner == len(prop.data)
            result.append((socket, targets))
        assert pos == len(raw)
        return result

    def set_connections(self, obj, connections):
        def prop(name, kind, data):
            return Property(self.name_id(name), self.name_id(kind), data)
        raw = bytearray(u32(len(connections)))
        for socket, targets in connections:
            fields = []
            if socket:
                fields.append(prop('socketId', 'CName', struct.pack('<H', self.name_id(socket))))
            if targets:
                blocks = bytearray(u32(len(targets)))
                for target, input_name in targets:
                    blocks += b'\0' + encode_properties([
                        prop('ock', 'ptr:CQuestGraphBlock', u32(target)),
                        prop('putName', 'CName', struct.pack('<H', self.name_id(input_name)))])
                fields.append(prop('blocks', 'array:2,0,SBlockDesc', bytes(blocks)))
            raw += b'\0' + encode_properties(fields)
        self.set(obj, 'cachedConnections', raw)

    def route(self, obj, socket, targets):
        connections = self.connections(obj)
        assert any(s == socket for s, _ in connections), (obj, socket)
        self.set_connections(obj, [(s, targets if s == socket else t) for s, t in connections])

    def register(self, graph, obj):
        raw = self.prop(graph, 'graphBlocks').data
        count = struct.unpack_from('<I', raw)[0]
        assert len(raw) == 4 + count * 4
        self.set(graph, 'graphBlocks', u32(count + 1) + raw[4:] + u32(obj))

    def clone_owned(self, obj, label):
        owned = [obj]
        for current in owned:
            owned.extend(i for i, chunk in enumerate(self.chunks, 1) if chunk.parent == current)
        mapping = {old: len(self.chunks) + index + 1 for index, old in enumerate(owned)}
        for old in owned:
            new = copy.deepcopy(self.chunk(old))
            new.parent = mapping.get(new.parent, new.parent)
            self.chunks.append(new)
            new_id = mapping[old]
            for prop in self.props(new_id):
                name, kind = self.names[prop.name], self.names[prop.kind]
                if name == 'guid':
                    self.set(new_id, name, uuid.uuid5(uuid.NAMESPACE_URL, 'dualromance/' + label + '/' + prop.data.hex()).bytes_le)
                elif kind.startswith(('ptr:', 'handle:')) and len(prop.data) == 4:
                    target = int.from_bytes(prop.data, 'little', signed=True)
                    if target in mapping:
                        self.set_int(new_id, name, mapping[target])
                elif kind.startswith('array:2,0,ptr:'):
                    size = struct.unpack_from('<I', prop.data)[0]
                    assert len(prop.data) == 4 + size * 4
                    vals = struct.unpack_from('<' + 'I' * size, prop.data, 4)
                    self.set(new_id, name, u32(size) + b''.join(u32(mapping.get(v, v)) for v in vals))
        return mapping[obj]

    def build(self):
        tables = list(self.table_data)
        counts = [len(tables[0]), len(tables[1]) // 8, len(tables[2]) // 8,
                  len(tables[3]) // 16, len(self.chunks)] + [0] * 5
        cursor = 160 + sum(len(t) for t in tables[:4]) + 24 * len(self.chunks)
        exports = bytearray()
        for chunk in self.chunks:
            exports += struct.pack('<HH5I', chunk.class_id, chunk.flags, chunk.parent,
                                   len(chunk.data), cursor, chunk.template, zlib.crc32(chunk.data))
            cursor += len(chunk.data)
        tables[4] = bytes(exports)
        header = bytearray(self.header + b'\0' * 120)
        struct.pack_into('<II', header, 24, cursor, cursor)
        offset = 160
        for i, (raw, count) in enumerate(zip(tables, counts)):
            if count:
                struct.pack_into('<III', header, 40 + i * 12, offset, count, zlib.crc32(raw))
                offset += len(raw)
        struct.pack_into('<I', header, 32, 0xdeadbeef)
        struct.pack_into('<I', header, 32, zlib.crc32(header))
        result = bytes(header) + b''.join(tables) + b''.join(c.data for c in self.chunks)
        assert len(result) == cursor
        return result


class BundleCatalog:
    def __init__(self, directory):
        self.items = {}
        for path in sorted(Path(directory).glob('*.bundle')):
            with path.open('rb') as file:
                header = file.read(32)
                assert header[:8] == b'POTATO70'
                assert struct.unpack_from('<H', header, 20)[0] == 5, 'Expected Remastered bundle'
                size = struct.unpack_from('<I', header, 16)[0]
                assert size % 304 == 0
                toc = file.read(size)
                for pos in range(0, size, 304):
                    entry = toc[pos:pos + 304]
                    name = entry[:256].split(b'\0', 1)[0].decode('utf-8')
                    offset, unpacked, packed, crc, compression = struct.unpack_from('<Q4I', entry, 272)
                    self.items[name] = (path, entry, offset, unpacked, packed, crc, compression)

    def extract(self, name):
        path, _, offset, size, packed, crc, compression = self.items[name]
        with path.open('rb') as file:
            file.seek(offset)
            raw = file.read(packed)
        assert compression in (0, 1), (name, compression)
        result = zlib.decompress(raw) if compression else raw
        assert len(result) == size and zlib.crc32(result) == crc
        return result


class Metadata:
    WIDTHS = [32, 24, 24, 4, 8, 12, 16]

    def __init__(self, data):
        assert data[:4] == b'\x03VTM' and struct.unpack_from('<I', data, 4)[0] == 7
        self.header = data[:16]
        count, pos = read_vlq(data, 16)
        self.strings = data[pos:pos + count]
        pos += count
        self.sections = []
        for width in self.WIDTHS:
            count, pos = read_vlq(data, pos)
            self.sections.append([data[pos + i * width:pos + (i + 1) * width] for i in range(count)])
            pos += count * width
        assert pos == len(data)
        self.by_path = {}
        for i, raw in enumerate(self.sections[0]):
            name = self.string(struct.unpack_from('<I', raw)[0])
            self.by_path[name] = i
        self.hashes = {struct.unpack('<qQ', row)[1]: struct.unpack('<qQ', row)[0] for row in self.sections[6]}

    def string(self, offset):
        return self.strings[offset:self.strings.index(b'\0', offset)].decode('utf-8')


def pack_mod(resources, catalog, source_metadata):
    """Build a v5 bundle and v7 index; retain source path hashes and flags."""
    paths = sorted(resources)
    toc_end = 32 + 304 * len(paths)
    bundle = bytearray(toc_end)
    entries = []
    for name in paths:
        raw = resources[name]
        compressed = zlib.compress(raw, 9)
        bundle += b'\0' * (-len(bundle) % 16)
        offset = len(bundle)
        source = catalog.items[name][1]
        entry = bytearray(source)
        struct.pack_into('<Q4I', entry, 272, offset, len(raw), len(compressed), zlib.crc32(raw), 1)
        entries.append((name, offset, len(compressed), len(raw), entry))
        bundle += compressed
    bundle[:8] = b'POTATO70'
    struct.pack_into('<QI', bundle, 8, len(bundle), 304 * len(paths))
    struct.pack_into('<HQH', bundle, 20, 5, toc_end, 0)
    for i, (_, _, _, _, entry) in enumerate(entries):
        bundle[32 + 304 * i:32 + 304 * (i + 1)] = entry

    strings, offsets = bytearray(b'\0'), {'': 0}
    def intern(value):
        if value not in offsets:
            offsets[value] = len(strings)
            strings.extend(value.encode('utf-8') + b'\0')
        return offsets[value]
    sections = [[b'\0' * 32], [b'\0' * 24], [b'\0' * 24], [], [b'\0' * 8], [], []]
    directories = {(): 0}
    for fid, (name, offset, packed, unpacked, _) in enumerate(entries, 1):
        source_id = source_metadata.by_path[name]
        old = struct.unpack('<8I', source_metadata.sections[0][source_id])
        # Retail v7 moves compression to the final u32; buffer_id and
        # has_buffer precede it. Do not use the legacy v6 field order here.
        assert old[6] == 0, 'Buffered resources unsupported'
        sections[0].append(struct.pack('<8I', intern(name), old[1], packed, unpacked, fid, 0, 0, 1))
        sections[1].append(struct.pack('<Q4I', offset, packed, 0, fid, 1))
        components = name.split('\\')
        for length in range(1, len(components)):
            key = tuple(components[:length])
            if key not in directories:
                directories[key] = len(sections[4])
                sections[4].append(struct.pack('<II', intern(key[-1]), directories[key[:-1]]))
        sections[5].append(struct.pack('<III', fid, directories[tuple(components[:-1])], intern(components[-1])))
        if source_id in source_metadata.hashes:
            sections[6].append(struct.pack('<qQ', source_metadata.hashes[source_id], fid))
    # Native v7 binary-searches these as unsigned 64-bit hashes.
    sections[6].sort(key=lambda row: struct.unpack_from('<Q', row)[0])
    sections[2].append(struct.pack('<Q4I', len(bundle) - toc_end, toc_end, intern('blob0.bundle'), 1, len(paths)))
    metadata = b'\x03VTM' + struct.pack('<3I', 7, max(e[2] for e in entries), max(e[3] for e in entries))
    metadata += vlq(len(strings)) + strings
    metadata += b''.join(vlq(len(rows)) + b''.join(rows) for rows in sections)
    return bytes(bundle), bytes(metadata)
