# TG Downloader (Telegram Media Downloader)

Descargador automatico masivo para canales y grupos de Telegram (fotos, videos, audios, documentos y stickers). Incluye soporte para **multiples cuentas**, **modo vigilancia en tiempo real**, **deduplicacion inteligente**, **archivo HTML navegable sin conexion** y un **panel web con diseno Windows Vista (Aero)**.

---

## Caracteristicas principales

- **Panel Web estilo Windows Vista Aero:**
  - Ventana translucida de cristal con controles completos (minimizar, maximizar, restaurar).
  - Barra de tareas integrada con boton de inicio y reloj en directo.
  - Gadget lateral con velocimetro en tiempo real.
  - Seleccion visual interactiva de canales, cuentas y filtros.
  - Dialogos y globos de notificacion clasicos de Windows Vista.
- **Soporte multi-cuenta:**
  - Conecta tantas cuentas de Telegram como quieras.
  - Dos modos de trabajo:
    - `canal`: cada cuenta descarga canales distintos en paralelo.
    - `mensajes`: todas las cuentas colaboran repartiendose los mensajes de un mismo canal para maxima velocidad.
- **Archivo web HTML sin conexion:**
  - Cada canal genera un archivo interactivo `index.html` estilo explorador de Windows Vista.
  - Busqueda instantanea en el texto de los mensajes y nombres de archivo.
  - Filtros rapidos por tipo (Fotos, Videos, Audios, Documentos, Texto).
  - Visor de fotos a pantalla completa estilo *Galeria fotografica de Windows*.
  - 100% autonomo (no requiere conexion a internet para ver el contenido guardado).
  - En canales grandes los mensajes se guardan por partes (`archivo_datos/`) y la pagina abre al instante aunque haya cientos de miles.
- **Deduplicacion inteligente:**
  - Si un archivo de Telegram ya fue descargado previamente (incluso en otro canal), no se vuelve a descargar: se vincula automaticamente ahorrando ancho de banda y espacio en disco.
- **Descargas rapidas y reanudables:**
  - Los archivos de 4 MB o mas se bajan por trozos, varios a la vez (`--conexiones`, por defecto 4).
  - Si se corta (Detener, sin conexion, apagar el PC), la siguiente vez sigue donde se quedo en vez de empezar de cero.
  - Modo exportacion de Telegram (`--takeout`) para historiales enormes, con menos esperas por FloodWait. La primera vez Telegram pide confirmarlo en la app.
- **Comodidades del panel:**
  - Boton **Repetir** en cada descarga terminada (relanza lo mismo y solo baja lo nuevo).
  - **Descargas programadas**: cada dia (o los dias que elijas) a una hora fija, mientras el panel este abierto.
  - Boton **Examinar...** para elegir la carpeta de destino.
  - Exportar los mensajes de un canal a **CSV** (para Excel) o **JSON**: texto, fecha, enlaces, archivo y vistas.
  - Historial de descargas que se conserva al reiniciar.
- **Registro en archivo:** todo lo que sale en pantalla se guarda tambien en `registro.log` (rota solo, maximo ~8 MB).
- **Organizacion automatica:**
  - Carpetas categorizadas (`fotos/`, `videos/`, `audios/`, `documentos/`, `stickers/`).
  - Albumes agrupados en subcarpetas propias con fecha.
  - Separacion por temas en grupos con foros.
  - Descarga opcional de comentarios anidados a cada publicacion.
- **Modo vigilancia continua (`--seguir`):**
  - Tras descargar todo el historial del canal, el programa se queda a la escucha y descarga al instante cualquier archivo nuevo que se publique.
- **Seguridad y fiabilidad:**
  - Base de datos local SQLite: si se interrumpe la descarga, continua justo donde se quedo.
  - Gestion automatica de limites de Telegram (*FloodWait*) con reintentos transparentes.
  - Limite de velocidad configurable y control de espacio libre minimo en disco.
  - Notificacion automatica a tus *Mensajes guardados* de Telegram al finalizar.

---

## Inicio rapido (Windows)

### 1. Requisitos
- Windows 10 / 11 (o Linux / macOS).
- [Python 3.10 o superior](https://www.python.org/downloads/) *(marcar la casilla "Add python.exe to PATH" durante la instalacion)*.

### 2. Clonar y configurar credenciales

1. Clona el repositorio:
   ```bash
   git clone https://github.com/TU_USUARIO/TU_REPOSITORIO.git
   cd TU_REPOSITORIO
   ```

2. Crea tu archivo `.env` a partir de la plantilla:
   ```bash
   copy .env.ejemplo .env
   ```

3. Obten tus claves gratuitas de la API de Telegram:
   - Entra en [https://my.telegram.org](https://my.telegram.org) e inicia sesion con tu numero de telefono.
   - Ve a **API development tools**.
   - Crea una app con cualquier nombre y copia tu **API_ID** y **API_HASH**.
   - Pegalos dentro del archivo `.env`:
     ```env
     API_ID=12345678
     API_HASH=abcdef1234567890abcdef1234567890
     ```

---

## Uso

### Opcion A: Panel grafico Web (Recomendado)

Haz doble clic en:
```
panel.bat
```
- Se instalaran automaticamente las dependencias en su propio entorno virtual si es la primera vez.
- Se abrira tu navegador con la interfaz Vista en `http://127.0.0.1:8765`.
- **Anadir cuenta:** Haz clic en **Anadir cuenta**, introduce tu telefono y escribe el codigo oficial que te enviara Telegram.
- **Descargar:** Ve a **Nueva descarga**, selecciona tu cuenta y el canal que desees de la lista y pulsa **Iniciar descarga**.

---

### Opcion B: Consola / Terminal

Haz doble clic en:
```
iniciar.bat
```
*(O ejecutalo desde el terminal con parametros)*:

```powershell
# Menu interactivo para elegir canal
.\iniciar.bat

# Descargar un canal concreto
.\iniciar.bat @canal

# Descargar con modo vigilancia y comentarios
.\iniciar.bat @canal --seguir --comentarios

# Varios canales en paralelo con cuentas separadas
.\iniciar.bat @canal1 @canal2 --reparto canal

# Filtrar solo videos de mas de 50MB desde 2025
.\iniciar.bat @canal -t videos --min-tamano 50MB --desde 2025-01-01

# Anadir una nueva cuenta a la coleccion
.\iniciar.bat --añadir-cuenta trabajo

# Listar canales o cuentas disponibles
.\iniciar.bat --listar
.\iniciar.bat --listar-cuentas

# Regenerar el archivo web HTML de un canal
.\iniciar.bat @canal --regenerar-html
```

---

## Opciones de la linea de comandos

| Parametro | Descripcion |
|---|---|
| `-t`, `--tipos` | Tipos a descargar: `fotos,videos,audios,documentos,stickers` |
| `--seguir` | Modo vigilancia: tras el historial, espera y descarga mensajes nuevos en vivo |
| `--comentarios` | Descargar archivos adjuntos en los comentarios de cada post |
| `--desde` / `--hasta` | Rango de fechas en formato `AAAA-MM-DD` |
| `--min-tamano` / `--max-tamano` | Filtro de tamano (ej: `10MB`, `1.5GB`) |
| `--ext` / `--excluir-ext` | Incluir o excluir extensiones (ej: `mp4,mkv,pdf`) |
| `--buscar TEXTO` | Descargar unicamente mensajes cuyo texto o nombre coincida |
| `--cuentas a,b` | Nombres de las cuentas a usar (por defecto todas las anadidas) |
| `--reparto canal\|mensajes` | Estrategia de reparto entre cuentas |
| `-n`, `--hilos` | Descargas simultaneas por cuenta (por defecto 3) |
| `-o`, `--salida` | Carpeta de descarga personalizada |
| `--limite-velocidad 5MB` | Limite de ancho de banda maximo por segundo |
| `--espacio-minimo 2GB` | Detiene las descargas si el disco baja de este espacio libre |
| `--sin-deduplicar` | Descarga aunque el mismo archivo de Telegram ya se haya bajado en otro canal |
| `--sin-albumes` | Guarda todas las fotos juntas sin subcarpetas de album |
| `--sin-html` | No genera el archivo interactivo `index.html` |
| `--sin-notificar` | No envia mensaje de aviso a Telegram al finalizar |
| `--conexiones 4` | Trozos que se piden a la vez de cada archivo grande (1-8) |
| `--takeout` | Modo exportacion de Telegram (menos esperas en historiales enormes) |
| `--exportar csv\|json` | Solo exporta a CSV/JSON los mensajes ya descargados de los canales indicados |

---

## Estructura de carpetas generada

```
descargas/
└── <Nombre_Del_Canal> [<id>]/   # el id evita mezclar canales con el mismo nombre
    ├── fotos/                  # Fotos sueltas
    ├── videos/                 # Videos y clips
    ├── audios/                 # Mensajes de voz y pistas de audio
    ├── documentos/             # Archivos, PDFs, ejecutables, etc.
    ├── stickers/               # Stickers animados y estaticos
    ├── albumes/<fecha>_<id>/   # Fotos y videos agrupados por album
    ├── temas/<Nombre_Tema>/    # Contenido clasificado por tema de foro
    ├── comentarios/<post_id>/  # Respuestas y debates
    └── index.html              # Archivo navegable sin conexion estilo Vista

sesiones/
└── <nombre>.session            # Sesiones de Telegram SIN cifrar (dan acceso total a la cuenta)

datos.db                        # Base de datos local de control y reanudacion
```

---

## Privacidad y seguridad

- Las sesiones de Telegram (`sesiones/*.session`) y las credenciales del archivo `.env` contienen tus claves de acceso privadas. **Nunca las subas a repositorios publicos ni las compartas**.
- Por defecto los archivos `.session` no estan cifrados: cualquiera que copie la carpeta `sesiones/` puede usar tu cuenta sin pedir codigo. Para protegerlos pon `CIFRAR_SESIONES=si` en el `.env`: al arrancar se pide una contrasena, las sesiones existentes se convierten a `.session.enc` (cifradas con AES-256 y una clave derivada con scrypt) y las originales se borran. Si olvidas la contrasena, borra los `.session.enc` y vuelve a iniciar sesion en cada cuenta.
- Si sospechas que alguien ha copiado una sesion, cierrala desde Telegram (Ajustes > Dispositivos).
- El panel solo escucha en `127.0.0.1` y acepta peticiones que vengan de su propia pagina: cada arranque genera un token secreto, y se rechazan otros origenes y otros nombres de host. Asi otra web abierta en el navegador no puede lanzar descargas ni leer tus datos. Si recargas el panel tras reiniciarlo, el token se renueva solo.
- Los archivos descargados se abren desde el panel aislados (`sandbox`): un `.html` o `.svg` de un canal se entrega como descarga y no puede usar el panel.
- El archivo `.gitignore` incluido ya viene preconfigurado para ignorar `.env`, la carpeta `sesiones/`, `descargas/` y `datos.db`.
- En Telegram > Ajustes > Dispositivos cada sesion aparece con el nombre de la app que creaste en my.telegram.org y el modelo "PC". Puedes cambiar el modelo, el sistema y la version con `NOMBRE_DISPOSITIVO`, `SISTEMA_DISPOSITIVO` y `VERSION_APP` en el `.env` (ver `.env.ejemplo`).
- Utiliza la herramienta respetando los terminos de servicio de Telegram y para contenido al que tengas derecho legitimo de acceso.

---

## Version .exe (sin instalar Python)

Ejecuta `construir_exe.bat`: crea `dist\telegram-looker-panel.exe` y `dist\telegram-looker-consola.exe`. Copialos a una carpeta con tu `.env`; las sesiones, `datos.db` y las descargas se guardan junto al `.exe`.
Tambien puedes descargarlos ya hechos desde GitHub: pestana *Actions* > *Ejecutables Windows* > *Run workflow*, y al terminar el artefacto `telegram-looker-windows`.

---

## Desarrollo

```bash
pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest -q
```

GitHub Actions ejecuta lo mismo en Windows y Linux en cada push (`.github/workflows/ci.yml`).
`cryptg` es opcional y no esta en `requirements.txt`: `_preparar.bat` intenta instalarlo aparte y, si no hay version para tu Python, sigue sin el.
