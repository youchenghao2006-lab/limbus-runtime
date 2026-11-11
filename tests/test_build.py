"""Check import safety and relocatable packaging without requiring Swift on Linux."""
import importlib.util
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_build():
    spec = importlib.util.spec_from_file_location('limbus_build', ROOT / 'scripts/build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildTests(unittest.TestCase):
    def test_import_does_not_build_or_create_directories(self):
        with patch('subprocess.run') as run, patch.object(Path, 'mkdir') as mkdir:
            load_build()
        run.assert_not_called()
        mkdir.assert_not_called()

    def test_bundle_moves_without_checkout_configuration(self):
        build = load_build()
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / 'private-checkout'
            (checkout / 'Sources').mkdir(parents=True)
            (checkout / 'Sources/LimbusLauncher.swift').write_text('// compiler is mocked in this packaging test\n')
            (checkout / 'scripts').mkdir()
            shutil.copy2(ROOT / 'scripts/backend.py', checkout / 'scripts/backend.py')
            resources = checkout / 'dist/Limbus Runtime.app/Contents/Resources'
            resources.mkdir(parents=True)
            (resources / 'config.json').write_text(json.dumps({'projectRoot': str(checkout)}))
            with patch.object(build.platform, 'system', return_value='Darwin'), patch.object(build.subprocess, 'run'):
                app = build.build(checkout)
            self.assertFalse((resources / 'config.json').exists())
            plist = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
            self.assertEqual(plist['CFBundleIdentifier'], 'io.github.limbus-runtime.launcher')
            self.assertEqual(plist['CFBundleShortVersionString'], '0.2.0')
            for artifact in app.rglob('*'):
                if artifact.is_file():
                    self.assertNotIn(str(checkout).encode(), artifact.read_bytes())
            moved = Path(tmp) / 'Different Location/Launcher.app'
            moved.parent.mkdir()
            shutil.move(str(app), str(moved))
            shutil.rmtree(checkout)
            # The copied backend remains usable after its source checkout is removed.
            state = Path(tmp) / 'new-state'
            result = subprocess.run([
                sys.executable, str(moved / 'Contents/Resources/backend.py'),
                '--root', str(state), 'status',
            ], capture_output=True, text=True, check=True)
            status = json.loads(result.stdout)
            self.assertEqual(status['root'], str(state.resolve()))
            self.assertFalse(status['runtimeReady'])
            self.assertFalse(state.exists())


if __name__ == '__main__':
    unittest.main()
