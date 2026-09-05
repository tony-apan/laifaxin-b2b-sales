# Bootstrap for Windows PowerShell (no Python required to run this script).
# Usage (for the AI; users should not type commands manually):
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap.ps1 -CheckOnly
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap.ps1 -Install
# Exit codes: 0 = all ready, 1 = still missing (incl. "no winget, cannot auto-install"), 2 = argument error.
# What it installs (-Install, via winget): Python.Python.3.12 (if no usable Python), Git.Git (if git/bash missing).
#   Git for Windows also provides bash.exe/grep/awk (Git Bash) - this repo's shell tools rely on them.
# It never: enables WSL, requires a reboot, or changes the system execution policy.
# Companion SOP: specs/environment-setup.md ; machine migration: specs/migration-handoff.md
param(
  [switch]$CheckOnly,
  [switch]$Install
)

$ErrorActionPreference = 'Continue'

if ($CheckOnly -and $Install) {
  Write-Output "ERROR: -CheckOnly and -Install are mutually exclusive (pick one mode per run)."
  exit 2
}
if (-not ($CheckOnly -or $Install)) {
  $CheckOnly = $true   # safe default = probe only
  Write-Output "NOTE: no mode switch given; defaulting to -CheckOnly."
}
$Mode = if ($CheckOnly) { 'check-only' } else { 'install' }

$PyUrl   = 'https://www.python.org/downloads/'
$GitUrl  = 'https://git-scm.com/download/win'

# ---------- helpers ----------
function Find-Cmd([string]$name) {
  $c = Get-Command $name -ErrorAction SilentlyContinue
  if ($c) { return $c.Source }
  return $null
}

function Refresh-Path() {
  # Re-read Machine+User PATH from registry (installers update these; current session does not see them).
  $m = [Environment]::GetEnvironmentVariable('Path', 'Machine')
  $u = [Environment]::GetEnvironmentVariable('Path', 'User')
  $env:Path = "$m;$u;$env:Path"
}

function Get-PyVersion([string]$exe, [string[]]$argList) {
  # Returns version string like 'Python 3.12.1', or $null if the command is not a working Python 3.
  try {
    $out = & $exe @argList 2>&1
    if ($LASTEXITCODE -eq 0) {
      $txt = ($out | Out-String).Trim()
      if ($txt -match '^Python 3') { return ($txt -split "`r?`n")[0] }
    }
  } catch { }
  return $null
}

function Find-Python() {
  # Resolution order (Windows): py launcher -> python -> python3.
  # Guards against the Windows Store "app execution alias" stub (exit code 9009, prints "Python was not found").
  $c = Find-Cmd 'py'
  if ($c) {
    $v = Get-PyVersion 'py' @('--version')
    if ($v) { return @{ cmd = 'py'; path = $c; version = $v } }
  }
  foreach ($name in @('python', 'python3')) {
    $c = Find-Cmd $name
    if ($c) {
      $v = Get-PyVersion $name @('--version')
      if ($v) { return @{ cmd = $name; path = $c; version = $v } }
    }
  }
  # Common install locations not yet on PATH (checked only after -Install refreshes, but harmless always)
  $candidates = @()
  $candidates += (Get-Item "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
  $candidates += (Get-Item "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
  foreach ($p in $candidates) {
    if ($p) {
      $v = Get-PyVersion $p @('--version')
      if ($v) { return @{ cmd = $p; path = $p; version = $v } }
    }
  }
  return $null
}

function Find-CurlExe() {
  $c = Find-Cmd 'curl.exe'
  if ($c) { return $c }
  foreach ($p in @("$env:ProgramFiles\Git\mingw64\bin\curl.exe", "${env:ProgramFiles(x86)}\Git\mingw64\bin\curl.exe")) {
    if (Test-Path $p) { return $p }
  }
  return $null
}

function Find-GitExe() {
  $c = Find-Cmd 'git'
  if ($c) { return $c }
  foreach ($p in @("$env:ProgramFiles\Git\cmd\git.exe", "${env:ProgramFiles(x86)}\Git\cmd\git.exe")) {
    if (Test-Path $p) { return $p }
  }
  return $null
}

function Find-BashExe() {
  $c = Find-Cmd 'bash.exe'
  if ($c) { return $c }
  foreach ($p in @("$env:ProgramFiles\Git\bin\bash.exe", "${env:ProgramFiles(x86)}\Git\bin\bash.exe")) {
    if (Test-Path $p) { return $p }
  }
  return $null
}

function Test-GrepAwk([string]$bashExe) {
  # Git Bash provides grep/awk; verify they are reachable inside that bash.
  if (-not $bashExe) { return $false }
  try {
    $null = & $bashExe -lc "command -v grep >/dev/null && command -v awk >/dev/null" 2>&1
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}

Write-Output "Bootstrap - mode=$Mode"
Write-Output "Platform: Windows PowerShell $($PSVersionTable.PSVersion.ToString())"

# ---------- probe ----------
$Py     = Find-Python
$PyCmd  = if ($Py) { $Py.cmd } else { '' }
$PyVer  = if ($Py) { $Py.version } else { '' }
$PyOk   = [bool]$Py

$CurlExe = Find-CurlExe   # Windows built-in curl.exe or Git for Windows copy; avoid PowerShell curl alias
$CurlOk  = [bool]$CurlExe

$GitExe = Find-GitExe
$GitOk  = [bool]$GitExe

$BashExe = Find-BashExe
$BashOk  = [bool]$BashExe
$GrepAwkOk = Test-GrepAwk $BashExe

$InstallResult = 'not_attempted'

# ---------- install ----------
if ($Mode -eq 'install') {
  $needPython = -not $PyOk
  $needGit    = (-not $GitOk) -or (-not $BashOk) -or (-not $GrepAwkOk)   # Git for Windows brings git+bash+grep+awk
  if (-not ($needPython -or $needGit)) {
    $InstallResult = 'nothing_to_do'
    Write-Output "OK: nothing missing; no install needed."
  } else {
    $winget = Find-Cmd 'winget'
    if (-not $winget) {
      $InstallResult = 'no_winget'
      Write-Output 'ERROR: cannot auto-install: winget was not found on this machine.'
      Write-Output "  Python (official installer): $PyUrl   (tick 'Add python to PATH' during setup)"
      Write-Output "  Git for Windows (provides git + bash + grep + awk): $GitUrl"
      Write-Output '  winget comes with "App Installer" from Microsoft Store; after installing it, re-run this script.'
    } else {
      if ($needPython) {
        Write-Output ' winget install Python.Python.3.12 ...'
        & winget install --id Python.Python.3.12 -e --source winget --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -eq 0) { $InstallResult = 'attempted' } else { $InstallResult = 'failed' }
      }
      if ($needGit) {
        Write-Output ' winget install Git.Git ...'
        & winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) { $InstallResult = 'failed' }
        elseif ($InstallResult -ne 'failed') { $InstallResult = 'attempted' }
      }
      # Re-scan: refresh PATH from registry, then probe common install paths as well. No reboot, no new terminal needed.
      Refresh-Path
    }
  }
}

# ---------- re-probe after install ----------
if ($Mode -eq 'install') {
  $Py        = Find-Python
  $PyCmd     = if ($Py) { $Py.cmd } else { '' }
  $PyVer     = if ($Py) { $Py.version } else { '' }
  $PyOk      = [bool]$Py
  $CurlExe   = Find-CurlExe
  $CurlOk    = [bool]$CurlExe
  $GitExe    = Find-GitExe
  $GitOk     = [bool]$GitExe
  $BashExe   = Find-BashExe
  $BashOk    = [bool]$BashExe
  $GrepAwkOk = Test-GrepAwk $BashExe
}

$Missing = @()
if (-not $PyOk)      { $Missing += 'python' }
if (-not $CurlOk)    { $Missing += 'curl' }
if (-not $GitOk)     { $Missing += 'git' }
if (-not $BashOk)    { $Missing += 'bash' }
if (-not $GrepAwkOk) { $Missing += 'grep/awk(via Git Bash)' }
$MissingTxt = if ($Missing.Count) { $Missing -join ',' } else { 'none' }
$AllOk = ($Missing.Count -eq 0)

# ---------- human-readable recap ----------
Write-Output ''
Write-Output 'Environment recap:'
if ($PyOk) { Write-Output "  [OK] Python: command = $PyCmd ($PyVer) at $($Py.path) - use this exact command in later steps" }
else       { Write-Output '  [MISSING] python (no usable py/python/python3 found)' }
if ($CurlOk) { Write-Output "  [OK] curl.exe ($CurlExe)" } else { Write-Output '  [MISSING] curl.exe (built into Windows 10 1803+; a missing one usually means a very old Windows)' }
if ($GitOk)  { Write-Output "  [OK] git ($GitExe)" } else { Write-Output '  [MISSING] git' }
if ($BashOk) { Write-Output "  [OK] bash.exe ($BashExe)" } else { Write-Output '  [MISSING] bash.exe (install Git for Windows to get it)' }
if ($GrepAwkOk) { Write-Output '  [OK] grep/awk (via Git Bash)' } else { Write-Output '  [MISSING] grep/awk (provided by Git Bash)' }
if ($AllOk) {
  Write-Output '  ALL READY. Next step: run  tools\onboard_check.py  with the python command above.'
} else {
  Write-Output "  STILL MISSING: $MissingTxt"
  if ($Mode -eq 'install') {
    Write-Output "  If winget install finished but items are still missing: open a NEW terminal once (PATH refresh), or use the full paths shown above."
    Write-Output "  Manual downloads: Python $PyUrl ; Git $GitUrl"
  } else {
    Write-Output '  Next step for the AI: re-run this script with -Install (uses winget).'
  }
}

# ---------- stable key=value summary (for AI/script parsing; do not rename keys) ----------
Write-Output ''
Write-Output '# ---- bootstrap summary (key=value) ----'
Write-Output "mode=$Mode"
Write-Output "platform=windows-powershell/$($PSVersionTable.PSVersion.ToString())"
Write-Output "install_result=$InstallResult"
Write-Output "python_cmd=$(if ($PyCmd) { $PyCmd } else { 'none' })"
Write-Output "python_version=$(if ($PyVer) { $PyVer } else { 'none' })"
Write-Output "python_ok=$(if ($PyOk) { 1 } else { 0 })"
Write-Output "curl_ok=$(if ($CurlOk) { 1 } else { 0 })"
Write-Output "git_ok=$(if ($GitOk) { 1 } else { 0 })"
Write-Output "bash_ok=$(if ($BashOk) { 1 } else { 0 })"
Write-Output "grep_ok=$(if ($GrepAwkOk) { 1 } else { 0 })"
Write-Output "awk_ok=$(if ($GrepAwkOk) { 1 } else { 0 })"
Write-Output "grep_awk_ok=$(if ($GrepAwkOk) { 1 } else { 0 })"
Write-Output "missing=$MissingTxt"
Write-Output "all_ok=$(if ($AllOk) { 1 } else { 0 })"

# ---------- execution policy hint (informational only; this script never changes any policy) ----------
$policy = Get-ExecutionPolicy -Scope Process
if ($policy -eq 'Restricted' -or $policy -eq 'Undefined') {
  Write-Output ''
  Write-Output 'NOTE: if a future run is blocked by the execution policy, use the one-shot form (does NOT change system settings):'
  Write-Output '  powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap.ps1 -CheckOnly'
}

if ($AllOk) { exit 0 } else { exit 1 }
