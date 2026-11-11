# Hidden-mode

Aplicación de escritorio para Windows que guarda archivos de forma privada, cifrados y protegidos con una contraseña maestra.

by @dairongranadaa

## Qué hace

- Guarda archivos (imágenes, videos y documentos) cifrados con **AES-256-GCM**.
- La clave se protege con tu contraseña usando **scrypt**. Los nombres de los archivos, los álbumes y las miniaturas también van cifrados.
- Galería con miniaturas, búsqueda, orden y álbumes.
- Visor de imágenes con zoom, rotación y presentación.
- Arrastrar y soltar archivos o carpetas.
- Bloqueo automático por inactividad, al minimizar y al bloquear Windows. `F12` o `Ctrl+L` bloquean al instante.
- Espera creciente tras varios intentos fallidos de contraseña.
- Respaldo y restauración de toda la colección en un solo archivo (`.vbk`).
- Ubicación elegible al crearla (por ejemplo, una unidad USB).

## Requisitos

- Windows 10 u 11.
- Python 3.12 (probado con esa versión).

## Ejecutar desde el código

```powershell
pip install -r requirements.txt
python app.py
```

La primera vez pide crear una contraseña maestra.

## Compilar el ejecutable y el instalador

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

Genera `dist\Boveda.exe` y, si tienes [Inno Setup 6](https://jrsoftware.org/isinfo.php) instalado, `installer\Boveda_Setup.exe`.

## Estructura

| Archivo | Descripción |
| --- | --- |
| `vault.py` | Cifrado y almacenamiento (sin interfaz). |
| `app.py` | Interfaz (customtkinter). |
| `installer.iss` | Script de Inno Setup para el instalador. |
| `build.ps1` | Compila el `.exe` y el instalador. |
| `requirements.txt` | Dependencias con versiones fijas. |

## Seguridad: lo que debes saber

- **Si olvidas la contraseña, no hay forma de recuperar los archivos.** Haz un respaldo y guárdalo en otro lugar.
- Los atributos de oculto y los nombres genéricos de las carpetas solo dificultan encontrarlas por casualidad. La protección real es el cifrado y la contraseña: usa una larga.
- La espera tras intentos fallidos solo frena a quien adivina desde la ventana de la app.
- Al abrir un video o un documento se descifra una copia temporal, que se sobrescribe y se borra al bloquear o cerrar.
- El borrado de los originales (si lo activas) los sobrescribe antes de eliminarlos, pero en SSD o en carpetas sincronizadas (como OneDrive) no se puede garantizar el borrado físico.
- Es un proyecto personal y no ha tenido una auditoría de seguridad.
