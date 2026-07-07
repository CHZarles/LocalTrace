param(
  [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "LocalTrace\App"),
  [switch]$KeepFiles
)

$ErrorActionPreference = "Stop"

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runNames = @("LocalTrace", "LocalTraceWinprobe")

if (Test-Path $runKey) {
  foreach ($runName in $runNames) {
    Remove-ItemProperty -Path $runKey -Name $runName -ErrorAction SilentlyContinue
  }
}

if (-not $KeepFiles -and (Test-Path $InstallDir)) {
  Remove-Item -Recurse -Force $InstallDir
}

Write-Host "LocalTrace autostart removed from: $runKey\LocalTrace"
Write-Host "LocalTrace app probe autostart removed from: $runKey\LocalTraceWinprobe"
if ($KeepFiles) {
  Write-Host "Kept installed files at: $InstallDir"
} else {
  Write-Host "Removed installed files from: $InstallDir"
}
