; Script de Inno Setup para instalar la app en Windows.
; Compilar:  ISCC.exe installer.iss   ->  installer\HakoSafe-Setup.exe

; Nombre visible (menú Inicio, "Aplicaciones", asistente). Debe coincidir con APP_NAME en vault.py.
#define AppName "HakoSafe"
; build.ps1 pasa la versión real (la de vault.py) con /DAppVersion=...
#ifndef AppVersion
  #define AppVersion "2.3.1"
#endif
#define AppExe "HakoSafe.exe"
; Nombres de versiones anteriores, que se limpian al actualizar.
#define OldExe "Boveda.exe"
#define OldExe2 "Notas.exe"
#define OldShortcut "B*veda"
#define OldShortcut2 "Notas"

[Setup]
AppId={{B3F1C2A4-7D5E-4F88-9A6B-2E1D4C7A9F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=@dairongranadaa
VersionInfoProductName={#AppName}
VersionInfoDescription=Instalador de {#AppName}
VersionInfoCompany=@dairongranadaa
; Las instalaciones existentes conservan su carpeta anterior; solo las nuevas usan esta.
DefaultDirName={autopf}\HakoSafe
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
CloseApplications=yes
OutputDir=installer
; Este nombre de archivo lo busca el actualizador (updater.INSTALLER_NAME). Las apps hasta la 2.3.0 buscan
; "Boveda_Setup.exe": release.py sube también una copia con ese nombre para que puedan actualizarse.
OutputBaseFilename=HakoSafe-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
; Instala siempre solo para el usuario actual: no pide permisos de administrador ni muestra la pregunta
; "¿para todos los usuarios?". (Se puede forzar desde la línea de comandos con /ALLUSERS.)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
; Asistente corto: bienvenida -> accesos -> instalar -> listo (sin elegir carpeta ni pantalla de resumen).
; (La bienvenida viene desactivada por defecto en Inno Setup; se activa para que se vea la imagen grande.)
DisableWelcomePage=no
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
; Aspecto: oscuro, con imágenes propias en varios tamaños (se elige según la escala de pantalla).
WizardStyle=modern dark
SetupIconFile=installer_art\setup.ico
WizardImageFile=installer_art\big_100.bmp,installer_art\big_150.bmp,installer_art\big_200.bmp
WizardSmallImageFile=installer_art\small_100.bmp,installer_art\small_150.bmp,installer_art\small_200.bmp

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Messages]
WelcomeLabel1={#AppName}
WelcomeLabel2=Se instalará en tu equipo en unos segundos.
FinishedHeadingLabel=Todo listo
FinishedLabel={#AppName} ya está instalada. La encontrarás en el menú Inicio.

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[InstallDelete]
; Al actualizar desde una versión con un nombre anterior: quita el ejecutable y los accesos viejos.
Type: files; Name: "{app}\{#OldExe}"
Type: files; Name: "{app}\{#OldExe2}"
Type: files; Name: "{autoprograms}\{#OldShortcut}.lnk"
Type: files; Name: "{autodesktop}\{#OldShortcut}.lnk"
Type: files; Name: "{autoprograms}\{#OldShortcut2}.lnk"
Type: files; Name: "{autodesktop}\{#OldShortcut2}.lnk"

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
