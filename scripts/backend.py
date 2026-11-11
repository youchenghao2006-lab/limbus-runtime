#!/usr/bin/env python3
"""Small fixed-purpose Wine controller. Never accepts credentials or shell commands."""
import argparse
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

APP_ID = '1973530'


def default_root():
    """Keep mutable state outside the source tree and movable app bundle."""
    configured = os.environ.get('LIMBUS_RUNTIME_HOME')
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / 'Library' / 'Application Support' / 'Limbus Runtime'


class Launcher:
    def __init__(self, root=None):
        self.root = Path(root).expanduser().resolve() if root is not None else default_root()
        self.wrapper = self.root / 'runtime' / 'LimbusRuntime.app'
        self.contents = self.wrapper / 'Contents'
        self.prefix = self.contents / 'SharedSupport' / 'prefix'
        self.wine_root = self.contents / 'SharedSupport' / 'wine'
        self.wine = self.wine_root / 'bin' / 'wine'
        self.steam = self.prefix / 'drive_c' / 'Program Files (x86)' / 'Steam' / 'Steam.exe'
        self.logs = self.root / 'logs'

    def environment(self, steam_ui=False):
        # No inherited Wine settings: a concurrently running CrossOver stays separate.
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('WINE', 'WINEDLL', 'CX_', 'DYLD_', 'Sikarugir'))}
        frameworks = self.contents / 'Frameworks'
        d3dmetal = frameworks / 'renderer' / 'd3dmetal'
        dxmt = frameworks / 'renderer' / 'dxmt' / 'wine'
        gst = frameworks / 'GStreamer.framework' / 'Libraries'
        env.update({
            'WINEPREFIX': str(self.prefix),
            'PATH': str(self.wine_root / 'bin') + ':/usr/bin:/bin:/usr/sbin:/sbin',
            'DYLD_FALLBACK_LIBRARY_PATH': ':'.join(map(str, (frameworks, d3dmetal / 'external', gst, self.wine_root / 'lib'))) + ':/usr/lib',
            'SikarugirAppWine11': '1',
            'WINEDLLPATH': str(self.wine_root / 'lib' / 'wine'),
            'WINEDLLPATH_PREPEND': str(d3dmetal / 'wine'),
            'WINEDLLPATH_D3DMETAL': str(d3dmetal / 'wine'),
            'WINEDLLPATH_DXMT': str(dxmt),
            'DXMT_ALLOW_CROSS_PROCESS_SWAPCHAIN': '1',
            'CX_D3DMETALPATH': str(d3dmetal),
            'CX_APPLEGPTK_LIBD3DSHARED_PATH': str(d3dmetal / 'external' / 'libd3dshared.dylib'),
            'WINEDEBUG': '-all',
            'WINEESYNC': '1', 'WINEMSYNC': '1',
            'ROSETTA_ADVERTISE_AVX': '1',
            'GST_PLUGIN_PATH': str(gst / 'gstreamer-1.0'),
        })
        # The Sikarugir engine routes Steam's web helpers to DXMT, while games
        # use D3DMetal. Keep BOTH paths in the parent environment so games
        # launched or restarted by Steam retain their renderer configuration.
        return env

    def game_installation(self):
        """Return state and an executable confined to this managed Steam library."""
        manifest = self.steam.parent / 'steamapps' / ('appmanifest_' + APP_ID + '.acf')
        common = manifest.parent / 'common'
        try:
            manifest.resolve().relative_to(self.prefix.resolve())
            common.resolve().relative_to(self.prefix.resolve())
        except ValueError:
            return 'unknown', None
        if manifest.is_symlink() or common.is_symlink():
            return 'unknown', None
        if not manifest.is_file():
            return 'missing', None
        if manifest.stat().st_size > 1024 * 1024:
            return 'unknown', None
        text = manifest.read_text(errors='replace')
        flags = re.search(r'"StateFlags"\s+"(\d+)"', text)
        directory = re.search(r'"installdir"\s+"([^"]+)"', text)
        appid = re.search(r'"appid"\s+"(\d+)"', text)
        if not flags or not directory or not appid or appid.group(1) != APP_ID:
            return 'unknown', None
        # Never allow a manifest to resolve outside this Steam library.
        relative = directory.group(1)
        if (any(c in relative for c in ('/', '\\', ':', '\x00', '\n', '\r'))
                or relative in ('.', '..') or relative != relative.strip()):
            return 'unknown', None
        game = common / relative
        executable = game / 'LimbusCompany.exe'
        if game.is_symlink() or executable.is_symlink():
            return 'unknown', None
        try:
            executable.resolve().relative_to(common.resolve())
        except ValueError:
            return 'unknown', None
        if int(flags.group(1)) == 4 and executable.is_file():
            return 'installed', executable
        return 'downloading', None

    def game_status(self):
        return self.game_installation()[0]

    def status(self):
        return {
            'runtimeReady': self.wine.is_file() and (self.prefix / 'system.reg').is_file(),
            'steamInstalled': self.steam.is_file(),
            'gameState': self.game_status(),
            'engine': 'Wine 11 · Sikarugir',
            'renderer': 'Apple D3DMetal',
            'root': str(self.root),
            'compatibility': 'experimental',
        }

    def is_running(self, executable):
        # Match this project's absolute executable path, not another Steam install.
        commands = subprocess.check_output(['/bin/ps', '-axo', 'command='], text=True)
        path = str(executable)
        return any(c.strip() == path or c.strip().startswith(path + ' ') for c in commands.splitlines())

    def launch(self, action, args, steam_ui=False):
        if not self.wine.is_file():
            raise RuntimeError('运行环境尚未准备好，请查看使用说明。')
        self.logs.mkdir(parents=True, exist_ok=True)
        # Own diagnostics only. Never collect Steam config, SSFN, cookies or login files.
        env = self.environment(steam_ui=steam_ui)
        if action == 'launch-game':
            # Identify the installed game to the running, signed-in Steam client.
            env.update(SteamAppId=APP_ID, SteamGameId=APP_ID)
        with (self.logs / 'runtime.log').open('ab', buffering=0) as log:
            log.write(('\n[' + datetime.now().isoformat(timespec='seconds') + '] ' + action + '\n').encode())
            process = subprocess.Popen([str(self.wine), *args], env=env,
                                       cwd=self.root, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True)
        time.sleep(1.0)
        code = process.poll()
        if code is not None and code != 0:
            raise RuntimeError('启动失败（退出码 %s），请查看运行日志。' % code)
        return {'ok': True, 'message': '请求已发送，请查看 Steam 窗口。', 'pid': process.pid}

    def action(self, action):
        if action == 'status':
            return self.status()
        if action == 'install-steam':
            if self.steam.is_file():
                return {'ok': True, 'message': 'Steam 已安装，可以打开登录。'}
            installer = self.root / '.cache' / 'SteamSetup.exe'
            if not installer.is_file():
                raise RuntimeError('找不到 Steam 官方安装包，请先准备环境。')
            result = self.launch(action, [str(installer), '/S'], steam_ui=True)
            result['message'] = '正在安装 Steam，完成后状态会自动更新。'
            return result
        if action in ('open-steam', 'install-game', 'launch-game'):
            if not self.steam.is_file():
                raise RuntimeError('请先安装 Steam。')
            args = [str(self.steam)]
            if action == 'install-game':
                args.append('steam://install/' + APP_ID)
            elif action == 'launch-game':
                game_state, game = self.game_installation()
                if game_state != 'installed':
                    raise RuntimeError('游戏尚未安装完成，请先在 Steam 中完成下载。')
                if not self.is_running(self.steam):
                    result = self.launch('open-steam', args, steam_ui=True)
                    result['message'] = '已打开 Steam。等待登录和更新完成后，再点「启动游戏」。'
                    return result
                if not game.is_file():
                    raise RuntimeError('找不到游戏程序，请在 Steam 中验证游戏文件。')
                if self.is_running(game):
                    return {'ok': True, 'message': '游戏已经在运行，请切换到游戏窗口。'}
                # Keep Unity in a window using the legacy presentation model.
                args = [str(game), '-force-d3d11',
                         '-force-d3d11-bitblt-model', '-screen-fullscreen', '0',
                         '-screen-width', '1280', '-screen-height', '800']
                result = self.launch(action, args)
                result['message'] = '已请求启动游戏，请查看游戏窗口。'
                return result
            return self.launch(action, args, steam_ui=True)
        if action == 'repair':
            # Refresh registry/system files only; never recreate/delete the prefix.
            result = self.launch(action, ['wineboot', '-u'])
            result['message'] = '已请求刷新运行环境。游戏文件和存档会保留。'
            return result
        if action == 'stop':
            subprocess.run([str(self.wine_root / 'bin' / 'wineserver'), '-k'],
                           env=self.environment(), timeout=15, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {'ok': True, 'message': '已停止本启动器的运行环境。'}
        raise ValueError('不支持的操作')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=default_root(),
                        help='Mutable runtime directory (default: LIMBUS_RUNTIME_HOME or user Application Support).')
    parser.add_argument('action', choices=['status', 'install-steam', 'open-steam', 'install-game', 'launch-game', 'repair', 'stop'])
    args = parser.parse_args()
    try:
        launcher = Launcher(args.root)
        if args.action == 'status':
            result = launcher.status()
        else:
            # Serialise mutations from double clicks / multiple launcher windows.
            launcher.logs.mkdir(parents=True, exist_ok=True)
            with (launcher.logs / 'operation.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = launcher.action(args.action)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'ok': False, 'message': str(error)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == '__main__':
    main()
