# Anthology DB Update Channel

This repository stores the small update manifest for Anthology DB archives.
Large `.xdb` and `.db` files should be uploaded as GitHub Release assets, not
committed to Git.

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
      "asset_name": "configs_anthology.xdb0",
      "size": 12496896,
      "sha256": "..."
    }
  ]
}
```

## Build Manifest

```powershell
py -3 .\tools\build_db_manifest.py `
  --db-root "D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db" `
  --version 2026.05.24.1 `
  --base-url "https://github.com/sysliveprime-ctrl/anthology-db/releases/download/2026.05.24.1/" `
  --out .\db_version.json
```

Upload every listed archive as a GitHub Release asset using its `asset_name`.

To stage release assets after building the manifest:

```powershell
py -3 .\tools\stage_release_assets.py `
  --db-root "D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db" `
  --manifest .\db_version.json `
  --out .\release\2026.05.24.1
```
