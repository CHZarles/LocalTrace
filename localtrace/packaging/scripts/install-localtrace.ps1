param(
  [string]$ReleaseRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runName = "LocalTrace"

if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
  throw "LOCALAPPDATA is not set."
}
if ([string]::IsNullOrWhiteSpace($InstallDir)) {
  $InstallDir = Join-Path $env:LOCALAPPDATA "LocalTrace\App"
}

function Get-NormalizedPath {
  param([Parameter(Mandatory = $true)][string]$Path)
  return [System.IO.Path]::GetFullPath($Path).TrimEnd("\", "/")
}

$normalizedReleaseRoot = Get-NormalizedPath -Path $ReleaseRoot
$normalizedInstallDir = Get-NormalizedPath -Path $InstallDir
if ($normalizedReleaseRoot -ieq $normalizedInstallDir) {
  throw "ReleaseRoot and InstallDir must be different. Run this script from an extracted release directory, not from the installed app directory."
}
$releaseRootPrefix = "$normalizedReleaseRoot$([System.IO.Path]::DirectorySeparatorChar)"
if ($normalizedInstallDir.StartsWith($releaseRootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "InstallDir must not be inside ReleaseRoot. Choose an install directory outside the extracted release directory."
}

$coreExe = Join-Path $InstallDir "localtrace.exe"

$requiredItems = @(
  "localtrace.exe",
  "localtrace-winprobe.exe",
  "manifest.json",
  "README.md",
  "web",
  "extension",
  "scripts"
)

foreach ($item in $requiredItems) {
  $source = Join-Path $ReleaseRoot $item
  if (-not (Test-Path $source)) {
    throw "Release root missing required artifact: $item"
  }
}

New-Item -ItemType Directory -Force $InstallDir | Out-Null

foreach ($item in $requiredItems) {
  $source = Join-Path $ReleaseRoot $item
  $target = Join-Path $InstallDir $item
  if (Test-Path $target) { Remove-Item -Recurse -Force $target }
  Copy-Item -Recurse -Force $source $target
}

New-Item -Path $runKey -Force | Out-Null
Set-ItemProperty -Path $runKey -Name $runName -Value "`"$coreExe`""

Write-Host "LocalTrace installed to: $InstallDir"
Write-Host "Autostart registered at: $runKey\$runName"
Write-Host "Start manually with: $coreExe"
