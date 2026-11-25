# Hidden-mode

Aplicación de escritorio para Windows que guarda archivos de forma privada, cifrados y protegidos con un PIN de 4 dígitos.

by @dairongranadaa

## Qué hace

- Guarda archivos (imágenes, videos y documentos) cifrados con **AES-256-GCM**.
- La clave se protege con tu PIN usando **scrypt**. Quien tenía una contraseña antigua la cambia por un PIN al entrar, sin recifrar los archivos. Los nombres de los archivos, los álbumes y las miniaturas también van cifrados.
- Galería con miniaturas, búsqueda, orden y álbumes.
- Visor de imágenes con zoom, rotación y presentación.
- Arrastrar y soltar archivos o carpetas.
- Bloqueo automático por inactividad, al minimizar y al bloquear Windows. `F12` o `Ctrl+L` bloquean al instante.
- Espera creciente tras varios intentos fallidos de PIN.
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

La primera vez pide crear un PIN de 4 dígitos.

## Compilar el ejecutable y el instalador

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

Genera `dist\HakoSafe.exe` y, si tienes [Inno Setup 6](https://jrsoftware.org/isinfo.php) instalado, `installer\HakoSafe-Setup.exe`.

## Actualizaciones

La app busca nuevas versiones en las *Releases* de este repositorio al abrir la bóveda (se puede desactivar en Ajustes). Si hay una, aparece el botón «Actualización pendiente»: descarga el instalador, comprueba su firma digital (Ed25519) y se actualiza sola. La bóveda no se toca.

Publicar una versión nueva, desde el PC donde desarrollas:

```powershell
# una sola vez: crea la clave de firma y pega la clave pública que imprime en updater.py (PUBLIC_KEY_B64)
python release.py --keygen

# cada versión: sube VERSION en vault.py, haz commit y push, y luego
python release.py --notes "Qué cambió"
```

`release.py` compila, firma el instalador y crea la release en GitHub (pide un token con permiso *Contents: Read and write*; no lo guarda). La clave privada se guarda en `%USERPROFILE%\.hidden-mode\` y nunca debe subirse al repositorio. Si la pierdes, las apps ya instaladas no aceptarán más actualizaciones y habrá que reinstalar a mano una vez.

La primera vez, en cada PC hay que instalar a mano una versión que ya incluya el actualizador; de ahí en adelante se actualiza sola.

## Estructura

| Archivo | Descripción |
| --- | --- |
| `vault.py` | Cifrado y almacenamiento (sin interfaz). |
| `app.py` | Interfaz (customtkinter). |
| `installer.iss` | Script de Inno Setup para el instalador. |
| `build.ps1` | Compila el `.exe` y el instalador. |
| `updater.py` | Búsqueda, descarga y verificación de actualizaciones. |
| `release.py` | Publica una versión firmada en GitHub. |
| `requirements.txt` | Dependencias con versiones fijas. |

## Seguridad: lo que debes saber

- **Si olvidas el PIN, no hay forma de recuperar los archivos.** Haz un respaldo y guárdalo en otro lugar.
- **Un PIN de 4 dígitos tiene solo 10.000 combinaciones.** La espera tras intentos fallidos solo frena a quien teclea en la ventana. Quien consiga una copia de la carpeta de datos o de un respaldo (`.vbk`) puede probar todos los PIN por su cuenta en pocos minutos. No dejes copias de los datos en sitios compartidos y no guardes aquí nada que no puedas permitirte exponer.
- Los atributos de oculto y los nombres genéricos de las carpetas solo dificultan encontrarlas por casualidad. La protección real es el cifrado y el PIN.
- La espera tras intentos fallidos solo frena a quien adivina desde la ventana de la app.
- Al abrir un video o un documento se descifra una copia temporal, que se sobrescribe y se borra al bloquear o cerrar.
- El borrado de los originales (si lo activas) los sobrescribe antes de eliminarlos, pero en SSD o en carpetas sincronizadas (como OneDrive) no se puede garantizar el borrado físico.
- Es un proyecto personal y no ha tenido una auditoría de seguridad.
