# Anthology Release Map

## Launcher

- Root: `E:\dev\Anthology-Work-Git\projects\AnthologyLauncher`
- Repo: `sysliveprime-ctrl/AnthologyLauncher`
- Runtime version source: `anthology_launcher.py`, `LAUNCHER_VERSION`
- Update manifest: `launcher_version.json`
- Release asset: latest GitHub Release, `AnomalyLauncher.exe`
- Local game exe is not copied by default.

## MO2 Modpack

- Root: `D:\Games\ANTHOLOGY\SYS_A.N.T.H.O.L.O.G.Y_mo2_CBT\mods`
- Repo: `sysliveprime-ctrl/anthology-mo2-modpack`
- Manifest: `version.json`
- Download mode: GitHub branch zip from `main`
- Do not deploy these changes to loose game `gamedata`.
- Deleted tracked files are removed by the launcher from the client's modpack
  using `.launcher_update_state.json`.
- Preserve local/manual R.A.K folders:
  `*R.A.K Weapon Pack Adaptation Global A.N.T.H.O.L.O.G.Y*/**`
- Test files named `anthology_release_*` must not remain in the repo.

## Anthology Source

- Root: `E:\dev\anomaly-codex-main\ai_workspace\Source_Anthology`
- Repo: `sysliveprime-ctrl/anthology-source`
- Scope: tracked source snapshot, mainly `gamedata/configs` and `gamedata/scripts`
- Delivery: plain git push, no launcher build, no update manifest, no release asset.

## Anthology Work Git

- Root: `E:\dev\Anthology-Work-Git`
- Repo: `sysliveprime-ctrl/anthology-db`
- Manifest: `db_version.json`
- Asset sources:
  - `D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\configs`
  - `D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\mods`
- Manifest paths stay logical: `db/configs/...`, `db/mods/...`
- Download mode: GitHub Release assets under tag equal to manifest version.
- Launcher reads the manifest through GitHub contents API first to avoid stale
  raw CDN cache.
- DB update is mirror mode: extra local DB archives are deleted.
- Do not keep copied DB archives in this repo.
- GitHub Release assets cannot be zero bytes.
