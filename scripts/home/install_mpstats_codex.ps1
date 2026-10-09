#requires -Version 5.1
<#
  Registers the OFFICIAL hosted MPSTATS MCP for the interactive Windows Codex user.
  It does not install a local MCP executable or touch REMOTE.
  The token is read only from the local hidden prompt, never from CLI arguments.
  -CheckOnly is safe read-only detection.
#>
[CmdletBinding()]
param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$profileDir = $env:USERPROFILE
$codexDir = if ([string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
    Join-Path $profileDir '.codex'
} else {
    [System.IO.Path]::GetFullPath($env:CODEX_HOME)
}
$target = Join-Path $codexDir 'config.toml'
$tablePattern = '(?im)^\s*\[mcp_servers\.mpstats\]\s*$'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$nl = [Environment]::NewLine

Write-Output 'HOME_MPSTATS_CODEX_SETUP'
Write-Output ('mode=' + $(if ($CheckOnly) { 'check' } else { 'install' }))
Write-Output ('config_path=' + $target)

if ([string]::IsNullOrWhiteSpace($profileDir) -or
    $profileDir -match '(?i)[\\/]Windows[\\/]ServiceProfiles[\\/]' -or
    $identity.Name -match '(?i)(NETWORK SERVICE|LOCAL SERVICE|SYSTEM)$') {
    Write-Output 'result=BLOCKED_SERVICE_IDENTITY'
    throw 'Run this script as the interactive HOME Codex user, not a runner service.'
}

$exists = Test-Path -LiteralPath $target -PathType Leaf
$current = if ($exists) { [System.IO.File]::ReadAllText($target) } else { '' }
$present = [regex]::IsMatch($current,$tablePattern)
Write-Output ('config_exists=' + $exists.ToString().ToLowerInvariant())
Write-Output ('mpstats_already_registered=' + $present.ToString().ToLowerInvariant())

if ($CheckOnly) {
    Write-Output 'result=CHECK_PASS'
    return
}

if ($present) {
    Write-Output 'result=ALREADY_PRESENT'
    Write-Output 'note=Existing MPSTATS table preserved; no changes made.'
    return
}

$secure = Read-Host 'Paste your existing personal MPSTATS token (hidden input)' -AsSecureString
$ptr = [IntPtr]::Zero
$token = $null
try {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
} finally {
    if ($ptr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
    $secure.Dispose()
}
if ([string]::IsNullOrWhiteSpace($token) -or
    $token.IndexOfAny([char[]]@([char]13,[char]10,[char]0)) -ge 0) {
    throw 'Token is empty/invalid. No change made.'
}
# Authenticated URL must never go into command history, logs, GitHub, or chat.
$url = 'https://mcp.mpstats.io/mcp?token=' + [Uri]::EscapeDataString($token)
if (-not (Test-Path -LiteralPath $codexDir -PathType Container)) {
    New-Item -ItemType Directory -Path $codexDir -Force | Out-Null
}

$latest = if (Test-Path -LiteralPath $target -PathType Leaf) {
    [System.IO.File]::ReadAllText($target)
} else { '' }
if ($latest -cne $current) {
    throw 'Codex config changed during token entry. No changes made.'
}

$section = [string]::Join($nl,@(
    '[mcp_servers.mpstats]',
    ('url = "' + $url + '"'),
    'enabled = true',
    'startup_timeout_sec = 30.0',
    'tool_timeout_sec = 600.0'
))
$updated = $current.TrimEnd([char[]]@([char]13,[char]10)) + $nl + $nl + $section + $nl
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$backup = Join-Path $codexDir ("config.toml.pre-mpstats-home.$stamp.bak")
$tmp = Join-Path $codexDir ('.config.toml.mpstats-install.' + [guid]::NewGuid().ToString('N') + '.tmp')
$createdBackup = $false

try {
    if ($exists) {
        [System.IO.File]::Copy($target,$backup,$false)
        $createdBackup = $true
    }
    [System.IO.File]::WriteAllText($tmp,$updated,$utf8)
    if ($exists) {
        [System.IO.File]::Replace($tmp,$target,$null)
    } else {
        [System.IO.File]::Move($tmp,$target)
    }
    $saved = [System.IO.File]::ReadAllText($target)
    if (-not [regex]::IsMatch($saved,$tablePattern) -or
        -not $saved.Contains($url)) {
        throw 'Post-write check failed. Keep the private backup for recovery.'
    }
} finally {
    if ([System.IO.File]::Exists($tmp)) {
        [System.IO.File]::Delete($tmp)
    }
    $token = $null
    $url = $null
}

Write-Output 'config_write=PASS'
Write-Output ('private_backup=' + $(if ($createdBackup) { 'CREATED' } else { 'NOT_NEEDED' }))
Write-Output 'registered_server=mpstats'
Write-Output 'transport=streamable_http'

$codex = Get-Command codex -ErrorAction SilentlyContinue
if ($null -eq $codex) {
    Write-Output 'codex_cli_check=SKIPPED_NOT_ON_PATH'
} else {
    try {
        # CLI JSON can include the token-bearing URL; capture and never print it.
        $rawCli = (& codex mcp list --json 2>$null | Out-String)
        if ($LASTEXITCODE -ne 0) {
            Write-Output 'codex_cli_check=FAILED'
        } else {
            $listed = $rawCli | ConvertFrom-Json
            $names = @($listed | ForEach-Object { $_.name })
            if ($listed -is [System.Collections.IDictionary]) {
                $names = @($listed.Keys)
            }
            Write-Output ('codex_cli_check=' + $(if ($names -contains 'mpstats') { 'PASS' } else { 'NOT_SEEN' }))
        }
    } catch {
        Write-Output 'codex_cli_check=UNAVAILABLE'
    }
}
Write-Output 'result=CONFIGURED'
Write-Output 'next=Restart Codex Desktop and validate in a fresh session.'
