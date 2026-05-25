# Anthology DB Update Channel

This repository stores the Anthology DB update manifest. Large `.xdb` and `.db`
files are uploaded as GitHub Release assets.

The launcher reads `db_version.json`, removes local extra DB archives in mirror
mode, and downloads only files whose size or SHA-256 hash does not match.

## Manifest Shape

```json
{
  "version": "2026.05.24.1",
  "mode": "mirror",
  "base_url": "https://github.com/sysliveprime-ctrl/anthology-db/releases/download/2026.05.24.1/",
  "files": [
    {
      "path": "db/configs/configs_anthology.xdb0",
      "asset_name": "db_configs_configs_anthology.xdb0",
      "size": 12496896,
      "sha256": "..."
    }
  ]
}
```

## Workflow

1. Pack DB archives yourself with the correct X-Ray packer.
2. Put the finished files in the live game DB folders.
3. Rebuild `db_version.json` from the live game DB folders.
4. Commit and push the manifest from this repository.
5. Upload release assets from the live game DB folders.

DB asset sources:

```text
D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\configs
D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\mods
```

Example:

```powershell
py -3 .\skills\anthology-release-ops\scripts\anthology_release_ops.py workgit --version 2026.05.24.1 --notes "Updated DB archives"
```

The MO2 modpack source is:

```text
D:\Games\ANTHOLOGY\SYS_A.N.T.H.O.L.O.G.Y_mo2_CBT\mods
```

The launcher repo lives inside this workspace as a separate Git checkout:

```text
E:\dev\Anthology-Work-Git\projects\AnthologyLauncher
```

The Anthology source snapshot is a separate repo used only for source updates:

```text
E:\dev\anomaly-codex-main\ai_workspace\Source_Anthology
```

It pushes to `sysliveprime-ctrl/anthology-source` and does not participate in
launcher builds, launcher update checks, or DB release uploads.

## Client Updates

Players do not need Git. GitHub repositories are used only by the maintainer to
publish update metadata and downloadable archives.

The launcher update flow is:

```text
launcher_version.json -> latest release AnomalyLauncher.exe
version.json          -> anthology-mo2-modpack main.zip
db_version.json       -> anthology-db release assets
```

`anthology-source` is not part of the launcher update flow.

## Codex Release Skill

The Anthology release helper skill source of truth is stored in this repository
at:

```text
skills/anthology-release-ops
```

Do not develop or maintain this skill under `C:\Users\parti\.codex\skills`.
That folder may contain only a small discovery pointer for Codex. All scripts,
release rules, docs, and fixes belong in `E:\dev\Anthology-Work-Git`.

After changing this repo copy, refresh only the local discovery pointer if
needed:

```powershell
Copy-Item .\skills\anthology-release-ops\SKILL.md "$env:USERPROFILE\.codex\skills\anthology-release-ops\SKILL.md" -Force
```
