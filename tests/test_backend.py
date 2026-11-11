import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'backend.py'
spec = importlib.util.spec_from_file_location('backend', MODULE)
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.launcher = backend.Launcher(self.tmp.name)

    def manifest(self, flags, directory='Limbus Company', exe=True):
        apps = self.launcher.steam.parent / 'steamapps'
        apps.mkdir(parents=True, exist_ok=True)
        (apps / 'appmanifest_1973530.acf').write_text(
            '"AppState" { "appid" "1973530" "StateFlags" "%s" "installdir" "%s" }' % (flags, directory))
        if exe:
            game = apps / 'common' / directory
            game.mkdir(parents=True, exist_ok=True)
            (game / 'LimbusCompany.exe').touch()

    def test_crossover_environment_cannot_leak_into_our_prefix(self):
        with patch.dict(os.environ, {'WINEPREFIX': '/other-prefix', 'CX_ROOT': '/Applications/CrossOver.app',
                                     'WINEDLLPATH': '/other-dll', 'DYLD_LIBRARY_PATH': '/other-lib'}):
            env = self.launcher.environment()
        self.assertEqual(env['WINEPREFIX'], str(self.launcher.prefix))
        self.assertNotIn('CX_ROOT', env)
        self.assertNotIn('DYLD_LIBRARY_PATH', env)
        self.assertNotIn('/other-dll', env['WINEDLLPATH'])
        self.assertEqual(env['SikarugirAppWine11'], '1')

    def test_default_root_is_user_data_not_source_checkout(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(backend.Path, 'home', return_value=Path(self.tmp.name)):
            self.assertEqual(backend.default_root(), Path(self.tmp.name) / 'Library/Application Support/Limbus Runtime')

    def test_environment_root_and_explicit_override(self):
        configured = Path(self.tmp.name) / 'configured'
        explicit = Path(self.tmp.name) / 'explicit'
        with patch.dict(os.environ, {'LIMBUS_RUNTIME_HOME': str(configured)}):
            self.assertEqual(backend.Launcher().root, configured.resolve())
            self.assertEqual(backend.Launcher(explicit).root, explicit.resolve())

    def test_status_on_clean_machine_is_read_only(self):
        root = Path(self.tmp.name) / 'not-created'
        result = backend.Launcher(root).status()
        self.assertFalse(root.exists())
        self.assertFalse(result['runtimeReady'])
        self.assertEqual(result['gameState'], 'missing')
        self.assertEqual(result['compatibility'], 'experimental')
        self.assertNotIn('startupVerified', result)

    def test_missing_install_does_not_allow_launch(self):
        self.assertEqual(self.launcher.game_status(), 'missing')
        self.launcher.steam.parent.mkdir(parents=True)
        self.launcher.steam.touch()
        with patch.object(self.launcher, 'launch') as launch:
            with self.assertRaisesRegex(RuntimeError, '尚未安装完成'):
                self.launcher.action('launch-game')
            launch.assert_not_called()

    def test_steam_children_inherit_both_renderer_paths(self):
        with patch.dict(os.environ, {'WINEDLLPATH_DXMT': '/other-dxmt',
                                     'WINEDLLPATH_D3DMETAL': '/other-metal'}):
            steam = self.launcher.environment(steam_ui=True)
            game = self.launcher.environment()
        # Steam-spawned games get the same complete configuration as a direct launch.
        self.assertEqual(steam, game)
        self.assertIn('/renderer/dxmt/', steam['WINEDLLPATH_DXMT'])
        self.assertIn('/renderer/d3dmetal/', steam['WINEDLLPATH_D3DMETAL'])
        self.assertIn('/renderer/d3dmetal/', steam['CX_APPLEGPTK_LIBD3DSHARED_PATH'])

    def test_cold_start_opens_steam_before_game(self):
        self.manifest(4)
        self.launcher.steam.touch()
        with patch.object(self.launcher, 'is_running', return_value=False), patch.object(self.launcher, 'launch', return_value={'ok': True}) as launch:
            result = self.launcher.action('launch-game')
        launch.assert_called_once_with('open-steam', [str(self.launcher.steam)], steam_ui=True)
        self.assertIn('等待登录', result['message'])

    def test_game_does_not_inherit_steam_graphics(self):
        self.manifest(4)
        self.launcher.steam.touch()
        with patch.object(self.launcher, 'is_running', side_effect=[True, False]), patch.object(self.launcher, 'launch', return_value={'ok': True}) as launch:
            self.launcher.action('launch-game')
        args, kwargs = launch.call_args
        self.assertEqual(args[0], 'launch-game')
        self.assertTrue(args[1][0].endswith('/LimbusCompany.exe'))
        self.assertNotIn('-applaunch', args[1])
        self.assertFalse(kwargs.get('steam_ui', False))

    def test_launch_uses_manifest_directory(self):
        self.manifest(4, directory='Custom Game Directory')
        self.launcher.steam.touch()
        with patch.object(self.launcher, 'is_running', side_effect=[True, False]), patch.object(self.launcher, 'launch', return_value={'ok': True}) as launch:
            self.launcher.action('launch-game')
        executable = Path(launch.call_args[0][1][0])
        self.assertEqual(executable.parent.name, 'Custom Game Directory')

    def test_download_in_progress_is_not_ready(self):
        self.manifest(1026)
        self.assertEqual(self.launcher.game_status(), 'downloading')

    def test_full_install_requires_files(self):
        self.manifest(4, exe=False)
        self.assertEqual(self.launcher.game_status(), 'downloading')
        self.manifest(4)
        self.assertEqual(self.launcher.game_status(), 'installed')

    def test_manifest_path_traversal_rejected(self):
        self.manifest(4, directory='../../outside', exe=False)
        self.assertEqual(self.launcher.game_status(), 'unknown')

    def test_manifest_for_another_app_rejected(self):
        self.manifest(4)
        manifest = self.launcher.steam.parent / 'steamapps/appmanifest_1973530.acf'
        manifest.write_text(manifest.read_text().replace('"1973530"', '"123"'))
        self.assertEqual(self.launcher.game_status(), 'unknown')

    def test_another_executable_is_not_a_complete_install(self):
        self.manifest(4)
        executable = self.launcher.steam.parent / 'steamapps/common/Limbus Company/LimbusCompany.exe'
        executable.rename(executable.with_name('uninstall.exe'))
        self.assertEqual(self.launcher.game_status(), 'downloading')

    def test_symlinked_game_directory_rejected(self):
        self.manifest(4, exe=False)
        common = self.launcher.steam.parent / 'steamapps/common'
        common.mkdir()
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        (outside / 'LimbusCompany.exe').touch()
        (common / 'Limbus Company').symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.launcher.game_status(), 'unknown')

    def test_symlinked_executable_rejected(self):
        self.manifest(4)
        executable = self.launcher.steam.parent / 'steamapps/common/Limbus Company/LimbusCompany.exe'
        executable.unlink()
        executable.symlink_to(Path(self.tmp.name) / 'outside.exe')
        self.assertEqual(self.launcher.game_status(), 'unknown')

    def test_symlinked_steamapps_cannot_escape_prefix(self):
        self.launcher.steam.parent.mkdir(parents=True)
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        (self.launcher.steam.parent / 'steamapps').symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.launcher.game_status(), 'unknown')

    def test_stop_targets_only_our_wineserver_and_prefix(self):
        with patch.object(backend.subprocess, 'run') as run:
            self.launcher.action('stop')
            args, kwargs = run.call_args
        self.assertEqual(args[0], [str(self.launcher.wine_root / 'bin' / 'wineserver'), '-k'])
        self.assertEqual(kwargs['env']['WINEPREFIX'], str(self.launcher.prefix))


if __name__ == '__main__':
    unittest.main()
