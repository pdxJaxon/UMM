param(
    [Parameter(Mandatory = $true)]
    [int]$DraftYear,
    [string]$At = '02:00',
    [string]$TaskName = 'UMM-PFF-Candidate-Import'
)

$ErrorActionPreference = 'Stop'
$time = [datetime]::ParseExact($At, 'HH:mm', [cultureinfo]::InvariantCulture)
$script = Join-Path $PSScriptRoot 'import-pff-prospects.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
    "-NoProfile -NonInteractive -File `"$script`" -DraftYear $DraftYear -Commit"
)
$trigger = New-ScheduledTaskTrigger -Daily -At $time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Import newer authorized PFF CSV candidates for $DraftYear; simulation approval remains manual."
