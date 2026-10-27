"""Genera un archivo HTML navegable (sin conexión) de cada canal descargado."""
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from .utilidades import tamano_legible


def _url(ruta, carpeta: Path):
    if not ruta:
        return None
    try:
        rel = os.path.relpath(ruta, carpeta)
    except ValueError:  # otra unidad de disco
        return Path(ruta).as_uri()
    return quote(rel.replace(os.sep, "/"))


def generar_html(bd, canal_id: int) -> Path:
    canal = bd.canal(canal_id)
    if canal is None:
        raise ValueError("Ese canal no está en la base de datos")
    carpeta = Path(canal["carpeta"])
    carpeta.mkdir(parents=True, exist_ok=True)
    mensajes = []
    for f in bd.mensajes_de(canal_id):
        mensajes.append({
            "i": f["msg_id"], "f": f["fecha"], "t": f["texto"] or "", "ty": f["tipo"] or "texto",
            "u": _url(f["ruta"], carpeta), "n": Path(f["ruta"]).name if f["ruta"] else None,
            "s": f["tamano"] or 0, "a": f["album"], "tm": f["tema"], "p": f["post_id"], "e": f["estado"],
        })
    res = bd.resumen(canal_id)
    datos = {
        "titulo": canal["titulo"], "generado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tamano": tamano_legible(res["bytes"]), "archivos": res["archivos"], "mensajes": mensajes,
    }
    json_datos = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    html = _PLANTILLA.replace("__TITULO__", _escapar(canal["titulo"])).replace("__DATOS__", json_datos)
    ruta = carpeta / "index.html"
    ruta.write_text(html, encoding="utf-8")
    return ruta


def _escapar(texto: str) -> str:
    return (texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# Plantilla autocontenida con estilo Windows Vista (Aero): no depende de ningún
# archivo externo para que funcione igual abierta con doble clic o desde el panel.
_PLANTILLA = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITULO__ · Archivo de Telegram</title>
<meta name="description" content="Copia local navegable del canal de Telegram __TITULO__">
<style>
:root{--azul:#1e3287;--borde:#d5dfe9;--sel-a:#dcebfc;--sel-b:#c1dcfc;--sel-borde:#7da2ce;
--hov-a:#f5faff;--hov-b:#e5f1fd;--hov-borde:#b8d6fb;--gris:#5a6573}
*{box-sizing:border-box}
html{background:#0a2f4f}
body{margin:0;min-height:100vh;padding:18px 16px 40px;font:13px/1.5 "Segoe UI",Tahoma,Verdana,sans-serif;color:#1c1c1c;
background:radial-gradient(1100px 520px at 88% 12%,rgba(120,255,205,.38),transparent 60%),
radial-gradient(900px 620px at 6% 92%,rgba(40,170,255,.38),transparent 60%),
radial-gradient(700px 300px at 50% 55%,rgba(150,255,230,.12),transparent 70%),
linear-gradient(160deg,#08243f 0%,#0c5068 42%,#13786a 68%,#0a2c4c 100%);background-attachment:fixed}
::-webkit-scrollbar{width:17px;height:17px}
::-webkit-scrollbar-track{background:linear-gradient(90deg,#e8e8e8,#f6f6f6)}
::-webkit-scrollbar-thumb{border:1px solid #9a9a9a;border-radius:3px;background:linear-gradient(90deg,#f3f3f3,#dcdcdc);box-shadow:inset 0 0 0 1px #fff}
::-webkit-scrollbar-thumb:hover{border-color:#3c7fb1;background:linear-gradient(90deg,#e3f4fc,#a9dbf6)}

/* ---- ventana Aero ---- */
.ventana{max-width:960px;margin:0 auto;padding:0 7px 7px;border-radius:9px 9px 6px 6px;border:1px solid rgba(0,0,0,.6);
background:linear-gradient(rgba(215,235,250,.62),rgba(160,200,228,.5) 70px,rgba(150,190,222,.55));
box-shadow:inset 0 0 0 1px rgba(255,255,255,.55),0 12px 44px rgba(0,0,0,.55);backdrop-filter:blur(12px)}
header.top{position:sticky;top:0;z-index:20;margin:0 -7px;padding:0 7px;border-radius:9px 9px 0 0;
background:linear-gradient(rgba(205,228,247,.88),rgba(165,203,230,.86));backdrop-filter:blur(14px)}
.barra-titulo{display:flex;align-items:center;gap:8px;height:31px;padding:0 4px;font-size:13px;color:#000;
text-shadow:0 0 9px #fff,0 0 5px #fff,0 0 2px #fff;white-space:nowrap;overflow:hidden}
.barra-titulo span:last-child{overflow:hidden;text-overflow:ellipsis}
.orbe{width:17px;height:17px;border-radius:50%;flex:none;display:grid;place-items:center;font-size:10px;color:#fff;
background:radial-gradient(circle at 50% 30%,#d6efff,#3a96e8 50%,#1257a8 56%,#2c7fd6);border:1px solid #0e4486;
box-shadow:inset 0 1px 0 rgba(255,255,255,.7)}
.direccion{display:flex;gap:8px;align-items:center;padding:0 0 6px}
.ruta{flex:1;min-width:0;display:flex;align-items:center;gap:6px;height:26px;padding:0 8px;background:#fff;
border:1px solid #6f8bab;border-radius:2px;box-shadow:inset 0 1px 2px rgba(0,0,0,.12);white-space:nowrap;overflow:hidden}
.ruta .sep{color:#6a7a8c;font-size:11px}
.ruta b{font-weight:400;overflow:hidden;text-overflow:ellipsis}
.buscar{width:250px;height:26px;padding:2px 28px 2px 8px;border:1px solid #6f8bab;border-radius:2px;outline:none;font:inherit;
background:#fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14'%3E%3Ccircle cx='5.5' cy='5.5' r='4.2' fill='none' stroke='%23365a85' stroke-width='1.6'/%3E%3Cpath d='M8.6 8.6l4 4' stroke='%23365a85' stroke-width='2.2' stroke-linecap='round'/%3E%3C/svg%3E") no-repeat right 8px center;
box-shadow:inset 0 1px 2px rgba(0,0,0,.12);transition:border-color .15s,box-shadow .15s}
.buscar::placeholder{color:#7b7b7b;font-style:italic}
.buscar:focus{border-color:#3c7fb1;box-shadow:inset 0 1px 2px rgba(0,0,0,.12),0 0 0 1px #a7d9f5}
.buscar::-webkit-search-cancel-button{cursor:default}

/* ---- barra de comandos ---- */
.filtros{display:flex;flex-wrap:wrap;gap:2px;align-items:center;min-height:34px;padding:3px 8px;border:1px solid #1d3a5c;border-bottom:0;
background:linear-gradient(#5d84ad,#3a6390 48%,#28507d 50%,#2f5a88);box-shadow:inset 0 1px 0 rgba(255,255,255,.35)}
.chip{height:26px;padding:0 10px;border:1px solid transparent;border-radius:3px;background:transparent;color:#fff;cursor:default;
font:13px "Segoe UI",Tahoma,sans-serif;text-shadow:0 1px 1px rgba(0,0,0,.45);transition:background .15s,border-color .15s}
.chip:hover{border-color:rgba(10,30,60,.7);background:linear-gradient(rgba(255,255,255,.35),rgba(255,255,255,.12) 50%,rgba(255,255,255,.04) 51%,rgba(255,255,255,.2));
box-shadow:inset 0 0 0 1px rgba(255,255,255,.4)}
.chip.on{border-color:rgba(5,20,45,.85);background:linear-gradient(rgba(0,20,50,.45),rgba(0,30,70,.25));box-shadow:inset 0 1px 3px rgba(0,0,0,.5)}
select.chip{appearance:none;-webkit-appearance:none;padding-right:22px;
background:transparent url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0h8L4 5z' fill='%23fff'/%3E%3C/svg%3E") no-repeat right 8px center}
select.chip option{color:#000;background:#fff;text-shadow:none}

/* ---- contenido ---- */
.contenido{background:#fff;border:1px solid #6f8bab;border-top-color:#1d3a5c;min-height:60vh}
.detalles{display:flex;align-items:center;gap:14px;padding:14px 20px;border-bottom:1px solid #d9e3ee;
background:linear-gradient(#ffffff,#eef4fa)}
.avatar{width:56px;height:56px;flex:none;border-radius:5px;display:grid;place-items:center;font:600 24px "Segoe UI",sans-serif;color:#fff;
text-shadow:0 1px 2px rgba(0,0,0,.4);background:linear-gradient(#5fb3ee,#2a78c8 50%,#1d63b0 51%,#3b8ad8);
border:1px solid #1b4f8f;box-shadow:inset 0 1px 0 rgba(255,255,255,.55),0 2px 5px rgba(0,0,0,.25)}
h1{margin:0;font:400 19px "Segoe UI",sans-serif;color:var(--azul)}
.meta{color:var(--gris);font-size:12px;margin-top:2px}
main{padding:6px 20px 30px}
.dia{display:flex;align-items:center;gap:10px;margin:20px 0 10px;color:var(--azul);font-size:13px}
.dia::first-letter{text-transform:uppercase}
.dia::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,#a9c3df,rgba(169,195,223,0))}
.card{padding:10px 12px;margin:0 0 10px;border:1px solid var(--borde);border-radius:3px;background:#fff;animation:entra .3s ease both;
transition:background .15s,border-color .15s}
.card:hover{border-color:var(--hov-borde);background:linear-gradient(var(--hov-a),var(--hov-b) 140px,#fff 141px)}
@keyframes entra{from{opacity:0}to{opacity:1}}
.card .info{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:12px;color:var(--gris);margin-bottom:7px}
.card .info span:first-child{color:#8794a3}
.tema{padding:0 7px;border:1px solid #a7c7ea;border-radius:2px;color:#1d3f7a;background:linear-gradient(#f4f9ff,#dcebfc)}
.texto{white-space:pre-wrap;word-wrap:break-word;font-size:14px;line-height:1.55}
.texto a,.doc a{color:#0066cc;text-decoration:none}.texto a:hover,.doc a:hover{text-decoration:underline}
.media{display:grid;gap:6px;margin-bottom:9px}
.media.n2{grid-template-columns:1fr 1fr}.media.n3,.media.n4,.media.nmas{grid-template-columns:repeat(3,1fr)}
.media.n4{grid-template-columns:1fr 1fr}
.media img,.media video{width:100%;max-height:520px;object-fit:cover;display:block;background:#000;cursor:zoom-in;
padding:3px;background:#fff;border:1px solid #c9d2dc;box-shadow:0 1px 3px rgba(0,0,0,.18);transition:border-color .15s,box-shadow .15s}
.media img:hover{border-color:#7da2ce;box-shadow:0 2px 8px rgba(30,80,140,.35)}
.media video{background:#000;cursor:auto}
.media.n1 img,.media.n1 video{object-fit:contain;max-height:620px;width:auto;max-width:100%}
.media audio{width:100%;margin-top:4px}
.doc{display:flex;align-items:center;gap:12px;padding:8px 10px;border:1px solid var(--borde);border-radius:3px;
background:linear-gradient(#fdfeff,#eef3f8);transition:border-color .15s,background .15s}
.doc:hover{border-color:var(--hov-borde);background:linear-gradient(var(--hov-a),var(--hov-b))}
.doc .ic{width:38px;height:38px;flex:none;display:grid;place-items:center;font-size:27px;filter:drop-shadow(0 1px 1px rgba(0,0,0,.25))}
.doc .nm{word-break:break-all}.doc .sz{color:var(--gris);font-size:12px}
.doc.falta{color:#5c3b00;border-color:#e4c366;background:linear-gradient(#fffbe3,#fff1b8)}
details.com{margin-top:9px;padding-top:7px;border-top:1px solid #e6ebf0}
details.com summary{display:inline-flex;align-items:center;gap:7px;color:var(--azul);font-size:13px;list-style:none;cursor:default;user-select:none}
details.com summary::-webkit-details-marker{display:none}
details.com summary::before{content:"\2304";width:17px;height:17px;display:inline-grid;place-items:center;border-radius:50%;font-size:11px;line-height:1;
color:#3a5a80;border:1px solid #9aabbf;background:linear-gradient(#fff,#e1e8ef);transition:transform .2s}
details.com summary:hover::before{border-color:#3c7fb1;background:linear-gradient(#eaf6fd,#a7d9f5)}
details.com[open]>summary::before{transform:rotate(180deg)}
details.com .card{margin:9px 0 0 22px;padding:8px 10px;background:#fafcfe}
#vacio{display:none;text-align:center;color:var(--gris);padding:60px 0 40px;font-size:14px}
#vacio::before{content:"\1F50D";display:block;font-size:42px;margin-bottom:6px;opacity:.75}
#centinela{height:40px}
.barra-estado{display:flex;gap:14px;align-items:center;height:24px;padding:0 10px;font-size:12px;color:#333;
border:1px solid #6f8bab;border-top:0;background:linear-gradient(#f4f7fb,#dfe7f0)}

/* ---- visor de fotos (estilo Galería fotográfica) ---- */
#lb{position:fixed;inset:0;z-index:50;display:none;place-items:center;cursor:zoom-out;animation:entra .2s;
background:radial-gradient(circle at 50% 40%,rgba(40,60,85,.97),rgba(8,14,24,.98))}
#lb img{max-width:92vw;max-height:88vh;border:4px solid #fff;box-shadow:0 10px 50px rgba(0,0,0,.7)}
#lb::after{content:"Haz clic o pulsa Esc para cerrar";position:fixed;bottom:16px;left:50%;transform:translateX(-50%);
color:#cfe0f2;font-size:12px;padding:4px 14px;border-radius:12px;border:1px solid rgba(255,255,255,.18);
background:linear-gradient(rgba(255,255,255,.14),rgba(255,255,255,.04))}

/* ---- botón volver arriba (orbe Aero) ---- */
#arriba{position:fixed;right:22px;bottom:22px;width:42px;height:42px;border-radius:50%;cursor:default;color:#fff;font-size:19px;
text-shadow:0 1px 2px rgba(0,0,0,.5);border:1px solid #0d3f80;
background:radial-gradient(circle at 50% 28%,#d8efff,#46a0ee 48%,#1458a9 54%,#2b80d8);
box-shadow:inset 0 1px 0 rgba(255,255,255,.7),0 3px 10px rgba(0,0,0,.45);
opacity:0;pointer-events:none;transition:opacity .3s,filter .2s}
#arriba.ver{opacity:1;pointer-events:auto}
#arriba:hover{filter:brightness(1.15) saturate(1.1)}
#arriba:active{filter:brightness(.92)}

@media (max-width:640px){
body{padding:0}
.ventana{border-radius:0;padding:0 3px 3px}
header.top{margin:0 -3px;padding:0 3px;border-radius:0}
.direccion{flex-wrap:wrap}.buscar{width:100%}
main{padding:4px 10px 24px}.detalles{padding:12px}
.media.n3,.media.nmas{grid-template-columns:1fr 1fr}
}
</style>
</head>
<body>
<div class="ventana">
  <header class="top">
    <div class="barra-titulo"><span class="orbe">⬇</span><span>__TITULO__ - Archivo de Telegram</span></div>
    <div class="direccion">
      <div class="ruta"><span>🗂️</span><span>Archivo de Telegram</span><span class="sep">▸</span><b>__TITULO__</b></div>
      <input class="buscar" id="q" type="search" placeholder="Buscar" aria-label="Buscar en textos y nombres de archivo" title="Buscar en textos y nombres de archivo">
    </div>
    <div class="filtros" id="filtros"></div>
  </header>
  <div class="contenido">
    <div class="detalles"><div class="avatar" id="av"></div><div><h1 id="titulo"></h1><div class="meta" id="meta"></div></div></div>
    <main id="lista"></main>
    <div id="vacio">No hay mensajes que coincidan con la búsqueda.</div><div id="centinela"></div>
  </div>
  <div class="barra-estado"><span id="estado-n"></span></div>
</div>
<div id="lb"><img alt=""></div>
<button id="arriba" title="Volver arriba" aria-label="Volver arriba">▲</button>
<script>
const D = __DATOS__;
const $ = s => document.querySelector(s);
const TIPOS = [["todo","Todo"],["fotos","📷 Fotos"],["videos","🎬 Vídeos"],["audios","🎵 Audios"],["documentos","📄 Documentos"],["texto","💬 Texto"]];
const ICONO = {pdf:"📕",zip:"🗜️",rar:"🗜️","7z":"🗜️",apk:"🤖",exe:"⚙️",mp3:"🎵",epub:"📚",txt:"📝",doc:"📘",docx:"📘",xls:"📗",xlsx:"📗"};
const IMG = /\.(jpe?g|png|gif|webp|bmp)$/i, VID = /\.(mp4|webm|mov|mkv|m4v)$/i;
const fmt = n => { const u=["B","KB","MB","GB","TB"]; let i=0; while(n>=1024&&i<4){n/=1024;i++} return n.toFixed(1)+" "+u[i]; };
const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const enl = s => esc(s).replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');

$("#titulo").textContent = D.titulo; $("#av").textContent = (D.titulo||"?").trim()[0].toUpperCase();
document.title = D.titulo + " · Archivo de Telegram";

// Agrupar: publicaciones (con álbumes unidos) y comentarios por publicación
const coms = {}, posts = [];
for (const m of D.mensajes) {
  if (m.p != null) { (coms[m.p] = coms[m.p] || []).push(m); continue; }
  const ult = posts[posts.length-1];
  if (m.a && ult && ult.a === m.a) { ult.items.push(m); ult.ids.push(m.i); if (m.t) ult.t = ult.t || m.t; }
  else posts.push({a:m.a, f:m.f, t:m.t, tm:m.tm, i:m.i, ids:[m.i], items:[m]});
}
for (const p of posts) {
  p.c = p.ids.flatMap(i => coms[i] || []);
  p.tipos = new Set(p.items.map(m => m.ty));
  p.busq = (p.t + " " + p.items.map(m => m.n||"").join(" ") + " " + p.c.map(c => c.t).join(" ")).toLowerCase();
}
const fechas = posts.map(p => p.f).filter(Boolean);
$("#meta").textContent = `${posts.length} publicaciones · ${D.archivos} archivos · ${D.tamano}` +
  (fechas.length ? ` · ${new Date(fechas[0]).toLocaleDateString()} – ${new Date(fechas[fechas.length-1]).toLocaleDateString()}` : "") +
  ` · generado ${D.generado}`;

// Filtros
const estado = {tipo:"todo", q:"", tema:"", orden:"asc"};
const filtros = $("#filtros");
for (const [k, v] of TIPOS) {
  const b = document.createElement("button"); b.className = "chip" + (k==="todo"?" on":""); b.textContent = v; b.dataset.k = k;
  b.onclick = () => { estado.tipo = k; filtros.querySelectorAll("button[data-k]").forEach(x => x.classList.toggle("on", x===b)); aplicar(); };
  filtros.appendChild(b);
}
const temas = [...new Set(posts.map(p => p.tm).filter(Boolean))];
if (temas.length) {
  const s = document.createElement("select"); s.className = "chip"; s.innerHTML = `<option value="">🗂 Todos los temas</option>` + temas.map(t => `<option>${esc(t)}</option>`).join("");
  s.onchange = () => { estado.tema = s.value; aplicar(); }; filtros.appendChild(s);
}
const ord = document.createElement("button"); ord.className = "chip"; ord.textContent = "⇅ Más antiguos primero"; ord.style.marginLeft = "auto";
ord.onclick = () => { estado.orden = estado.orden==="asc"?"desc":"asc"; ord.textContent = estado.orden==="asc"?"⇅ Más antiguos primero":"⇅ Más recientes primero"; aplicar(); };
filtros.appendChild(ord);
let t0; $("#q").oninput = e => { clearTimeout(t0); t0 = setTimeout(() => { estado.q = e.target.value.trim().toLowerCase(); aplicar(); }, 200); };

// Render
function medio(m) {
  if (m.e === "fallo" || !m.u) return `<div class="doc falta"><div class="ic">⚠️</div><div><div class="nm">Archivo no descargado</div><div class="sz">mensaje ${m.i}</div></div></div>`;
  const n = m.n || "";
  if (m.ty === "fotos" || (IMG.test(n) && m.ty !== "videos")) return `<img loading="lazy" src="${m.u}" alt="">`;
  if (m.ty === "videos" || (m.ty === "stickers" && VID.test(n))) return `<video controls preload="metadata" src="${m.u}"${m.ty==="stickers"?" autoplay loop muted":""}></video>`;
  if (m.ty === "audios") return `<div class="doc"><div class="ic">🎵</div><div style="flex:1"><div class="nm">${esc(n)}</div><audio controls preload="none" src="${m.u}"></audio></div></div>`;
  const ext = (n.split(".").pop()||"").toLowerCase();
  return `<div class="doc"><div class="ic">${ICONO[ext]||"📄"}</div><div><div class="nm"><a href="${m.u}" target="_blank">${esc(n)}</a></div><div class="sz">${fmt(m.s)}</div></div></div>`;
}
function tarjeta(p, esCom) {
  const vis = p.items.filter(m => m.ty !== "texto");
  const inline = vis.filter(m => m.ty==="fotos"||m.ty==="videos"||(m.ty==="stickers"));
  const otros = vis.filter(m => !inline.includes(m));
  const n = inline.length, cls = n>4?"nmas":"n"+n;
  const fecha = p.f ? new Date(p.f) : null;
  let h = `<article class="card"><div class="info"><span>#${p.i}</span>${fecha?`<time>${fecha.toLocaleString()}</time>`:""}${p.tm?`<span class="tema">${esc(p.tm)}</span>`:""}</div>`;
  if (n) h += `<div class="media ${cls}">${inline.map(medio).join("")}</div>`;
  if (otros.length) h += `<div class="media">${otros.map(medio).join("")}</div>`;
  if (p.t) h += `<div class="texto">${enl(p.t)}</div>`;
  if (!esCom && p.c && p.c.length) {
    h += `<details class="com"><summary>💬 ${p.c.length} comentario${p.c.length>1?"s":""}</summary>` +
      p.c.map(c => tarjeta({f:c.f,t:c.t,i:c.i,items:[c]}, true)).join("") + `</details>`;
  }
  return h + `</article>`;
}
let filtrados = [], pos = 0, ultimoDia = "";
const lista = $("#lista");
function aplicar() {
  filtrados = posts.filter(p =>
    (estado.tipo === "todo" || p.tipos.has(estado.tipo)) &&
    (!estado.tema || p.tm === estado.tema) &&
    (!estado.q || p.busq.includes(estado.q)));
  if (estado.orden === "desc") filtrados.reverse();
  lista.innerHTML = ""; pos = 0; ultimoDia = "";
  $("#vacio").style.display = filtrados.length ? "none" : "block";
  $("#estado-n").textContent = filtrados.length === posts.length
    ? `${posts.length} elementos` : `${filtrados.length} de ${posts.length} elementos`;
  mas();
}
function mas() {
  const frag = [];
  for (const p of filtrados.slice(pos, pos + 40)) {
    const dia = p.f ? new Date(p.f).toLocaleDateString(undefined, {weekday:"long", day:"numeric", month:"long", year:"numeric"}) : "";
    if (dia && dia !== ultimoDia) { frag.push(`<div class="dia">${dia}</div>`); ultimoDia = dia; }
    frag.push(tarjeta(p));
  }
  pos += 40; lista.insertAdjacentHTML("beforeend", frag.join(""));
}
new IntersectionObserver(e => { if (e[0].isIntersecting && pos < filtrados.length) mas(); }, {rootMargin:"1200px"}).observe($("#centinela"));

// Visor de imágenes y botón arriba
const lb = $("#lb");
lista.addEventListener("click", e => { if (e.target.tagName === "IMG") { lb.querySelector("img").src = e.target.src; lb.style.display = "grid"; } });
lb.onclick = () => lb.style.display = "none";
document.addEventListener("keydown", e => { if (e.key === "Escape") lb.style.display = "none"; });
const arriba = $("#arriba");
addEventListener("scroll", () => arriba.classList.toggle("ver", scrollY > 900), {passive:true});
arriba.onclick = () => scrollTo({top:0, behavior:"smooth"});
aplicar();
</script>
</body>
</html>
"""
