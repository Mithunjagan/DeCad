$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from PowerShell as Administrator.'
}

# Preserve Docker data. Only temporary socket directories are relocated.
$dockerExecutable = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
$desktopExecutable = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
$dockerDirectory = 'C:\Users\mith1\AppData\Local\Docker'
$runtimeDirectories = @(
    'C:\Users\mith1\AppData\Local\Docker\run',
    'C:\Users\mith1\AppData\Local\docker-secrets-engine'
)
if (-not (Test-Path -LiteralPath $desktopExecutable)) { throw 'Docker Desktop is missing.' }

Write-Host 'Stopping Docker and restarting WSL...'
$desktopProcesses = @(Get-Process -Name 'Docker Desktop','com.docker.backend','com.docker.build','docker-ai' -ErrorAction SilentlyContinue)
foreach ($desktopProcess in $desktopProcesses) {
    if ($desktopProcess.Path -and $desktopProcess.Path.StartsWith('C:\Program Files\Docker\', [StringComparison]::OrdinalIgnoreCase)) {
        Stop-Process -Id $desktopProcess.Id -ErrorAction SilentlyContinue
        $desktopProcess.WaitForExit(10000) | Out-Null
    }
}
Restart-Service -Name WslService -Force -ErrorAction Stop

$backupStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
foreach ($runtimeDirectory in $runtimeDirectories) {
    if (Test-Path -LiteralPath $runtimeDirectory) {
        $resolvedDirectory = (Resolve-Path -LiteralPath $runtimeDirectory).Path
        if ($resolvedDirectory -ine $runtimeDirectory) { throw 'Unexpected runtime directory.' }
        $backupDirectory = Join-Path $dockerDirectory ((Split-Path -Leaf $runtimeDirectory) + '.preserved-' + $backupStamp)
        [IO.Directory]::Move($runtimeDirectory, $backupDirectory)
        Write-Host "Preserved $backupDirectory"
    }
}

Start-Process -FilePath $desktopExecutable -WindowStyle Hidden
Write-Host 'Waiting for the Docker engine...'
$engineReady = $false
$engineDeadline = [DateTime]::UtcNow.AddMinutes(3)
while ([DateTime]::UtcNow -lt $engineDeadline) {
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $dockerExecutable
    $startInfo.Arguments = 'info --format {{.ServerVersion}}'
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $probeProcess = [Diagnostics.Process]::Start($startInfo)
    if ($probeProcess.WaitForExit(10000)) {
        $engineReady = $probeProcess.ExitCode -eq 0
        if ($engineReady) { Write-Host ('Docker engine: ' + $probeProcess.StandardOutput.ReadToEnd().Trim()) }
    } else {
        $probeProcess.Kill()
        $probeProcess.WaitForExit()
    }
    $probeProcess.Dispose()
    if ($engineReady) { break }
    Start-Sleep -Seconds 2
}
if (-not $engineReady) { throw 'Docker is still unavailable. Keep the Docker error message for diagnosis.' }

Set-Location -LiteralPath $projectDirectory
Write-Host 'Building the DeCad containers. The first build may take several minutes...'
& $dockerExecutable compose build kicad frontend
if ($LASTEXITCODE -ne 0) { throw 'Container build failed. The direct DeCad server has been left running.' }

# Release only the direct servers launched for this checkout, after the build succeeds.
foreach ($servicePort in @(3100, 8100)) {
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $servicePort -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $listenerProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if (-not $listenerProcess) { continue }
        $parentProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listenerProcess.ParentProcessId)"
        $ownCommand = [string]$listenerProcess.CommandLine
        $parentCommand = [string]$parentProcess.CommandLine
        $belongsToProject = $ownCommand.IndexOf($projectDirectory, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or $parentCommand.IndexOf($projectDirectory, [StringComparison]::OrdinalIgnoreCase) -ge 0
        $isDirectServer = $ownCommand -match 'uvicorn|next.*start-server\.js'
        if ($belongsToProject -and $isDirectServer) {
            Stop-Process -Id $listenerProcess.ProcessId -ErrorAction SilentlyContinue
            if ($parentCommand -match 'uvicorn|node_modules[/\\]next[/\\]dist[/\\]bin[/\\]next') {
                Stop-Process -Id $listenerProcess.ParentProcessId -ErrorAction SilentlyContinue
            }
        }
    }
}

& $dockerExecutable compose up -d --wait --wait-timeout 180 kicad frontend
if ($LASTEXITCODE -ne 0) { throw 'Container startup failed. See Docker output above.' }
$health = Invoke-RestMethod -Uri 'http://localhost:3100/api/health' -TimeoutSec 30
$health | Format-List
if (-not ($health.kicad -and $health.ngspice -and $health.embedded)) {
    throw 'DeCad started, but one or more native services are unavailable.'
}
Write-Host 'DeCad is ready: http://localhost:3100'
