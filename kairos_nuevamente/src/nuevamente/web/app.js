// Front end de Kairos: consume la API REST del mismo servidor.
// Todo el texto que viene del documento o de la API se inserta con textContent
// (vía h()), nunca como HTML: el documento es dato, no código.

const $ = (sel) => document.querySelector(sel);

const PERFILES = {
  "Principiante": "🌱",
  "Desarrollador Junior/Semi Senior": "💻",
  "Líder Técnico/Arquitecto": "🏗️",
  "Gestor/Ejecutivo": "📈",
};

const FORMATOS = {
  "Flashcards": { icono: "🃏", ayuda: "Tarjetas para repasar" },
  "Quiz": { icono: "❓", ayuda: "Preguntas con respuesta" },
  "Tutorial": { icono: "🧭", ayuda: "Paso a paso" },
  "Resumen Ejecutivo": { icono: "📊", ayuda: "Lo esencial en 1 minuto" },
  "Guion de Clase": { icono: "🎬", ayuda: "Para explicar en clase" },
};

const ETAPAS = [
  "📥 Leyendo y dividiendo el documento",
  "🔎 Buscando evidencia por sección",
  "✍️ Redactando el material",
  "✅ Verificando cada afirmación contra la fuente",
];

const EJEMPLO_TITULO = "Protocolo de bioseguridad";
const EJEMPLO = `# Lavado de manos
El lavado de manos con agua y jabón durante al menos 20 segundos elimina la mayoría de los microorganismos de las manos. Es la medida más efectiva y económica para prevenir infecciones en el personal de salud.

# Equipos de protección personal
Los guantes, mascarillas y batas desechables forman parte del equipo de protección personal, conocido como EPP. El EPP debe usarse correctamente y desecharse tras cada procedimiento para evitar contaminación cruzada entre pacientes.

# Manejo de residuos
Los residuos biocontaminados deben separarse en bolsas rojas y desecharse según el protocolo institucional vigente. El personal debe estar capacitado en la clasificación correcta de residuos para evitar accidentes.`;

const HISTORIAL_KEY = "nuevamente.historial";

const estado = {
  modo: "texto",
  archivo: null,
  perfil: null,
  formato: null,
  maxUploadMb: 10,
  respuesta: null,
  tituloDocumento: "",
};

// ---------- Utilidades ----------

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

function leerHistorial() {
  try {
    return JSON.parse(localStorage.getItem(HISTORIAL_KEY)) || [];
  } catch {
    return [];
  }
}

function guardarHistorial(lista) {
  try {
    localStorage.setItem(HISTORIAL_KEY, JSON.stringify(lista.slice(0, 8)));
  } catch {
    // sin almacenamiento del navegador: el historial simplemente no persiste
  }
}

async function mensajeDeError(resp) {
  try {
    const cuerpo = await resp.json();
    if (cuerpo.mensaje_amigable) return cuerpo.mensaje_amigable;
    if (typeof cuerpo.detail === "string") return cuerpo.detail;
    if (Array.isArray(cuerpo.detail)) return cuerpo.detail.map((d) => d.msg).join(" · ");
  } catch {
    // respuesta sin JSON
  }
  return `El servidor respondió con un error (${resp.status}).`;
}

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- Formulario ----------

function radioGrupo(contenedor, valores, crear, alElegir) {
  const botones = valores.map((valor) => {
    const btn = crear(valor);
    btn.type = "button";
    btn.setAttribute("role", "radio");
    btn.setAttribute("aria-checked", "false");
    btn.addEventListener("click", () => {
      botones.forEach((b) => b.setAttribute("aria-checked", String(b === btn)));
      alElegir(valor);
    });
    return btn;
  });
  contenedor.replaceChildren(...botones);
  botones[0]?.click();
}

function llenarSelect(select, valores, porDefecto) {
  select.replaceChildren(...valores.map((v) => h("option", { value: v }, v)));
  if (porDefecto && valores.includes(porDefecto)) select.value = porDefecto;
}

async function cargarOpciones() {
  const resp = await fetch("/api/v1/opciones");
  if (!resp.ok) throw new Error(await mensajeDeError(resp));
  const op = await resp.json();
  estado.maxUploadMb = op.max_upload_mb;
  $("#zona-ayuda").textContent = `PDF, Markdown o texto · hasta ${op.max_upload_mb} MB`;

  radioGrupo(
    $("#perfiles"),
    op.perfiles,
    (p) => h("button", { class: "chip" }, PERFILES[p] || "👤", " ", p),
    (p) => (estado.perfil = p),
  );
  radioGrupo(
    $("#formatos"),
    op.formatos,
    (f) =>
      h(
        "button",
        { class: "tarjeta-formato" },
        h("span", { class: "icono", "aria-hidden": "true" }, FORMATOS[f]?.icono || "📄"),
        h("strong", {}, f),
        h("small", {}, FORMATOS[f]?.ayuda || ""),
      ),
    (f) => (estado.formato = f),
  );
  llenarSelect($("#nicho"), op.nichos, "Salud");
  llenarSelect($("#nivel"), op.niveles, "Didáctico");
  actualizarAvisoSalud();
}

async function cargarEstado() {
  const indicador = $("#estado-oci");
  const poner = (clase, texto) => {
    indicador.className = `estado estado-${clase}`;
    indicador.querySelector(".estado-texto").textContent = texto;
    indicador.title = texto;
  };
  try {
    const salud = await (await fetch("/health")).json();
    if (salud.oci_disponible) poner("ok", "Guardando en OCI");
    else poner("aviso", "Guardado local");
  } catch {
    poner("error", "API sin conexión");
  }
}

function actualizarAvisoSalud() {
  $("#aviso-salud").hidden = $("#nicho").value !== "Salud";
}

function cambiarModo(modo) {
  estado.modo = modo;
  document.querySelectorAll(".seg").forEach((b) => {
    const activo = b.dataset.modo === modo;
    b.classList.toggle("activo", activo);
    b.setAttribute("aria-selected", String(activo));
  });
  $("#modo-texto").hidden = modo !== "texto";
  $("#modo-archivo").hidden = modo !== "archivo";
}

function elegirArchivo(archivo) {
  const zona = $("#zona-archivo");
  estado.archivo = archivo || null;
  zona.classList.toggle("lista", Boolean(archivo));
  $("#zona-texto").textContent = archivo ? `✓ ${archivo.name}` : "Arrastra tu archivo aquí o haz clic para elegirlo";
}

function mostrarError(mensaje) {
  const el = $("#error-form");
  el.textContent = mensaje;
  el.hidden = !mensaje;
}

function construirPeticion() {
  const comunes = {
    perfil_destinatario: estado.perfil,
    formato_salida: estado.formato,
    nicho_sector: $("#nicho").value,
    nivel_detalle: $("#nivel").value,
  };

  if (estado.modo === "archivo") {
    if (!estado.archivo) throw new Error("Elige un archivo para continuar.");
    if (estado.archivo.size > estado.maxUploadMb * 1024 * 1024) {
      throw new Error(`El archivo supera el límite de ${estado.maxUploadMb} MB.`);
    }
    const datos = new FormData();
    datos.append("archivo", estado.archivo);
    for (const [k, v] of Object.entries(comunes)) datos.append(k, v);
    const titulo = estado.archivo.name.replace(/\.[^.]+$/, "");
    return { url: "/api/v1/adaptar/archivo", opciones: { method: "POST", body: datos }, titulo };
  }

  const contenido = $("#contenido").value.trim();
  if (contenido.length < 20) throw new Error("Pega un texto de al menos 20 caracteres.");
  let titulo = $("#titulo").value.trim();
  if (titulo.length < 3) titulo = "Documento sin título";
  return {
    url: "/api/v1/adaptar",
    opciones: {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ documento_titulo: titulo, documento_contenido: contenido, ...comunes }),
    },
    titulo,
  };
}

// ---------- Progreso ----------

function mostrarVista(vista) {
  $("#vacio").hidden = vista !== "vacio";
  $("#progreso").hidden = vista !== "progreso";
  $("#resultado").hidden = vista !== "resultado";
}

async function animarEtapas(peticion) {
  const lista = $("#etapas");
  const items = ETAPAS.map((texto) => h("li", {}, texto));
  lista.replaceChildren(...items);
  mostrarVista("progreso");

  // El flujo es rápido: cada etapa se muestra un momento para que se entienda
  // el recorrido, y la última espera a que responda la API. Si la API falla,
  // generar() captura el error; aquí solo se deja de animar.
  for (let i = 0; i < items.length; i++) {
    items[i].classList.add("activa");
    if (i < items.length - 1) await esperar(380);
    else await peticion;
    items[i].classList.replace("activa", "hecha");
  }
  await esperar(250);
}

async function generar(evento) {
  evento.preventDefault();
  mostrarError("");

  let peticion;
  try {
    peticion = construirPeticion();
  } catch (err) {
    mostrarError(err.message);
    return;
  }

  const boton = $("#btn-generar");
  boton.disabled = true;
  $(".btn-texto").textContent = "Creando…";

  const vistaAnterior = estado.respuesta ? "resultado" : "vacio";
  const llamada = fetch(peticion.url, peticion.opciones).then(async (resp) => {
    if (!resp.ok) throw new Error(await mensajeDeError(resp));
    return resp.json();
  });
  llamada.catch(() => {}); // el error se maneja abajo; evita el aviso de promesa sin capturar

  try {
    await animarEtapas(llamada);
    const respuesta = await llamada;
    estado.tituloDocumento = peticion.titulo;
    mostrarResultado(respuesta, peticion.titulo);
    agregarAlHistorial(respuesta, peticion.titulo);
  } catch (err) {
    mostrarVista(vistaAnterior);
    mostrarError(
      err instanceof TypeError ? "No se pudo conectar con la API. ¿Está corriendo el servidor?" : err.message,
    );
  } finally {
    boton.disabled = false;
    $(".btn-texto").textContent = "Crear mi material";
  }
}

// ---------- Resultado ----------

function mostrarResultado(respuesta, tituloDocumento) {
  estado.respuesta = respuesta;
  const c = respuesta.contenido_adaptado;
  const m = respuesta.metadatos;

  $("#res-etiqueta").textContent = `${FORMATOS[c.formato]?.icono || ""} ${c.formato} · ${m.perfil_aplicado}`;
  $("#res-titulo").textContent = tituloDocumento;

  renderMetricas(respuesta);
  $("#p-contenido").replaceChildren(renderContenido(c));
  $("#p-calidad").replaceChildren(renderCalidad(respuesta.evaluacion_calidad));
  $("#p-almacenamiento").replaceChildren(renderAlmacenamiento(respuesta.almacenamiento_oci));
  $("#json").textContent = JSON.stringify(respuesta, null, 2);

  activarPestana("contenido");
  mostrarVista("resultado");
  habilitarEnlace("material", true);
  marcarSeccion("material");
  $("#resultado").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderMetricas(r) {
  const ev = r.evaluacion_calidad;
  const score = Math.round(ev.anclaje_fuente_score * 100);
  const metrica = (etiqueta, valor, clase = "") =>
    h("div", { class: `metrica ${clase}` }, h("small", {}, etiqueta), h("strong", {}, valor));
  $("#metricas").replaceChildren(
    metrica("Fidelidad a la fuente", `${score}%`, ev.aprobado_por_critico ? "ok" : "aviso"),
    metrica("Tiempo de estudio", `${r.metadatos.tiempo_estimado_estudio_minutos} min`),
    metrica("Generado en", `${r.metadatos.tiempo_generacion_segundos.toFixed(2)} s`),
    metrica("Revisión", ev.aprobado_por_critico ? "✅ Aprobado" : "⚠️ Revisar", ev.aprobado_por_critico ? "ok" : "aviso"),
  );
}

function renderContenido(c) {
  switch (c.formato) {
    case "Flashcards": return renderFlashcards(c);
    case "Quiz": return renderQuiz(c);
    case "Tutorial": return renderTutorial(c);
    case "Resumen Ejecutivo": return renderResumen(c);
    case "Guion de Clase": return renderGuion(c);
    default: return h("p", {}, "Formato no reconocido.");
  }
}

function barraProgreso(texto) {
  const relleno = h("span", { style: "width:0%" });
  const etiqueta = h("span", {}, texto);
  const el = h("div", { class: "contador" }, etiqueta, h("div", { class: "barra" }, relleno));
  return {
    el,
    actualizar(hechas, total, sufijo) {
      relleno.style.width = `${total ? (hechas / total) * 100 : 0}%`;
      etiqueta.textContent = `${hechas} de ${total} ${sufijo}`;
    },
  };
}

function renderFlashcards(c) {
  const vistas = new Set();
  const progreso = barraProgreso("");
  progreso.actualizar(0, c.items.length, "repasadas");

  const tarjetas = c.items.map((item, i) =>
    h(
      "button",
      {
        type: "button",
        class: "flashcard",
        "aria-label": `Tarjeta ${i + 1}: ${item.frente}. Pulsa para voltear.`,
        onclick: (e) => {
          e.currentTarget.classList.toggle("volteada");
          vistas.add(i);
          progreso.actualizar(vistas.size, c.items.length, "repasadas");
        },
      },
      h(
        "div",
        { class: "flashcard-interior" },
        h("div", { class: "cara cara-frente" }, h("strong", {}, item.frente), h("small", {}, "Toca para ver la respuesta ↻")),
        h(
          "div",
          { class: "cara cara-dorso" },
          h("span", {}, item.dorso),
          item.pista_didactica && h("span", { class: "pista" }, "💡 ", item.pista_didactica),
        ),
      ),
    ),
  );

  return h(
    "div",
    {},
    h("p", { class: "intro" }, c.introduccion_contextualizada),
    progreso.el,
    h("div", { class: "mazo" }, tarjetas),
  );
}

function renderQuiz(c) {
  let respondidas = 0;
  let aciertos = 0;
  const progreso = barraProgreso("");
  const actualizar = () => {
    progreso.actualizar(respondidas, c.preguntas.length, `respondidas · ${aciertos} correctas`);
  };
  actualizar();

  const preguntas = c.preguntas.map((p, i) => {
    const retro = h("p", { class: "retro", hidden: true });
    const botones = p.opciones.map((opcion, j) =>
      h(
        "button",
        {
          type: "button",
          class: "opcion",
          onclick: () => {
            botones.forEach((b) => (b.disabled = true));
            botones[p.indice_correcto].classList.add("correcta");
            const acerto = j === p.indice_correcto;
            if (!acerto) botones[j].classList.add("incorrecta");
            retro.textContent = `${acerto ? "🎉 ¡Correcto! " : "💭 Casi. "}${p.justificacion}`;
            retro.hidden = false;
            respondidas += 1;
            if (acerto) aciertos += 1;
            actualizar();
          },
        },
        h("span", { class: "letra" }, String.fromCharCode(65 + j)),
        h("span", {}, opcion),
      ),
    );
    return h(
      "div",
      { class: "pregunta" },
      h("h4", {}, `${i + 1}. ${p.enunciado}`),
      h("div", { class: "opciones" }, botones),
      retro,
    );
  });

  return h("div", {}, progreso.el, preguntas);
}

function renderTutorial(c) {
  const progreso = barraProgreso("");
  const casillas = [];
  const actualizar = () =>
    progreso.actualizar(casillas.filter((x) => x.checked).length, casillas.length, "completados");

  const checklist = c.checklist_final.map((texto) => {
    const casilla = h("input", { type: "checkbox", onchange: actualizar });
    casillas.push(casilla);
    return h("label", { class: "check" }, casilla, h("span", {}, texto));
  });
  actualizar();

  return h(
    "div",
    {},
    h("p", { class: "intro" }, "🎯 ", c.objetivo),
    c.prerrequisitos.length > 0 &&
      h("div", { class: "caja" }, h("h4", {}, "Antes de empezar"), h("ul", {}, c.prerrequisitos.map((p) => h("li", {}, p)))),
    h(
      "ol",
      { class: "linea-tiempo" },
      c.pasos.map((paso) =>
        h(
          "li",
          { "data-orden": paso.orden },
          h("h4", {}, paso.titulo),
          h("p", {}, paso.instruccion),
          paso.resultado_esperado && h("p", { class: "resultado-esperado" }, "→ ", paso.resultado_esperado),
        ),
      ),
    ),
    c.errores_comunes.length > 0 &&
      h("div", { class: "caja" }, h("h4", {}, "⚠️ Errores comunes"), h("ul", {}, c.errores_comunes.map((e) => h("li", {}, e)))),
    checklist.length > 0 && h("div", { class: "caja" }, h("h4", {}, "✅ Checklist final"), progreso.el, checklist),
  );
}

function renderResumen(c) {
  return h(
    "div",
    {},
    h("p", { class: "resumen-texto" }, c.resumen),
    h("h4", {}, "Puntos clave"),
    h("div", { class: "etiquetas" }, c.puntos_clave.map((p) => h("span", {}, p))),
    c.decisiones_o_riesgos.length > 0 &&
      h("div", { class: "caja" }, h("h4", {}, "⚠️ Riesgos y decisiones"), h("ul", {}, c.decisiones_o_riesgos.map((r) => h("li", {}, r)))),
    c.impacto_de_negocio && h("div", { class: "destacado" }, h("strong", {}, "💼 Impacto: "), c.impacto_de_negocio),
  );
}

function renderGuion(c) {
  let acumulado = 0;
  const reloj = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  return h(
    "div",
    {},
    h("p", { class: "intro" }, `🎬 Duración total aproximada: ${c.duracion_total_min} min`),
    c.escenas.map((e) => {
      const inicio = acumulado;
      acumulado += e.duracion_seg;
      return h(
        "div",
        { class: "escena" },
        h("div", { class: "escena-tiempo" }, reloj(inicio), h("small", {}, `Escena ${e.orden} · ${e.duracion_seg}s`)),
        h("div", {}, h("p", {}, e.narracion), e.apoyo_visual && h("p", { class: "visual" }, "🖼️ ", e.apoyo_visual)),
      );
    }),
  );
}

function renderCalidad(ev) {
  const score = Math.round(ev.anclaje_fuente_score * 100);
  const anillo = h("div", {
    class: "anillo",
    "data-texto": `${score}%`,
    style: `--valor:${score};--color-anillo:var(${ev.aprobado_por_critico ? "--menta" : "--coral"})`,
    role: "img",
    "aria-label": `Fidelidad ${score}%`,
  });

  return h(
    "div",
    {},
    h(
      "div",
      { class: "fidelidad-cabecera" },
      anillo,
      h(
        "div",
        {},
        h("h3", {}, ev.aprobado_por_critico ? "✅ Todo está respaldado por tu documento" : "⚠️ Hay puntos para revisar"),
        h(
          "p",
          { class: "nota" },
          `${ev.afirmaciones_sustentadas} de ${ev.afirmaciones_total} afirmaciones sustentadas · umbral exigido ${Math.round(ev.umbral_aplicado * 100)}% · claridad ${ev.claridad_pedagogica.toLowerCase()}`,
        ),
        h("p", { class: "nota" }, ev.observaciones),
      ),
    ),
    ev.afirmaciones_no_sustentadas.length > 0
      ? h(
          "div",
          {},
          h("h4", {}, "Afirmaciones que no encontramos en la fuente"),
          h("ul", { class: "afirmaciones" }, ev.afirmaciones_no_sustentadas.map((a) => h("li", {}, a))),
        )
      : h("p", { class: "nota" }, "Cada afirmación se comparó con el fragmento del documento del que dice venir."),
  );
}

function renderAlmacenamiento(al) {
  const enOci = al.status_upload === "completado";
  return h(
    "div",
    {},
    h(
      "p",
      { class: `pill ${enOci ? "pill-ok" : "pill-aviso"}` },
      enOci ? "☁️ Guardado en OCI Object Storage" : "💾 Guardado en el respaldo local (OCI no configurado)",
    ),
    h(
      "dl",
      { class: "datos" },
      h("dt", {}, "Bucket"), h("dd", {}, al.bucket || "—"),
      h("dt", {}, "Material"), h("dd", {}, al.objeto_id || "—"),
      h("dt", {}, "Documento original"), h("dd", {}, al.objeto_documento_original || "—"),
    ),
  );
}

function activarPestana(nombre) {
  document.querySelectorAll(".pestana").forEach((b) => {
    const activa = b.dataset.pestana === nombre;
    b.classList.toggle("activa", activa);
    b.setAttribute("aria-selected", String(activa));
  });
  document.querySelectorAll(".panel-pestana").forEach((p) => (p.hidden = p.id !== `p-${nombre}`));
}

async function exportar(formato) {
  const objetoId = estado.respuesta?.almacenamiento_oci?.objeto_id;
  if (!objetoId) return;
  try {
    const resp = await fetch(`/api/v1/contenidos/${objetoId}/exportar?formato=${formato}`);
    if (!resp.ok) throw new Error(await mensajeDeError(resp));
    const blob = await resp.blob();
    const nombreBase = estado.tituloDocumento.replace(/[^\p{L}\p{N}]+/gu, "_").replace(/^_|_$/g, "") || "material";
    const enlace = h("a", {
      href: URL.createObjectURL(blob),
      download: `${nombreBase}${formato === "markdown" ? ".md" : "_anki.csv"}`,
    });
    enlace.click();
    URL.revokeObjectURL(enlace.href);
  } catch (err) {
    mostrarError(`No se pudo descargar: ${err.message}`);
  }
}

// ---------- Historial ----------

function agregarAlHistorial(respuesta, titulo) {
  const objetoId = respuesta.almacenamiento_oci.objeto_id;
  const lista = leerHistorial().filter((x) => x.objeto_id !== objetoId);
  lista.unshift({
    objeto_id: objetoId,
    titulo,
    formato: respuesta.contenido_adaptado.formato,
    perfil: respuesta.metadatos.perfil_aplicado,
    fecha: new Date().toISOString(),
  });
  guardarHistorial(lista);
  renderHistorial();
}

function renderHistorial() {
  const lista = leerHistorial();
  $("#historial-caja").hidden = lista.length === 0;
  habilitarEnlace("historial", lista.length > 0);
  const contador = $("#contador-historial");
  contador.textContent = lista.length;
  contador.hidden = lista.length === 0;
  $("#historial").replaceChildren(
    ...lista.map((item) =>
      h(
        "li",
        {},
        h(
          "button",
          { type: "button", onclick: () => abrirDelHistorial(item) },
          h("span", {}, `${FORMATOS[item.formato]?.icono || "📄"} ${item.titulo}`),
          h("small", {}, `${item.perfil} · ${new Date(item.fecha).toLocaleString()}`),
        ),
      ),
    ),
  );
}

async function abrirDelHistorial(item) {
  mostrarError("");
  try {
    const resp = await fetch(`/api/v1/contenidos/${item.objeto_id}`);
    if (!resp.ok) throw new Error(await mensajeDeError(resp));
    estado.tituloDocumento = item.titulo;
    mostrarResultado(await resp.json(), item.titulo);
  } catch (err) {
    mostrarError(`No se pudo abrir "${item.titulo}": ${err.message}`);
    if (/no encontrado/i.test(err.message)) {
      guardarHistorial(leerHistorial().filter((x) => x.objeto_id !== item.objeto_id));
      renderHistorial();
    }
  }
}

// ---------- Menú superior ----------

const TEMA_KEY = "nuevamente.tema";

function temaActual() {
  const elegido = document.documentElement.dataset.theme;
  if (elegido) return elegido;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function pintarBotonTema() {
  const oscuro = temaActual() === "dark";
  const boton = $("#btn-tema");
  boton.textContent = oscuro ? "☀️" : "🌙";
  boton.setAttribute("aria-label", oscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro");
}

function alternarTema() {
  const nuevo = temaActual() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = nuevo;
  try {
    localStorage.setItem(TEMA_KEY, nuevo);
  } catch {
    // sin almacenamiento: el tema vale solo para esta visita
  }
  pintarBotonTema();
}

function abrirMenu(abierto) {
  $("#menu").classList.toggle("abierto", abierto);
  const boton = $("#btn-menu");
  boton.setAttribute("aria-expanded", String(abierto));
  boton.setAttribute("aria-label", abierto ? "Cerrar menú" : "Abrir menú");
}

function marcarSeccion(nombre) {
  document.querySelectorAll(".menu-enlaces a").forEach((a) => {
    const activo = a.dataset.seccion === nombre;
    a.classList.toggle("activo", activo);
    if (activo) a.setAttribute("aria-current", "true");
    else a.removeAttribute("aria-current");
  });
}

function habilitarEnlace(seccion, habilitado) {
  const enlace = document.querySelector(`.menu-enlaces a[data-seccion="${seccion}"]`);
  if (habilitado) enlace.removeAttribute("aria-disabled");
  else enlace.setAttribute("aria-disabled", "true");
}

function iniciarMenu() {
  pintarBotonTema();
  $("#btn-tema").addEventListener("click", alternarTema);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", pintarBotonTema);

  $("#btn-menu").addEventListener("click", () => abrirMenu(!$("#menu").classList.contains("abierto")));
  // En escritorio el formulario y el material se ven lado a lado, así que no se
  // deduce la sección por el scroll: se resalta la que el usuario eligió.
  document.querySelectorAll(".menu-enlaces a").forEach((a) =>
    a.addEventListener("click", () => {
      abrirMenu(false);
      marcarSeccion(a.dataset.seccion);
      if (a.dataset.seccion === "inicio") setTimeout(() => $("#titulo").focus({ preventScroll: true }), 400);
    }),
  );
  document.addEventListener("keydown", (e) => e.key === "Escape" && abrirMenu(false));

  const dialogo = $("#dialogo-como");
  $("#btn-como").addEventListener("click", () => {
    abrirMenu(false);
    dialogo.showModal();
  });
  dialogo.addEventListener("click", (e) => e.target === dialogo && dialogo.close()); // clic fuera cierra
}

// ---------- Inicio ----------

function iniciar() {
  iniciarMenu();
  document.querySelectorAll(".seg").forEach((b) => b.addEventListener("click", () => cambiarModo(b.dataset.modo)));
  document.querySelectorAll(".pestana").forEach((b) => b.addEventListener("click", () => activarPestana(b.dataset.pestana)));
  document.querySelectorAll("[data-exportar]").forEach((b) => b.addEventListener("click", () => exportar(b.dataset.exportar)));

  $("#nicho").addEventListener("change", actualizarAvisoSalud);
  $("#form").addEventListener("submit", generar);
  $("#btn-ejemplo").addEventListener("click", () => {
    $("#titulo").value = EJEMPLO_TITULO;
    $("#contenido").value = EJEMPLO;
  });

  const zona = $("#zona-archivo");
  $("#archivo").addEventListener("change", (e) => elegirArchivo(e.target.files[0]));
  zona.addEventListener("dragover", (e) => {
    e.preventDefault();
    zona.classList.add("arrastrando");
  });
  zona.addEventListener("dragleave", () => zona.classList.remove("arrastrando"));
  zona.addEventListener("drop", (e) => {
    e.preventDefault();
    zona.classList.remove("arrastrando");
    elegirArchivo(e.dataTransfer.files[0]);
  });

  renderHistorial();
  cargarEstado();
  cargarOpciones().catch((err) => mostrarError(`No se pudieron cargar las opciones: ${err.message}`));
}

iniciar();
