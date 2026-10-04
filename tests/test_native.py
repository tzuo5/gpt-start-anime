import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from asar import Archive, header_bytes, integrity
import launcher
import native


def fixture(path, files=None, extras=None):
    files = files or {'a.txt': b'first', 'folder/b.js': b'second'}
    tree = {'files': {}}
    offset = 0
    for name, data in files.items():
        parent = tree
        parts = name.split('/')
        for part in parts[:-1]:
            parent = parent['files'].setdefault(part, {'files': {}})
        parent['files'][parts[-1]] = {'size': len(data), 'offset': str(offset),
                                   'integrity': integrity(data, 4)}
        offset += len(data)
    if extras:
        tree['files'].update(extras)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header_bytes(tree) + b''.join(files.values()))
    return Archive(path)


class ArchiveTests(unittest.TestCase):
    def test_rewrite_preserves_links_unpacked_and_unchanged_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.asar'
            archive = fixture(source, extras={'native.node': {'size': 100, 'unpacked': True},
                                             'alias': {'link': 'a.txt'}})
            original = source.read_bytes()
            archive.node('a.txt')['executable'] = True
            updated = archive.rewrite(Path(tmp) / 'updated.asar', {
                'a.txt': b'changed across blocks', 'new/c.js': b'new module'})
            self.assertEqual(updated.read('a.txt'), b'changed across blocks')
            self.assertEqual(updated.node('a.txt')['integrity'], integrity(b'changed across blocks', 4))
            self.assertTrue(updated.node('a.txt')['executable'])
            self.assertEqual(updated.read('folder/b.js'), b'second')
            self.assertEqual(updated.read('new/c.js'), b'new module')
            self.assertEqual(updated.node('native.node'), {'size': 100, 'unpacked': True})
            self.assertEqual(updated.node('alias'), {'link': 'a.txt'})
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(updated.verify(), 3)
            damaged = Path(tmp) / 'updated.asar'
            with damaged.open('r+b') as stream:
                stream.seek(updated.base)
                stream.write(b'X')
            with self.assertRaisesRegex(ValueError, 'integrity mismatch'): updated.verify()

    def test_rejects_malformed_header_offsets_and_unsafe_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.asar'
            source.write_bytes(b'broken')
            with self.assertRaises(ValueError): Archive(source)
            archive = fixture(source, extras={'link': {'link': 'a.txt'}})
            for key in ['../escape', '/absolute', 'link']:
                with self.assertRaises(ValueError):
                    archive.rewrite(Path(tmp) / 'bad.asar', {key: b'bad'})
            with self.assertRaises(ValueError): archive.rewrite(source, {'a.txt': b'bad'})
            tree = {'files': {'x': {'offset': '999', 'size': 1}}}
            source.write_bytes(header_bytes(tree))
            with self.assertRaises(ValueError): Archive(source)

    def test_patch_anchor_is_unique_and_bridge_path_is_literal(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {native.APPEARANCE: b'children:(0,h.jsx)(u,{defaultAdvancedExpanded:i},r)',
                     native.PRELOAD: b'require("electron").contextBridge.exposeInMainWorld("other",{});',
                     native.EARLY: b'require("electron");'}
            archive = fixture(Path(tmp) / 'app.asar', files)
            path = Path(tmp) / 'quoted " $(touch nope)/manage.py'
            changes = native.patch_changes(archive, path)
            bridge = changes['.vite/build/startup-animation-bridge.cjs'].decode()
            self.assertIn(json.dumps(str(path)), bridge)
            self.assertIn('shell: false', bridge)
            self.assertEqual(changes[native.APPEARANCE].count(b'(0,h.jsx)(StartupEntry,{})'), 1)
            rewritten = archive.rewrite(Path(tmp) / 'patched.asar', changes)
            with self.assertRaises(RuntimeError): native.patch_changes(rewritten, path)


class NativeStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {'XDG_DATA_HOME': str(self.root / 'data'),
            'XDG_CONFIG_HOME': str(self.root / 'config'), 'XDG_STATE_HOME': str(self.root / 'state')})
        self.environment.start()
        self.policy = patch.object(native, 'policy_required', return_value=False)
        self.policy.start()
        self.source = self.root / 'system'
        self.copy = native.root_path() / 'versions/test-copy'
        for directory in [self.source, self.copy]:
            (directory / 'resources').mkdir(parents=True)
            (directory / 'resources/app.asar').write_bytes(b'sample')
            (directory / 'ChatGPT').write_bytes(b'executable')
            (directory / 'codex-launcher').write_bytes(b'launcher')
        self.command = [str(self.source / 'codex-launcher'), '--a']
        self.state = {'enabled': True, 'validated': True, 'source': str(self.source), 'copy': str(self.copy),
            'adapter_hash': native.adapter_hash(),
            'source_fingerprint': native.fingerprint(self.source / 'resources/app.asar'),
            'binary_fingerprint': native.fingerprint(self.source / 'ChatGPT'),
            'copy_fingerprint': native.fingerprint(self.copy / 'resources/app.asar'),
            'copy_binary_fingerprint': native.fingerprint(self.copy / 'ChatGPT'),
            'original_command': self.command}
        native.write_json(native.state_path(), self.state)

    def tearDown(self):
        self.policy.stop()
        self.environment.stop()
        self.temporary.cleanup()

    def test_uses_copy_and_keeps_original_flags_and_command(self):
        self.assertEqual(native.resolve_command(self.command), [str(self.copy / 'codex-launcher'), '--a'])
        self.assertEqual(native.resolve_command(['/usr/bin/other']), ['/usr/bin/other'])
        self.assertEqual(native.read_state()['original_command'], self.command)

    def test_upgrade_missing_binary_and_copy_changes_fall_back(self):
        for path in [self.source / 'resources/app.asar', self.source / 'ChatGPT',
                     self.copy / 'resources/app.asar', self.copy / 'ChatGPT']:
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b'updated')
                self.assertEqual(native.resolve_command(self.command), self.command)
                path.write_bytes(original)
                self.state['source_fingerprint'] = native.fingerprint(self.source / 'resources/app.asar')
                self.state['binary_fingerprint'] = native.fingerprint(self.source / 'ChatGPT')
                self.state['copy_fingerprint'] = native.fingerprint(self.copy / 'resources/app.asar')
                self.state['copy_binary_fingerprint'] = native.fingerprint(self.copy / 'ChatGPT')
                native.write_json(native.state_path(), self.state)
        (self.copy / 'ChatGPT').unlink()
        self.assertEqual(native.resolve_command(self.command), self.command)

    def test_missing_policy_or_invalid_state_never_launches_copy(self):
        with patch.object(native, 'policy_required', return_value=True), patch.object(native, 'policy_installed', return_value=False):
            self.assertTrue(native.status()['available'])
            self.assertFalse(native.status()['enabled'])
            self.assertEqual(native.resolve_command(self.command), self.command)
        native.state_path().write_text('not JSON')
        self.assertEqual(native.resolve_command(self.command), self.command)

    def test_disable_and_running_uninstall_preserve_recovery(self):
        native.disable()
        self.assertEqual(native.resolve_command(self.command), self.command)
        with patch.object(native, 'running_in', return_value=True):
            self.assertIn('仍在运行', native.uninstall())
        self.assertTrue(self.copy.exists())
        self.assertTrue(native.state_path().exists())
        with patch.object(native, 'running_in', return_value=False): native.uninstall()
        self.assertFalse(self.copy.exists())
        self.assertFalse(native.state_path().exists())

    def test_policy_is_user_specific_and_rejects_pattern_injection(self):
        policy = native.apparmor_profile()
        self.assertIn(str(native.root_path().resolve()) + '/versions/*/ChatGPT', policy)
        self.assertIn('userns,', policy)
        self.assertNotIn('/usr/lib/chatgpt', policy)
        with patch.dict(os.environ, {'XDG_DATA_HOME': str(self.root / 'bad*')}):
            with self.assertRaises(ValueError): native.apparmor_profile()

    def test_unsupported_package_does_not_touch_state_or_original(self):
        fixture(self.source / 'resources/app.asar', {'package.json': json.dumps({
            'name': 'openai-codex-electron', 'version': 'future'}).encode()})
        original = native.state_path().read_bytes()
        with patch.object(os, 'geteuid', return_value=1000), self.assertRaises(RuntimeError):
            native.install(self.source)
        self.assertEqual(native.state_path().read_bytes(), original)

    def supported_fixture(self):
        from asar import digest_file
        fixture(self.source / 'resources/app.asar', {'package.json': json.dumps({
            'name': 'openai-codex-electron', 'version': native.SUPPORTED_VERSION}).encode()})
        self.state['validated'] = False
        native.write_json(native.state_path(), self.state)
        launcher.config_path().parent.mkdir(parents=True, exist_ok=True)
        launcher.config_path().write_text(json.dumps({'app_command': self.command}))
        return digest_file(self.source / 'resources/app.asar')

    def test_low_disk_keeps_existing_state(self):
        digest = self.supported_fixture()
        original = native.state_path().read_bytes()
        with patch.object(os, 'geteuid', return_value=1000), \
             patch.object(native, 'SUPPORTED_SHA256', digest), \
             patch.object(native.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)), \
             patch.dict(os.environ, {'DISPLAY': ':test'}), self.assertRaisesRegex(RuntimeError, '磁盘空间'):
            native.install(self.source)
        self.assertEqual(native.state_path().read_bytes(), original)

    def test_failed_probe_cleans_stage_without_switching_target(self):
        digest = self.supported_fixture()
        original = native.state_path().read_bytes()
        def copy_tree(command, **kwargs):
            import shutil
            shutil.copytree(self.source, Path(command[-1]), dirs_exist_ok=True)
        with patch.object(os, 'geteuid', return_value=1000), \
             patch.object(native, 'SUPPORTED_SHA256', digest), \
             patch.object(native.subprocess, 'run', side_effect=copy_tree), \
             patch.object(native, 'probe', side_effect=RuntimeError('probe failed')), \
             patch.dict(os.environ, {'DISPLAY': ':test'}), self.assertRaisesRegex(RuntimeError, 'probe failed'):
            native.install(self.source)
        self.assertEqual(native.state_path().read_bytes(), original)
        self.assertEqual(list((native.root_path() / 'versions').iterdir()), [self.copy])
