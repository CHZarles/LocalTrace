$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
  throw "LocalTrace skill install is currently documented for Windows agents only."
}

function Find-Python {
  if ($env:PYTHON) {
    return $env:PYTHON
  }
  if (Get-Command python -ErrorAction SilentlyContinue) {
    return "python"
  }
  if (Get-Command py -ErrorAction SilentlyContinue) {
    return "py"
  }
  throw "LocalTrace skill install failed: python or py is required."
}

function Get-ArchiveInstallPy {
  param([string]$Archive)

  $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("localtrace-skill-" + [System.Guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Path $tempDir | Out-Null

  if ($Archive -match "^https?://") {
    $downloaded = Join-Path $tempDir "localtrace-skill.tar.gz"
    Invoke-WebRequest -Uri $Archive -OutFile $downloaded
    $Archive = $downloaded
  }

  tar -xzf $Archive -C $tempDir
  $installPy = Get-ChildItem -Path $tempDir -Filter install.py -Recurse |
    Where-Object { $_.FullName -match "[\\/]skill[\\/]install.py$" } |
    Select-Object -First 1

  if (-not $installPy) {
    throw "LocalTrace skill install failed: archive does not contain skill/install.py."
  }

  return $installPy.FullName
}

function Get-LocalInstallPy {
  if ($env:LOCALTRACE_SKILL_ARCHIVE) {
    return Get-ArchiveInstallPy -Archive $env:LOCALTRACE_SKILL_ARCHIVE
  }

  if ($PSCommandPath) {
    return Join-Path (Split-Path -Parent $PSCommandPath) "install.py"
  }

  $repoInstallPy = Join-Path (Get-Location) "skill\install.py"
  if (Test-Path $repoInstallPy) {
    return $repoInstallPy
  }

  throw "LocalTrace skill install failed: run from the repository root or set LOCALTRACE_SKILL_ARCHIVE."
}

$python = Find-Python
$installPy = Get-LocalInstallPy
$passthroughArgs = $args
$installOutput = & $python $installPy --python $python @passthroughArgs
$installExitCode = $LASTEXITCODE
$installOutputText = ($installOutput | Out-String).Trim()
if ($installOutputText) {
  Write-Output $installOutputText
}

if ($installExitCode -ne 0) {
  exit $installExitCode
}

try {
  $installResult = $installOutputText | ConvertFrom-Json
  if ($installResult.ok -and $installResult.must_tell_user_zh) {
    Write-Host ""
    Write-Host "=== LocalTrace browser extension details: 请转告用户 ==="
    Write-Host $installResult.must_tell_user_zh
    Write-Host "======================================================"
  }
} catch {
  Write-Warning "LocalTrace skill installed, but browser extension guidance could not be parsed."
}

exit $installExitCode
