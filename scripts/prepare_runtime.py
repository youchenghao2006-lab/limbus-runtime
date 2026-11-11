#!/usr/bin/env python3
"""Prepare user-local third-party components; never distribute a populated prefix."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import posixpath
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SOURCE_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = 'Template-1.0.21.tar.xz'
ENGINE = 'WS12WineSikarugir11.0_1.tar.xz'
CHUNK = 1024 * 1024


def default_root():
    value = os.environ.get('LIMBUS_RUNTIME_HOME') or str(Path.home() / 'Library' / 'Application Support' / 'Limbus Runtime')
    return Path(value).expanduser().resolve()


def verify_asset(path, asset):
    """Hash incrementally so checking an archive does not duplicate it in RAM."""
    digest = hashlib.sha256()
    size = 0
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(CHUNK), b''):
            digest.update(block)
            size += len(block)
    if size != asset['size'] or digest.hexdigest() != asset['sha256']:
        raise ValueError('组件大小或 SHA-256 校验失败：' + asset['name'])


def load_manifest(path):
    manifest = json.loads(Path(path).read_text())
    assets = manifest.get('assets', [])
    if len(assets) != 2 or {a.get('name') for a in assets} != {TEMPLATE, ENGINE}:
        raise ValueError('组件清单必须包含已支持的固定模板和 Wine 引擎。')
    for asset in assets:
        if (urlparse(asset['url']).scheme != 'https'
                or not isinstance(asset['size'], int) or asset['size'] <= 0
                or len(asset['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in asset['sha256'])):
            raise ValueError('组件清单的 HTTPS 地址、大小或校验值无效。')
    if manifest.get('steam_url') != 'https://cdn.akamai.steamstatic.com/client/installer/SteamSetup.exe':
        raise ValueError('Steam 安装包必须来自清单中的 Valve 官方 HTTPS 地址。')
    return manifest


def platform_issues():
    issues = []
    if platform.system() != 'Darwin':
        return ['运行环境仅支持 macOS。']
    if platform.machine() != 'arm64':
        issues.append('请使用 Apple Silicon Mac 的原生 arm64 Python。')
    version = tuple(int(part) for part in platform.mac_ver()[0].split('.')[:2])
    if version < (14, 6):
        issues.append('需要 macOS 14.6 或更高版本。')
    # Probe translation support without invoking or installing anything else.
    probe = subprocess.run(['/usr/bin/arch', '-x86_64', '/usr/bin/true'], capture_output=True)
    if probe.returncode:
        issues.append('未检测到 Rosetta 2；请通过 macOS 安装后重试。')
    return issues


def check(root, manifest):
    """Read-only report, safe on a fresh machine or an unsupported platform."""
    report = {'root': str(root), 'platformIssues': platform_issues(), 'assets': []}
    for asset in manifest['assets']:
        path = root / '.cache' / asset['name']
        state = 'missing'
        if path.is_file():
            try:
                verify_asset(path, asset)
                state = 'verified'
            except ValueError:
                state = 'invalid'
        report['assets'].append({'name': asset['name'], 'cache': state, 'url': asset['url']})
    wrapper = root / 'runtime' / 'LimbusRuntime.app'
    report['runtimeReady'] = ((wrapper / 'Contents/SharedSupport/wine/bin/wine').is_file()
                              and (wrapper / 'Contents/SharedSupport/prefix/system.reg').is_file())
    report['steamInstallerPresent'] = (root / '.cache/SteamSetup.exe').is_file()
    return report


def download(url, destination, asset=None):
    """Publish only complete verified downloads; preserve existing cache on failure."""
    if urlparse(url).scheme != 'https':
        raise ValueError('只允许 HTTPS 下载。')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=destination.name + '.', suffix='.part', dir=destination.parent)
    temporary = Path(temporary_name)
    limit = asset['size'] if asset else 128 * CHUNK
    try:
        with os.fdopen(fd, 'wb') as output:
            request = Request(url, headers={'User-Agent': 'Limbus-Runtime/0.2.0'})
            with urlopen(request, timeout=60) as response:
                if urlparse(response.geturl()).scheme != 'https':
                    raise ValueError('拒绝非 HTTPS 重定向。')
                count = 0
                for block in iter(lambda: response.read(CHUNK), b''):
                    count += len(block)
                    if count > limit:
                        raise ValueError('下载大小超出预期。')
                    output.write(block)
        if asset:
            verify_asset(temporary, asset)
        else:
            with temporary.open('rb') as stream:
                if stream.read(2) != b'MZ':
                    raise ValueError('Steam 下载结果不是 Windows 安装程序。')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _relative_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or not path.parts:
        raise ValueError('压缩包包含不安全路径：' + name)
    return path


def safe_extract(archive_path, destination):
    """Validate every member before writing, and never write through archive links."""
    destination = Path(destination)
    if not destination.is_dir() or any(destination.iterdir()):
        raise ValueError('解压目标必须是独立的空暂存目录。')
    with tarfile.open(archive_path, 'r:*') as archive:
        members = archive.getmembers()
        names = {}
        links = set()
        for member in members:
            path = _relative_name(member.name)
            if path in names:
                raise ValueError('压缩包包含重复路径：' + member.name)
            names[path] = member
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise ValueError('压缩包包含特殊设备或不支持的文件。')
            if member.issym() or member.islnk():
                links.add(path)
                target = member.linkname
                if PurePosixPath(target).is_absolute() or '\\' in target:
                    raise ValueError('压缩包包含不安全链接：' + member.name)
                resolved = posixpath.normpath(str(path.parent / target) if member.issym() else target)
                if resolved == '..' or resolved.startswith('../'):
                    raise ValueError('压缩包链接越过目标目录：' + member.name)
        for path, member in names.items():
            if any(parent in links for parent in path.parents):
                raise ValueError('压缩包试图通过链接写入文件：' + member.name)
            if member.islnk():
                target = names.get(PurePosixPath(member.linkname))
                if target is None or not target.isfile():
                    raise ValueError('压缩包硬链接必须指向包内普通文件。')
        # Regular files/directories first, links last. tarfile's platform defaults
        # differ across Python versions, so perform the writes explicitly.
        for path, member in names.items():
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                target.chmod(member.mode & 0o777)
        for path, member in names.items():
            target = destination.joinpath(*path.parts)
            if member.issym():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(member.linkname)
            elif member.islnk():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.link(destination.joinpath(*PurePosixPath(member.linkname).parts), target)
        for path in links:
            try:
                destination.joinpath(*path.parts).resolve().relative_to(destination.resolve())
            except (ValueError, RuntimeError):
                raise ValueError('压缩包包含越界或循环链接：' + str(path))


def assemble(root, manifest):
    runtime = root / 'runtime'
    wrapper = runtime / 'LimbusRuntime.app'
    if wrapper.exists() or wrapper.is_symlink():
        raise RuntimeError('目标运行环境已经存在，拒绝覆盖。')
    runtime.mkdir(parents=True, exist_ok=True)
    for asset in manifest['assets']:
        verify_asset(root / '.cache' / asset['name'], asset)
    with tempfile.TemporaryDirectory(prefix='.prepare-', dir=runtime) as scratch:
        scratch = Path(scratch)
        template_dir, engine_dir = scratch / 'template', scratch / 'engine'
        template_dir.mkdir()
        engine_dir.mkdir()
        safe_extract(root / '.cache' / TEMPLATE, template_dir)
        safe_extract(root / '.cache' / ENGINE, engine_dir)
        source = template_dir / 'Template-1.0.21.app'
        wine = engine_dir / 'wswine.bundle'
        if not (source / 'Contents/Info.plist').is_file() or not (wine / 'bin/wine').is_file():
            raise ValueError('上游组件布局不符合固定版本的预期。')
        support = source / 'Contents/SharedSupport'
        support.mkdir(exist_ok=True)
        wine.rename(support / 'wine')
        plist_path = source / 'Contents/Info.plist'
        with plist_path.open('rb') as stream:
            settings = plistlib.load(stream)
        settings.update({
            'CFBundleName': 'Limbus Runtime',
            'CFBundleIdentifier': 'io.github.limbus-runtime.runtime',
            'Program Name and Path': '/Program Files (x86)/Steam/Steam.exe',
            'Program Flags': '', 'Skip Gecko': 1, 'Skip Mono': 1,
            'D3DMETAL': 0, 'DXVK': 0, 'CNC_DDRAW': 0, 'D9VK': 0,
            'Symlinks In User Folder': 0, 'WINEDEBUG': '-all',
        })
        with plist_path.open('wb') as stream:
            plistlib.dump(settings, stream)
        # All upstream license and notice files remain in this user-local wrapper.
        source.rename(wrapper)
    return wrapper


def initialize(root):
    from backend import Launcher
    launcher = Launcher(root)
    launcher.logs.mkdir(parents=True, exist_ok=True)
    with (launcher.logs / 'prepare.log').open('ab') as log:
        subprocess.run([str(launcher.wine), 'wineboot', '-u'], env=launcher.environment(),
                       cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                       timeout=180, check=True)
        subprocess.run([str(launcher.wine_root / 'bin/wineserver'), '-w'],
                       env=launcher.environment(), stdin=subprocess.DEVNULL,
                       stdout=log, stderr=log, timeout=180, check=True)
    if not (launcher.prefix / 'system.reg').is_file():
        raise RuntimeError('Wine 初始化未生成注册表，请查看 logs/prepare.log。')


def prepare(root, manifest, steam_installer=False, skip_init=False):
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.prepare.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('另一个初始化进程正在运行。')
        wrapper = root / 'runtime/LimbusRuntime.app'
        exists = wrapper.exists() or wrapper.is_symlink()
        ready = ((wrapper / 'Contents/SharedSupport/wine/bin/wine').is_file()
                 and (wrapper / 'Contents/SharedSupport/prefix/system.reg').is_file())
        if exists and not ready:
            raise RuntimeError('检测到未完成的运行环境，拒绝覆盖。请查看 logs/prepare.log；先备份并手动移走该 runtime/LimbusRuntime.app 后重试，或使用新的 --root。')
        if not exists:
            cache = root / '.cache'
            for asset in manifest['assets']:
                path = cache / asset['name']
                if path.is_file():
                    verify_asset(path, asset)  # Invalid caches require explicit removal.
                else:
                    print('下载并校验：' + asset['name'], flush=True)
                    download(asset['url'], path, asset)
            assemble(root, manifest)
            if not skip_init:
                initialize(root)
        if steam_installer:
            print('Steam 安装包来自 Valve 官方 HTTPS 地址，但地址会更新且没有固定 SHA-256；本脚本不会执行它。', flush=True)
            download(manifest['steam_url'], root / '.cache/SteamSetup.exe')
        return {'wrapper': str(wrapper), 'initialized': not skip_init or ready,
                'steamInstallerDownloaded': steam_installer}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=default_root())
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Read-only platform, manifest and cache report')
    mode.add_argument('--download', action='store_true', help='Download verified third-party components and prepare runtime')
    parser.add_argument('--accept-third-party-licenses', action='store_true', help='Confirm you reviewed THIRD_PARTY_NOTICES.md and applicable upstream terms')
    parser.add_argument('--steam-installer', action='store_true', help='Also download mutable official Steam installer; never execute it')
    parser.add_argument('--skip-init', action='store_true', help='Expert/test use: assemble without running Wine; resulting runtime is incomplete')
    args = parser.parse_args(argv)
    try:
        root = args.root.expanduser().resolve()
        manifest = load_manifest(SOURCE_ROOT / 'runtime-sources.json')
        if args.check:
            if args.steam_installer or args.skip_init or args.accept_third_party_licenses:
                parser.error('--check 不得与安装选项一起使用。')
            print(json.dumps(check(root, manifest), ensure_ascii=False, indent=2))
            return 0
        if not args.download or not args.accept_third_party_licenses:
            parser.error('先阅读 THIRD_PARTY_NOTICES.md，再使用 --download --accept-third-party-licenses；只检查请使用 --check。')
        issues = platform_issues()
        if issues:
            raise RuntimeError(' '.join(issues))
        print(json.dumps(prepare(root, manifest, args.steam_installer, args.skip_init), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, tarfile.TarError) as error:
        print('准备失败：' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
