param(
    [string]$KicadDir,
    [string]$OcrPython,
    [string]$OrcadRoot,
    [switch]$RequireOrcad,
    [switch]$ProbeServices,
    [switch]$Json
)
$ErrorActionPreference = 'Stop'
$setupRepository = Split-Path -Parent $PSScriptRoot
$setupPython = Join-Path $setupRepository 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $setupPython)) {
    $setupCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $setupCommand) { throw 'Install Python or complete the KiCad-backed environment setup in docs/SETUP.md.' }
    $setupPython = $setupCommand.Source
}
$setupArguments = @((Join-Path $PSScriptRoot 'check_setup.py'))
if ($KicadDir) { $setupArguments += @('--kicad-dir', $KicadDir) }
if ($OcrPython) { $setupArguments += @('--ocr-python', $OcrPython) }
if ($OrcadRoot) { $setupArguments += @('--orcad-root', $OrcadRoot) }
if ($RequireOrcad) { $setupArguments += '--require-orcad' }
if ($ProbeServices) { $setupArguments += '--probe-services' }
if ($Json) { $setupArguments += '--json' }
& $setupPython @setupArguments
exit $LASTEXITCODE
