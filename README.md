# 📥 TG Downloader (Telegram Media Downloader)

Descargador automático masivo para canales y grupos de Telegram (fotos, vídeos, audios, documentos y stickers). Incluye soporte para **múltiples cuentas**, **modo vigilancia en tiempo real**, **deduplicación inteligente**, **archivo HTML navegable sin conexión** y un **panel web con diseño Windows Vista (Aero)**.

---

## ✨ Características principales

- 🪟 **Panel Web estilo Windows Vista Aero:**
  - Ventana translúcida de cristal con controles completos (minimizar, maximizar, restaurar).
  - Barra de tareas integrada con botón de inicio y reloj en directo.
  - Gadget lateral con velocímetro en tiempo real.
  - Selección visual interactiva de canales, cuentas y filtros.
  - Diálogos y globos de notificación clásicos de Windows Vista.
- 👥 **Soporte multi-cuenta:**
  - Conecta tantas cuentas de Telegram como quieras.
  - Dos modos de trabajo:
    - `canal`: cada cuenta descarga canales distintos en paralelo.
    - `mensajes`: todas las cuentas colaboran repartiéndose los mensajes de un mismo canal para máxima velocidad.
- 🌐 **Archivo web HTML sin conexión:**
  - Cada canal genera un archivo interactivo `index.html` estilo explorador de Windows Vista.
  - Búsqueda instantánea en el texto de los mensajes y nombres de archivo.
  - Filtros rápidos por tipo (Fotos, Vídeos, Audios, Documentos, Texto).
  - Visor de fotos a pantalla completa estilo *Galería fotográfica de Windows*.
  - 100% autónomo (no requiere conexión a internet para ver el contenido guardado).
- ♻️ **Deduplicación inteligente (SHA-256):**
  - Si un archivo ya fue descargado previamente (incluso en otro canal), no se vuelve a descargar: se vincula automáticamente ahorrando ancho de banda y espacio en disco.
- 📁 **Organización automática:**
  - Carpetas categorizadas (`fotos/`, `videos/`, `audios/`, `documentos/`, `stickers/`).
  - Álbumes agrupados en subcarpetas propias con fecha.
  - Separación por temas en grupos con foros.
  - Descarga opcional de comentarios anidados a cada publicación.
- 👀 **Modo vigilancia continua (`--seguir`):**
  - Tras descargar todo el historial del canal, el programa se queda a la escucha y descarga al instante cualquier archivo nuevo que se publique.
- 🛡️ **Seguridad y fiabilidad:**
  - Base de datos local SQLite: si se interrumpe la descarga, continúa justo donde se quedó.
  - Gestión automática de límites de Telegram (*FloodWait*) con reintentos transparentes.
  - Límite de velocidad configurable y control de espacio libre mínimo en disco.
  - Notificación automática a tus *Mensajes guardados* de Telegram al finalizar.

---

## 🚀 Inicio rápido (Windows)

### 1. Requisitos
- Windows 10 / 11 (o Linux / macOS).
- [Python 3.10 o superior](https://www.python.org/downloads/) *(marcar la casilla "Add python.exe to PATH" durante la instalación)*.

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

3. Obtén tus claves gratuitas de la API de Telegram:
   - Entra en [https://my.telegram.org](https://my.telegram.org) e inicia sesión con tu número de teléfono.
   - Ve a **API development tools**.
   - Crea una app con cualquier nombre y copia tu **API_ID** y **API_HASH**.
   - Pégalos dentro del archivo `.env`:
     ```env
     API_ID=12345678
     API_HASH=abcdef1234567890abcdef1234567890
     ```

---

## 💻 Uso

### Opción A: Panel gráfico Web (Recomendado)

Haz doble clic en:
```
panel.bat
```
- Se instalarán automáticamente las dependencias en su propio entorno virtual si es la primera vez.
- Se abrirá tu navegador con la interfaz Vista en `http://127.0.0.1:8765`.
- **Añadir cuenta:** Haz clic en **Añadir cuenta**, introduce tu teléfono y escribe el código oficial que te enviará Telegram.
- **Descargar:** Ve a **Nueva descarga**, selecciona tu cuenta y el canal que desees de la lista y pulsa **Iniciar descarga**.

---

### Opción B: Consola / Terminal

Haz doble clic en:
```
iniciar.bat
```
*(O ejecútalo desde el terminal con parámetros)*:

```powershell
# Menú interactivo para elegir canal
.\iniciar.bat

# Descargar un canal concreto
.\iniciar.bat @canal

# Descargar con modo vigilancia y comentarios
.\iniciar.bat @canal --seguir --comentarios

# Varios canales en paralelo con cuentas separadas
.\iniciar.bat @canal1 @canal2 --reparto canal

# Filtrar solo vídeos de más de 50MB desde 2025
.\iniciar.bat @canal -t videos --min-tamano 50MB --desde 2025-01-01

# Añadir una nueva cuenta a la colección
.\iniciar.bat --añadir-cuenta trabajo

# Listar canales o cuentas disponibles
.\iniciar.bat --listar
.\iniciar.bat --listar-cuentas

# Regenerar el archivo web HTML de un canal
.\iniciar.bat @canal --regenerar-html
```

---

## ⚙️ Opciones de la línea de comandos

| Parámetro | Descripción |
|---|---|
| `-t`, `--tipos` | Tipos a descargar: `fotos,videos,audios,documentos,stickers` |
| `--seguir` | Modo vigilancia: tras el historial, espera y descarga mensajes nuevos en vivo |
| `--comentarios` | Descargar archivos adjuntos en los comentarios de cada post |
| `--desde` / `--hasta` | Rango de fechas en formato `AAAA-MM-DD` |
| `--min-tamano` / `--max-tamano` | Filtro de tamaño (ej: `10MB`, `1.5GB`) |
| `--ext` / `--excluir-ext` | Incluir o excluir extensiones (ej: `mp4,mkv,pdf`) |
| `--buscar TEXTO` | Descargar únicamente mensajes cuyo texto o nombre coincida |
| `--cuentas a,b` | Nombres de las cuentas a usar (por defecto todas las añadidas) |
| `--reparto canal\|mensajes` | Estrategia de reparto entre cuentas |
| `-n`, `--hilos` | Descargas simultáneas por cuenta (por defecto 3) |
| `-o`, `--salida` | Carpeta de descarga personalizada |
| `--limite-velocidad 5MB` | Límite de ancho de banda máximo por segundo |
| `--espacio-minimo 2GB` | Detiene las descargas si el disco baja de este espacio libre |
| `--sin-deduplicar` | Desactiva el cálculo de hashes SHA-256 para omitir duplicados |
| `--sin-albumes` | Guarda todas las fotos juntas sin subcarpetas de álbum |
| `--sin-html` | No genera el archivo interactivo `index.html` |
| `--sin-notificar` | No envía mensaje de aviso a Telegram al finalizar |

---

## 📂 Estructura de carpetas generada

```
descargas/
└── <Nombre_Del_Canal>/
    ├── fotos/                  # Fotos sueltas
    ├── videos/                 # Vídeos y clips
    ├── audios/                 # Mensajes de voz y pistas de audio
    ├── documentos/             # Archivos, PDFs, ejecutables, etc.
    ├── stickers/               # Stickers animados y estáticos
    ├── albumes/<fecha>_<id>/   # Fotos y vídeos agrupados por álbum
    ├── temas/<Nombre_Tema>/    # Contenido clasificado por tema de foro
    ├── comentarios/<post_id>/  # Respuestas y debates
    └── index.html              # Archivo navegable sin conexión estilo Vista

sesiones/
└── <nombre>.session            # Sesiones cifradas de Telegram (¡nunca las compartas!)

datos.db                        # Base de datos local de control y reanudación
```

---

## 🔒 Privacidad y seguridad

- Las sesiones de Telegram (`sesiones/*.session`) y las credenciales del archivo `.env` contienen tus claves de acceso privadas. **Nunca las subas a repositorios públicos ni las compartas**.
- El archivo `.gitignore` incluido ya viene preconfigurado para ignorar `.env`, la carpeta `sesiones/`, `descargas/` y `datos.db`.
- Utiliza la herramienta respetando los términos de servicio de Telegram y para contenido al que tengas derecho legítimo de acceso.
