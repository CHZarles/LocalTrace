param(
  [string]$ReleaseRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$coreRunName = "LocalTrace"
$winprobeRunName = "LocalTraceWinprobe"

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

function Open-BrowserExtensionPage {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Url,
    [Parameter(Mandatory = $true)][string[]]$ExecutableNames
  )

  foreach ($browser in $ExecutableNames) {
    try {
      Start-Process -FilePath $browser -ArgumentList $Url -ErrorAction Stop
      Write-Host "Opened $Name extension page: $Url"
      return $true
    } catch {
      Write-Verbose "Could not open $Name using $browser."
    }
  }

  return $false
}

function Prepare-BrowserExtension {
  param([Parameter(Mandatory = $true)][string]$InstallDir)

  $extensionZip = Get-NormalizedPath -Path (Join-Path $InstallDir "extension\localtrace-extension.zip")
  $extensionLoadDir = Get-NormalizedPath -Path (Join-Path $InstallDir "extension\localtrace-extension")

  if (-not (Test-Path $extensionZip)) {
    Write-Warning "Browser extension zip not found: $extensionZip"
    return
  }

  if (Test-Path $extensionLoadDir) {
    Remove-Item -Recurse -Force $extensionLoadDir
  }
  New-Item -ItemType Directory -Force $extensionLoadDir | Out-Null
  Expand-Archive -Path $extensionZip -DestinationPath $extensionLoadDir -Force

  try {
    Set-Clipboard -Value $extensionLoadDir
    Write-Host "Copied browser extension directory to clipboard."
  } catch {
    Write-Warning "Could not copy browser extension directory to clipboard."
  }

  $opened = @()
  if (Open-BrowserExtensionPage -Name "Edge" -Url "edge://extensions/" -ExecutableNames @("msedge.exe", "msedge")) {
    $opened += "Edge"
  }
  if (Open-BrowserExtensionPage -Name "Chrome" -Url "chrome://extensions/" -ExecutableNames @("chrome.exe", "chrome")) {
    $opened += "Chrome"
  }

  Write-Host "Load unpacked extension directory: $extensionLoadDir"
  Write-Host "Browser security requires the final confirmation step."
  Write-Host "In Chrome or Edge, enable Developer mode, click Load unpacked, and select the copied directory."
  if ($opened.Count -eq 0) {
    Write-Host "Chrome or Edge was not found automatically. Open chrome://extensions/ or edge://extensions/ manually."
  }
}

function Start-LocalTraceProcess {
  param(
    [Parameter(Mandatory = $true)][string]$ProcessName,
    [Parameter(Mandatory = $true)][string]$ExecutablePath
  )

  if (Get-Process -Name $ProcessName -ErrorAction SilentlyContinue) {
    Write-Host "$ProcessName is already running."
    return
  }

  Start-Process -FilePath $ExecutablePath -WorkingDirectory (Split-Path -Parent $ExecutablePath)
  Write-Host "Started $ProcessName: $ExecutablePath"
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

$ReleaseRoot = $normalizedReleaseRoot
$InstallDir = $normalizedInstallDir

$coreExe = Join-Path $InstallDir "localtrace.exe"
$winprobeExe = Join-Path $InstallDir "localtrace-winprobe.exe"

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
Set-ItemProperty -Path $runKey -Name $coreRunName -Value "`"$coreExe`""
Set-ItemProperty -Path $runKey -Name $winprobeRunName -Value "`"$winprobeExe`""

Prepare-BrowserExtension -InstallDir $InstallDir
Start-LocalTraceProcess -ProcessName "localtrace" -ExecutablePath $coreExe
Start-LocalTraceProcess -ProcessName "localtrace-winprobe" -ExecutablePath $winprobeExe

Write-Host "LocalTrace installed to: $InstallDir"
Write-Host "Autostart registered at: $runKey\$coreRunName"
Write-Host "Autostart registered at: $runKey\$winprobeRunName"
Write-Host "Windows app capture should start immediately after install."
