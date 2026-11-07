#!/usr/bin/env python3
"""Build a movable arm64 macOS launcher; runtime data is never bundled."""
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def build(root=ROOT):
    if platform.system() != 'Darwin':
        raise RuntimeError('The native launcher requires macOS and Apple Command Line Tools.')
    root = Path(root).resolve()
    app = root / 'dist' / 'Limbus Runtime.app'
    contents = app / 'Contents'
    macos = contents / 'MacOS'
    resources = contents / 'Resources'
    macos.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    cache = root / '.build' / 'ModuleCache'
    cache.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        '/usr/bin/xcrun', 'swiftc', '-parse-as-library', '-O',
        '-target', 'arm64-apple-macosx14.6', '-module-cache-path', str(cache),
        '-framework', 'SwiftUI', '-framework', 'AppKit',
        str(root / 'Sources' / 'LimbusLauncher.swift'),
        '-o', str(macos / 'LimbusLauncher'),
    ], check=True)
    shutil.copy2(root / 'scripts' / 'backend.py', resources / 'backend.py')
    # Remove the development-only absolute path configuration from older builds.
    (resources / 'config.json').unlink(missing_ok=True)
    with (contents / 'Info.plist').open('wb') as file:
        plistlib.dump({
            'CFBundleExecutable': 'LimbusLauncher',
            'CFBundleIdentifier': 'io.github.limbus-runtime.launcher',
            'CFBundleName': 'Limbus Runtime',
            'CFBundleDisplayName': 'Limbus Runtime',
            'CFBundlePackageType': 'APPL',
            'CFBundleShortVersionString': '0.2.0',
            'CFBundleVersion': '2',
            'LSMinimumSystemVersion': '14.6',
            'NSHighResolutionCapable': True,
        }, file)
    # Ad-hoc signing is for local use, not Developer ID signing or notarization.
    subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(app)], check=True)
    return app


def main():
    print(build())


if __name__ == '__main__':
    main()
