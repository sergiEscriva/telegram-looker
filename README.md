# TG Downloader

Descarga **automáticamente todo** el contenido de canales y grupos de Telegram (fotos, vídeos, audios, documentos y stickers) con **una o varias cuentas**, desde un **panel web** o desde la consola.

## Inicio rápido

| Quiero… | Haz doble clic en |
|---|---|
| Usar la interfaz gráfica (recomendado) | `panel.bat` → se abre `http://127.0.0.1:8765` |
| Usar la consola | `iniciar.bat` |

La primera vez se instala todo solo. En el panel: **Cuentas → Añadir cuenta** (teléfono + código) y después **Nueva descarga**.

> Las credenciales `API_ID` / `API_HASH` ya están en [`.env`](.env). Si faltan, el programa te las pide paso a paso.

## Funciones

- 👥 **Varias cuentas** con dos modos de reparto:
  - `canal`: cada cuenta descarga canales distintos en paralelo.
  - `mensajes`: todas las cuentas se reparten los mensajes de un mismo canal (más rápido; ver aviso abajo).
- 👀 **Modo vigilancia**: tras el historial, descarga los mensajes nuevos al instante.
- ♻️ **Sin duplicados**: un archivo repetido (aunque esté en otro canal) no se vuelve a bajar; se crea un enlace duro que no ocupa espacio.
- 🔎 **Filtros**: por tipo, fechas, tamaño, extensiones y texto.
- 🗂 **Organización**: álbumes en su propia carpeta, temas de foros en carpetas, nombres originales o basados en el texto.
- 💬 **Comentarios** de las publicaciones (opcional).
- 🌐 **Archivo HTML** navegable sin conexión de cada canal (búsqueda, filtros, visor de imágenes).
- ⏯ **Reanudable** (SQLite): si se corta, continúa donde se quedó; los fallos se reintentan solos.
- 🛡 FloodWait, reconexiones, referencias caducadas, **límite de velocidad**, **parada si queda poco disco**.
- 🔔 **Aviso** en tus *Mensajes guardados* al terminar cada canal.

## Consola

```powershell
.\iniciar.bat                                   # menú interactivo (admite 1,3,5-8)
.\iniciar.bat @canal                            # un canal
.\iniciar.bat @canal --seguir --comentarios     # + vigilancia y comentarios
.\iniciar.bat @c1 @c2 --reparto canal           # varios canales, una cuenta cada uno
.\iniciar.bat @canal --reparto mensajes         # todas las cuentas en el mismo canal
.\iniciar.bat @canal -t videos --min-tamano 50MB --desde 2025-01-01
.\iniciar.bat --añadir-cuenta trabajo           # añadir otra cuenta
.\iniciar.bat --listar-cuentas | --listar       # ver cuentas / canales
.\iniciar.bat @canal --regenerar-html           # rehacer el archivo HTML
```

<details><summary>Todas las opciones</summary>

| Opción | Descripción |
|---|---|
| `--cuentas a,b` | Cuentas a usar (por defecto todas) |
| `--añadir-cuenta N` / `--eliminar-cuenta N` | Gestionar cuentas |
| `--reparto canal\|mensajes` | Cómo se reparten las cuentas |
| `-o`, `--salida` | Carpeta de destino |
| `-n`, `--hilos` | Descargas simultáneas por cuenta (def. 3) |
| `--seguir` | Modo vigilancia |
| `--comentarios` | Descargar comentarios |
| `--nombres original\|texto` | Cómo nombrar los archivos |
| `--sin-albumes` / `--sin-deduplicar` / `--sin-html` / `--sin-notificar` | Desactivar funciones |
| `--limite-velocidad 5MB` | Velocidad máxima total por segundo |
| `--espacio-minimo 1GB` | Se detiene si queda menos espacio |
| `-t`, `--tipos` | `fotos,videos,audios,documentos,stickers` |
| `--desde` / `--hasta` | Fechas `AAAA-MM-DD` |
| `--min-tamano` / `--max-tamano` | p. ej. `10MB`, `2GB` |
| `--ext` / `--excluir-ext` | p. ej. `mp4,mkv` |
| `--buscar TEXTO` | Solo archivos cuyo texto/nombre lo contenga |
</details>

## Estructura

```
descargas/<Canal>/
├── fotos/ videos/ audios/ documentos/ stickers/
├── albumes/<fecha>_<id>/        # álbumes
├── temas/<Tema>/...             # grupos con foros
├── comentarios/<publicación>/   # con --comentarios
└── index.html                   # archivo navegable
sesiones/<cuenta>.session        # una por cuenta (¡no las compartas!)
datos.db                         # progreso, duplicados e historial
```

## Avisos

> **Varias cuentas:** Telegram puede restringir cuentas que usa para saltarse sus límites. Usa cuentas antiguas, no subas `--hilos` por encima de 5 y prefiere el reparto `canal`.

> **No abras el panel y la consola a la vez con la misma cuenta**: la sesión queda bloqueada.

> Usa la herramienta para contenido al que tengas acceso legítimo, respetando los derechos de autor y los términos de Telegram.
