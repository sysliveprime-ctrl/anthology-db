---
name: anthology-release-ops
description: Automate Anthology release operations from E:\dev\Anthology-Work-Git for launcher, MO2 modpack, DB/WorkGit, and source snapshot. Use for short commands like launcher updated, fake launcher update, modpack updated, workgit/db updated, source updated, upload latest AnomalyLauncher.exe, or publish Anthology release assets.
---

# Anthology Release Ops

This skill's source of truth is this repository:

```text
E:\dev\Anthology-Work-Git\skills\anthology-release-ops
```

Do not maintain release logic in `C:\Users\parti\.codex\skills`. That folder may
only contain a tiny discovery pointer to this repo copy.

## Roots

```text
release workspace: E:\dev\Anthology-Work-Git
launcher repo:      E:\dev\Anthology-Work-Git\projects\AnthologyLauncher
modpack repo:       D:\Games\ANTHOLOGY\SYS_A.N.T.H.O.L.O.G.Y_mo2_CBT\mods
source repo:        E:\dev\anomaly-codex-main\ai_workspace\Source_Anthology
engine repo:        E:\dev\xray-monolith
DB manifest repo:   E:\dev\Anthology-Work-Git
DB asset sources:   D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\configs
                    D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\mods
                    D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\shaders_anthology.xdb0
                    D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\textures\textures_trees.xdb0
                    D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\textures\textures_trees.xdb1
                    D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\textures\textures_trees.xdb3
```

Primary helper:

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py <command> [args]
```

## Intent Mapping

- `лаунчер обновился <version>` / fake launcher / latest exe: run `launcher`.
- `модпак обновился <version>`: run `modpack`.
- `work git обновился <version>` / DB updated: run `workgit`.
- `source обновился <version>` / source snapshot: run `source`.

## Client Delivery Model

Players do not need Git. Git is only our publishing transport.

- Launcher self-update reads `launcher_version.json`, then downloads
  `AnomalyLauncher.exe` from latest GitHub Release.
- Modpack update reads `version.json` through the GitHub contents API first
  because raw GitHub CDN can lag; raw URL is only fallback. It then downloads
  `sysliveprime-ctrl/anthology-mo2-modpack` `main.zip`.
- DB update reads `db_version.json` through the GitHub contents API first
  because raw GitHub CDN can lag; raw URL is only fallback.
- DB files download from GitHub Release assets by `base_url + asset_name`.
- Engine update reads `engine_version.json` through the GitHub contents API first
  from `sysliveprime-ctrl/xray-monolith` branch
  `anthology-2026.5.8-mt-nanfix`; raw URL is only fallback. It then downloads
  the ZIP from the URL in that manifest.
- `anthology-source` is never used by the launcher.

## Current Update Semantics

- DB is mirror mode: files absent from `db_version.json` are deleted locally from
  `db/configs` and `db/mods`; the root DB archive
  `db/shaders_anthology.xdb0` is managed explicitly by the DB channel.
- `db/mods/00_modded_exes_gamedata.db0` belongs to the engine ZIP, not the DB
  channel. The launcher preserves it during DB cleanup.
- Modpack stores installed file paths in `.launcher_update_state.json`.
- Modpack updater now removes previously tracked files when they disappear from
  the new `main.zip`, then prunes empty folders left by those removals.
- Modpack `version.json` may include `removed_files`. These are explicit
  repo-relative cleanup paths generated from Git history during release; players
  do not need Git for this cleanup.
- R.A.K weapon pack folders are manual/local and must be preserved even if they
  are absent from `main.zip`.
- The modpack repo ignores `*R.A.K Weapon Pack Adaptation Global A.N.T.H.O.L.O.G.Y*/**`;
  do not re-add those folders to Git unless explicitly requested.
- Launcher code should only need a release when update logic changes. Content
  updates must be delivered by external manifests: `version.json`,
  `db_version.json`, and `engine_version.json`.

## Launcher

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py launcher --version YYYY.MM.DD.N --notes "..."
```

Does:

- updates `LAUNCHER_VERSION` in `anthology_launcher.py`
- updates `launcher_version.json`
- runs `py_compile`
- builds `dist\AnomalyLauncher.exe` with PyInstaller
- commits and pushes launcher `main`
- replaces `AnomalyLauncher.exe` in latest GitHub Release

Never copy the built exe to the local game folder unless explicitly asked.

Launcher top news can be published through the wizard:

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_publish_wizard.py
```

Choose `Launcher news`; it inserts the entered news item at the top of the
launcher news feed, bumps the launcher version, builds `AnomalyLauncher.exe`,
pushes `main`, and replaces the latest Release asset. CLI equivalent:

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py launcher-news --version YYYY.MM.DD.N --news-title "..." --news-body "..."
```

## Modpack

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py modpack --version YYYY.MM.DD.N --notes "..."
```

Does:

- updates `version.json`
- auto-fills `removed_files` with deleted tracked `gamedata/configs`,
  `gamedata/scripts`, and `gamedata/textures` files that are absent from current Git
- commits tracked modpack changes
- pushes `sysliveprime-ctrl/anthology-mo2-modpack` `main`

The launcher installs from `main.zip`; no release asset is needed.

After publishing, verify modpack `version.json` through the GitHub contents API,
not raw GitHub. Raw can return the previous version for a while and make it look
like the push failed.

Preview cleanup list without publishing:

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py modpack-removed
```

Before publishing, inspect `git status --short --branch`. R.A.K paths should not
be tracked. Test files named `anthology_release_*` must not be present.

## Engine

Engine release channel:

```text
repo:   E:\dev\xray-monolith
branch: anthology-2026.5.8-mt-nanfix
public: sysliveprime-ctrl/xray-monolith
manifest: engine_version.json
release asset: STALKER-Anomaly-modded-exes-MT-TEST_<tag>.zip
```

Current known-good MT base/nanfix lineage:

```text
080c4e8b  2026-05-08 MT base
34b1c5f2  nanfix over MT
```

Rules:

- Players do not need Git; the launcher only reads `engine_version.json` over
  HTTP/API and downloads a GitHub Release ZIP.
- Build/deploy the engine with:

```powershell
powershell -ExecutionPolicy Bypass -File E:\dev\anomaly-codex-main\tools\build_anthology_engine.ps1 -Deploy
```

- The build deploys DX11 and DX11-AVX exe/PDB to:

```text
D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\bin
```

- Package engine ZIP from the live game `bin` plus
  `db\mods\00_modded_exes_gamedata.db0`. Include PDB files. At minimum include
  `bin\AnomalyDX11.pdb` and `bin\AnomalyDX11AVX.pdb`.
- The archive must have top-level `bin/...` and `db/...` paths. The launcher
  ignores anything outside these top-level folders.
- If a release asset is replaced with corrected contents but keeps the same
  download URL/tag, bump `engine_version.json` `version` anyway. Otherwise
  clients with the old `engine_state.json` version will think the engine is
  already installed and will not redownload.
- Verify the uploaded Release asset size/digest. The corrected MT nanfix asset
  was `183427219` bytes with SHA-256
  `a42d12c232485c066ee3f22ccec98073a748974a0dad76db29e6d77e3df8dff2`.
- Verify `engine_version.json` through the GitHub contents API and confirm the
  local launcher comparison would report `manifest.version != engine_state.version`
  when a redownload is expected.

## WorkGit / DB

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py workgit --version YYYY.MM.DD.N --notes "..."
```

Does:

- scans live game DB source folders, not copied repo folders
- writes logical paths `db/configs/...`, `db/mods/...`, and
  `db/shaders_anthology.xdb0` to `db_version.json`
- commits and pushes `sysliveprime-ctrl/anthology-db` `main`
- creates/updates GitHub Release tag equal to the version
- uploads DB assets from the live game DB folders

Rules:

- Do not store DB archives under `E:\dev\Anthology-Work-Git\db`.
- GitHub rejects zero-byte release assets; use at least 1 byte for test assets.
- If upload fails after commit/push, stop and say which asset/phase failed.
- After cleanup, verify GitHub contents API, not only raw GitHub URL.

## Source

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py source --version YYYY.MM.DD.N --notes "..."
```

Commits and pushes `E:\dev\anomaly-codex-main\ai_workspace\Source_Anthology` to
`sysliveprime-ctrl/anthology-source`. This is maintainer-only and not part of
launcher updates.

## Safety Checklist

Default collaboration rule:

- The maintainer can publish routine launcher/MO2/DB/engine updates through
  `anthology_publish_wizard.py`. Do not push or publish release assets by
  default after routine changes; prepare the code/tooling and explain what to
  run. Only run release publishing commands when explicitly asked to push,
  publish, upload, or release.

Before publishing:

```powershell
git status --short --branch
```

After publishing:

- check helper JSON output
- check repo status is clean
- check public metadata:
  - launcher via GitHub contents API
  - DB via GitHub contents API
  - modpack `version.json`
- search for test leftovers:

```powershell
rg -n "anthology_release_(test|batch)" E:\dev\Anthology-Work-Git D:\Games\ANTHOLOGY\SYS_A.N.T.H.O.L.O.G.Y_mo2_CBT\mods "D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db"
```

Never print GitHub credentials or tokens.

## Final Response Shape

Keep final release answers short:

```text
Gotovo: <launcher/modpack/source/workgit> <version>
Commit: <hash>
Release/asset: <tag or size>
```
