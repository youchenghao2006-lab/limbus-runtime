# Contributing / 参与开发

欢迎提交可复现的问题、文档改进和小范围补丁。提交代码表示你有权按本项目的 MIT 许可证贡献该代码；外部代码必须保留出处和相容的许可信息。

## Local checks

```sh
python3 -m unittest discover -s tests -v
python3 scripts/source_release.py --check
```

On macOS with Apple developer tools:

```sh
python3 scripts/build.py
```

The Python code uses the standard library. Tests use temporary roots and mocks; tests must not touch real Steam accounts, start Wine, terminate a running game, or require downloads. When changing initialization, cover integrity failures and extraction boundaries. When changing the backend, keep the dedicated prefix and renderer inheritance behavior covered.

## Changes and bug reports

- Describe the problem, final behavior and relevant checks. Distinguish unit tests, compiler checks and real gameplay observations.
- Include macOS version, architecture, launcher version, and a minimal reproduction. Redact identifying paths, Steam IDs and credentials before sharing logs.
- Do not attach game resources, runtime bundles, Steam configuration, saved credentials or personal saves.
- New public files must be added to `release-files.json`; do not weaken the source-only release boundary.
- Update both READMEs when user-facing setup changes. Keep unsupported combinations and incomplete features visible.

Before a versioned release, run the checks on the source archive after extraction, inspect its contents, and review source-license and external-component boundaries. GitHub Actions does not perform public release uploads. Set up a real repository and maintainers before advertising support channels; this source package deliberately contains no invented owner/contact address.

Original source: MIT. External dependencies: see [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md).
