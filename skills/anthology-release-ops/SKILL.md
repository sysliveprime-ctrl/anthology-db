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
DB manifest repo:   E:\dev\Anthology-Work-Git
DB asset sources:   D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\configs
                    D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\mods
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
- Modpack update reads `version.json`, then downloads
  `sysliveprime-ctrl/anthology-mo2-modpack` `main.zip`.
- DB update reads `db_version.json` through the GitHub contents API first
  because raw GitHub CDN can lag; raw URL is only fallback.
- DB files download from GitHub Release assets by `base_url + asset_name`.
- `anthology-source` is never used by the launcher.

## Current Update Semantics

- DB is mirror mode: files absent from `db_version.json` are deleted locally from
  `db/configs` and `db/mods`.
- Modpack stores installed file paths in `.launcher_update_state.json`.
- Modpack updater now removes previously tracked files when they disappear from
  the new `main.zip`.
- Modpack `version.json` may include `removed_files`. These are explicit
  repo-relative cleanup paths generated from Git history during release; players
  do not need Git for this cleanup.
- R.A.K weapon pack folders are manual/local and must be preserved even if they
  are absent from `main.zip`.
- The modpack repo ignores `*R.A.K Weapon Pack Adaptation Global A.N.T.H.O.L.O.G.Y*/**`;
  do not re-add those folders to Git unless explicitly requested.

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

## Modpack

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py modpack --version YYYY.MM.DD.N --notes "..."
```

Does:

- updates `version.json`
- auto-fills `removed_files` with deleted tracked `gamedata/configs` and
  `gamedata/scripts` files that are absent from current Git
- commits tracked modpack changes
- pushes `sysliveprime-ctrl/anthology-mo2-modpack` `main`

The launcher installs from `main.zip`; no release asset is needed.

Preview cleanup list without publishing:

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py modpack-removed
```

Before publishing, inspect `git status --short --branch`. R.A.K paths should not
be tracked. Test files named `anthology_release_*` must not be present.

## WorkGit / DB

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py workgit --version YYYY.MM.DD.N --notes "..."
```

Does:

- scans live game DB source folders, not copied repo folders
- writes logical paths `db/configs/...` and `db/mods/...` to `db_version.json`
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
