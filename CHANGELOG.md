# Changelog

## 0.2.0 — 2026-11-07 — Experimental source release

- Extracted a source-only project from the local launcher prototype.
- Added an MIT license for project source and documented external-component boundaries.
- Removed embedded checkout paths and personal identifiers from the build; the app uses a separate, configurable data directory.
- Added an explicit runtime preparation flow with pinned archive checks and safe staging.
- Kept Steam/DXMT and game/D3DMetal renderer paths together in the inherited environment.
- Added setup, portability and source-publication tests plus CI configuration.
- Added deterministic source packaging with an explicit file allowlist.
- Removed machine-specific game import and local compatibility-marker claims from the public project.

Known gaps: no clean-machine end-to-end gameplay validation, no battle/long-session compatibility guarantee, no notarized binary release, and no fully open-source replacement for every runtime dependency.
