# Recompila Boveda.exe y el instalador. Uso:  powershell -ExecutionPolicy Bypass -File build.ps1
Set-Location $PSScriptRoot
python -m PyInstaller --noconfirm --onefile --windowed --name Boveda --icon icon.ico --add-data "icon.ico;." --collect-all customtkinter --collect-all tkinterdnd2 app.py
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss
Remove-Item -Recurse -Force build, Boveda.spec, __pycache__ -ErrorAction SilentlyContinue
Write-Host "Listo: installer\Boveda_Setup.exe"
