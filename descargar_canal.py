#!/usr/bin/env python3
"""
TG Downloader (consola): descarga automáticamente todo el contenido de canales/grupos de Telegram.

Ejemplos:
    python descargar_canal.py                         menú interactivo
    python descargar_canal.py @canal                  descarga un canal
    python descargar_canal.py @canal --seguir         y luego sigue bajando lo nuevo
    python descargar_canal.py --añadir-cuenta trabajo añade otra cuenta
    python descargar_canal.py @canal --reparto mensajes   varias cuentas se reparten un canal
Para la interfaz gráfica usa panel.bat (o python panel.py).
"""
import argparse
import asyncio
import re
import sys

# La consola de Windows usa cp1252 por defecto y falla con emojis/acentos.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

try:
    from tgdl.bd import BD
    from tgdl.config import RUTA_BD, SALIDA_POR_DEFECTO, cargar_config, obtener_credenciales
    from tgdl.cuentas import GestorCuentas, validar_nombre
    from tgdl.html_export import generar_html
    from tgdl.informes import InformeConsola
    from tgdl.motor import Opciones, ejecutar, listar_dialogos, resolver
    from tgdl.utilidades import TIPOS
except ImportError as e:
    print(f"Faltan dependencias ({e}). Ejecuta:  pip install -r requirements.txt")
    sys.exit(1)


def parsear_args(cfg: dict):
    p = argparse.ArgumentParser(
        description="Descarga automáticamente todo el contenido de canales de Telegram.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("canales", nargs="*", help="@usuario, enlace t.me, enlace de invitación o ID numérico.")

    g = p.add_argument_group("cuentas")
    g.add_argument("--cuentas", default=cfg.get("CUENTAS", ""), help="Cuentas a usar separadas por comas (por defecto todas).")
    g.add_argument("--añadir-cuenta", "--anadir-cuenta", dest="anadir_cuenta", metavar="NOMBRE", help="Inicia sesión con una cuenta nueva.")
    g.add_argument("--eliminar-cuenta", metavar="NOMBRE", help="Cierra la sesión y borra una cuenta.")
    g.add_argument("--listar-cuentas", action="store_true", help="Muestra las cuentas guardadas.")
    g.add_argument("--reparto", choices=("canal", "mensajes"), default=cfg.get("REPARTO", "canal"),
                   help="canal: cada cuenta baja canales distintos. mensajes: todas las cuentas se reparten cada canal.")

    g = p.add_argument_group("descarga")
    g.add_argument("-o", "--salida", default=cfg.get("CARPETA_DESTINO", str(SALIDA_POR_DEFECTO)), help="Carpeta de destino.")
    g.add_argument("-n", "--hilos", type=int, default=int(cfg.get("HILOS", 3)), help="Descargas simultáneas por cuenta (def. 3).")
    g.add_argument("--seguir", action="store_true", help="Tras el historial, sigue descargando los mensajes nuevos al instante.")
    g.add_argument("--comentarios", action="store_true", help="Descarga también los comentarios de las publicaciones.")
    g.add_argument("--nombres", choices=("original", "texto"), default="original",
                   help="Nombre de archivo: original o basado en el texto del mensaje.")
    g.add_argument("--sin-albumes", action="store_true", help="No agrupar álbumes en carpetas propias.")
    g.add_argument("--sin-deduplicar", action="store_true", help="Descargar aunque el archivo ya exista en otro canal.")
    g.add_argument("--sin-html", action="store_true", help="No generar el archivo HTML navegable.")
    g.add_argument("--sin-notificar", action="store_true", help="No enviar aviso a Mensajes guardados al terminar.")
    g.add_argument("--limite-velocidad", default="", metavar="TAM", help="Velocidad máxima total, p. ej. 5MB (por segundo).")
    g.add_argument("--espacio-minimo", default="1GB", metavar="TAM", help="Se detiene si quedan menos de esto libres (def. 1GB).")

    g = p.add_argument_group("filtros")
    g.add_argument("-t", "--tipos", default=",".join(TIPOS), help=f"Tipos: {','.join(TIPOS)} (def. todos).")
    g.add_argument("--desde", metavar="AAAA-MM-DD", help="Solo mensajes desde esta fecha.")
    g.add_argument("--hasta", metavar="AAAA-MM-DD", help="Solo mensajes hasta esta fecha.")
    g.add_argument("--min-tamano", metavar="TAM", help="Tamaño mínimo, p. ej. 10MB.")
    g.add_argument("--max-tamano", metavar="TAM", help="Tamaño máximo, p. ej. 2GB.")
    g.add_argument("--ext", metavar="LISTA", help="Solo estas extensiones, p. ej. mp4,mkv,pdf.")
    g.add_argument("--excluir-ext", metavar="LISTA", help="Excluir estas extensiones.")
    g.add_argument("--buscar", metavar="TEXTO", help="Solo archivos cuyo texto o nombre contenga esto.")

    g = p.add_argument_group("otros")
    g.add_argument("-l", "--listar", action="store_true", help="Lista tus canales/grupos y sale.")
    g.add_argument("--regenerar-html", action="store_true", help="Solo regenera el HTML de los canales indicados.")
    return p.parse_args()


def seleccion_multiple(texto: str, maximo: int) -> list:
    """'1,3,5-7' -> [1,3,5,6,7]"""
    numeros = []
    for parte in texto.replace(" ", "").split(","):
        if re.fullmatch(r"\d+-\d+", parte):
            a, b = map(int, parte.split("-"))
            numeros += list(range(a, b + 1))
        elif parte.isdigit():
            numeros.append(int(parte))
        else:
            return []
    return [n for n in numeros if 1 <= n <= maximo]


async def elegir_canales(cliente) -> list:
    print("\nCargando tus canales y grupos...\n")
    dialogos = await listar_dialogos(cliente)
    for i, d in enumerate(dialogos, 1):
        print(f"{i:4}. [{'Grupo' if d.is_group else 'Canal'}] {d.name}   (id: {d.id})")
    print("\nPuedes elegir varios: 1,3,5-8. También vale @usuario, un enlace o un ID.")
    while True:
        sel = input("Canal(es) a descargar: ").strip()
        numeros = seleccion_multiple(sel, len(dialogos))
        if numeros:
            return [dialogos[n - 1].id for n in numeros]
        if sel:
            return [sel]


async def main():
    cfg = cargar_config()
    args = parsear_args(cfg)
    api_id, api_hash = obtener_credenciales()
    gestor = GestorCuentas(api_id, api_hash)
    try:
        # --- gestión de cuentas ---
        if args.anadir_cuenta:
            nombre = validar_nombre(args.anadir_cuenta)
            print(f"Iniciando sesión para la cuenta '{nombre}'...")
            await gestor.login_interactivo(nombre)
            info = await gestor.info(nombre)
            print(f"✅ Cuenta '{nombre}' añadida: {info['nombre_mostrado']} (@{info['usuario'] or '-'})")
            return
        if args.eliminar_cuenta:
            await gestor.eliminar(args.eliminar_cuenta)
            print(f"🗑  Cuenta '{args.eliminar_cuenta}' eliminada.")
            return
        if not gestor.nombres():
            print("No hay ninguna cuenta configurada. Vamos a iniciar sesión.")
            nombre = validar_nombre(input("Nombre para esta cuenta [principal]: ").strip() or "principal")
            await gestor.login_interactivo(nombre)

        seleccion = [c.strip() for c in args.cuentas.split(",") if c.strip()] or gestor.nombres()
        clientes = {}
        for nombre in seleccion:
            if await gestor.conectar(nombre) is None:
                print(f"⚠️  La cuenta '{nombre}' no tiene sesión válida. Usa:  --añadir-cuenta {nombre}")
                continue
            clientes[nombre] = gestor.clientes[nombre]
            info = await gestor.info(nombre)
            print(f"🔑 [{nombre}] {info['nombre_mostrado']} (@{info['usuario'] or '-'})")
        if args.listar_cuentas:
            return
        if not clientes:
            sys.exit("No hay ninguna cuenta conectada.")
        principal = next(iter(clientes.values()))

        if args.listar:
            for d in await listar_dialogos(principal):
                print(f"[{'Grupo' if d.is_group else 'Canal'}] {d.name}   (id: {d.id})")
            return

        objetivos = args.canales or ([cfg["CANAL"]] if cfg.get("CANAL") else []) or await elegir_canales(principal)

        if args.regenerar_html:
            bd = BD(RUTA_BD)
            for obj in objetivos:
                from telethon import utils
                ent = await resolver(principal, obj)
                print(f"🌐 {generar_html(bd, utils.get_peer_id(ent))}")
            return

        opc = Opciones.desde_dict({
            "salida": args.salida, "hilos": args.hilos, "tipos": args.tipos, "reparto": args.reparto,
            "desde": args.desde, "hasta": args.hasta, "min_tamano": args.min_tamano, "max_tamano": args.max_tamano,
            "extensiones": args.ext, "excluir_extensiones": args.excluir_ext, "buscar": args.buscar,
            "albumes": not args.sin_albumes, "nombres": args.nombres, "comentarios": args.comentarios,
            "seguir": args.seguir, "html": not args.sin_html, "deduplicar": not args.sin_deduplicar,
            "notificar": not args.sin_notificar, "limite_velocidad": args.limite_velocidad,
            "espacio_minimo": args.espacio_minimo,
        })
        if len(clientes) > 1:
            modo = "repartiéndose los mensajes" if opc.reparto == "mensajes" else "un canal por cuenta"
            print(f"👥 Usando {len(clientes)} cuentas ({modo}).")
        print()
        await ejecutar(clientes, objetivos, opc, InformeConsola())
    finally:
        await gestor.cerrar()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏸  Interrumpido. El progreso está guardado: vuelve a ejecutarlo para continuar.")
    except ValueError as e:
        print(f"\n❌ {e}")
        sys.exit(1)
