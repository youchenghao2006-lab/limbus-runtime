# Limbus Runtime

[简体中文](README.md) · **0.2.0 / Experimental** · Original project source: [MIT](LICENSE)

An unofficial SwiftUI launcher for Limbus Company on Apple Silicon Macs, with a Python controller for a dedicated Wine environment. Steam handles authentication, installation and game updates.

This is an open-source **launcher**, not game source or an entirely open-source runtime distribution. Source releases exclude Wine, D3DMetal, Steam, game content, accounts and local logs. External components retain their own licenses; see [third-party notices](THIRD_PARTY_NOTICES.md). There is no affiliation with Project Moon, Valve, Apple or Sikarugir.

## Status and requirements

Experimental: the original prototype reached startup and rendered scenes on one M2 Mac. This does not establish compatibility of this release on other machines. Combat, long sessions, future updates and a full fresh-machine setup remain unverified. Offline tests and successful compilation are separate from gameplay verification.

Requirements: Apple Silicon, macOS 14.6+, Apple Command Line Tools or Xcode, Python 3.9+, Rosetta 2, network access and space for the runtime/game. The GUI currently uses `/usr/bin/python3`; a Homebrew-only Python installation does not satisfy that requirement. Follow Apple's installation prompts and review applicable licenses for Rosetta.

## Build without downloading a runtime

```sh
python3 -m unittest discover -s tests -v
python3 scripts/source_release.py --check
python3 scripts/prepare_runtime.py --check
python3 scripts/build.py
```

`--check` does not download or run Wine. Missing caches on a new machine are expected. The relocatable app is `dist/Limbus Runtime.app`. It is ad-hoc signed, not Developer ID signed or notarized. Source-only publication is the default; binary distribution needs separate signing and third-party license work.

## Prepare locally

Review [third-party notices](THIRD_PARTY_NOTICES.md) and the upstream licenses. If you accept the applicable terms:

```sh
python3 scripts/prepare_runtime.py --download --accept-third-party-licenses --steam-installer
```

The tool obtains pinned engine/template archives, verifies sizes and SHA-256, assembles a dedicated wrapper and initializes its Wine prefix. The optional Steam installer comes from Valve's mutable official HTTPS URL and has no pinned hash; setup does not execute it automatically. See `--help` for offline caches and initialization options. Existing wrappers are not overwritten.

Open the app, install Steam, sign in using Steam's window, install Limbus Company, then launch. If launching opens Steam first, wait for sign-in and client updates before trying again.

Data defaults to `~/Library/Application Support/Limbus Runtime/`, containing `.cache/`, `runtime/` and `logs/`. `runtime/LimbusRuntime.app/Contents/SharedSupport/prefix/` contains Steam, games and user data. The source tree is independent from this directory. Use `LIMBUS_RUNTIME_HOME` or CLI `--root` to override it. Finder-launched apps do not normally inherit terminal exports; launch `dist/Limbus Runtime.app/Contents/MacOS/LimbusLauncher` from that terminal for a custom root.

Steam uses DXMT and the game uses separately licensed D3DMetal. The MIT license does not grant rights to external components. A DXMT-only game renderer is not claimed as an equivalent fallback.

## Privacy and contributing

The launcher has no telemetry, credential prompt or automatic log upload. Steam/game networking and privacy are controlled by their vendors. Review diagnostic logs before sharing. No original account, installation or local verification data is included. The old machine-specific game-reuse script is deliberately absent.

Run `python3 scripts/backend.py status` to inspect local state. Other actions: `install-steam`, `open-steam`, `install-game`, `launch-game`, `repair`, `stop`. Save progress before repair/stop. Do not delete incomplete runtime directories without checking for existing saves.

Generate a deterministic source archive and checksum with `python3 scripts/source_release.py`. Only files listed in `release-files.json` are included. Never upload an initialized runtime or the original personal project directory. Automated publication checks detect only some classes of secrets and private content; review changes manually as well.

See [CONTRIBUTING](CONTRIBUTING.md), [SECURITY](SECURITY.md), and [CHANGELOG](CHANGELOG.md). CI runs offline tests, source checks and macOS compilation; it does not publish artifacts, sign in or download a game.
