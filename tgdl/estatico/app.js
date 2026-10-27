"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const TIPOS = [["fotos", "📷 Fotos"], ["videos", "🎬 Vídeos"], ["audios", "🎵 Audios"], ["documentos", "📄 Documentos"], ["stickers", "✨ Stickers"]];
const ESTADOS = { iniciando: "Iniciando", "en curso": "Descargando", vigilando: "Vigilando", terminado: "Terminado", detenido: "Detenido", error: "Error" };

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = n => { const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0; n = +n || 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return n.toFixed(i ? 1 : 0) + " " + u[i]; };
const dur = s => { s = Math.max(0, Math.floor(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60); return h ? `${h} h ${m} min` : m ? `${m} min ${s % 60} s` : `${s} s`; };
const hue = t => [...String(t)].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7);
const avatar = t => `background:linear-gradient(135deg,hsl(${hue(t)} 70% 58%),hsl(${(hue(t) + 50) % 360} 70% 48%))`;
const inicial = t => (String(t || "?").trim()[0] || "?").toUpperCase();

// Token que el panel mete en la página: sin él la API rechaza la petición (protege de otras webs).
const TOKEN = document.querySelector('meta[name="tgdl-token"]')?.content || "";

async function api(url, opts = {}) {
  const r = await fetch(url, { method: opts.method || "GET", headers: { "Content-Type": "application/json", "X-Token": TOKEN }, body: opts.body ? JSON.stringify(opts.body) : undefined });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || r.statusText);
  return d;
}
function toast(texto, tipo = "") {
  const el = document.createElement("div");
  el.className = "toast " + tipo; el.textContent = texto;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.style.transition = "opacity .4s"; el.style.opacity = 0; setTimeout(() => el.remove(), 400); }, 4200);
}

/* ------------------------------------------------------------------ navegación */
const NOMBRES_VISTA = { panel: "Descargas", nueva: "Nueva descarga", cuentas: "Cuentas", archivo: "Archivo" };
const historial = { pila: ["panel"], pos: 0 };
let vistaActual = "panel";

function ir(vista, { registrar = true } = {}) {
  vistaActual = vista;
  $$(".vista").forEach(v => v.classList.toggle("on", v.id === "vista-" + vista));
  $$(".nav").forEach(n => n.classList.toggle("on", n.dataset.vista === vista));
  $("#ruta").textContent = NOMBRES_VISTA[vista] || vista;
  document.title = `${NOMBRES_VISTA[vista]} · TG Downloader`;
  if (registrar && historial.pila[historial.pos] !== vista) {
    historial.pila = historial.pila.slice(0, historial.pos + 1).concat(vista);
    historial.pos = historial.pila.length - 1;
  }
  $("#btn-atras").disabled = historial.pos <= 0;
  $("#btn-adelante").disabled = historial.pos >= historial.pila.length - 1;
  if (vista === "cuentas") cargarCuentas();
  if (vista === "archivo") cargarArchivo();
  if (vista === "nueva") prepararNueva();
  $("#contenido").scrollTo({ top: 0 });
  restaurarVentana();
}
document.addEventListener("click", e => {
  const destino = e.target.closest("[data-ir]");
  if (destino) { e.preventDefault(); ir(destino.dataset.ir); return; }
  const nav = e.target.closest(".nav");
  if (nav) ir(nav.dataset.vista);
});
$("#btn-atras").onclick = () => { if (historial.pos > 0) ir(historial.pila[--historial.pos], { registrar: false }); };
$("#btn-adelante").onclick = () => { if (historial.pos < historial.pila.length - 1) ir(historial.pila[++historial.pos], { registrar: false }); };
$("#btn-refrescar").onclick = () => ir(vistaActual, { registrar: false });
$("#cmd-cuenta").onclick = () => { ir("cuentas"); $("#btn-anadir-cuenta").click(); };
$("#cmd-ayuda").onclick = () => toast("Consejo: puedes cerrar esta pestaña; las descargas siguen mientras la ventana negra del panel esté abierta.");

/* ventana: minimizar / maximizar / cerrar */
const ventana = $("#ventana");
function restaurarVentana() { ventana.classList.remove("minimizada"); $("#tarea-app").classList.add("activa"); }
function minimizarVentana() { ventana.classList.add("minimizada"); $("#tarea-app").classList.remove("activa"); }
$("#bv-min").onclick = minimizarVentana;
$("#bv-max").onclick = () => ventana.classList.toggle("maximizada");
$("#barra-titulo").ondblclick = e => { if (!e.target.closest(".bv")) ventana.classList.toggle("maximizada"); };
$("#bv-cerrar").onclick = () => { minimizarVentana(); toast("El panel sigue funcionando en segundo plano. Para salir cierra la ventana de consola del panel."); };
$("#tarea-app").onclick = () => ventana.classList.contains("minimizada") ? restaurarVentana() : minimizarVentana();
$("#orbe").onclick = () => ir("panel");
function reloj() { $("#reloj").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
reloj(); setInterval(reloj, 10000);

/* ------------------------------------------------------------------ tiempo real */
function conectarWS() {
  const ws = new WebSocket(`ws://${location.host}/ws?token=${encodeURIComponent(TOKEN)}`);
  const ind = $("#conexion");
  ws.onopen = () => { ind.className = "estado-conexion ok"; ind.querySelector("span").textContent = "Conectado"; };
  ws.onmessage = e => renderTrabajos(JSON.parse(e.data).trabajos);
  ws.onclose = () => { ind.className = "estado-conexion mal"; ind.querySelector("span").textContent = "Reconectando…"; setTimeout(conectarWS, 2000); };
}

/* ------------------------------------------------------------------ panel de trabajos */
const tarjetas = new Map();
const abiertos = new Set();
const activo = t => ["iniciando", "en curso", "vigilando"].includes(t.estado);

function renderTrabajos(lista) {
  const cont = $("#lista-trabajos");
  const ids = new Set(lista.map(t => t.id));
  for (const [id, el] of tarjetas) if (!ids.has(id)) { el.remove(); tarjetas.delete(id); }
  for (const t of [...lista].reverse()) {
    let el = tarjetas.get(t.id);
    if (!el) { el = crearTarjeta(t); tarjetas.set(t.id, el); cont.prepend(el); }
    actualizarTarjeta(el, t);
  }
  const activos = lista.filter(activo);
  $("#trabajos-vacio").hidden = lista.length > 0;
  $("#m-vel").textContent = fmt(activos.reduce((a, t) => a + t.velocidad, 0)) + "/s";
  $("#m-bytes").textContent = fmt(lista.reduce((a, t) => a + t.bytes, 0));
  $("#m-archivos").textContent = activos.reduce((a, t) => a + t.archivos.length, 0);
  $("#m-activos").textContent = activos.length;
  const badge = $("#badge-activos");
  badge.hidden = !activos.length; badge.textContent = activos.length;
  const vel = activos.reduce((a, t) => a + t.velocidad, 0);
  const enCurso = activos.reduce((a, t) => a + t.archivos.length, 0);
  $("#g-vel").textContent = fmt(vel) + "/s";
  $("#g-medidor").style.width = Math.min(100, vel / (20 * 1024 * 1024) * 100).toFixed(1) + "%";
  $("#g-pie").textContent = activos.length ? `${enCurso} archivo${enCurso === 1 ? "" : "s"} · ${activos.length} trabajo${activos.length === 1 ? "" : "s"}` : "Sin descargas activas";
  $("#estado-resumen").textContent = activos.length ? `${activos.length} descarga${activos.length === 1 ? "" : "s"} en curso · ${fmt(vel)}/s` : "Listo";
}

function crearTarjeta(t) {
  const el = document.createElement("article");
  el.className = "trabajo";
  el.innerHTML = `
    <div class="trabajo-cab">
      <span class="insignia"></span><h2></h2>
      <button class="btn mini peligro" data-acc="detener">■ Detener</button>
      <button class="btn mini" data-acc="quitar">Quitar</button>
    </div>
    <div class="trabajo-meta"></div>
    <div class="progreso"><i></i></div>
    <div class="canales" style="margin-top:12px"></div>
    <div class="archivos-activos"></div>
    <details class="registro"><summary>Más información</summary><div class="consola"></div></details>`;
  $("[data-acc=detener]", el).onclick = async () => {
    try { await api(`/api/trabajos/${t.id}/detener`, { method: "POST" }); toast("Deteniendo la descarga…"); } catch (e) { toast(e.message, "error"); }
  };
  $("[data-acc=quitar]", el).onclick = async () => {
    try { await api(`/api/trabajos/${t.id}`, { method: "DELETE" }); el.remove(); tarjetas.delete(t.id); } catch (e) { toast(e.message, "error"); }
  };
  const det = $("details", el);
  det.ontoggle = () => det.open ? abiertos.add(t.id) : abiertos.delete(t.id);
  return el;
}

function actualizarTarjeta(el, t) {
  el.dataset.estado = t.estado;
  const ins = $(".insignia", el);
  ins.className = "insignia " + t.estado.replace(" ", "-");
  ins.textContent = ESTADOS[t.estado] || t.estado;
  $("h2", el).textContent = t.etiquetas.join(" · ");
  $("[data-acc=detener]", el).hidden = !activo(t);
  $("[data-acc=quitar]", el).hidden = activo(t);

  const fin = t.fin || Date.now() / 1000;
  $(".trabajo-meta", el).innerHTML =
    `<span>👤 ${esc(t.cuentas.join(", "))}</span><span>⏱ ${dur(fin - t.inicio)}</span>` +
    (activo(t) ? `<span>⚡ ${fmt(t.velocidad)}/s</span>` : "") + `<span>💾 ${esc(t.bytes_txt)}</span>` +
    (t.error ? `<span style="color:var(--rojo)">${esc(t.error)}</span>` : "");

  const total = t.canales.reduce((a, c) => a + c.total, 0), hechos = t.canales.reduce((a, c) => a + Math.min(c.hechos, c.total), 0);
  const pct = t.estado === "terminado" || t.estado === "vigilando" ? 100 : total ? hechos / total * 100 : 0;
  $(".progreso > i", el).style.width = pct.toFixed(1) + "%";

  $(".canales", el).innerHTML = t.canales.map(c => {
    const p = c.total ? Math.min(100, c.hechos / c.total * 100) : 0;
    const s = c.stats ? ` · ✅ ${c.stats.ok} · ♻️ ${c.stats.duplicados} · ❌ ${c.stats.fallos}` : "";
    return `<div class="canal-fila"><div class="linea"><b>${esc(c.titulo)} <small style="color:var(--suave)">[${esc(c.cuenta)}]</small></b>
      <span>${c.hechos.toLocaleString()} / ${c.total.toLocaleString()} mensajes${s}</span></div>
      <div class="progreso fino"><i style="width:${(c.terminado ? 100 : p).toFixed(1)}%"></i></div></div>`;
  }).join("");

  $(".archivos-activos", el).innerHTML = t.archivos.map(a => {
    const p = a.total ? a.recibido / a.total * 100 : 0;
    return `<div class="archivo-activo"><span>⬇ ${esc(a.nombre)}</span><span>${fmt(a.recibido)} / ${fmt(a.total)}</span>
      <div class="progreso fino"><i style="width:${p.toFixed(1)}%"></i></div></div>`;
  }).join("");

  const det = $("details", el);
  if (abiertos.has(t.id) && !det.open) det.open = true;
  const consola = $(".consola", el);
  const firma = t.logs.length + ":" + (t.logs.at(-1)?.t || 0);
  if (consola.dataset.firma !== firma) {
    const abajo = consola.scrollHeight - consola.scrollTop - consola.clientHeight < 30;
    consola.innerHTML = t.logs.map(l => `<div class="l-${l.n}"><time>${new Date(l.t * 1000).toLocaleTimeString()}</time>${esc(l.x)}</div>`).join("") || "<div>Sin actividad todavía.</div>";
    consola.dataset.firma = firma;
    if (abajo) consola.scrollTop = consola.scrollHeight;
  }
}

/* ------------------------------------------------------------------ nueva descarga */
let cuentas = [];
const cacheCanales = {};
const seleccion = new Map();
const cuentasSel = new Set();
const tiposSel = new Set(TIPOS.map(t => t[0]));
let configCargada = false;

async function obtenerCuentas() {
  cuentas = await api("/api/cuentas");
  return cuentas;
}

async function prepararNueva() {
  try { await obtenerCuentas(); } catch (e) { toast(e.message, "error"); }
  if (!configCargada) {
    try { const c = await api("/api/config"); $("#op-salida").value = c.salida; $("#op-hilos").value = c.hilos; $("#hilos-val").textContent = c.hilos; configCargada = true; } catch { }
  }
  const conectadas = cuentas.filter(c => c.conectada);
  for (const n of [...cuentasSel]) if (!conectadas.some(c => c.nombre === n)) cuentasSel.delete(n);
  if (!cuentasSel.size && conectadas.length) cuentasSel.add(conectadas[0].nombre);
  $("#sin-cuentas").hidden = conectadas.length > 0;
  const cont = $("#sel-cuentas");
  cont.innerHTML = conectadas.map(c => `<button class="chip ${cuentasSel.has(c.nombre) ? "on" : ""}" data-cuenta="${esc(c.nombre)}">
      <b>${esc(c.nombre)}</b> <small>${esc(c.usuario ? "@" + c.usuario : c.nombre_mostrado || "")}</small></button>`).join("");
  $$("[data-cuenta]", cont).forEach(b => b.onclick = () => {
    const n = b.dataset.cuenta;
    cuentasSel.has(n) ? cuentasSel.delete(n) : cuentasSel.add(n);
    b.classList.toggle("on", cuentasSel.has(n));
    cargarCanales(); actualizarResumen();
  });
  cargarCanales(); actualizarResumen();
}

async function cargarCanales() {
  const lista = $("#lista-canales");
  const primera = [...cuentasSel][0];
  if (!primera) { lista.innerHTML = `<div class="cargando">Elige una cuenta para ver sus canales.</div>`; return; }
  if (!cacheCanales[primera]) {
    lista.innerHTML = `<div class="cargando">Cargando canales de ${esc(primera)}…</div>`;
    try { cacheCanales[primera] = await api(`/api/cuentas/${encodeURIComponent(primera)}/canales`); }
    catch (e) { lista.innerHTML = `<div class="cargando">${esc(e.message)}</div>`; return; }
  }
  pintarCanales();
}

function pintarCanales() {
  const primera = [...cuentasSel][0];
  const datos = cacheCanales[primera] || [];
  const q = $("#buscar-canal").value.trim().toLowerCase();
  const vis = datos.filter(c => !q || c.nombre.toLowerCase().includes(q) || (c.usuario || "").toLowerCase().includes(q));
  $("#lista-canales").innerHTML = vis.map(c => `
    <div class="canal-item ${seleccion.has(String(c.id)) ? "on" : ""}" data-id="${c.id}">
      <div class="av" style="${avatar(c.nombre)}">${esc(inicial(c.nombre))}</div>
      <div class="nm"><b>${esc(c.nombre)}${c.descargado ? '<span class="etiqueta">descargado</span>' : ""}</b>
        <small>${c.tipo === "grupo" ? "👥 Grupo" : "📢 Canal"}${c.usuario ? " · @" + esc(c.usuario) : ""}${c.sin_leer ? " · " + c.sin_leer + " sin leer" : ""}</small></div>
      <div class="check">✓</div>
    </div>`).join("") || `<div class="cargando">No hay coincidencias.</div>`;
}

$("#lista-canales").addEventListener("click", e => {
  const item = e.target.closest(".canal-item"); if (!item) return;
  const id = item.dataset.id;
  const datos = cacheCanales[[...cuentasSel][0]] || [];
  if (seleccion.has(id)) seleccion.delete(id);
  else { const c = datos.find(x => String(x.id) === id); seleccion.set(id, { id: c.id, nombre: c.nombre }); }
  item.classList.toggle("on", seleccion.has(id));
  pintarSeleccion();
});
$("#buscar-canal").addEventListener("input", pintarCanales);
$("#enlace-canal").addEventListener("keydown", e => {
  if (e.key !== "Enter") return;
  const v = e.target.value.trim(); if (!v) return;
  seleccion.set(v, { id: v, nombre: v }); e.target.value = ""; pintarSeleccion();
});

function pintarSeleccion() {
  const cont = $("#seleccionados");
  cont.innerHTML = [...seleccion.entries()].map(([k, c]) => `<button class="chip on" data-quitar="${esc(k)}">${esc(c.nombre)} <span class="x">✕</span></button>`).join("");
  $$("[data-quitar]", cont).forEach(b => b.onclick = () => { seleccion.delete(b.dataset.quitar); pintarSeleccion(); pintarCanales(); });
  actualizarResumen();
}

function actualizarResumen() {
  $("#contador-canales").textContent = `${seleccion.size} seleccionado${seleccion.size === 1 ? "" : "s"}`;
  $("#reparto").hidden = cuentasSel.size < 2;
  const ok = cuentasSel.size && seleccion.size && tiposSel.size;
  $("#btn-iniciar").disabled = !ok;
  $("#resumen-accion").textContent = ok
    ? `${seleccion.size} canal${seleccion.size > 1 ? "es" : ""} · ${cuentasSel.size} cuenta${cuentasSel.size > 1 ? "s" : ""} · ${tiposSel.size === TIPOS.length ? "todo el contenido" : [...tiposSel].join(", ")}${$("#op-seguir").checked ? " · vigilancia" : ""}`
    : "Selecciona al menos una cuenta, un canal y un tipo de contenido.";
}

(function pintarTipos() {
  const cont = $("#sel-tipos");
  cont.innerHTML = TIPOS.map(([k, v]) => `<button class="chip on" data-tipo="${k}">${v}</button>`).join("");
  $$("[data-tipo]", cont).forEach(b => b.onclick = () => {
    const k = b.dataset.tipo; tiposSel.has(k) ? tiposSel.delete(k) : tiposSel.add(k);
    b.classList.toggle("on", tiposSel.has(k)); actualizarResumen();
  });
})();
$("#op-hilos").addEventListener("input", e => $("#hilos-val").textContent = e.target.value);
$("#op-seguir").addEventListener("change", actualizarResumen);

$("#btn-iniciar").addEventListener("click", async () => {
  const v = id => $(id).value.trim();
  const opciones = {
    tipos: [...tiposSel], seguir: $("#op-seguir").checked, comentarios: $("#op-comentarios").checked,
    albumes: $("#op-albumes").checked, deduplicar: $("#op-deduplicar").checked, html: $("#op-html").checked,
    notificar: $("#op-notificar").checked, desde: v("#op-desde"), hasta: v("#op-hasta"),
    min_tamano: v("#op-min"), max_tamano: v("#op-max"), extensiones: v("#op-ext"), excluir_extensiones: v("#op-excluir"),
    buscar: v("#op-buscar"), nombres: v("#op-nombres"), hilos: +v("#op-hilos"), limite_velocidad: v("#op-limite"),
    espacio_minimo: v("#op-espacio"), salida: v("#op-salida"),
    reparto: ($("input[name=reparto]:checked") || {}).value || "canal",
  };
  const btn = $("#btn-iniciar"); btn.disabled = true;
  try {
    await api("/api/trabajos", { method: "POST", body: { cuentas: [...cuentasSel], canales: [...seleccion.values()], opciones } });
    toast("🚀 Descarga iniciada", "ok");
    seleccion.clear(); pintarSeleccion(); pintarCanales();
    ir("panel");
  } catch (e) { toast(e.message, "error"); }
  finally { actualizarResumen(); }
});

/* ------------------------------------------------------------------ cuentas */
async function cargarCuentas() {
  const cont = $("#lista-cuentas");
  cont.innerHTML = `<div class="cargando">Cargando cuentas…</div>`;
  try { await obtenerCuentas(); } catch (e) { cont.innerHTML = `<div class="cargando">${esc(e.message)}</div>`; return; }
  if (!cuentas.length) {
    cont.innerHTML = `<div class="vacio" style="grid-column:1/-1"><div class="vacio-ic">🔑</div><h2>Añade tu primera cuenta</h2><p>Inicia sesión con tu número de Telegram.</p></div>`;
    return;
  }
  cont.innerHTML = cuentas.map(c => `
    <div class="tarjeta">
      <div class="cab"><div class="av" style="${avatar(c.nombre)}">${esc(inicial(c.nombre_mostrado || c.nombre))}</div>
        <div style="min-width:0"><h2>${esc(c.nombre_mostrado || c.nombre)}</h2>
        <div class="sub">${c.usuario ? "@" + esc(c.usuario) + " · " : ""}${esc(c.telefono || "")}</div></div></div>
      <div class="sub" style="margin-bottom:14px">Sesión: <b>${esc(c.nombre)}</b> · ${c.conectada ? '<span style="color:var(--verde)">● conectada</span>' : '<span style="color:var(--rojo)">● sesión caducada</span>'}</div>
      <div class="acciones"><button class="btn mini peligro" data-borrar="${esc(c.nombre)}">Cerrar sesión y quitar</button></div>
    </div>`).join("");
  $$("[data-borrar]", cont).forEach(b => b.onclick = async () => {
    if (!confirm(`¿Cerrar la sesión de "${b.dataset.borrar}" y quitarla del programa?`)) return;
    try { await api(`/api/cuentas/${encodeURIComponent(b.dataset.borrar)}`, { method: "DELETE" }); delete cacheCanales[b.dataset.borrar]; cuentasSel.delete(b.dataset.borrar); toast("Cuenta eliminada", "ok"); cargarCuentas(); }
    catch (e) { toast(e.message, "error"); }
  });
}

/* modal de login */
const modal = $("#modal-cuenta");
function pasoModal(n) {
  $$(".modal-paso", modal).forEach(p => p.classList.toggle("on", +p.dataset.paso === n));
  $$(".pasos-modal i", modal).forEach((i, k) => i.classList.toggle("on", k < n));
  $("#mc-error").textContent = "";
  setTimeout(() => ($(".modal-paso.on input", modal) || {}).focus?.(), 50);
}
$("#btn-anadir-cuenta").onclick = () => {
  $("#mc-nombre").value = cuentas.length ? "" : "principal";
  ["#mc-telefono", "#mc-codigo", "#mc-password"].forEach(s => $(s).value = "");
  modal.hidden = false; pasoModal(1);
};
function cerrarModal() {
  modal.hidden = true;
  // Si el login se quedó a medias, se avisa al panel para que libere la sesión sin terminar.
  if (!$('.modal-paso[data-paso="1"]', modal).classList.contains("on"))
    api("/api/cuentas/cancelar", { method: "POST", body: { nombre: $("#mc-nombre").value.trim() } }).catch(() => { });
}
$("#cerrar-modal").onclick = cerrarModal;
modal.addEventListener("click", e => { if (e.target === modal) cerrarModal(); });

async function accionModal(btn, fn) {
  btn.disabled = true; $("#mc-error").textContent = "";
  try { await fn(); } catch (e) { $("#mc-error").textContent = e.message; } finally { btn.disabled = false; }
}
async function terminarLogin(r) {
  if (r.resultado === "password") return pasoModal(3);
  modal.hidden = true; pasoModal(1);
  toast(`✅ Cuenta añadida: ${r.cuenta?.nombre_mostrado || $("#mc-nombre").value}`, "ok");
  cargarCuentas();
}
$("#mc-enviar").onclick = e => accionModal(e.target, async () => {
  await api("/api/cuentas/codigo", { method: "POST", body: { nombre: $("#mc-nombre").value.trim(), telefono: $("#mc-telefono").value.trim() } });
  pasoModal(2);
});
$("#mc-verificar").onclick = e => accionModal(e.target, async () => {
  terminarLogin(await api("/api/cuentas/verificar", { method: "POST", body: { nombre: $("#mc-nombre").value.trim(), codigo: $("#mc-codigo").value.trim() } }));
});
$("#mc-password-ok").onclick = e => accionModal(e.target, async () => {
  terminarLogin(await api("/api/cuentas/verificar", { method: "POST", body: { nombre: $("#mc-nombre").value.trim(), password: $("#mc-password").value } }));
});
modal.addEventListener("keydown", e => { if (e.key === "Enter") $(".modal-paso.on .btn", modal).click(); });

/* ------------------------------------------------------------------ archivo */
async function cargarArchivo() {
  const cont = $("#lista-archivo");
  cont.innerHTML = `<div class="cargando">Cargando…</div>`;
  let datos;
  try { datos = await api("/api/archivo"); } catch (e) { cont.innerHTML = `<div class="cargando">${esc(e.message)}</div>`; return; }
  if (!datos.length) {
    cont.innerHTML = `<div class="vacio" style="grid-column:1/-1"><div class="vacio-ic">🗂️</div><h2>Aún no hay nada descargado</h2><p>Cuando descargues un canal aparecerá aquí.</p></div>`;
    return;
  }
  cont.innerHTML = datos.map(c => `
    <div class="tarjeta">
      <div class="cab"><div class="av" style="${avatar(c.titulo)}">${esc(inicial(c.titulo))}</div>
        <div style="min-width:0"><h2>${esc(c.titulo)}</h2><div class="sub">Actualizado ${c.actualizado ? new Date(c.actualizado).toLocaleString() : "—"}</div></div></div>
      <div class="datos"><div><small>Archivos</small><b>${c.archivos.toLocaleString()}</b></div>
        <div><small>Tamaño</small><b>${esc(c.tamano)}</b></div><div><small>Fallidos</small><b>${c.fallos}</b></div></div>
      <div class="acciones">
        ${c.html ? `<a class="btn mini primario" href="/ver/${c.id}/index.html" target="_blank" rel="noopener">🌐 Abrir archivo</a>` : ""}
        <button class="btn mini" data-html="${c.id}">↻ ${c.html ? "Regenerar" : "Generar"} HTML</button>
      </div>
      <div class="ruta">📂 ${esc(c.carpeta)}</div>
    </div>`).join("");
  $$("[data-html]", cont).forEach(b => b.onclick = async () => {
    b.disabled = true;
    try { await api(`/api/archivo/${b.dataset.html}/html`, { method: "POST" }); toast("HTML actualizado", "ok"); cargarArchivo(); }
    catch (e) { toast(e.message, "error"); b.disabled = false; }
  });
}

/* ------------------------------------------------------------------ inicio */
conectarWS();
obtenerCuentas().then(c => { if (!c.length) { ir("cuentas"); toast("👋 Empieza añadiendo tu cuenta de Telegram"); } }).catch(() => { });
