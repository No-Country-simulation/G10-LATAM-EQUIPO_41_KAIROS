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
  "Podcast": { icono: "🎙️", ayuda: "Para escuchar" },
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
  voces: { femenina: null, masculina: null },
  voz: "femenina",
  respuesta: null,
  tituloDocumento: "",
  textoUsado: "", // contenido con el que se generó el último material
  documentoAnterior: null, // lo que había en el formulario al pulsar "Nuevo material"
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
  estado.voces = op.voces || estado.voces;
  if (!estado.voces[estado.voz]) estado.voz = estado.voces.masculina ? "masculina" : "femenina";
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
    if (salud.oci_disponible) {
      poner("ok", "Guardando en OCI");
      $("#estado-detalle").textContent =
        "Cada material se guarda en OCI Object Storage, en la nube de Oracle. Puedes volver a abrirlo desde el Historial.";
    } else {
      poner("aviso", "Guardado local");
      $("#estado-detalle").replaceChildren(
        "OCI Object Storage no está configurado, así que cada material se guarda en este equipo (",
        h("code", {}, "data/fallback/"),
        "). Sigue disponible en el Historial. Para guardarlo en la nube, configura las credenciales de OCI (ver ",
        h("code", {}, "docs/SETUP_OCI.md"),
        ").",
      );
    }
  } catch {
    poner("error", "API sin conexión");
    $("#estado-detalle").textContent = "No se pudo contactar con la API. Revisa que el servidor esté en marcha.";
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

// Sin título escrito, se usa el del propio documento: su primera línea si parece un
// título (corta y sin punto final). Si esa línea es solo el primer apartado ("# Lavado
// de manos" seguido de más "# ...", o "1. Acceso"), no titula todo el documento.
function tituloDesdeContenido(contenido) {
  const lineas = contenido.split("\n").map((l) => l.trim()).filter(Boolean);
  const primera = lineas[0] || "";
  const nivel = primera.match(/^#+(?=\s)/)?.[0];
  const esApartado = nivel
    ? lineas.filter((l) => l.startsWith(`${nivel} `)).length > 1
    : /^\d{1,2}(?:\.\d{1,2})*[.)]?\s/.test(primera);
  const titulo = primera.replace(/^#+\s*/, "");
  const valido = !esApartado && titulo.length >= 3 && titulo.length <= 90 && !/[.;,:]$/.test(titulo);
  return valido ? titulo : "Documento sin título";
}

function construirPeticion() {
  if (!estado.perfil || !estado.formato) {
    throw new Error("Las opciones aún se están cargando. Espera un momento y vuelve a intentarlo.");
  }
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
  if (titulo.length < 3) titulo = tituloDesdeContenido(contenido);
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

// Barra de avance en porcentaje. La API responde en una sola llamada, sin avance
// intermedio: cada etapa tiene su tramo del 0-100% y, mientras se redacta (lo que
// más tarda), el porcentaje se acerca poco a poco al final del tramo sin llegar a
// él. Solo marca 100% cuando la respuesta ya llegó.
const TRAMOS = [
  [0, 10], // leer y dividir
  [10, 25], // buscar evidencia
  [25, 90], // redactar (espera la respuesta de la API)
  [90, 100], // verificar
];
const RITMO_REDACCION_MS = 12000; // a los ~12 s se ha recorrido el 63% del tramo de redacción

function barraAvance() {
  const caja = $("#progreso-avance");
  let actual = 0;
  const pintar = (valor, etapa) => {
    actual = Math.max(actual, Math.min(100, valor)); // nunca retrocede
    const redondeado = Math.floor(actual);
    $("#avance-relleno").style.width = `${actual}%`;
    $("#avance-porcentaje").textContent = `${redondeado}%`;
    caja.setAttribute("aria-valuenow", String(redondeado));
    if (etapa) {
      $("#avance-etapa").textContent = etapa;
      caja.setAttribute("aria-valuetext", `${redondeado}% · ${etapa}`);
    }
  };
  $("#avance-relleno").style.width = "0%";
  pintar(0, "Iniciando…");
  return { pintar, valor: () => actual };
}

// Lleva la barra de `desde` a `hasta` en `ms` milisegundos, con un paso suave.
async function avanzar(barra, desde, hasta, ms, etapa) {
  const inicio = performance.now();
  barra.pintar(desde, etapa);
  while (performance.now() - inicio < ms) {
    await esperar(50);
    barra.pintar(desde + ((hasta - desde) * (performance.now() - inicio)) / ms);
  }
  barra.pintar(hasta);
}

async function animarEtapas(peticion) {
  const lista = $("#etapas");
  const items = ETAPAS.map((texto) => h("li", {}, texto));
  lista.replaceChildren(...items);
  const barra = barraAvance();
  mostrarVista("progreso");

  let termino = false;
  peticion.then(
    () => (termino = true),
    () => (termino = true),
  );

  // Si la API falla, generar() captura el error; aquí solo se deja de animar.
  for (let i = 0; i < items.length; i++) {
    const [desde, hasta] = TRAMOS[i];
    items[i].classList.add("activa");
    if (i === 2) {
      // redacción: avanza en forma asintótica mientras la API trabaja
      const inicio = performance.now();
      barra.pintar(desde, ETAPAS[i]);
      while (!termino) {
        await esperar(100);
        const t = performance.now() - inicio;
        barra.pintar(desde + (hasta - desde) * 0.97 * (1 - Math.exp(-t / RITMO_REDACCION_MS)));
      }
      await peticion;
      await avanzar(barra, barra.valor(), hasta, 200, ETAPAS[i]);
    } else {
      await avanzar(barra, Math.max(desde, barra.valor()), hasta, i === 3 ? 300 : 380, ETAPAS[i]);
    }
    items[i].classList.replace("activa", "hecha");
  }
  barra.pintar(100, "✅ Material listo");
  await esperar(350);
}

async function generar(evento) {
  ocultarAvisoReutilizar();
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
    const publica = await llamada;
    estado.tituloDocumento = peticion.titulo;
    estado.textoUsado = $("#contenido").value;
    mostrarResultado(await cargarRegistro(publica), peticion.titulo, publica);
    agregarAlHistorial(publica, peticion.titulo);
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

// La API devuelve la forma pública del enunciado (sin fuentes, secciones ni el detalle de
// la verificación). Para pintar el material con sus secciones y el panel de calidad, la
// interfaz lee el registro completo guardado. Si no se puede, usa la respuesta pública con
// valores por defecto en lo que falta.
async function cargarRegistro(publica) {
  try {
    const resp = await fetch(`/api/v1/contenidos/${publica.almacenamiento_oci.objeto_id}/detalle`);
    if (resp.ok) return { ...(await resp.json()), almacenamiento_oci: publica.almacenamiento_oci };
  } catch {
    // sigue con la respuesta pública
  }
  const ev = publica.evaluacion_calidad;
  return {
    ...publica,
    metadatos: { modelo_llm: "", tiempo_generacion_segundos: 0, ...publica.metadatos },
    contenido_adaptado: { formato: publica.metadatos.formato_generado, ...publica.contenido_adaptado },
    evaluacion_calidad: {
      afirmaciones_total: 0,
      afirmaciones_sustentadas: 0,
      afirmaciones_no_sustentadas: [],
      umbral_aplicado: 0,
      aprobado_por_critico: ev.claridad_pedagogica !== "Baja",
      ...ev,
    },
  };
}

function mostrarResultado(respuesta, tituloDocumento, publica = respuesta) {
  estado.respuesta = respuesta;
  const c = respuesta.contenido_adaptado;
  const m = respuesta.metadatos;

  $("#res-etiqueta").textContent = `${FORMATOS[c.formato]?.icono || ""} ${c.formato} · ${m.perfil_aplicado}`;
  $("#res-titulo").textContent = tituloDocumento;
  const actual = $("#material-actual");
  actual.textContent = `${FORMATOS[c.formato]?.icono || ""} ${c.formato} · ${m.perfil_aplicado}`;
  actual.hidden = false;
  // el podcast es solo audio: se descarga desde su reproductor, no como texto ni diapositivas
  document.querySelector(".descargas").hidden = c.formato === "Podcast";

  renderMetricas(respuesta);
  // el generador cayó al respaldo local (Claude o Gemini sin crédito/cuota, saturado o sin red)
  const proveedor = /claude/i.test(m.modelo_llm) ? "Claude" : "Gemini";
  const aviso = /respaldo/.test(m.modelo_llm)
    ? h("p", { class: "pill pill-aviso" }, `⚠️ ${proveedor} no estuvo disponible: este material se generó con el modo local.`)
    : null;
  $("#p-contenido").replaceChildren(...[aviso, renderContenido(c)].filter(Boolean));
  $("#p-calidad").replaceChildren(renderCalidad(respuesta.evaluacion_calidad));
  $("#p-almacenamiento").replaceChildren(renderAlmacenamiento(respuesta.almacenamiento_oci));
  $("#json").textContent = JSON.stringify(publica, null, 2);

  activarPestana("contenido");
  mostrarVista("resultado");
  habilitarBoton($("#btn-material"), true);
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
    case "Podcast": return renderPodcast(c);
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

// Título de sección sin la numeración del documento de origen ("2. Modos" -> "Modos"),
// para que todos los títulos se vean igual (materiales guardados antes incluidos).
const tituloSeccion = (s) => (s || "").replace(/^\d{1,2}(?:\.\d{1,2})*[.)]?\s+/, "");

// Todas las listas del material con la misma viñeta, y todos los bloques con el mismo formato.
const lista = (textos) => h("ul", { class: "lista" }, textos.map((t) => h("li", {}, t)));
const caja = (titulo, ...contenido) => h("div", { class: "caja" }, h("h4", {}, titulo), ...contenido);

// Título y subtítulo del material, iguales en todos los formatos.
function cabeceraMaterial(titulo, subtitulo) {
  return h(
    "header",
    { class: "material-cabecera" },
    h("h3", { class: "material-titulo" }, titulo),
    subtitulo && h("p", { class: "material-subtitulo" }, subtitulo),
  );
}

// Agrupa las partes consecutivas de una misma sección del documento y pone el
// título de la sección encima de cada grupo. Si el material no trae secciones
// (resultados anteriores o documento sin encabezados), las muestra sin agrupar.
function porSeccion(partes, renderGrupo) {
  const grupos = [];
  partes.forEach((parte, i) => {
    const seccion = tituloSeccion(parte.seccion);
    const ultimo = grupos[grupos.length - 1];
    if (ultimo && ultimo.seccion === seccion) ultimo.partes.push([parte, i]);
    else grupos.push({ seccion, partes: [[parte, i]] });
  });
  const sinTitulos = grupos.every((g) => !g.seccion || g.seccion === "Documento completo");
  if (sinTitulos) return renderGrupo(partes.map((p, i) => [p, i]));
  return grupos.map((g) =>
    h(
      "section",
      { class: "bloque-seccion" },
      h(
        "h4",
        { class: "seccion-titulo" },
        h("span", {}, g.seccion || "Otras partes"),
        h("small", {}, `${g.partes.length} ${g.partes.length === 1 ? "parte" : "partes"}`),
      ),
      renderGrupo(g.partes),
    ),
  );
}

function renderFlashcards(c) {
  const vistas = new Set();
  const progreso = barraProgreso("");
  progreso.actualizar(0, c.items.length, "repasadas");

  const tarjeta = ([item, i]) =>
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
        h(
          "div",
          { class: "cara cara-frente" },
          h("span", { class: "numero-parte" }, `Tarjeta ${i + 1}`),
          h("strong", {}, item.frente),
          h("small", {}, "Toca para ver la respuesta ↻"),
        ),
        h(
          "div",
          { class: "cara cara-dorso" },
          h("span", {}, item.dorso),
          item.pista_didactica && h("span", { class: "pista" }, "💡 ", item.pista_didactica),
        ),
      ),
    );

  return h(
    "div",
    {},
    cabeceraMaterial(c.titulo, c.introduccion_contextualizada),
    progreso.el,
    porSeccion(c.items, (partes) => h("div", { class: "mazo" }, partes.map(tarjeta))),
  );
}

// El quiz se califica sobre 100 y todas las preguntas valen lo mismo.
const PUNTAJE_QUIZ = 100;
const formatoPuntos = (n) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

// Nivel según la nota final: icono, título, mensaje y clase de color.
function nivelQuiz(nota) {
  if (nota >= 90) return ["🏆", "Excelente", "Dominas el contenido del documento.", "nivel-alto"];
  if (nota >= 70) return ["✅", "Aprobado", "Tienes una buena base; repasa los temas de abajo para afianzarla.", "nivel-alto"];
  if (nota >= 50) return ["📚", "En progreso", "Vas por buen camino, pero aún hay temas por reforzar.", "nivel-medio"];
  return ["🔁", "Necesitas repasar", "Vuelve a estudiar los temas de abajo antes de intentarlo de nuevo.", "nivel-bajo"];
}

// Preguntas falladas agrupadas por el tema (sección del documento) que hay que estudiar.
function puntosDeMejora(fallos) {
  if (!fallos.length) {
    return h("p", { class: "mejora-vacia" }, "🎯 ¡Sin errores! No tienes temas pendientes de repaso.");
  }
  const temas = new Map();
  for (const f of fallos) {
    const seccion = tituloSeccion(f.p.seccion);
    const tema = seccion && seccion !== "Documento completo" ? seccion : "Tema general del documento";
    if (!temas.has(tema)) temas.set(tema, []);
    temas.get(tema).push(f);
  }
  return h(
    "div",
    { class: "mejora-temas" },
    [...temas].map(([tema, items]) =>
      h(
        "div",
        { class: "mejora-tema" },
        h("h5", {}, `📌 ${tema}`),
        h(
          "ul",
          { class: "lista" },
          items.map(({ p, i }) =>
            h(
              "li",
              {},
              h("strong", {}, `Pregunta ${i + 1}: `),
              p.enunciado,
              h("span", { class: "mejora-correcta" }, `Respuesta correcta: ${p.opciones[p.indice_correcto]}`),
              h("span", { class: "mejora-estudiar" }, `Qué estudiar: ${p.justificacion}`),
            ),
          ),
        ),
      ),
    ),
  );
}

function renderQuiz(c) {
  const total = c.preguntas.length;
  const valor = PUNTAJE_QUIZ / total;
  const fallos = [];
  let respondidas = 0;
  let aciertos = 0;
  const puntaje = () => Math.round(aciertos * valor);
  const progreso = barraProgreso("");
  const actualizar = () => {
    progreso.actualizar(respondidas, total, `respondidas · ${puntaje()} / ${PUNTAJE_QUIZ} pts`);
  };
  actualizar();

  const resultado = h("section", { class: "quiz-resultado", hidden: true, "aria-live": "polite" });
  const mostrarResultado = () => {
    const nota = puntaje();
    const [icono, titulo, mensaje, clase] = nivelQuiz(nota);
    resultado.className = `quiz-resultado ${clase}`;
    resultado.replaceChildren(
      h(
        "div",
        { class: "resultado-nota" },
        h("span", { class: "resultado-icono" }, icono),
        h(
          "div",
          {},
          h("span", { class: "numero-parte" }, "Resultado final"),
          h("strong", { class: "resultado-puntaje" }, `${nota} / ${PUNTAJE_QUIZ} pts`),
          h("span", { class: "resultado-nivel" }, `${titulo} · ${aciertos} de ${total} correctas`),
        ),
      ),
      h("p", { class: "resultado-mensaje" }, mensaje),
      h("h4", {}, "Puntos de mejora"),
      puntosDeMejora(fallos),
      h(
        "button",
        {
          type: "button",
          class: "btn-secundario",
          onclick: () => {
            const nuevo = renderQuiz(c);
            raiz.replaceWith(nuevo);
            nuevo.scrollIntoView({ behavior: "smooth", block: "start" });
          },
        },
        "↻ Volver a intentar",
      ),
    );
    resultado.hidden = false;
    resultado.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  const pregunta = ([p, i]) => {
    const retro = h("p", { class: "retro", hidden: true });
    const chip = h("span", { class: "puntos-pregunta" }, `${formatoPuntos(valor)} pts`);
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
            const letraCorrecta = String.fromCharCode(65 + p.indice_correcto);
            retro.textContent = acerto
              ? `🎉 ¡Correcto! ${p.justificacion}`
              : `❌ Incorrecto. La respuesta correcta es la ${letraCorrecta}. ${p.justificacion}`;
            retro.hidden = false;
            chip.textContent = acerto ? `+${formatoPuntos(valor)} pts` : `0 de ${formatoPuntos(valor)} pts`;
            chip.classList.add(acerto ? "ganados" : "perdidos");
            respondidas += 1;
            if (acerto) aciertos += 1;
            else fallos.push({ p, i });
            actualizar();
            if (respondidas === total) mostrarResultado();
          },
        },
        h("span", { class: "letra" }, String.fromCharCode(65 + j)),
        h("span", {}, opcion),
      ),
    );
    return h(
      "div",
      { class: "pregunta" },
      h("div", { class: "pregunta-cabecera" }, h("span", { class: "numero-parte" }, `Pregunta ${i + 1}`), chip),
      h("h4", {}, p.enunciado),
      h("div", { class: "opciones" }, botones),
      retro,
    );
  };

  const raiz = h(
    "div",
    {},
    cabeceraMaterial(
      c.titulo,
      `${total} preguntas de opción múltiple · cada una vale ${formatoPuntos(valor)} pts · total ${PUNTAJE_QUIZ} pts.`,
    ),
    progreso.el,
    porSeccion(c.preguntas, (partes) => partes.map(pregunta)),
    resultado,
  );
  return raiz;
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

  // si el paso se titula igual que su sección, el título ya está encima del grupo
  const paso = ([p]) =>
    h(
      "li",
      { "data-orden": p.orden },
      h("span", { class: "numero-parte" }, `Paso ${p.orden}`),
      p.titulo && p.titulo !== p.seccion && tituloSeccion(p.titulo) !== tituloSeccion(p.seccion) && h("h4", {}, p.titulo),
      h("p", {}, p.instruccion),
      p.resultado_esperado && h("p", { class: "resultado-esperado" }, "→ ", p.resultado_esperado),
    );

  return h(
    "div",
    {},
    cabeceraMaterial("Tutorial paso a paso", `🎯 ${c.objetivo}`),
    c.prerrequisitos.length > 0 &&
      caja("📋 Antes de empezar", lista(c.prerrequisitos)),
    porSeccion(c.pasos, (partes) => h("ol", { class: "linea-tiempo" }, partes.map(paso))),
    c.errores_comunes.length > 0 &&
      caja("⚠️ Errores comunes", lista(c.errores_comunes)),
    checklist.length > 0 && caja("✅ Checklist final", progreso.el, checklist),
    c.reto_practico && caja("🏆 Reto práctico", h("p", {}, c.reto_practico)),
  );
}

function renderResumen(c) {
  return h(
    "div",
    {},
    cabeceraMaterial("Resumen ejecutivo", `Lo esencial de «${estado.tituloDocumento || "el documento"}» en un minuto.`),
    caja("📝 Resumen", h("p", { class: "resumen-texto" }, c.resumen)),
    caja("📌 Puntos clave", lista(c.puntos_clave.map(tituloSeccion))),
    c.decisiones_o_riesgos.length > 0 && caja("⚠️ Riesgos y decisiones", lista(c.decisiones_o_riesgos)),
    c.impacto_de_negocio && caja("💼 Impacto", h("p", {}, c.impacto_de_negocio)),
  );
}

const TIPOS_VOZ = [
  { tipo: "femenina", icono: "👩", etiqueta: "Femenina" },
  { tipo: "masculina", icono: "👨", etiqueta: "Masculina" },
];

let audioMuestra = null;

function selectorVoz() {
  const botones = TIPOS_VOZ.map(({ tipo, icono, etiqueta }) => {
    const nombre = estado.voces[tipo];
    return h(
      "button",
      {
        type: "button",
        class: "voz-opcion",
        role: "radio",
        "aria-checked": String(estado.voz === tipo),
        disabled: !nombre,
        title: nombre ? `Voz: ${nombre}` : `No hay una voz ${tipo} instalada en el servidor`,
        onclick: () => {
          estado.voz = tipo;
          botones.forEach((b, i) => b.setAttribute("aria-checked", String(TIPOS_VOZ[i].tipo === tipo)));
        },
      },
      h("span", { class: "voz-icono", "aria-hidden": "true" }, icono),
      h("span", {}, h("strong", {}, etiqueta), h("small", {}, nombre || "No disponible")),
    );
  });

  const escuchar = h("button", { type: "button", class: "btn-secundario" }, "🔊 Escuchar");
  escuchar.addEventListener("click", async () => {
    audioMuestra?.pause();
    escuchar.disabled = true;
    escuchar.textContent = "⏳ Cargando…";
    try {
      const resp = await fetch(`/api/v1/voces/${estado.voz}/muestra`);
      if (!resp.ok) throw new Error(await mensajeDeError(resp));
      audioMuestra = new Audio(URL.createObjectURL(await resp.blob()));
      escuchar.textContent = "🔊 Sonando…";
      audioMuestra.addEventListener("ended", () => (escuchar.textContent = "🔊 Escuchar"));
      await audioMuestra.play();
    } catch (err) {
      escuchar.textContent = "🔊 Escuchar";
      mostrarError(`No se pudo reproducir la muestra: ${err.message}`);
    } finally {
      escuchar.disabled = false;
    }
  });

  const hayVoz = Boolean(estado.voces.femenina || estado.voces.masculina);
  return h(
    "div",
    { class: "voz-selector" },
    h("span", { class: "voz-titulo" }, "Voz de la narración"),
    h("div", { class: "voz-opciones", role: "radiogroup", "aria-label": "Voz de la narración" }, botones),
    hayVoz ? escuchar : h("small", { class: "nota" }, "Sin voces instaladas: el video saldrá sin narración."),
  );
}

function panelVideo() {
  const objetoId = estado.respuesta?.almacenamiento_oci?.objeto_id;
  const titulo = estado.tituloDocumento || "Guion de clase";
  const zona = h("div", { class: "video-zona" });
  const nota = h(
    "p",
    { class: "nota" },
    "Una diapositiva por escena, narrada como en una clase: saludo, transiciones y cierre. Puede tardar un minuto.",
  );
  const boton = h("button", { type: "button", class: "btn-video" }, "🎬 Generar video");

  boton.addEventListener("click", async () => {
    audioMuestra?.pause();
    boton.disabled = true;
    boton.textContent = "⏳ Generando video…";
    nota.textContent = "Preparando diapositivas y narración. No cierres la página.";
    try {
      const parametros = new URLSearchParams({ titulo, voz: estado.voz });
      const resp = await fetch(`/api/v1/contenidos/${objetoId}/video?${parametros}`);
      if (!resp.ok) throw new Error(await mensajeDeError(resp));
      const url = URL.createObjectURL(await resp.blob());
      const base = titulo.replace(/[^\p{L}\p{N}]+/gu, "_").replace(/^_|_$/g, "") || "guion";
      zona.replaceChildren(
        h("video", { class: "video", src: url, controls: true, preload: "auto" }),
        h("a", { class: "btn-secundario", href: url, download: `${base}_voz_${estado.voz}.mp4` }, "⬇️ Descargar MP4"),
      );
      nota.textContent = `Listo, narrado con voz ${estado.voz}. Puedes cambiar la voz y generarlo otra vez.`;
      boton.textContent = "🎬 Generar de nuevo";
    } catch (err) {
      boton.textContent = "🎬 Reintentar";
      nota.textContent = `No se pudo generar el video: ${err.message}`;
    } finally {
      boton.disabled = false;
    }
  });

  return h(
    "div",
    { class: "panel-video" },
    h("div", { class: "panel-video-cabecera" }, h("div", {}, h("h4", {}, "🎬 Video de la clase"), nota), boton),
    selectorVoz(),
    zona,
  );
}

function renderGuion(c) {
  const reloj = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  // minuto en que empieza cada escena, acumulando las anteriores
  const inicios = [];
  c.escenas.reduce((acumulado, e) => (inicios.push(acumulado), acumulado + e.duracion_seg), 0);
  const escena = ([e, i]) =>
    h(
      "div",
      { class: "escena" },
      h("div", { class: "escena-tiempo" }, reloj(inicios[i]), h("small", {}, `Escena ${e.orden} · ${e.duracion_seg}s`)),
      h("div", {}, h("p", {}, e.narracion), e.apoyo_visual && h("p", { class: "visual" }, "🖼️ ", e.apoyo_visual)),
    );

  return h(
    "div",
    {},
    cabeceraMaterial(
      "Guion de clase",
      `🎬 ${c.escenas.length} escenas · duración total aproximada: ${c.duracion_total_min} min`,
    ),
    estado.respuesta?.almacenamiento_oci?.objeto_id && panelVideo(),
    porSeccion(c.escenas, (partes) => partes.map(escena)),
  );
}

// El podcast se entrega solo como audio: al mostrar el resultado se graba (o se
// toma de la caché) y se ofrece el reproductor, sin transcripción en pantalla.
function renderPodcast(c) {
  const objetoId = estado.respuesta?.almacenamiento_oci?.objeto_id;
  const titulo = estado.tituloDocumento || "podcast";
  const hayVoz = Boolean(estado.voces.femenina || estado.voces.masculina);
  const zona = h("div", { class: "video-zona" });
  const nota = h("p", { class: "nota" });
  const reintentar = h("button", { type: "button", class: "btn-video", hidden: true }, "🎙️ Reintentar");

  async function grabar() {
    reintentar.hidden = true;
    nota.textContent = "⏳ Ana y Leo están grabando el episodio. Puede tardar uno o dos minutos.";
    try {
      const resp = await fetch(`/api/v1/contenidos/${objetoId}/podcast`);
      if (!resp.ok) throw new Error(await mensajeDeError(resp));
      const naturales = resp.headers.get("X-Podcast-Voces") === "gemini";
      const url = URL.createObjectURL(await resp.blob());
      const base = titulo.replace(/[^\p{L}\p{N}]+/gu, "_").replace(/^_|_$/g, "") || "podcast";
      const audio = h("audio", { class: "audio", src: url, controls: true, preload: "auto" });
      zona.replaceChildren(
        audio,
        h("a", { class: "btn-secundario", href: url, download: `${base}_podcast.mp3` }, "⬇️ Descargar MP3"),
      );
      const voces = naturales
        ? "Voces naturales."
        : "Voces del sistema: las voces naturales no estuvieron disponibles.";
      nota.textContent = `Episodio con Ana y Leo. ${voces}`;
      // la duración real del MP3, no la estimada al redactar
      audio.addEventListener("loadedmetadata", () => {
        const s = Math.round(audio.duration);
        nota.textContent = `Episodio de ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} min con Ana y Leo. ${voces}`;
      });
    } catch (err) {
      nota.textContent = `No se pudo grabar el episodio: ${err.message}`;
      reintentar.hidden = false;
    }
  }
  reintentar.addEventListener("click", grabar);

  if (!objetoId) nota.textContent = "El episodio no se guardó, así que no se puede grabar el audio.";
  else if (!hayVoz) nota.textContent = "No hay voces instaladas en el servidor para grabar el episodio.";
  else grabar();

  // temas del episodio: las secciones del documento que explica Leo, en orden
  const temas = [
    ...new Set(c.intervenciones.map((x) => tituloSeccion(x.seccion)).filter((s) => s && s !== "Documento completo")),
  ];

  return h(
    "div",
    {},
    cabeceraMaterial(c.titulo, `🎙️ Conversación entre Ana y Leo · unos ${c.duracion_total_min} min`),
    h(
      "div",
      { class: "panel-video" },
      h("div", { class: "panel-video-cabecera" }, h("div", {}, h("h4", {}, "🎧 Escucha el episodio"), nota), reintentar),
      zona,
    ),
    temas.length > 0 &&
      caja("📚 Temas del episodio", lista(temas)),
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

async function exportar(formato, boton) {
  const objetoId = estado.respuesta?.almacenamiento_oci?.objeto_id;
  if (!objetoId) return;
  mostrarError("");
  boton.disabled = true;
  try {
    const parametros = new URLSearchParams({ formato, titulo: estado.tituloDocumento || "" });
    const resp = await fetch(`/api/v1/contenidos/${objetoId}/exportar?${parametros}`);
    if (!resp.ok) throw new Error(await mensajeDeError(resp));
    const blob = await resp.blob();
    const nombreBase = estado.tituloDocumento.replace(/[^\p{L}\p{N}]+/gu, "_").replace(/^_|_$/g, "") || "material";
    const enlace = h("a", {
      href: URL.createObjectURL(blob),
      download: `${nombreBase}${{ markdown: ".md", anki_csv: "_anki.csv", pptx: ".pptx", docx: ".docx" }[formato]}`,
    });
    enlace.click();
    URL.revokeObjectURL(enlace.href);
  } catch (err) {
    mostrarError(`No se pudo descargar: ${err.message}`);
  } finally {
    boton.disabled = false;
  }
}

// ---------- Historial ----------

function agregarAlHistorial(respuesta, titulo) {
  const objetoId = respuesta.almacenamiento_oci.objeto_id;
  const lista = leerHistorial().filter((x) => x.objeto_id !== objetoId);
  lista.unshift({
    objeto_id: objetoId,
    titulo,
    formato: respuesta.metadatos.formato_generado,
    perfil: respuesta.metadatos.perfil_aplicado,
    fecha: new Date().toISOString(),
  });
  guardarHistorial(lista);
  renderHistorial();
}

// Texto comparable para buscar: sin tildes y en minúsculas ("Guión" encuentra "guion").
const normalizar = (texto) =>
  texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();

function renderHistorial() {
  const lista = leerHistorial();
  $("#historial-caja").hidden = lista.length === 0;
  habilitarBoton($("#btn-historial"), lista.length > 0, "Aún no hay materiales en el historial");
  if (lista.length === 0) abrirHistorial(false);
  const contador = $("#contador-historial");
  contador.textContent = lista.length;
  contador.hidden = lista.length === 0;
  // la misma lista en el desplegable del menú y al pie de la página; el desplegable se
  // puede filtrar con su buscador
  const consulta = normalizar($("#buscar-historial").value);
  const filtrada = consulta
    ? lista.filter((item) => normalizar(`${item.titulo} ${item.formato} ${item.perfil}`).includes(consulta))
    : lista;
  $("#historial-sin-resultados").hidden = filtrada.length > 0;
  const elementos = (items) =>
    items.map((item) =>
      h(
        "li",
        {},
        h(
          "button",
          {
            type: "button",
            onclick: () => {
              abrirHistorial(false);
              abrirMenu(false);
              abrirDelHistorial(item);
            },
          },
          h("span", {}, `${FORMATOS[item.formato]?.icono || "📄"} ${item.titulo}`),
          h("small", {}, `${item.formato} · ${item.perfil} · ${new Date(item.fecha).toLocaleString()}`),
        ),
      ),
    );
  $("#historial").replaceChildren(...elementos(lista));
  $("#historial-lista-menu").replaceChildren(...elementos(filtrada));
}

async function abrirDelHistorial(item) {
  mostrarError("");
  try {
    const resp = await fetch(`/api/v1/contenidos/${item.objeto_id}`);
    if (!resp.ok) throw new Error(await mensajeDeError(resp));
    const publica = await resp.json();
    estado.tituloDocumento = item.titulo;
    mostrarResultado(await cargarRegistro(publica), item.titulo, publica);
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
  document.querySelectorAll(".menu-enlaces [data-seccion]").forEach((b) => {
    const activo = b.dataset.seccion === nombre;
    b.classList.toggle("activo", activo);
    if (activo) b.setAttribute("aria-current", "true");
    else b.removeAttribute("aria-current");
  });
}

// Un botón del menú sin nada que mostrar se desactiva y explica por qué al pasar el cursor.
function habilitarBoton(boton, habilitado, motivo = "") {
  boton.disabled = !habilitado;
  boton.title = habilitado ? boton.dataset.titulo || "" : motivo;
}

function abrirHistorial(abierto) {
  $("#historial-menu").hidden = !abierto;
  $("#btn-historial").setAttribute("aria-expanded", String(abierto));
  if (abierto) $("#buscar-historial").focus();
}

// Panel del indicador de almacenamiento ("Guardado local" / "Guardando en OCI").
function abrirEstado(abierto) {
  $("#estado-menu").hidden = !abierto;
  $("#estado-oci").setAttribute("aria-expanded", String(abierto));
  $("#btn-ver-guardado").hidden = !estado.respuesta;
}

// Vacía el formulario. Si hay texto escrito que todavía no se usó para generar nada,
// pide confirmación antes de borrarlo.
function vaciarFormulario() {
  const contenido = $("#contenido").value.trim();
  if (contenido && contenido !== estado.textoUsado.trim() && contenido !== EJEMPLO.trim()) {
    if (!confirm("¿Empezar un material nuevo? Se borrará el texto que escribiste y aún no usaste.")) return false;
  }
  const anterior = {
    modo: estado.modo,
    titulo: $("#titulo").value,
    contenido: $("#contenido").value,
    archivo: estado.archivo,
  };
  estado.documentoAnterior = anterior.contenido.trim() || anterior.archivo ? anterior : null;
  $("#titulo").value = "";
  $("#contenido").value = "";
  $("#contenido").dispatchEvent(new Event("input", { bubbles: true }));
  $("#archivo").value = "";
  elegirArchivo(null);
  return true;
}

function ocultarAvisoReutilizar() {
  $("#aviso-reutilizar").hidden = true;
}

// "Usar el mismo documento": vuelve a poner el documento anterior para generar otra
// versión (otro perfil o formato) sin pegarlo ni subirlo de nuevo.
function reutilizarDocumento() {
  const doc = estado.documentoAnterior;
  if (!doc) return;
  cambiarModo(doc.modo);
  $("#titulo").value = doc.titulo;
  $("#contenido").value = doc.contenido;
  $("#contenido").dispatchEvent(new Event("input", { bubbles: true }));
  if (doc.archivo) elegirArchivo(doc.archivo);
  ocultarAvisoReutilizar();
  document.querySelectorAll(".paso")[1]?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// Lleva al formulario y lo resalta, sin borrar nada.
function irAlFormulario() {
  mostrarError("");
  if ($("#progreso").hidden) mostrarVista("vacio"); // mientras se genera, no se interrumpe
  marcarSeccion("inicio");
  window.scrollTo({ top: 0, behavior: "smooth" });
  const formulario = $("#form");
  formulario.classList.remove("resaltado");
  void formulario.offsetWidth; // reinicia la animación si se pulsa dos veces seguidas
  formulario.classList.add("resaltado");
  const campo = estado.modo === "archivo" ? $("#archivo") : $("#titulo");
  campo.focus({ preventScroll: true });
  if (campo.select) campo.select();
}

// "Nuevo material": formulario vacío para otro documento. El material anterior sigue en
// "Mi material" y en el Historial, y su documento se puede recuperar con un clic.
function nuevoMaterial() {
  if (!vaciarFormulario()) return;
  $("#aviso-reutilizar").hidden = !estado.documentoAnterior;
  irAlFormulario();
}

// Atajos de teclado del menú: N, M, H y ?. No actúan mientras se escribe en un campo ni
// con un diálogo abierto.
function atajoDeTeclado(e) {
  if (e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
  if (e.target.closest("input, textarea, select, [contenteditable]") || $("#dialogo-como").open) return;
  const accion = {
    n: () => nuevoMaterial(),
    m: () => !$("#btn-material").disabled && verMaterial(),
    h: () => !$("#btn-historial").disabled && abrirHistorial($("#historial-menu").hidden),
    "?": () => $("#btn-como").click(),
  }[e.key.toLowerCase()];
  if (!accion) return;
  e.preventDefault();
  accion();
}

function verMaterial() {
  if (!estado.respuesta) return;
  if ($("#progreso").hidden) mostrarVista("resultado");
  marcarSeccion("material");
  $("#resultado").scrollIntoView({ behavior: "smooth", block: "start" });
}

function iniciarMenu() {
  pintarBotonTema();
  $("#btn-tema").addEventListener("click", alternarTema);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", pintarBotonTema);

  $("#btn-menu").addEventListener("click", () => abrirMenu(!$("#menu").classList.contains("abierto")));
  // En escritorio el formulario y el material se ven lado a lado, así que no se
  // deduce la sección por el scroll: se resalta la que el usuario eligió.
  $("#btn-nuevo").addEventListener("click", () => {
    abrirMenu(false);
    nuevoMaterial();
  });
  $("#btn-reutilizar").addEventListener("click", reutilizarDocumento);
  $("#buscar-historial").addEventListener("input", renderHistorial);
  document.addEventListener("keydown", atajoDeTeclado);
  // escribir o elegir otro documento descarta la oferta de reutilizar el anterior
  ["#titulo", "#contenido"].forEach((sel) => $(sel).addEventListener("input", (e) => e.isTrusted && ocultarAvisoReutilizar()));
  $("#archivo").addEventListener("change", ocultarAvisoReutilizar);
  $(".marca").addEventListener("click", (e) => {
    e.preventDefault();
    irAlFormulario();
  });
  $("#btn-material").addEventListener("click", () => {
    abrirMenu(false);
    verMaterial();
  });

  $("#btn-historial").addEventListener("click", () => abrirHistorial($("#historial-menu").hidden));
  $("#estado-oci").addEventListener("click", () => abrirEstado($("#estado-menu").hidden));
  $("#btn-ver-guardado").addEventListener("click", () => {
    abrirEstado(false);
    abrirMenu(false);
    verMaterial();
    activarPestana("almacenamiento");
  });
  $("#btn-borrar-historial").addEventListener("click", () => {
    guardarHistorial([]);
    renderHistorial();
  });
  // clic fuera: cierra el desplegable del historial y el menú del móvil
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#btn-historial, #historial-menu")) abrirHistorial(false);
    if (!e.target.closest("#estado-oci, #estado-menu")) abrirEstado(false);
    if (!e.target.closest(".navbar")) abrirMenu(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("#historial-menu").hidden) $("#btn-historial").focus();
    if (!$("#estado-menu").hidden) $("#estado-oci").focus();
    abrirHistorial(false);
    abrirEstado(false);
    abrirMenu(false);
  });

  const dialogo = $("#dialogo-como");
  $("#btn-como").addEventListener("click", () => {
    abrirMenu(false);
    abrirHistorial(false);
    dialogo.showModal();
  });
  dialogo.addEventListener("click", (e) => e.target === dialogo && dialogo.close()); // clic fuera cierra
}

// ---------- Inicio ----------

function iniciar() {
  iniciarMenu();
  document.querySelectorAll(".seg").forEach((b) => b.addEventListener("click", () => cambiarModo(b.dataset.modo)));
  document.querySelectorAll(".pestana").forEach((b) => b.addEventListener("click", () => activarPestana(b.dataset.pestana)));
  document.querySelectorAll("[data-exportar]").forEach((b) => b.addEventListener("click", () => exportar(b.dataset.exportar, b)));

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
