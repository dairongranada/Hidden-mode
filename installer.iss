; Script de Inno Setup para instalar la app en Windows.
; Compilar:  ISCC.exe installer.iss   ->  installer\Boveda_Setup.exe

; Nombre visible (menú Inicio, "Aplicaciones", asistente). Debe coincidir con APP_NAME en vault.py.
#define AppName "Notas"
; build.ps1 pasa la versión real (la de vault.py) con /DAppVersion=...
#ifndef AppVersion
  #define AppVersion "2.2.0"
#endif
#define AppExe "Notas.exe"
; Nombres de versiones anteriores, que se limpian al actualizar.
#define OldExe "Boveda.exe"
#define OldShortcut "B*veda"

[Setup]
AppId={{B3F1C2A4-7D5E-4F88-9A6B-2E1D4C7A9F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=@dairongranadaa
; Las instalaciones existentes conservan su carpeta anterior; solo las nuevas usan esta.
DefaultDirName={autopf}\Notas
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=icon.ico
CloseApplications=yes
OutputDir=installer
; OJO: este nombre de archivo lo busca el actualizador de las apps ya instaladas (updater.INSTALLER_NAME).
; No lo cambies hasta que todas las copias estén en una versión que busque el nombre nuevo.
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

[InstallDelete]
; Al actualizar desde una versión con el nombre anterior: quita el ejecutable y los accesos viejos.
Type: files; Name: "{app}\{#OldExe}"
Type: files; Name: "{autoprograms}\{#OldShortcut}.lnk"
Type: files; Name: "{autodesktop}\{#OldShortcut}.lnk"

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

; Importante: los datos NO se borran al desinstalar (están en una carpeta dentro de
; %LOCALAPPDATA%\Microsoft, o donde la hayas elegido), así no se pierden al reinstalar o actualizar.

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent
; Actualización automática desde la app: el instalador corre en silencio con /RELAUNCH=1 y reabre la app al terminar.
Filename: "{app}\{#AppExe}"; Flags: nowait skipifnotsilent; Check: Relaunch

[Code]
function SetEnvironmentVariable(lpName, lpValue: String): Boolean;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

function Relaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
  { La app que lanzó este instalador es de PyInstaller: sin esto, la copia reabierta hereda su carpeta
    temporal (ya borrada) y falla con «Failed to load Python DLL». Así también funciona al actualizar
    desde versiones antiguas que aún no limpian el entorno. }
  if Result then
    SetEnvironmentVariable('PYINSTALLER_RESET_ENVIRONMENT', '1');
end;
