# Recompila la app (dist\HakoSafe.exe) y el instalador. Uso:  powershell -ExecutionPolicy Bypass -File build.ps1
Set-Location $PSScriptRoot
$version = (Select-String -Path vault.py -Pattern '^VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "Compilando version $version"
python -m PyInstaller --noconfirm --onefile --windowed --name HakoSafe --icon icon.ico --add-data "icon.ico;." --collect-all customtkinter --collect-all tkinterdnd2 app.py
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" "/DAppVersion=$version" installer.iss
Remove-Item -Recurse -Force build, HakoSafe.spec, __pycache__ -ErrorAction SilentlyContinue
Write-Host "Listo: installer\HakoSafe-Setup.exe"
