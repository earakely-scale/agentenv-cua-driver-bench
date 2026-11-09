# install-windows.ps1, run elevated in the app's folder once its downloads are in: the runtimes they brought unpacked in
# place of their archives (Electron, and Node and Chrome for Testing where the task needs them), and LibreOffice and
# GnuCash installed silently where the task's Windows descriptor runs them, in place of their installers.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$runtime = Join-Path $PSScriptRoot 'runtime'

# An archive unpacked to runtime\<name>: its one top folder, where it has one, else all it holds.
function Unpack([string]$Name) {
    $zip = Join-Path $runtime "$Name.zip"
    if (-not (Test-Path $zip)) { return }
    $unpacked = Join-Path $runtime "$Name-unpacked"
    Expand-Archive -Path $zip -DestinationPath $unpacked
    $top = @(Get-ChildItem $unpacked)
    if ($top.Count -eq 1 -and $top[0].PSIsContainer) { Move-Item $top[0].FullName (Join-Path $runtime $Name); Remove-Item $unpacked }
    else { Move-Item $unpacked (Join-Path $runtime $Name) }
    Remove-Item $zip
}

# An installer run to its end, refused unless it exits 0 or asks for a restart (3010) and leaves the program the
# task runs, $Installs, then removed. An MSI given any feature property installs only the features it names, so
# LibreOffice's names them all.
function Install([string]$File, [string]$Installs, [string[]]$Arguments) {
    $path = Join-Path $runtime $File
    if (-not (Test-Path $path)) { return }
    $run = Start-Process -FilePath $Arguments[0] -ArgumentList $Arguments[1..($Arguments.Count - 1)] -Wait -PassThru
    if ($run.ExitCode -notin 0, 3010) { throw "$File exited $($run.ExitCode)" }
    if (-not (Test-Path $Installs)) { throw "$File exited $($run.ExitCode) but left no $Installs" }
    Remove-Item $path
}

Unpack 'electron'
Unpack 'node'
Unpack 'chromium'
$msi = Join-Path $runtime 'LibreOffice.msi'
Install 'LibreOffice.msi' 'C:\Program Files\LibreOffice\program\soffice.exe' @('msiexec.exe', '/i', "`"$msi`"", '/qn', '/norestart', 'ALLUSERS=1', 'CREATEDESKTOPLINK=0',
    'REGISTER_NO_MSO_TYPES=1', 'ISCHECKFORPRODUCTUPDATES=0', 'QUICKSTART=0', 'UI_LANGS=en_US', 'ADDLOCAL=ALL', 'REMOVE=gm_o_Onlineupdate')
Install 'gnucash-setup.exe' 'C:\Program Files (x86)\gnucash\bin\gnucash.exe' @((Join-Path $runtime 'gnucash-setup.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-')
if (-not (Test-Path (Join-Path $runtime 'electron\electron.exe'))) { throw 'Electron did not unpack' }
