; Script de Inno Setup para instalar Bóveda en cualquier PC con Windows.
; Compilar:  ISCC.exe installer.iss   ->  installer\Boveda_Setup.exe

#define AppName "Bóveda"
#define AppVersion "2.0.0"
#define AppExe "Boveda.exe"

[Setup]
AppId={{B3F1C2A4-7D5E-4F88-9A6B-2E1D4C7A9F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=@dairongranadaa
DefaultDirName={autopf}\Boveda
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=icon.ico
CloseApplications=yes
OutputDir=installer
OutputBaseFilename=Boveda_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; Instala solo para el usuario actual: no pide permisos de administrador.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent

; Importante: NO se borra la bóveda al desinstalar (está en una carpeta CLR_xxxx o CLRCache dentro de
; %LOCALAPPDATA%\Microsoft, o donde la hayas elegido), así no pierdes tus archivos al reinstalar o actualizar.
