#!/usr/bin/env python3
"""Validate and package an explicit source allowlist without runtime or user data."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'release-files.json'
MAX_SOURCE_BYTES = 2 * 1024 * 1024
PRIVATE_COMPONENTS = {
    '.git', '.cache', '.build', '.venv', 'venv', '__pycache__', 'node_modules',
    'runtime', 'logs', 'dist', 'prefix', 'drive_c', 'steamapps', 'userdata',
    'config', 'config.json', 'credentials.json', 'secrets.json', 'accounts.json',
    '.netrc', '.npmrc', '.pypirc', 'loginusers.vdf', 'localconfig.vdf', 'config.vdf', 'cookies',
    'cookies.binarycookies', 'startup-verified.json', 'gameplay-verified.json',
}
BINARY_SUFFIXES = {
    '.exe', '.dll', '.dylib', '.so', '.app', '.zip', '.tar', '.gz', '.xz',
    '.dmg', '.pkg', '.db', '.sqlite', '.sqlite3', '.p12', '.pfx', '.pem', '.key', '.log', '.reg',
}
CONTENT_RULES = (
    ('personal absolute path', re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+(?:/|\b)')),
    ('private key', re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----')),
    ('GitHub token', re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b')),
    ('API token', re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b')),
    ('cloud access key', re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')),
    ('credential assignment', re.compile(
        r'''(?ix)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password)\b
        ["']?\s*[:=]\s*["'][A-Za-z0-9_+/.=-]{16,}["']''')),
)


class ReleaseError(ValueError):
    pass


def validate_name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+', name):
        raise ReleaseError('Release paths must be portable relative paths.')
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ('', '.', '..') for part in name.split('/')):
        raise ReleaseError('Release paths must stay inside the project.')
    for part in path.parts:
        low = part.lower()
        if (low in PRIVATE_COMPONENTS or low == '.env' or low.startswith('.env.')
                or re.fullmatch(r'ssfn\d+', low) or low.startswith('appmanifest_')
                or PurePosixPath(low).suffix in BINARY_SUFFIXES):
            raise ReleaseError('A private or runtime path is present in the source allowlist.')
    return path


def read_source(root, name):
    relative = validate_name(name)
    current = root
    if root.is_symlink():
        raise ReleaseError('The source root must not be a symbolic link.')
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ReleaseError('Symbolic links are not allowed in source paths: ' + name)
    if not current.is_file():
        raise ReleaseError('Missing source file: ' + name)
    if current.stat().st_size > MAX_SOURCE_BYTES:
        raise ReleaseError('Source file exceeds the size limit: ' + name)
    data = current.read_bytes()
    try:
        content = data.decode('utf-8')
    except UnicodeDecodeError as error:
        raise ReleaseError('Source file is not UTF-8 text: ' + name) from error
    if '\x00' in content:
        raise ReleaseError('Binary data is not allowed in source files: ' + name)
    for category, pattern in CONTENT_RULES:
        if pattern.search(content):
            # Report only the category and reviewed filename, never matched data.
            raise ReleaseError('Possible ' + category + ' in ' + name)
    return data


def check_tracked_files(root, allowed):
    # A surrounding repository must not make unrelated files part of this release.
    marker = root / '.git'
    if not marker.exists():
        return
    try:
        top = subprocess.check_output(
            ['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
            text=True, stderr=subprocess.DEVNULL).strip()
        if Path(top).resolve() != root.resolve():
            raise ReleaseError('Git metadata does not belong to this project root.')
        tracked = subprocess.check_output(
            ['git', '-C', str(root), 'ls-files', '--cached', '-z'],
            stderr=subprocess.DEVNULL).decode('utf-8').split('\x00')
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise ReleaseError('Unable to inspect this project\'s Git index.') from error
    unexpected = sorted(set(tracked) - {''} - set(allowed))
    if unexpected:
        raise ReleaseError('Git tracks files outside the source allowlist; remove them from the index: '
                           + ', '.join(unexpected))


def collect_sources(root):
    root = Path(root).absolute()
    manifest_data = read_source(root, MANIFEST)
    try:
        manifest = json.loads(manifest_data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseError('Invalid release manifest JSON.') from error
    if not isinstance(manifest, dict):
        raise ReleaseError('Release manifest must be an object.')
    version = manifest.get('version')
    if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ReleaseError('Release version must use major.minor.patch.')
    files = manifest.get('files')
    if not isinstance(files, list) or not files or not all(isinstance(item, str) for item in files):
        raise ReleaseError('Release manifest must contain a nonempty file allowlist.')
    if len(files) != len(set(files)) or MANIFEST not in files:
        raise ReleaseError('Release file allowlist must be unique and include its manifest.')
    sources = {name: read_source(root, name) for name in sorted(files)}
    check_tracked_files(root, sources)
    return version, sources


def write_archive(root, version, sources):
    root = Path(root).absolute()
    output_dir = root / 'dist'
    if output_dir.is_symlink():
        raise ReleaseError('The release output directory must not be a symbolic link.')
    output_dir.mkdir(exist_ok=True)
    archive = output_dir / ('limbus-runtime-' + version + '-source.zip')
    checksum = archive.with_name(archive.name + '.sha256')
    if archive.is_symlink() or checksum.is_symlink():
        raise ReleaseError('Release outputs must not be symbolic links.')
    descriptor, temporary_name = tempfile.mkstemp(prefix='.source-release-', suffix='.zip', dir=output_dir)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        # Stored entries avoid differences between zlib versions; metadata is fixed.
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as output:
            for name, data in sorted(sources.items()):
                info = zipfile.ZipInfo('limbus-runtime-' + version + '/' + name, (1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (0o100644 << 16)
                output.writestr(info, data)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        temporary.replace(archive)
        checksum.write_text(digest + '  ' + archive.name + '\n', encoding='utf-8')
    finally:
        temporary.unlink(missing_ok=True)
    return archive, checksum


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='validate sources without creating an archive')
    args = parser.parse_args(argv)
    try:
        version, sources = collect_sources(ROOT)
        if args.check:
            print('Source checks passed: %d files, version %s.' % (len(sources), version))
        else:
            archive, checksum = write_archive(ROOT, version, sources)
            print(archive)
            print(checksum)
    except ReleaseError as error:
        parser.exit(1, 'Release check failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
