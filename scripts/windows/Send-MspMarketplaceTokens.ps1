#Requires -Version 5.1
<#
  SECURE ONE-TIME WB/Ozon token transfer from a Windows PC to MSP VPS.
  - Nine masked prompts, all JSON constructed in memory.
  - No credential file, transcript, command-line token, clipboard, or log.
  - SSH host key must already be trusted; public-key login required.
  - Server receiver must first be installed after an approved deployment.
  - Remote receiver accepts stdin and writes root-owned 0600 secrets.
  Usage: .\Send-MspMarketplaceTokens.ps1 -SshTarget root@verified-vps -IdentityFile "C:\Users\user\.ssh\msp_remote_ed25519" -Port 22
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$SshTarget,
    [ValidateRange(1,65535)][int]$Port=22,
    [Parameter(Mandatory=$true)][string]$IdentityFile,
    [switch]$ReplaceExisting
)
$ErrorActionPreference = 'Stop'

if ($SshTarget -notmatch '^[A-Za-z0-9][A-Za-z0-9_.@-]{0,254}$') {
    throw 'Invalid SSH target. Use only trusted user@hostname or configured SSH alias.'
}
if (-not (Get-Command 'ssh.exe' -ErrorAction SilentlyContinue)) {
    throw 'OpenSSH client ssh.exe not found.'
}
if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
    throw 'SSH private key file not found. No secrets have been entered.'
}
if ($IdentityFile -match '["\r\n]') { throw 'Invalid SSH key path.' }

# No user-selected remote command or path. The fixed receiver must be
# deployed/version-reviewed before executing this local transfer script.
$receiver = '/root/msp_reports_credentials_receiver.py'

function Invoke-SshReceiver {
    param([string]$Mode, [byte[]]$StdinBytes)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'ssh.exe'
    $flag = if ($Mode -eq 'check') { ' --check' } elseif ($Mode -eq 'replace') { ' --replace' } else { '' }
    $remoteCommand = 'sudo -n python3 ' + $receiver + $flag
    $psi.Arguments = '-T -i "' + $IdentityFile + '" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -p ' +
        $Port + ' ' + $SshTarget + ' "' + $remoteCommand + '"'
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    try {
        if (-not $process.Start()) { throw 'Unable to start SSH process.' }
        if ($null -ne $StdinBytes) {
            $process.StandardInput.BaseStream.Write($StdinBytes, 0, $StdinBytes.Length)
            $process.StandardInput.BaseStream.Flush()
        }
        $process.StandardInput.Close()
        $output = $process.StandardOutput.ReadToEnd().Trim()
        $errors = $process.StandardError.ReadToEnd().Trim()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            # Deliberately do not echo arbitrary output from remote or ssh.
            throw ('SSH receiver failed (code ' + $process.ExitCode + '). Check trusted host key, SSH key, sudo permissions and deployed receiver.')
        }
        return $output
    } finally {
        $process.Dispose()
    }
}

# Probe server readiness BEFORE asking the user to enter any keys.
$result = Invoke-SshReceiver -Mode 'check' -StdinBytes $null
if ($result -notmatch '^RECEIVER_READY=YES;SECRETS_RECEIVED=NO$') {
    throw 'Unexpected receiver readiness response. No credentials were collected or transmitted.'
}
Write-Host 'Receiver is ready. Enter credentials on THIS PC; values will be hidden.'

function Read-Secret([string]$label) {
    $secure = Read-Host -Prompt $label -AsSecureString
    if ($null -eq $secure -or $secure.Length -eq 0) {
        throw 'A required credential field is empty.'
    }
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secure.Dispose()
    }
}

$bundle = [ordered]@{}
try {
    $bundle['wb_laser_master'] = [ordered]@{ token = (Read-Secret 'WB Лазер-Мастер: токен') }
    $bundle['wb_novokshenov'] = [ordered]@{ token = (Read-Secret 'WB Новокшенов: токен') }
    $bundle['wb_dmitrieva'] = [ordered]@{ token = (Read-Secret 'WB Дмитриева: токен') }
    $bundle['ozon_laser_master'] = [ordered]@{
        client_id = (Read-Secret 'Ozon Лазер-Мастер: Client-Id')
        api_key = (Read-Secret 'Ozon Лазер-Мастер: API Key')
    }
    $bundle['ozon_novokshenov'] = [ordered]@{
        client_id = (Read-Secret 'Ozon Новокшенов: Client-Id')
        api_key = (Read-Secret 'Ozon Новокшенов: API Key')
    }
    $bundle['ozon_dmitrieva'] = [ordered]@{
        client_id = (Read-Secret 'Ozon Дмитриева: Client-Id')
        api_key = (Read-Secret 'Ozon Дмитриева: API Key')
    }
    $json = ConvertTo-Json -InputObject $bundle -Compress -Depth 5
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [byte[]]$bytes = $utf8.GetBytes($json)
    try {
        $mode = if ($ReplaceExisting) { 'replace' } else { 'create' }
        $result = Invoke-SshReceiver -Mode $mode -StdinBytes $bytes
        if ($result -notmatch '^RESULT=(CREATED|UPDATED|UNCHANGED);CABINETS=6;SECRETS_PRINTED=NO;SERVICES_RESTARTED=NO$') {
            throw 'Unexpected receiver result. Check server state without printing secrets.'
        }
        Write-Host $result
    } finally {
        [Array]::Clear($bytes, 0, $bytes.Length)
        $json = $null
    }
} finally {
    $bundle.Clear()
}
