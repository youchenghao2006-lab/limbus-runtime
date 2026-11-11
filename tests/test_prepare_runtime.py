import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_runtime', ROOT / 'scripts/prepare_runtime.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class Response(io.BytesIO):
    def geturl(self):
        return 'https://example.invalid/release'


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = prepare.load_manifest(ROOT / 'runtime-sources.json')

    def asset(self, data):
        return {'name': 'test.tar', 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

    def archive(self, entries):
        path = self.root / 'test.tar'
        with tarfile.open(path, 'w') as stream:
            for name, kind, content in entries:
                info = tarfile.TarInfo(name)
                if kind == 'file':
                    data = content.encode()
                    info.size = len(data)
                    info.mode = 0o755
                    stream.addfile(info, io.BytesIO(data))
                else:
                    info.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
                    info.linkname = content
                    stream.addfile(info)
        destination = self.root / 'stage'
        destination.mkdir()
        return path, destination

    def test_streamed_hash_and_size_are_both_required(self):
        file = self.root / 'asset'
        file.write_bytes(b'valid')
        prepare.verify_asset(file, self.asset(b'valid'))
        with self.assertRaises(ValueError):
            prepare.verify_asset(file, self.asset(b'wrong'))
        mismatched = self.asset(b'valid')
        mismatched['size'] += 1
        with self.assertRaises(ValueError):
            prepare.verify_asset(file, mismatched)

    def test_check_does_not_create_data_or_download(self):
        target = self.root / 'never-created'
        with patch.object(prepare, 'platform_issues', return_value=[]), patch.object(prepare, 'download') as download:
            report = prepare.check(target, self.manifest)
        self.assertFalse(target.exists())
        self.assertFalse(report['runtimeReady'])
        self.assertEqual([a['cache'] for a in report['assets']], ['missing', 'missing'])
        download.assert_not_called()

    def test_check_reports_corrupt_cache(self):
        target = self.root / '.cache'
        target.mkdir()
        (target / self.manifest['assets'][0]['name']).write_bytes(b'broken')
        with patch.object(prepare, 'platform_issues', return_value=[]):
            report = prepare.check(self.root, self.manifest)
        self.assertEqual(report['assets'][0]['cache'], 'invalid')

    def test_default_data_root_is_configurable(self):
        with patch.dict(os.environ, {'LIMBUS_RUNTIME_HOME': str(self.root)}):
            self.assertEqual(prepare.default_root(), self.root.resolve())

    def test_download_rejects_hash_mismatch_and_preserves_cache(self):
        destination = self.root / 'cache'
        destination.write_bytes(b'previous')
        with patch.object(prepare, 'urlopen', return_value=Response(b'wrong')):
            with self.assertRaises(ValueError):
                prepare.download('https://example.invalid/file', destination, self.asset(b'valid'))
        self.assertEqual(destination.read_bytes(), b'previous')
        self.assertEqual(list(self.root.glob('*.part')), [])

    def test_download_success_is_atomic(self):
        destination = self.root / 'cache'
        with patch.object(prepare, 'urlopen', return_value=Response(b'valid')):
            prepare.download('https://example.invalid/file', destination, self.asset(b'valid'))
        self.assertEqual(destination.read_bytes(), b'valid')
        self.assertEqual(list(self.root.glob('*.part')), [])

    def test_download_rejects_http(self):
        with self.assertRaises(ValueError), patch.object(prepare, 'urlopen') as open_url:
            prepare.download('http://example.invalid/file', self.root / 'asset')
        open_url.assert_not_called()

    def test_extract_preserves_internal_symlinks_and_executable_bit(self):
        archive, target = self.archive([('app/bin/tool', 'file', 'source'), ('app/bin/current', 'symlink', 'tool')])
        prepare.safe_extract(archive, target)
        self.assertEqual((target / 'app/bin/current').read_text(), 'source')
        self.assertTrue((target / 'app/bin/current').is_symlink())
        self.assertTrue((target / 'app/bin/tool').stat().st_mode & 0o100)

    def test_extract_rejects_path_traversal_before_writing(self):
        archive, target = self.archive([('valid', 'file', 'ok'), ('../outside', 'file', 'bad')])
        with self.assertRaises(ValueError):
            prepare.safe_extract(archive, target)
        self.assertEqual(list(target.iterdir()), [])
        self.assertFalse((self.root / 'outside').exists())

    def test_extract_rejects_absolute_link(self):
        archive, target = self.archive([('link', 'symlink', '/tmp/outside')])
        with self.assertRaises(ValueError):
            prepare.safe_extract(archive, target)

    def test_extract_never_writes_through_links(self):
        archive, target = self.archive([('a', 'symlink', 'b'), ('a/data', 'file', 'unsafe')])
        with self.assertRaises(ValueError):
            prepare.safe_extract(archive, target)
        self.assertEqual(list(target.iterdir()), [])

    def test_extract_rejects_chained_escape(self):
        archive, target = self.archive([('a/deep/link', 'symlink', '../..'), ('outer', 'symlink', 'a/deep/link/..')])
        with self.assertRaises(ValueError):
            prepare.safe_extract(archive, target)

    def test_extract_rejects_missing_hardlink_target(self):
        archive, target = self.archive([('link', 'hardlink', '../outside')])
        with self.assertRaises(ValueError):
            prepare.safe_extract(archive, target)

    def test_partial_existing_wrapper_is_never_overwritten(self):
        wrapper = self.root / 'runtime/LimbusRuntime.app'
        wrapper.mkdir(parents=True)
        sentinel = wrapper / 'user-file'
        sentinel.write_text('keep')
        with patch.object(prepare, 'download') as download, self.assertRaisesRegex(RuntimeError, '未完成'):
            prepare.prepare(self.root, self.manifest)
        self.assertEqual(sentinel.read_text(), 'keep')
        download.assert_not_called()

    def test_initialize_creates_log_directory_for_fresh_root(self):
        data = self.root / 'fresh'
        launcher = types.SimpleNamespace(
            logs=data / 'logs', prefix=data / 'runtime/prefix',
            wine=data / 'runtime/wine/bin/wine', wine_root=data / 'runtime/wine',
            environment=lambda: {'WINEPREFIX': str(data / 'runtime/prefix')})
        def run(*args, **kwargs):
            launcher.prefix.mkdir(parents=True, exist_ok=True)
            (launcher.prefix / 'system.reg').write_text('registry')
        backend = types.SimpleNamespace(Launcher=lambda root: launcher)
        with patch.dict(sys.modules, {'backend': backend}), patch.object(prepare.subprocess, 'run', side_effect=run) as process:
            prepare.initialize(data)
        self.assertTrue((launcher.logs / 'prepare.log').is_file())
        self.assertEqual(process.call_count, 2)

    def test_empty_environment_uses_default_home(self):
        with patch.dict(os.environ, {'LIMBUS_RUNTIME_HOME': ''}):
            self.assertEqual(prepare.default_root(), (Path.home() / 'Library/Application Support/Limbus Runtime').resolve())

    def test_default_invocation_requires_explicit_consent_and_has_no_writes(self):
        target = self.root / 'never-created'
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            prepare.main(['--root', str(target)])
        self.assertEqual(result.exception.code, 2)
        self.assertFalse(target.exists())

    def test_check_cli_remains_read_only(self):
        target = self.root / 'never-created'
        output = io.StringIO()
        with patch.object(prepare, 'platform_issues', return_value=[]), contextlib.redirect_stdout(output):
            code = prepare.main(['--check', '--root', str(target)])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(output.getvalue())['runtimeReady'])
        self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
