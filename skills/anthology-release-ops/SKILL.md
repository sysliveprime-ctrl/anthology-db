---
name: anthology-release-ops
description: Automate Anthology release operations for launcher, MO2 modpack, Anthology source, and Anthology Work Git. Use when the user says the launcher version changed, the modpack changed, Anthology source changed, Anthology Work Git changed, DB changed, asks to push an Anthology update, publish a fake/test launcher update, upload latest AnomalyLauncher.exe, bump version.json/db_version.json, or release Anthology artifacts to GitHub.
---

# Anthology Release Ops

Use this skill when the user wants to publish an Anthology update with a short command.
The goal is to avoid rediscovering paths, release rules, and GitHub asset behavior every time.

Default roots and sources:

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

- Launcher update, fake launcher update, latest exe, or "push launcher": use `launcher`.
- MO2 modpack update, mods update, `version.json`, or "push modpack": use `modpack`.
- Anthology source update, source snapshot, gamedata configs/scripts update: use `source`.
- Anthology Work Git update, `db_version.json`, DB mirror, or DB release assets: use `workgit` (`db` is kept as an alias).

## Client Delivery Model

Players do not need Git and the launcher must not depend on Git on their side.
Git is only a publishing transport for the maintainer.

Launcher behavior:

- Launcher self-update reads `launcher_version.json` from
  `sysliveprime-ctrl/AnthologyLauncher` and downloads `AnomalyLauncher.exe` from
  the latest GitHub Release.
- Modpack update reads `version.json` from `sysliveprime-ctrl/anthology-mo2-modpack`
  and downloads the branch archive `main.zip`.
- DB update reads `db_version.json` from `sysliveprime-ctrl/anthology-db` and
  downloads DB archives from GitHub Release assets listed by `base_url` and
  `asset_name`.
- `anthology-source` is only a maintainer source snapshot. The launcher does not
  read it and players do not download it through the launcher.

## Launcher Workflow

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py launcher --version YYYY.MM.DD.N --notes "..."
```

This updates `LAUNCHER_VERSION`, updates `launcher_version.json`, runs `py_compile`,
builds with PyInstaller, commits and pushes `main`, and replaces
`AnomalyLauncher.exe` in the latest GitHub Release.

Rules:

- Do not copy the built exe to the local game folder unless the user explicitly asks.
- For a local check without publishing, use `--dry-run`.
- For compile/build only without GitHub upload, use `--skip-upload`.

## Modpack Workflow

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py modpack --version YYYY.MM.DD.N --notes "..."
```

This updates `version.json`, commits relevant tracked changes, and pushes `main`.
The modpack is downloaded from the GitHub `main.zip` URL, so no release asset is needed.

Rules:

- Do not deploy MO2 modpack fixes to loose game `gamedata`.
- Inspect `git status --short --branch` before publishing if there are unrelated changes.

## Anthology Source Workflow

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py source --version YYYY.MM.DD.N --notes "..."
```

This commits and pushes the tracked source snapshot in
`E:\dev\anomaly-codex-main\ai_workspace\Source_Anthology` to
`sysliveprime-ctrl/anthology-source`.

Rules:

- This source repo is only for updating the source snapshot.
- It does not participate in launcher build, launcher update checks, or DB asset upload.
- Inspect `git status --short --branch` before publishing because source edits can be unrelated.

## Anthology Work Git Workflow

```powershell
py -3 E:\dev\Anthology-Work-Git\skills\anthology-release-ops\scripts\anthology_release_ops.py workgit --version YYYY.MM.DD.N --notes "..."
```

This scans the live game DB folders listed above, writes logical paths
`db/configs/...` and `db/mods/...` with sizes and SHA-256 hashes to
`E:\dev\Anthology-Work-Git\db_version.json`, commits and pushes `main`, then
creates or updates a GitHub Release tagged with the version and uploads all DB
assets from the game DB folders.

Rules:

- Work Git assets can be large. Use `--manifest-only` when only the manifest should change.
- Use `--dry-run` before a risky Work Git publish.
- If any asset upload fails, do not claim the Work Git release is complete.
- Do not store copied DB archives under this repo. DB archives are uploaded directly from the game DB folders.

## Safety

- Never print GitHub credentials.
- Check helper output and Git status before final response.
- Do not overwrite unrelated user changes.
- If the helper reports dirty files after a publish, inspect them before answering.
- If upload fails after a commit, say exactly which phase failed.

## Final Response Shape

Keep the final answer short:

```text
Gotovo: <launcher/modpack/source/workgit> <version>
Commit: <hash>
Release/asset: <tag or size>
```
