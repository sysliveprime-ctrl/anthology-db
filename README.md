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
2. Put the finished files under `db/configs/` and `db/mods/`.
3. Rebuild `db_version.json` and stage release assets.
4. Commit and push the manifest.
5. Upload release assets.

Example:

```powershell
Copy-Item "D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\configs\*.xdb*" .\db\configs\
Copy-Item "D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\configs\*.db*" .\db\configs\
Copy-Item "D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\mods\*.xdb*" .\db\mods\
Copy-Item "D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\mods\*.db*" .\db\mods\

py -3 .\tools\build_db_manifest.py --version 2026.05.24.1
py -3 .\tools\stage_release_assets.py --manifest .\db_version.json --out .\release\2026.05.24.1

git add .gitignore README.md db_version.json tools
git commit -m "Update DB manifest"
git push

powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\upload_release.ps1 -Version 2026.05.24.1
```
