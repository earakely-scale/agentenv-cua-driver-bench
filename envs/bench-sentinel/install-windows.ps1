# trycua's runner starts the sentinel from a copy of pythonw.exe named BenchSentinel.exe, beside it, so every tool
# sees it by that name: here a copy of the pythonw.exe of the Python the app's venv was made from.
$ErrorActionPreference = 'Stop'
$python = (Get-Content "$env:PREFIX\venv\pyvenv.cfg" | Where-Object { $_ -match '^home = ' }) -replace '^home = ', ''
Copy-Item -Force (Join-Path $python 'pythonw.exe') (Join-Path $python 'BenchSentinel.exe')
