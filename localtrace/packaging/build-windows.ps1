param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$DistDir = "",
  [string]$Python = "python",
  [switch]$SkipReleaseZip
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($DistDir)) {
  $DistDir = Join-Path $RepoRoot "dist\pyinstaller"
}

Set-Location $RepoRoot

Write-Host "[localtrace-package] repo: $RepoRoot"
Write-Host "[localtrace-package] exe dir: $DistDir"

$null = (& $Python -m PyInstaller --version)
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller is required for Windows executable packaging. Install it in your packaging environment, then retry."
}

$buildDir = Join-Path $RepoRoot "dist\pyinstaller-build"
$specDir = Join-Path $RepoRoot "dist\pyinstaller-spec"
$webDir = Join-Path $RepoRoot "web"

New-Item -ItemType Directory -Force $DistDir | Out-Null
New-Item -ItemType Directory -Force $buildDir | Out-Null
New-Item -ItemType Directory -Force $specDir | Out-Null

# PyInstaller command: --name localtrace
$coreArgs = @(
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name", "localtrace",
  "--paths", (Join-Path $RepoRoot "apps\localtrace"),
  "--add-data", "$webDir;web",
  "--distpath", $DistDir,
  "--workpath", (Join-Path $buildDir "localtrace"),
  "--specpath", $specDir,
  (Join-Path $RepoRoot "packaging\launchers\localtrace_launcher.py")
)

# PyInstaller command: --name localtrace-winprobe
$winprobeArgs = @(
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name", "localtrace-winprobe",
  "--paths", (Join-Path $RepoRoot "apps\winprobe"),
  "--distpath", $DistDir,
  "--workpath", (Join-Path $buildDir "localtrace-winprobe"),
  "--specpath", $specDir,
  (Join-Path $RepoRoot "packaging\launchers\localtrace_winprobe_launcher.py")
)

Write-Host "[localtrace-package] build localtrace.exe"
& $Python -m PyInstaller @coreArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed for localtrace.exe" }

Write-Host "[localtrace-package] build localtrace-winprobe.exe"
& $Python -m PyInstaller @winprobeArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed for localtrace-winprobe.exe" }

$coreExe = Join-Path $DistDir "localtrace.exe"
$winprobeExe = Join-Path $DistDir "localtrace-winprobe.exe"
if (-not (Test-Path $coreExe)) { throw "Missing output: $coreExe" }
if (-not (Test-Path $winprobeExe)) { throw "Missing output: $winprobeExe" }

if (-not $SkipReleaseZip) {
  Write-Host "[localtrace-package] assemble release zip"
  & $Python -m localtrace_packaging.package_release `
    --dist-dir (Join-Path $RepoRoot "dist\windows") `
    --exe-dir $DistDir
  if ($LASTEXITCODE -ne 0) { throw "Release zip assembly failed" }
}

Write-Host "[localtrace-package] done"
Write-Host "  Core:     $coreExe"
Write-Host "  Winprobe: $winprobeExe"
