"""Pruebas del enrutado por salud: circuit breaker, orden por latencia y carrera.

Responsable: Diana Dure (QA Tester).

Nada aquí toca la red: los proveedores son dobles que cuentan llamadas, fallan o se tardan
bajo demanda, y el reloj del router se inyecta para que los cooldowns se puedan probar sin
esperar de verdad.
"""
from __future__ import annotations

import threading
import time

import pytest
from pydantic import BaseModel

from nuevamente.llm.base import LLMError
from nuevamente.llm.salud import ABIERTO, CERRADO, SEMIABIERTO, RouterSalud


class Salida(BaseModel):
    titulo: str
    puntos: list[str]


class Reloj:
    """Reloj manual: los cooldowns se prueban avanzando el tiempo, no durmiendo."""

    def __init__(self) -> None:
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora

    def avanza(self, segundos: float) -> None:
        self.ahora += segundos


class Lento:
    """Proveedor que tarda lo que se le pida y puede fallar las veces que se le pidan."""

    def __init__(self, etiqueta: str, *, segundos: float = 0.0, falla: bool = False) -> None:
        self.etiqueta = etiqueta
        self.nombre_modelo = f"{etiqueta}-modelo"
        self.segundos = segundos
        self.falla = falla
        self.llamadas = 0
        self.libre = threading.Event()
        self.libre.set()

    @property
    def clave_proveedor(self) -> str:
        return self.etiqueta.lower()

    def generar_estructurado(self, schema, system, user):
        self.llamadas += 1
        self.libre.clear()
        try:
            if self.segundos:
                time.sleep(self.segundos)
            if self.falla:
                raise LLMError("503 high demand")
            return schema.model_validate({"titulo": self.etiqueta, "puntos": ["a"]})
        finally:
            self.libre.set()


def _router(claves, reloj=None, **kwargs):
    return RouterSalud(claves, reloj=reloj or Reloj(), **kwargs)


@pytest.fixture
def cfg(monkeypatch):
    """Ajusta la configuración de la cadena en un test.

    `Settings` es un dataclass congelado, así que no se puede monkeypatchear un atributo su
   elta: se sustituye el objeto entero que el módulo under test tiene importado, que es lo
    que ya hace el resto de la suite para Gemini.

    Antes de aplicar los cambios del test se anula lo que sí depende del entorno. `Settings` se
    construye al importar `config`, leyendo el `.env` de quien esté en la máquina, así que sin
    esto estos tests dependerían de qué priors tenga puestos el desarrollador y el orden de
    los dobles cambiaría bajo los pies.
    """
    from dataclasses import replace

    import nuevamente.llm.cadena_llm as modulo
    from nuevamente.config import settings as reales

    def _cfg(**cambios) -> None:
        neutro = replace(
            reales,
            salud_activada=True,
            salud_latencia_inicial={},
            carrera_activada=False,
        )
        monkeypatch.setattr(modulo, "settings", replace(neutro, **cambios))

    return _cfg


# --- Orden por latencia ------------------------------------------------------


def test_sin_datos_respeta_el_orden_configurado():
    """Sin historial ni priors, el router no inventa una ventaja: manda LLM_CADENA."""
    r = _router(["gemini", "groq", "openrouter"])
    assert r.ordenar(["gemini", "groq", "openrouter"]) == ["gemini", "groq", "openrouter"]


def test_los_priors_sirven_para_arrancar_en_frio():
    """La primera petición no debe esperar a descubrir que Groq es 3 veces más rápido."""
    r = _router(["gemini", "groq"], latencia_inicial={"gemini": 4.0, "groq": 1.2})
    assert r.ordenar(["gemini", "groq"]) == ["groq", "gemini"]


def test_el_mas_rapido_medido_pasa_delante():
    r = _router(["gemini", "groq"])
    r.registrar_exito("gemini", 5.0)
    r.registrar_exito("groq", 1.1)
    assert r.ordenar(["gemini", "groq"]) == ["groq", "gemini"]


def test_la_latencia_es_media_movil_no_promedio():
    """Una llamada mala reciente tiene que mover el aguja, pero no borrar el historial."""
    r = _router(["gemini", "groq"], alfa=0.3)
    for _ in range(9):
        r.registrar_exito("gemini", 2.0)
    r.registrar_exito("groq", 1.0)
    assert r.estado_de("gemini").latencia == pytest.approx(2.0)

    r.registrar_exito("gemini", 50.0)
    assert 2.0 < r.estado_de("gemini").latencia < 17.0
    assert r.ordenar(["gemini", "groq"]) == ["groq", "gemini"]


# --- Circuit breaker ---------------------------------------------------------


def test_un_fallo_aislado_no_abre_el_circuito():
    """Con umbral 2, un 503 suelto no apaga a un proveedor sano."""
    r = _router(["gemini", "groq"], umbral_fallos=2)
    r.registrar_fallo("gemini", "503")
    assert r.estado_de("gemini").circuito == CERRADO


def test_una_racha_de_fallos_abre_el_circuito_y_lo_aparta():
    r = _router(["gemini", "groq"], umbral_fallos=2)
    r.registrar_exito("groq", 1.1)
    r.registrar_fallo("gemini", "503")
    r.registrar_fallo("gemini", "503")
    assert r.estado_de("gemini").circuito == ABIERTO
    assert r.ordenar(["gemini", "groq"]) == ["groq", "gemini"]


def test_lentura_no_considera_caida():
    """Un proveedor que responde tarde sigue siendo sano: baja de puesto, no se apaga."""
    r = _router(["gemini", "groq"], umbral_fallos=1)
    r.registrar_exito("gemini", 40.0)
    r.registrar_exito("groq", 1.1)

    assert r.estado_de("gemini").circuito == CERRADO
    assert r.estado_de("gemini").fallos == 0
    assert r.ordenar(["gemini", "groq"]) == ["groq", "gemini"]


def test_tras_el_cooldown_el_caido_vuelve_a_probarse():
    reloj = Reloj()
    r = _router(["gemini", "groq"], reloj=reloj, umbral_fallos=1, cooldown=45.0)
    r.registrar_fallo("gemini", "503")
    assert r.estado_de("gemini").circuito == ABIERTO

    reloj.avanza(44.0)
    assert r.estado_de("gemini").circuito == ABIERTO

    reloj.avanza(2.0)
    # Al ordenar, el cooldown vencido lo pasa a semiabierto y lo devuelve a lalid.
    assert r.ordenar(["gemini", "groq"])[0] == "gemini"
    assert r.estado_de("gemini").circuito == SEMIABIERTO


def test_el_caido_recuperado_vuelve_a_competir_y_a_ganar():
    """Lo que se pidió: si el proveedor lento se recuperó, vuelve a ser el primero."""
    reloj = Reloj()
    r = _router(["gemini", "groq"], reloj=reloj, umbral_fallos=1, cooldown=45.0)
    r.registrar_exito("groq", 5.0)
    r.registrar_fallo("gemini", "503")
    reloj.avanza(46.0)
    r.ordenar(["gemini", "groq"])

    # Se recuperó y además ahora es más rápido que el que estaba sano.
    r.registrar_exito("gemini", 0.9)

    assert r.estado_de("gemini").circuito == CERRADO
    assert r.estado_de("gemini").veces_abierto == 0
    assert r.ordenar(["gemini", "groq"]) == ["gemini", "groq"]


def test_lo_no_probado_no_gana_por_el_hecho_de_no_probarse():
    """Poner al desconocido primero deja que gane el más rápido y peor: el TemplateLLM local.

    Se probó contra la cadena real: el extractivo responde en 1 ms, se quedaba ganando siempre y
    las siguientes peticiones salían con material extractivo en vez de generado."""
    r = _router(["groq", "template"])
    r.registrar_exito("template", 0.001)
    assert r.ordenar(["groq", "template"])[0] == "template"

    r2 = _router(["gemini", "groq", "template"], latencia_inicial={"gemini": 4.0, "groq": 1.2})
    assert r2.ordenar(["gemini", "groq", "template"]) == ["groq", "gemini", "template"]


def test_un_proveedor_ganador_lento_no_bloquea_el_resto():
    """Si el que gana siempre es el lento, el resto no llega a probarse nunca.

    El que evita ese atasco no es el orden (explorar en secuencial es pagar la latencia del
    desconocido) sino la carrera, que pregunta a varios a la vez."""
    r = _router(["gemini", "groq"])
    r.registrar_exito("gemini", 40.0)
    assert r.estado_de("groq").exitos == 0
    assert r.ordenar(["gemini", "groq"]) == ["gemini", "groq"]

    # Con prior, en cambio, el orden sí sabe a priori que Groq es mejor y lo pone delante.
    r2 = _router(["gemini", "groq"], latencia_inicial={"gemini": 40.0, "groq": 1.2})
    assert r2.ordenar(["gemini", "groq"]) == ["groq", "gemini"]


def test_un_caido_antes_que_un_desconocido():
    """Sin medir, un circuito abierto es lo único que sabemos con certeza: prima sobre el
    silencio de un proveedor nunca probado."""
    r = _router(["gemini", "template"], umbral_fallos=1)
    r.registrar_fallo("gemini", "503")
    assert r.ordenar(["gemini", "template"]) == ["template", "gemini"]


def test_el_cooldown_crece_cada_vez_que_se_reincide():
    reloj = Reloj()
    r = _router(["gemini"], reloj=reloj, umbral_fallos=1, cooldown=10.0, cooldown_max=40.0)
    esperas = []
    for _ in range(5):
        r.registrar_fallo("gemini", "503")
        esperas.append(r.estado_de("gemini").cooldown_actual(10.0, 40.0))
        reloj.avanza(60.0)
        r.ordenar(["gemini"])  # reabre la puerta para el siguiente ciclo
    assert esperas == [10.0, 20.0, 40.0, 40.0, 40.0]


def test_nunca_se_descarta_a_un_proveedor_del_todo():
    """Si todos están caídos, el sistema los prueba igual: no generar es peor que esperar."""
    r = _router(["gemini", "groq"], umbral_fallos=1)
    r.registrar_fallo("gemini", "503")
    r.registrar_fallo("groq", "429")
    assert sorted(r.ordenar(["gemini", "groq"])) == ["gemini", "groq"]


def test_ordenar_no_repite_ni_omite_proveedores():
    r = _router(["gemini", "groq", "openrouter"], umbral_fallos=1)
    r.registrar_exito("openrouter", 9.0)
    r.registrar_fallo("groq", "429")
    orden = r.ordenar(["gemini", "groq", "openrouter"])
    assert sorted(orden) == ["gemini", "groq", "openrouter"]
    assert len(set(orden)) == 3


def test_perder_una_carrera_no_es_contar_como_caida():
    """Un proveedor lento pierde la carrera, pero está sano: perder no es estar caído."""
    r = _router(["gemini", "groq"])
    r.registrar_latencia("gemini", 8.0)
    assert r.estado_de("gemini").circuito == CERRADO
    assert r.estado_de("gemini").fallos == 0
    assert r.estado_de("gemini").latencia == pytest.approx(8.0)


def test_el_estado_reporta_lo_pedido_por_la_api():
    r = _router(["gemini", "groq"], umbral_fallos=1, cooldown=30.0)
    r.registrar_exito("groq", 1.25)
    r.registrar_fallo("gemini", "503 high demand")
    filas = {f["proveedor"]: f for f in r.estado()}

    assert filas["groq"]["estado"] == CERRADO
    assert filas["groq"]["latencia_s"] == 1.25
    assert filas["gemini"]["estado"] == ABIERTO
    assert filas["gemini"]["reintento_en_s"] == 30.0
    assert "503" in filas["gemini"]["ultimo_error"]


# --- Integración con CadenaLLM -----------------------------------------------


def test_la_cadena_no_paga_al_proveedor_caido(cfg):
    """El problema que resuelve: antes cada request se comía los reintentos de Gemini.

    No hace falta ni abrirle el circuito: basta con que el que falla baje al final. Su error
    se paga una vez, no en cada request."""
    from nuevamente.llm.cadena_llm import CadenaLLM

    cfg(salud_umbral_fallos=2)
    gemini = Lento("gemini", falla=True)
    groq = Lento("groq")
    cadena = CadenaLLM([gemini, groq])

    for _ in range(6):
        cadena.generar_estructurado(Salida, "sys", "user")

    assert gemini.llamadas == 1
    assert groq.llamadas == 6
    assert cadena.router.estado_de("gemini").fallos == 1
    assert cadena.router.ordenar(["gemini", "groq"]) == ["groq", "gemini"]
    assert cadena.nombre_modelo == "groq:groq-modelo"


def test_un_proveedor_aplazado_se_acaba_apagando_si_el_sano_tambien_cae(cfg):
    """El que se aplazó no se olvida: si el sano abre su circuito, vuelve a tocarse y cuenta."""
    from nuevamente.llm.cadena_llm import CadenaLLM

    cfg(salud_umbral_fallos=2)
    gemini = Lento("gemini", falla=True)
    groq = Lento("groq")
    cadena = CadenaLLM([gemini, groq])

    # Un request: Gemini falla y queda atrás; Groq gana y ya es el medido más rápido.
    cadena.generar_estructurado(Salida, "sys", "user")
    assert gemini.llamadas == 1

    groq.falla = True
    # Ya no queda a quién llamar: sin respaldo local la cadena debe fallar, no inventarse texto.
    for _ in range(4):
        with pytest.raises(LLMError):
            cadena.generar_estructurado(Salida, "sys", "user")

    assert cadena.router.estado_de("gemini").circuito == ABIERTO
    assert cadena.router.estado_de("groq").circuito == ABIERTO
    assert gemini.llamadas == 2  # la del primer request, más la que le tocó al caer Groq


def test_la_cadena_sigue_funcionando_si_todos_estan_caidos(cfg):
    from nuevamente.llm.cadena_llm import CadenaLLM

    cfg(salud_umbral_fallos=1)
    cadena = CadenaLLM([Lento("gemini", falla=True), Lento("groq", falla=True)])
    with pytest.raises(LLMError, match="Ninguna API"):
        cadena.generar_estructurado(Salida, "sys", "user")
    # Aunque los dos estén caídos, se han intentado los dos.
    assert cadena.router.estado_de("gemini").circuito == ABIERTO
    assert cadena.router.estado_de("groq").circuito == ABIERTO


def test_la_carrera_se_queda_con_el_primer_que_contesta(cfg):
    """El objetivo: preguntar a los dos y ganar el primero, sin esperar al lento."""
    from nuevamente.llm.cadena_llm import CadenaLLM

    cfg(carrera_activada=True, carrera_espera=0.0)

    rapido = Lento("groq", segundos=0.05)
    lento = Lento("gemini", segundos=1.2)
    cadena = CadenaLLM([lento, rapido])
    # Sin historial, gana el orden configurado; la carrera lo ignora y lanza a los dos.
    resultado = cadena.generar_estructurado(Salida, "sys", "user")

    assert resultado.titulo == "groq"
    assert cadena.nombre_modelo == "groq:groq-modelo"
    assert rapido.llamadas == 1
    assert lento.llamadas == 1  # se lanzó también: por eso gana el primero que conteste


def test_la_carrera_escala_la_salida_del_segundo(cfg):
    """Con espera, si el primero contesta a tiempo no se gasta la llamada del segundo."""
    from nuevamente.llm.cadena_llm import CadenaLLM

    cfg(carrera_activada=True, carrera_espera=0.5)

    primero = Lento("groq", segundos=0.02)
    segundo = Lento("gemini")
    CadenaLLM([primero, segundo]).generar_estructurado(Salida, "sys", "user")

    assert primero.llamadas == 1
    assert segundo.llamadas == 0, "no hacía falta gastar la segunda llamada"


def test_la_carrera_cae_al_segundo_si_el_primero_falla(cfg):
    from nuevamente.llm.cadena_llm import CadenaLLM

    cfg(carrera_activada=True, carrera_espera=0.0)

    caido = Lento("gemini", falla=True)
    sano = Lento("groq")
    resultado = CadenaLLM([caido, sano]).generar_estructurado(Salida, "sys", "user")

    assert resultado.titulo == "groq"


def test_sin_carrera_se_recorre_en_orden(cfg):
    from nuevamente.llm.cadena_llm import CadenaLLM

    cfg(carrera_activada=False)

    primero = Lento("gemini")
    segundo = Lento("groq")
    cadena = CadenaLLM([primero, segundo])
    cadena.generar_estructurado(Salida, "sys", "user")

    assert primero.llamadas == 1
    assert segundo.llamadas == 0, "en modo secuencial no se llama al segundo si el primero respondió"


def test_el_router_se_puede_apagar(cfg):
    """Con la salud desactivada, la cadena se comporta como antes: siempre en orden."""
    from nuevamente.llm.cadena_llm import CadenaLLM

    cfg(salud_activada=False)

    caido = Lento("gemini", falla=True)
    sano = Lento("groq")
    cadena = CadenaLLM([caido, sano])

    assert cadena.router is None
    for _ in range(3):
        cadena.generar_estructurado(Salida, "sys", "user")
    assert caido.llamadas == 3, "sin router, el caído se vuelve a intentar siempre"


def test_el_nombre_del_ganador_no_se_pisa_entre_hilos(cfg):
    """Dos peticiones simultáneas deben leer cada una el proveedor que ganó su llamada."""
    from nuevamente.llm.cadena_llm import CadenaLLM

    cfg(carrera_activada=False)

    rapido = Lento("groq")
    lento = Lento("gemini", segundos=0.3)
    cadena = CadenaLLM([lento, rapido])

    leido: dict[str, str] = {}
    barrera = threading.Barrier(2)

    def peticion(nombre: str) -> None:
        barrera.wait()
        cadena.generar_estructurado(Salida, "sys", "user")
        leido[nombre] = cadena.nombre_modelo

    hilos = [threading.Thread(target=peticion, args=(n,)) for n in ("a", "b")]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert leido["a"] == leido["b"], "cada hilo debe ver el proveedor que ganó su llamada"
# --- Endpoint de salud -------------------------------------------------------


def test_el_endpoint_de_salud_responde_sin_tocar_la_red(api_client, monkeypatch):
    """Existió un `crear_llm` sin importar aquí que solo reventaba al pegarle al endpoint.

    Ninguna prueba lo cubría porque solo se llegaba por HTTP, así que ahora se llama igual."""
    import nuevamente.llm.factory as factory
    from nuevamente.llm.salud import CERRADO

    class Falso:
        def __init__(self):
            self.nombre_modelo = "groq-modelo"
            self.router = _router(["gemini", "groq"])

        def generar_estructurado(self, schema, system, user):
            return Salida(titulo="x", puntos=[])

    cliente = Falso()
    cliente.router.registrar_exito("groq", 1.2)
    monkeypatch.setattr(factory, "crear_llm", lambda *a, **k: cliente)

    r = api_client.get("/api/v1/salud-llm")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["activo"] is True
    assert cuerpo["carrera"] is False

    groq = next(f for f in cuerpo["proveedores"] if f["proveedor"] == "groq")
    assert groq["estado"] == CERRADO
    assert groq["latencia_s"] == pytest.approx(1.2)
    assert groq["exitos"] == 1


def test_el_endpoint_no_inventa_salud_si_no_hay_router(api_client, monkeypatch):
    """Con LLM_PROVIDER=groq (una sola API) no hay cadena ni router: debe decirlo, no
    devolver una lista vacía que parece "todo bien"."""
    import nuevamente.llm.factory as factory

    class Suelto:
        nombre_modelo = "groq-modelo"

        def generar_estructurado(self, schema, system, user):
            return Salida(titulo="x", puntos=[])

    monkeypatch.setattr(factory, "crear_llm", lambda *a, **k: Suelto())

    cuerpo = api_client.get("/api/v1/salud-llm").json()
    assert cuerpo["activo"] is False
    assert cuerpo["proveedores"] == []
