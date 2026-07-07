param(
  [string]$BaseUrl = "http://127.0.0.1:8765"
)

$ErrorActionPreference = "Stop"

function Test-ProcessRunning {
  param([Parameter(Mandatory = $true)][string]$Name)
  $process = Get-Process -Name $Name -ErrorAction SilentlyContinue
  return $null -ne $process
}

function Test-SourceSeen {
  param([object]$Source)
  if ($null -eq $Source) {
    return $false
  }
  return -not [string]::IsNullOrWhiteSpace([string]$Source.last_observed_at)
}

$base = $BaseUrl.TrimEnd("/")
$result = [ordered]@{
  ok = $false
  diagnosis = "unknown"
  base_url = $base
  core_process_running = Test-ProcessRunning -Name "localtrace"
  winprobe_process_running = Test-ProcessRunning -Name "localtrace-winprobe"
  core_health_ok = $false
  windows_probe_seen = $false
  browser_extension_seen = $false
  windows_probe_last_observed_at = $null
  browser_extension_last_observed_at = $null
  error = $null
}

try {
  $health = Invoke-RestMethod -Method Get -Uri "$base/health" -TimeoutSec 3
  $result.core_health_ok = $true

  $windowsProbe = $health.sources.windows_probe
  $browserExtension = $health.sources.browser_extension
  $result.windows_probe_seen = Test-SourceSeen -Source $windowsProbe
  $result.browser_extension_seen = Test-SourceSeen -Source $browserExtension
  if ($null -ne $windowsProbe) {
    $result.windows_probe_last_observed_at = $windowsProbe.last_observed_at
  }
  if ($null -ne $browserExtension) {
    $result.browser_extension_last_observed_at = $browserExtension.last_observed_at
  }
} catch {
  $result.error = $_.Exception.Message
}

if (-not $result.core_health_ok) {
  $result.diagnosis = "core_health_unreachable"
} elseif (-not $result.winprobe_process_running) {
  $result.diagnosis = "probe_not_running"
  $result.error = "localtrace-winprobe process is not running."
} elseif (-not $result.windows_probe_seen) {
  $result.diagnosis = "probe_running_no_events"
  $result.error = "localtrace-winprobe process is running but /health has no windows_probe events."
} else {
  $result.ok = $true
  $result.diagnosis = "ok"
}

$result | ConvertTo-Json -Depth 6
if (-not $result.ok) {
  exit 1
}
