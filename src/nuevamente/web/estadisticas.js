// Página de estadísticas de Kairos: lee GET /api/v1/estadisticas y lo pinta.
// Los comentarios los escriben los usuarios: se insertan con textContent (vía h()), nunca como HTML.

const $ = (sel) => document.querySelector(sel);

const PERFILES = {
  "Principiante": "Inicial/Básico",
  "Desarrollador Junior/Semi Senior": "Intermedio",
  "Líder Técnico/Arquitecto": "Avanzado",
  "Gestor/Ejecutivo": "Experto / Directivo",
};
const ORIGENES = { texto: "Texto pegado", pdf: "PDF", docx: "Word (.docx)", md: "Markdown", markdown: "Markdown", txt: "Texto (.txt)" };
const DESCARGAS = {
  docx: "Word", pdf: "PDF", pptx: "PowerPoint", markdown: "Markdown", anki_csv: "Anki (CSV)",
  video: "Video del guion", podcast: "Audio del podcast",
};

function h(tag, attrs = {}, ...hijos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style") el.style.cssText = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const hijo of hijos.flat()) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    el.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
  return el;
}

const porcentaje = (v) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);
const estrellasTexto = (n) => "★".repeat(n) + "☆".repeat(5 - n);
const vacio = (texto = "Todavía no hay datos.") => h("p", { class: "est-vacio" }, texto);

// ---------- Tooltip compartido ----------

const tooltip = h("div", { class: "est-tooltip", role: "est-tooltip", hidden: true });
document.body.append(tooltip);

function conTooltip(el, texto) {
  const mostrar = (x, y) => {
    tooltip.textContent = texto;
    tooltip.hidden = false;
    const ancho = tooltip.offsetWidth;
    tooltip.style.left = `${Math.min(Math.max(8, x - ancho / 2), innerWidth - ancho - 8)}px`;
    tooltip.style.top = `${Math.max(8, y - tooltip.offsetHeight - 12)}px`;
  };
  el.addEventListener("pointermove", (e) => mostrar(e.clientX, e.clientY));
  el.addEventListener("pointerleave", () => (tooltip.hidden = true));
  el.addEventListener("focus", () => {
    const r = el.getBoundingClientRect();
    mostrar(r.left + r.width / 2, r.top);
  });
  el.addEventListener("blur", () => (tooltip.hidden = true));
  el.setAttribute("aria-label", texto);
  return el;
}

// ---------- Piezas ----------

function tile(etiqueta, valor, nota = "") {
  return h("div", { class: "est-tile" }, h("small", {}, etiqueta), h("strong", {}, valor), nota ? h("span", {}, nota) : null);
}

// Barras horizontales de una sola serie: el valor va en la punta de cada barra.
function barras(filas, nombrar = (n) => n, unidad = "") {
  const conDatos = filas.filter((f) => f.total > 0);
  if (!conDatos.length) return vacio();
  const maximo = Math.max(...conDatos.map((f) => f.total));
  const suma = conDatos.reduce((s, f) => s + f.total, 0);
  return h("ul", { class: "est-barras" }, filas.map((f) => {
    const nombre = nombrar(f.nombre);
    const parte = suma ? Math.round((f.total / suma) * 100) : 0;
    return conTooltip(
      h("li", { class: "est-barra", tabindex: "0" },
        h("span", { class: "est-barra-nombre" }, nombre),
        h("span", { class: "est-barra-pista" },
          h("span", { class: "est-barra-relleno", style: `width: calc((100% - 4.5rem) * ${f.total / maximo}); min-width: ${f.total ? 2 : 0}px` }),
          h("span", { class: "est-barra-valor" }, f.total))),
      `${nombre}: ${f.total}${unidad} (${parte}% del total)`,
    );
  }));
}

function actividad(dias) {
  if (!dias.some((d) => d.total)) return vacio("No se creó ningún material en los últimos 14 días.");
  const maximo = Math.max(...dias.map((d) => d.total));
  const fecha = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString("es", { day: "numeric", month: "short" });
  return h("div", {},
    h("div", { class: "est-columnas", role: "img", "aria-label": dias.map((d) => `${fecha(d.fecha)}: ${d.total}`).join(", ") },
      dias.map((d) => conTooltip(
        h("div", { class: "est-columna", tabindex: "0" },
          h("span", { class: "est-columna-relleno", style: `height: ${d.total ? Math.max(3, (d.total / maximo) * 85) : 0}%` }),
          d.total === maximo ? h("span", { class: "est-columna-valor", style: `bottom: calc(${(d.total / maximo) * 85}% + 4px)` }, d.total) : null),
        `${fecha(d.fecha)}: ${d.total} material${d.total === 1 ? "" : "es"}`,
      ))),
    h("div", { class: "est-ejes", "aria-hidden": "true" }, dias.map((d) => h("span", {}, fecha(d.fecha)))),
  );
}

function tablaFormatos(filas) {
  if (!filas.length) return vacio();
  return h("div", { class: "est-tabla-envoltura" },
    h("table", { class: "est-tabla" },
      h("thead", {}, h("tr", {},
        h("th", {}, "Formato"),
        h("th", { class: "est-num" }, "Creados"),
        h("th", { class: "est-num" }, "Fidelidad media"),
        h("th", { class: "est-num" }, "Calificación media"),
        h("th", { class: "est-num" }, "Calificaciones"))),
      h("tbody", {}, filas.map((f) => h("tr", {},
        h("td", {}, f.nombre),
        h("td", { class: "est-num" }, f.total),
        h("td", { class: "est-num" }, porcentaje(f.fidelidad_promedio)),
        h("td", { class: "est-num" }, f.calificacion_promedio === null ? "—" : `${f.calificacion_promedio} ★`),
        h("td", { class: "est-num" }, f.calificaciones))))));
}

function comentarios(lista) {
  if (!lista.length) return vacio("Aún nadie dejó un comentario.");
  return h("ul", { class: "est-comentarios" }, lista.map((c) => h("li", { class: "est-comentario" },
    h("span", { class: "estrellas-fijas", "aria-label": `${c.estrellas} de 5 estrellas` }, estrellasTexto(c.estrellas)),
    " ",
    h("small", {}, `${c.formato || ""} · ${PERFILES[c.perfil] || c.perfil || ""} · ${new Date(c.fecha).toLocaleDateString("es")}`),
    h("p", {}, c.comentario))));
}

// ---------- Carga ----------

async function cargar() {
  const error = $("#error");
  error.hidden = true;
  let datos;
  try {
    const resp = await fetch("/api/v1/estadisticas", { cache: "no-store" });
    if (!resp.ok) throw new Error(`el servidor respondió ${resp.status}`);
    datos = await resp.json();
  } catch (err) {
    error.textContent = `No se pudieron cargar las estadísticas: ${err.message}`;
    error.hidden = false;
    return;
  }

  const t = datos.totales;
  $("#tiles").replaceChildren(
    tile("Materiales creados", t.materiales,
      [t.historicos ? `${t.historicos} del historial anterior` : "", t.modo_local ? `${t.modo_local} en modo local` : ""]
        .filter(Boolean).join(" · ")),
    tile("Calificación media", t.calificacion_promedio === null ? "—" : `${t.calificacion_promedio} ★`, `${t.calificaciones} calificaciones`),
    tile("Fidelidad media", porcentaje(t.fidelidad_promedio), "Afirmaciones con respaldo en la fuente"),
    tile("Aprobados por el Crítico", porcentaje(t.tasa_aprobacion)),
    tile("Tiempo medio de creación", t.tiempo_generacion_promedio_s === null ? "—" : `${t.tiempo_generacion_promedio_s} s`),
    tile("Descargas", t.descargas),
  );
  $("#actividad").replaceChildren(actividad(datos.actividad_diaria));
  $("#formatos").replaceChildren(tablaFormatos(datos.por_formato));
  $("#estrellas").replaceChildren(
    barras(datos.distribucion_estrellas.map((d) => ({ nombre: d.estrellas, total: d.total })), estrellasTexto, " usuarios"),
  );
  $("#comentarios").replaceChildren(comentarios(datos.comentarios_recientes));
  $("#perfiles").replaceChildren(barras(datos.por_perfil, (n) => PERFILES[n] || n));
  $("#sectores").replaceChildren(barras(datos.por_sector));
  $("#origenes").replaceChildren(barras(datos.por_origen, (n) => ORIGENES[n] || n));
  $("#niveles").replaceChildren(barras(datos.por_nivel));
  $("#descargas").replaceChildren(barras(datos.descargas_por_tipo, (n) => DESCARGAS[n] || n));
}

// ---------- Tema (el mismo que la página principal) ----------

const TEMA_KEY = "nuevamente.tema";
const temaActual = () =>
  document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

function pintarBotonTema() {
  const oscuro = temaActual() === "dark";
  $("#btn-tema").textContent = oscuro ? "☀️" : "🌙";
  $("#btn-tema").setAttribute("aria-label", oscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro");
}

$("#btn-tema").addEventListener("click", () => {
  const nuevo = temaActual() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = nuevo;
  try {
    localStorage.setItem(TEMA_KEY, nuevo);
  } catch {
    // sin almacenamiento: el tema vale solo para esta visita
  }
  pintarBotonTema();
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", pintarBotonTema);
$("#btn-actualizar").addEventListener("click", cargar);

pintarBotonTema();
cargar();
