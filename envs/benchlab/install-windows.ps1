# trycua's runner starts BenchLab from a copy of pythonw.exe named BenchLab.exe, beside it, so every tool sees it by
# that name: here a copy of the pythonw.exe of the Python the app's venv was made from.
$ErrorActionPreference = 'Stop'
$python = (Get-Content "$env:PREFIX\venv\pyvenv.cfg" | Where-Object { $_ -match '^home = ' }) -replace '^home = ', ''
Copy-Item -Force (Join-Path $python 'pythonw.exe') (Join-Path $python 'BenchLab.exe')
# wxPython's DLLs need Microsoft's Visual C++ runtime, which a trimmed Windows lacks: installed quietly, an
# install that finds it there (1638) or wants the restart the next boot gives (3010) as good as one that ran.
$vc = Start-Process -Wait -PassThru -FilePath "$env:PREFIX\vc_redist.x64.exe" -ArgumentList '/install', '/quiet', '/norestart'
if ($vc.ExitCode -notin 0, 1638, 3010) { throw "the Visual C++ runtime's install exited $($vc.ExitCode)" }
Remove-Item "$env:PREFIX\vc_redist.x64.exe"
