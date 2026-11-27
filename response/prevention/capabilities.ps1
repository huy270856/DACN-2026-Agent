# Read-only TASK09B probe. No policy/service/registry writes, no elevation.
$ErrorActionPreference = 'Stop'
$errorsFound = @()
$osInfo = $null
$admin = $null
$serviceStatus = $null
$policyDigest = $null
$availableCommands = @()
try {
    $versionKey = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
    $osInfo = @{edition=$versionKey.EditionID; build=$versionKey.CurrentBuildNumber;
        ubr=$versionKey.UBR; display_version=$versionKey.DisplayVersion}
} catch { $errorsFound += 'OS_REGISTRY_READ_FAILED' }
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $admin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
} catch { $errorsFound += 'TOKEN_READ_FAILED' }
try { $serviceStatus = (Get-Service -Name AppIDSvc).Status.ToString() }
catch { $errorsFound += 'APPIDSVC_READ_FAILED' }
foreach ($commandName in @('Get-AppLockerPolicy','Get-AppLockerFileInformation','Test-AppLockerPolicy')) {
    if (Get-Command -Name $commandName -ErrorAction SilentlyContinue) { $availableCommands += $commandName }
}
if ($availableCommands -contains 'Get-AppLockerPolicy') {
    try {
        $xml = Get-AppLockerPolicy -Effective -Xml
        $algorithm = [Security.Cryptography.SHA256]::Create()
        try {
            $policyDigest = ([BitConverter]::ToString($algorithm.ComputeHash(
                [Text.Encoding]::UTF8.GetBytes($xml)))).Replace('-','').ToLowerInvariant()
        } finally { $algorithm.Dispose() }
    } catch { $errorsFound += 'EFFECTIVE_POLICY_READ_FAILED' }
} else { $errorsFound += 'APPLOCKER_READ_CMDLET_UNAVAILABLE' }
[ordered]@{
    schema_version='task09b-capabilities-draft-v1'
    evaluation_type='WINDOWS_READ_ONLY_PROBE'
    os=$osInfo
    token_is_administrator=$admin
    appidsvc_status=$serviceStatus
    read_commands=$availableCommands
    effective_policy_xml_sha256=$policyDigest
    # No edition/build shortcut can establish safe enforcement/rollback.
    enforce_support='UNKNOWN_NOT_LIVE_TESTED'
    approved_vm='NOT_ESTABLISHED'
    rollback_rehearsal='NOT_RUN'
    live_status='BLOCKED'
    reason_code='POWERSHELL_PROBE_DOES_NOT_AUTHORIZE_LIVE_ACTIONS'
    errors=$errorsFound
    policy_writes=0
    service_writes=0
} | ConvertTo-Json -Depth 5 -Compress
