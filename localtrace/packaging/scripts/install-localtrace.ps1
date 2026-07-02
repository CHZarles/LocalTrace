param(
  [string]$ReleaseRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "LocalTrace\App")
)

$ErrorActionPreference = "Stop"

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runName = "LocalTrace"
$coreExe = Join-Path $InstallDir "localtrace.exe"

if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
  throw "LOCALAPPDATA is not set."
}
if (-not (Test-Path (Join-Path $ReleaseRoot "localtrace.exe"))) {
  throw "Release root must contain localtrace.exe: $ReleaseRoot"
}
if (-not (Test-Path (Join-Path $ReleaseRoot "localtrace-winprobe.exe"))) {
  throw "Release root must contain localtrace-winprobe.exe: $ReleaseRoot"
}

New-Item -ItemType Directory -Force $InstallDir | Out-Null

$items = @(
  "localtrace.exe",
  "localtrace-winprobe.exe",
  "manifest.json",
  "README.md",
  "web",
  "extension",
  "scripts"
)

foreach ($item in $items) {
  $source = Join-Path $ReleaseRoot $item
  $target = Join-Path $InstallDir $item
  if (-not (Test-Path $source)) { continue }
  if (Test-Path $target) { Remove-Item -Recurse -Force $target }
  Copy-Item -Recurse -Force $source $target
}

New-Item -Path $runKey -Force | Out-Null
Set-ItemProperty -Path $runKey -Name $runName -Value "`"$coreExe`""

Write-Host "LocalTrace installed to: $InstallDir"
Write-Host "Autostart registered at: $runKey\$runName"
Write-Host "Start manually with: $coreExe"
