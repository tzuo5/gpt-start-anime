"""Small streaming ASAR editor; never extracts or executes archive members."""
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct


def digest_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def integrity(data, block_size=4194304):
    return {'algorithm': 'SHA256', 'hash': hashlib.sha256(data).hexdigest(),
            'blockSize': block_size,
            'blocks': [hashlib.sha256(data[i:i + block_size]).hexdigest()
                       for i in range(0, len(data), block_size)]}


def members(tree, prefix=''):
    for name, node in tree['files'].items():
        path = prefix + name
        if 'files' in node:
            yield from members(node, path + '/')
        else:
            yield path, node


def header_bytes(tree):
    data = json.dumps(tree, ensure_ascii=False, separators=(',', ':')).encode()
    payload = struct.pack('<I', len(data)) + data
    payload += b'\0' * (-len(payload) % 4)
    header = struct.pack('<I', len(payload)) + payload
    return struct.pack('<II', 4, len(header)) + header


class Archive:
    def __init__(self, path):
        self.path = Path(path)
        with self.path.open('rb') as stream:
            prefix = stream.read(16)
            if len(prefix) != 16:
                raise ValueError('Truncated ASAR header')
            size, header_size, payload_size, json_size = struct.unpack('<IIII', prefix)
            if size != 4 or header_size != payload_size + 4 or not 0 < json_size <= 64 * 1024 * 1024:
                raise ValueError('Unsupported ASAR header')
            if header_size != 8 + json_size + (-json_size % 4):
                raise ValueError('Invalid ASAR alignment')
            self.tree = json.loads(stream.read(json_size))
        self.base = 8 + header_size
        total = self.path.stat().st_size
        for _, node in members(self.tree):
            if 'offset' in node and not node.get('unpacked'):
                start, length = int(node['offset']), node['size']
                if start < 0 or length < 0 or self.base + start + length > total:
                    raise ValueError('ASAR member outside archive')

    def node(self, path):
        node = self.tree
        for part in path.split('/'):
            node = node['files'][part]
        return node

    def read(self, path):
        node = self.node(path)
        if node.get('unpacked') or 'offset' not in node:
            raise ValueError('Expected a packed regular file: ' + path)
        with self.path.open('rb') as stream:
            stream.seek(self.base + int(node['offset']))
            return stream.read(node['size'])

    def verify(self):
        """Verify every packed member against its stored whole/block digests."""
        checked = 0
        with self.path.open('rb') as stream:
            for path, node in members(self.tree):
                if 'offset' not in node or node.get('unpacked'):
                    continue
                info = node.get('integrity')
                if not info or info.get('algorithm') != 'SHA256':
                    raise ValueError('Missing SHA256 integrity: ' + path)
                block_size = info.get('blockSize')
                if not isinstance(block_size, int) or not 1 <= block_size <= 64 * 1024 * 1024:
                    raise ValueError('Invalid block size: ' + path)
                stream.seek(self.base + int(node['offset']))
                remaining = node['size']
                whole = hashlib.sha256()
                blocks = []
                while remaining:
                    data = stream.read(min(remaining, block_size))
                    if not data:
                        raise ValueError('Truncated member: ' + path)
                    whole.update(data)
                    blocks.append(hashlib.sha256(data).hexdigest())
                    remaining -= len(data)
                # Some ASAR writers emit one digest for an empty block.
                if node['size'] == 0 and info['blocks'] == [whole.hexdigest()]:
                    blocks = [whole.hexdigest()]
                if whole.hexdigest() != info['hash'] or blocks != info['blocks']:
                    raise ValueError('ASAR integrity mismatch: ' + path)
                checked += 1
        return checked

    def rewrite(self, destination, changes):
        destination = Path(destination)
        if destination.resolve() == self.path.resolve():
            raise ValueError('Source and destination must differ')
        tree = copy.deepcopy(self.tree)
        for path, data in changes.items():
            parts = PurePosixPath(path).parts
            if not parts or path.startswith('/') or '..' in parts or '\\' in path:
                raise ValueError('Invalid member path')
            parent = tree
            for part in parts[:-1]:
                parent = parent.setdefault('files', {}).setdefault(part, {'files': {}})
            node = parent.setdefault('files', {}).setdefault(parts[-1], {})
            if node.get('unpacked') or 'link' in node or 'files' in node:
                raise ValueError('Cannot replace non-packed member')
            block_size = node.get('integrity', {}).get('blockSize', 4194304)
            node.update(size=len(data), integrity=integrity(data, block_size))
        offset = 0
        for _, node in members(tree):
            if 'size' in node and not node.get('unpacked') and 'link' not in node:
                node['offset'] = str(offset)
                offset += node['size']
        try:
            with destination.open('xb') as output, self.path.open('rb') as source:
                output.write(header_bytes(tree))
                for path, node in members(tree):
                    if 'offset' not in node or node.get('unpacked'):
                        continue
                    if path in changes:
                        output.write(changes[path])
                    else:
                        original = self.node(path)
                        source.seek(self.base + int(original['offset']))
                        remaining = original['size']
                        while remaining:
                            chunk = source.read(min(remaining, 1024 * 1024))
                            if not chunk:
                                raise ValueError('Truncated member')
                            output.write(chunk)
                            remaining -= len(chunk)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return Archive(destination)
