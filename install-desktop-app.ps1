$ErrorActionPreference = 'Stop'
# Adds a "DeCad" icon to the Desktop and Start Menu. It starts the native backend + frontend if they
# are not running and opens DeCad in its own window (no browser tabs), like an installed web app.
# Remove: delete the two DeCad.lnk shortcuts.
$launcher = Join-Path $PSScriptRoot 'DeCad.vbs'
$icon = Join-Path $PSScriptRoot 'frontend\public\decad.ico'
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('Programs')) ''))) {
 $lnk = $shell.CreateShortcut((Join-Path $dir 'DeCad.lnk'))
 $lnk.TargetPath = "$env:SystemRoot\System32\wscript.exe"
 $lnk.Arguments = "`"$launcher`""
 $lnk.WorkingDirectory = $PSScriptRoot
 $lnk.IconLocation = $icon
 $lnk.Description = 'DeCad: schematic image to verified OrCAD Capture design'
 $lnk.Save()
 Write-Host "Created $(Join-Path $dir 'DeCad.lnk')"
}
