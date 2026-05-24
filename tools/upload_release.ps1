param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [string]$ReleaseDir = "",
    [string]$Repo = "sysliveprime-ctrl/anthology-db"
)

$ErrorActionPreference = "Stop"

$GhCommand = Get-Command gh -ErrorAction SilentlyContinue
if ($GhCommand) {
    $GhExe = $GhCommand.Source
} else {
    $GhExe = "C:\Program Files\GitHub CLI\gh.exe"
    if (-not (Test-Path -LiteralPath $GhExe)) {
        throw "GitHub CLI 'gh' is not installed or not in PATH."
    }
}

if (-not $ReleaseDir) {
    $ReleaseDir = Join-Path (Split-Path -Parent $PSScriptRoot) "release\$Version"
}

if (-not (Test-Path -LiteralPath $ReleaseDir)) {
    throw "Release asset folder not found: $ReleaseDir"
}

$assets = Get-ChildItem -LiteralPath $ReleaseDir -File
if (-not $assets) {
    throw "No release assets found in: $ReleaseDir"
}

$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $GhExe release view $Version --repo $Repo *> $null
$ViewExitCode = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorActionPreference
if ($ViewExitCode -ne 0) {
    & $GhExe release create $Version --repo $Repo --title $Version --notes "Anthology DB manifest release $Version"
}

$index = 0
foreach ($asset in $assets) {
    $index += 1
    Write-Host "Uploading $index/$($assets.Count): $($asset.Name)"
    & $GhExe release upload $Version --repo $Repo --clobber $asset.FullName
}
