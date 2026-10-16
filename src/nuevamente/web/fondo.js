// Fondo animado: una red de nodos que se mueven, se conectan cuando están cerca y
// por cuyas conexiones viajan pulsos de datos. Es decorativo: va detrás del
// contenido, no recibe clics y se detiene si el sistema pide reducir el movimiento.

const lienzo = document.createElement("canvas");
lienzo.className = "fondo-red";
lienzo.setAttribute("aria-hidden", "true");
document.body.prepend(lienzo);

const ctx = lienzo.getContext("2d");
const movimientoReducido = matchMedia("(prefers-reduced-motion: reduce)");
const DISTANCIA = 150;          // distancia máxima para unir dos nodos (px)
const DISTANCIA_PUNTERO = 190;  // radio en que el puntero atrae conexiones

let ancho = 0, alto = 0, nodos = [], pulsos = [], colores = {};
let puntero = null, animacion = null;

function leerColores() {
  const css = getComputedStyle(document.documentElement);
  colores = {
    primario: css.getPropertyValue("--primario").trim() || "#6c4ef5",
    menta: css.getPropertyValue("--menta").trim() || "#12a37f",
    oscuro: css.colorScheme === "dark" || document.documentElement.dataset.theme === "dark"
      || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches),
  };
}

function conAlfa(hex, alfa) {
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alfa})`;
}

function crearNodos() {
  const cantidad = Math.min(110, Math.round((ancho * alto) / 15000));
  nodos = Array.from({ length: cantidad }, () => ({
    x: Math.random() * ancho,
    y: Math.random() * alto,
    vx: (Math.random() - 0.5) * 0.35,
    vy: (Math.random() - 0.5) * 0.35,
    r: 1.2 + Math.random() * 1.8,
  }));
  pulsos = [];
}

function ajustarTamano() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  ancho = window.innerWidth;
  alto = window.innerHeight;
  lienzo.width = ancho * dpr;
  lienzo.height = alto * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  crearNodos();
}

function lanzarPulso() {
  const a = nodos[Math.floor(Math.random() * nodos.length)];
  const cercanos = nodos.filter((b) => b !== a && Math.hypot(a.x - b.x, a.y - b.y) < DISTANCIA);
  if (!cercanos.length) return;
  pulsos.push({ a, b: cercanos[Math.floor(Math.random() * cercanos.length)], t: 0 });
}

function dibujar() {
  const intensidad = colores.oscuro ? 1 : 0.75;
  ctx.clearRect(0, 0, ancho, alto);

  // Conexiones entre nodos cercanos
  ctx.lineWidth = 1;
  for (let i = 0; i < nodos.length; i++) {
    const a = nodos[i];
    for (let j = i + 1; j < nodos.length; j++) {
      const b = nodos[j];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (d < DISTANCIA) {
        ctx.strokeStyle = conAlfa(colores.primario, (1 - d / DISTANCIA) * 0.22 * intensidad);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
    }
    // Conexiones hacia el puntero
    if (puntero) {
      const d = Math.hypot(a.x - puntero.x, a.y - puntero.y);
      if (d < DISTANCIA_PUNTERO) {
        ctx.strokeStyle = conAlfa(colores.menta, (1 - d / DISTANCIA_PUNTERO) * 0.35 * intensidad);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(puntero.x, puntero.y);
        ctx.stroke();
      }
    }
  }

  // Nodos
  for (const n of nodos) {
    ctx.fillStyle = conAlfa(colores.primario, 0.45 * intensidad);
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
    ctx.fill();
  }

  // Pulsos de datos viajando por las conexiones
  for (const p of pulsos) {
    const x = p.a.x + (p.b.x - p.a.x) * p.t;
    const y = p.a.y + (p.b.y - p.a.y) * p.t;
    const brillo = ctx.createRadialGradient(x, y, 0, x, y, 7);
    brillo.addColorStop(0, conAlfa(colores.menta, 0.9 * intensidad));
    brillo.addColorStop(1, conAlfa(colores.menta, 0));
    ctx.fillStyle = brillo;
    ctx.beginPath();
    ctx.arc(x, y, 7, 0, Math.PI * 2);
    ctx.fill();
  }
}

function avanzar() {
  for (const n of nodos) {
    n.x += n.vx;
    n.y += n.vy;
    if (n.x < 0 || n.x > ancho) n.vx *= -1;
    if (n.y < 0 || n.y > alto) n.vy *= -1;
  }
  for (const p of pulsos) p.t += 0.012;
  pulsos = pulsos.filter((p) => p.t < 1 && Math.hypot(p.a.x - p.b.x, p.a.y - p.b.y) < DISTANCIA * 1.2);
  if (pulsos.length < 14 && Math.random() < 0.08) lanzarPulso();
}

function cuadro() {
  avanzar();
  dibujar();
  animacion = requestAnimationFrame(cuadro);
}

function iniciar() {
  detener();
  if (movimientoReducido.matches) dibujar();  // red estática, sin movimiento
  else animacion = requestAnimationFrame(cuadro);
}

function detener() {
  if (animacion) cancelAnimationFrame(animacion);
  animacion = null;
}

let esperaTamano;
window.addEventListener("resize", () => {
  clearTimeout(esperaTamano);
  esperaTamano = setTimeout(() => { ajustarTamano(); iniciar(); }, 150);
});
window.addEventListener("pointermove", (e) => { puntero = { x: e.clientX, y: e.clientY }; }, { passive: true });
document.addEventListener("pointerleave", () => { puntero = null; });
document.addEventListener("visibilitychange", () => (document.hidden ? detener() : iniciar()));
movimientoReducido.addEventListener("change", iniciar);

// Cambios de tema (botón claro/oscuro o preferencia del sistema)
const releerColores = () => { leerColores(); if (!animacion) dibujar(); };
new MutationObserver(releerColores).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", releerColores);

leerColores();
ajustarTamano();
iniciar();
