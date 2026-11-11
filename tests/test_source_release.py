import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'source_release.py'
spec = importlib.util.spec_from_file_location('source_release', MODULE)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class SourceReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'project'
        self.root.mkdir()
        (self.root / 'README.md').write_text('# Example project\n', encoding='utf-8')
        self.set_manifest(['README.md', 'release-files.json'])

    def set_manifest(self, files):
        (self.root / 'release-files.json').write_text(
            json.dumps({'version': '0.2.0', 'files': files}), encoding='utf-8')

    def test_archive_is_deterministic_and_contains_only_allowlisted_files(self):
        (self.root / 'runtime').mkdir()
        (self.root / 'runtime' / 'private-data.txt').write_text('local data')
        version, sources = release.collect_sources(self.root)
        archive, checksum = release.write_archive(self.root, version, sources)
        first = archive.read_bytes()
        os.utime(self.root / 'README.md', (1700000000, 1700000000))
        (self.root / 'README.md').chmod(0o600)
        version, sources = release.collect_sources(self.root)
        release.write_archive(self.root, version, sources)
        self.assertEqual(archive.read_bytes(), first)
        self.assertEqual(checksum.read_text(), hashlib.sha256(first).hexdigest() + '  ' + archive.name + '\n')
        with zipfile.ZipFile(archive) as output:
            self.assertEqual(output.namelist(), [
                'limbus-runtime-0.2.0/README.md', 'limbus-runtime-0.2.0/release-files.json'])
            for info in output.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.external_attr >> 16, 0o100644)

    def test_private_paths_are_rejected_even_when_allowlisted(self):
        for name in ['runtime/data.txt', 'logs/runtime.log', '.cache/installer.txt',
                     'data/ssfn12345', 'data/loginusers.vdf', 'data/credentials.json',
                     'startup-verified.json', 'vendor/Steam.exe', 'data/user.reg']:
            with self.subTest(name=name):
                self.set_manifest(['release-files.json', name])
                with self.assertRaises(release.ReleaseError):
                    release.collect_sources(self.root)

    def test_absolute_and_traversal_paths_are_rejected(self):
        outside = Path(self.temporary.name) / 'outside.txt'
        outside.write_text('outside')
        for name in [str(outside), '../outside.txt', 'docs/../../outside.txt',
                     'docs//guide.md', './README.md', 'C:\\outside.txt']:
            with self.subTest(name=name):
                self.set_manifest(['release-files.json', name])
                with self.assertRaises(release.ReleaseError):
                    release.collect_sources(self.root)

    def test_symlink_file_is_rejected(self):
        link = self.root / 'link.md'
        link.symlink_to(self.root / 'README.md')
        self.set_manifest(['release-files.json', 'link.md'])
        with self.assertRaisesRegex(release.ReleaseError, 'Symbolic links'):
            release.collect_sources(self.root)

    def test_symlink_parent_is_rejected(self):
        outside = Path(self.temporary.name) / 'docs'
        outside.mkdir()
        (outside / 'guide.md').write_text('outside')
        (self.root / 'docs').symlink_to(outside, target_is_directory=True)
        self.set_manifest(['release-files.json', 'docs/guide.md'])
        with self.assertRaisesRegex(release.ReleaseError, 'Symbolic links'):
            release.collect_sources(self.root)

    def test_symlink_manifest_and_root_are_rejected(self):
        alias = Path(self.temporary.name) / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(release.ReleaseError):
            release.collect_sources(alias)
        manifest = self.root / 'release-files.json'
        outside = Path(self.temporary.name) / 'manifest.json'
        manifest.rename(outside)
        manifest.symlink_to(outside)
        with self.assertRaises(release.ReleaseError):
            release.collect_sources(self.root)

    def test_sensitive_content_is_rejected_without_disclosing_value(self):
        values = ['/' + 'Users' + '/example-person/project',
                  'gh' + 'p_' + 'a' * 36,
                  'sk' + '-proj-' + 'A' * 40,
                  'pass' + 'word = "' + 'abc123xyz456def789' + '"',
                  '-----BEGIN ' + 'PRIVATE KEY-----']
        for value in values:
            with self.subTest(kind=value[:3]):
                (self.root / 'README.md').write_text(value)
                with self.assertRaises(release.ReleaseError) as context:
                    release.collect_sources(self.root)
                self.assertNotIn(value, str(context.exception))
                self.assertIn('README.md', str(context.exception))

    def test_missing_binary_and_duplicate_files_are_rejected(self):
        self.set_manifest(['release-files.json', 'missing.md'])
        with self.assertRaisesRegex(release.ReleaseError, 'Missing source file'):
            release.collect_sources(self.root)
        self.set_manifest(['release-files.json', 'README.md'])
        (self.root / 'README.md').write_bytes(b'binary\x00data')
        with self.assertRaisesRegex(release.ReleaseError, 'Binary data'):
            release.collect_sources(self.root)
        self.set_manifest(['release-files.json', 'release-files.json'])
        with self.assertRaisesRegex(release.ReleaseError, 'unique'):
            release.collect_sources(self.root)

    def test_output_symlinks_cannot_overwrite_other_files(self):
        outside = Path(self.temporary.name) / 'outside'
        outside.mkdir()
        (self.root / 'dist').symlink_to(outside, target_is_directory=True)
        version, sources = release.collect_sources(self.root)
        with self.assertRaises(release.ReleaseError):
            release.write_archive(self.root, version, sources)
        self.assertEqual(list(outside.iterdir()), [])

    @unittest.skipUnless(shutil.which('git'), 'Git is unavailable')
    def test_staged_private_file_fails_but_parent_repository_is_ignored(self):
        # The user's surrounding checkout must not be interpreted as this project.
        parent = Path(self.temporary.name)
        subprocess.run(['git', 'init', '-q', str(parent)], check=True)
        (parent / 'unrelated.txt').write_text('unrelated')
        subprocess.run(['git', '-C', str(parent), 'add', 'unrelated.txt'], check=True)
        release.collect_sources(self.root)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'runtime').mkdir()
        (self.root / 'runtime' / 'private.txt').write_text('private')
        subprocess.run(['git', '-C', str(self.root), 'add', 'runtime/private.txt'], check=True)
        with self.assertRaisesRegex(release.ReleaseError, 'outside the source allowlist'):
            release.collect_sources(self.root)
        subprocess.run(['git', '-C', str(self.root), 'rm', '--cached', '-q', 'runtime/private.txt'], check=True)
        release.collect_sources(self.root)


if __name__ == '__main__':
    unittest.main()
