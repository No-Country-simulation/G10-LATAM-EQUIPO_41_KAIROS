"""Esquemas de contenido por formato pedagógico (unión discriminada por `formato`).

Responsable: Ethan Espinoza Acosta (Backend Developer), con Bryan Infante
(AI Engineer) definiendo qué campos necesita cada formato para el grafo de agentes.
"""
from __future__ import annotations

import re
from copy import copy
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

# Identificador interno de un fragmento del documento ("3af0b24977faa74f-c008"): sirve para
# la trazabilidad (campo `fuentes`), nunca para el texto que lee el estudiante.
_ID_CHUNK = r"[0-9a-f]{16}-c\d{3,}"
_LISTA_IDS = rf"{_ID_CHUNK}(?:\s*(?:,|y|e)\s*{_ID_CHUNK})*"
_LIMPIEZAS = [
    # "(chunk 3af0…-c008)", "[3af0…-c008, 3af0…-c011]"
    (re.compile(rf"\s*[(\[]\s*(?:(?:el|los)\s+)?(?:chunks?|fragmentos?|fuentes?)?\s*:?\s*{_LISTA_IDS}\s*[)\]]", re.I), ""),
    # "El chunk 3af0…-c008 indica" -> "El documento indica"
    (re.compile(rf"\b(?:chunks?|fragmentos?)\s+{_LISTA_IDS}", re.I), "documento"),
    (re.compile(_LISTA_IDS), ""),
    # "chunk" sin identificador, solo cuando cita la fuente ("según el chunk", "el chunk indica");
    # en un documento que trate de chunks como concepto, la palabra se queda
    (re.compile(r"\b(según|segun|como indica|de acuerdo con|conforme a)\s+(?:el|los|su|sus)\s+chunks?\b", re.I), r"\1 el documento"),
    (re.compile(r"\b([Ee])l chunk (?=(?:indica|señala|dice|menciona|establece|afirma|explica|describe|detalla)\b)"), r"\1l documento "),
    (re.compile(r"\b([Ll])os chunks (?=(?:indican|señalan|dicen|mencionan|establecen|afirman|explican|describen|detallan)\b)"), lambda m: ("E" if m.group(1) == "L" else "e") + "l documento "),
    (re.compile(r"\b(?:los|sus) documento\b"), "el documento"),
    (re.compile(r"\b(?:Los|Sus) documento\b"), "El documento"),
    (re.compile(r"[ \t]{2,}"), " "),
    (re.compile(r"[ \t]+([.,;:!?)])"), r"\1"),
]
# Campos que guardan identificadores o metadatos, no texto para el estudiante.
_CAMPOS_INTERNOS = {"fuentes", "seccion", "formato"}


def sin_referencias_internas(texto: str) -> str:
    """Quita del texto visible las referencias a los fragmentos internos del documento."""
    for patron, reemplazo in _LIMPIEZAS:
        texto = patron.sub(reemplazo, texto)
    return texto.strip()


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _limpiar_textos(cls, datos: Any) -> Any:
        """El LLM a veces cita "el chunk 3af0…-c008" en una justificación o una respuesta.
        Se limpia al construir el modelo, así vale para lo recién generado y para lo que
        se lee de almacenamiento (incluidos los materiales guardados antes del cambio)."""
        if not isinstance(datos, dict):
            return datos
        limpio = {}
        for clave, valor in datos.items():
            if clave not in _CAMPOS_INTERNOS and isinstance(valor, str):
                valor = sin_referencias_internas(valor)
            elif clave not in _CAMPOS_INTERNOS and isinstance(valor, list):
                valor = [sin_referencias_internas(v) if isinstance(v, str) else v for v in valor]
            limpio[clave] = valor
        return limpio


class FlashcardItem(_Base):
    frente: str = Field(min_length=3, max_length=300)
    dorso: str = Field(min_length=3, max_length=800)
    pista_didactica: str = Field(default="", max_length=300)
    fuentes: list[str] = Field(default_factory=list, description="chunk_id de evidencia")
    seccion: str = Field(default="", description="sección del documento de la que sale")


class FlashcardsContenido(_Base):
    formato: Literal["Flashcards"] = "Flashcards"
    titulo: str
    introduccion_contextualizada: str
    items: list[FlashcardItem] = Field(min_length=1, max_length=15)


class QuizPregunta(_Base):
    enunciado: str
    opciones: list[str] = Field(min_length=4, max_length=4)
    indice_correcto: int = Field(ge=0, le=3)
    justificacion: str
    fuentes: list[str] = Field(default_factory=list)
    seccion: str = Field(default="", description="sección del documento de la que sale")


class QuizContenido(_Base):
    formato: Literal["Quiz"] = "Quiz"
    titulo: str
    preguntas: list[QuizPregunta] = Field(min_length=1, max_length=10)


class TutorialPaso(_Base):
    orden: int
    titulo: str
    instruccion: str
    resultado_esperado: str = ""
    fuentes: list[str] = Field(default_factory=list)
    seccion: str = Field(default="", description="sección del documento de la que sale")


class TutorialContenido(_Base):
    formato: Literal["Tutorial"] = "Tutorial"
    objetivo: str
    prerrequisitos: list[str] = Field(default_factory=list)
    pasos: list[TutorialPaso] = Field(min_length=1)
    errores_comunes: list[str] = Field(default_factory=list)
    checklist_final: list[str] = Field(default_factory=list)
    reto_practico: str = Field(default="", description="ejercicio para aplicar lo aprendido")


class ResumenEjecutivoContenido(_Base):
    formato: Literal["Resumen Ejecutivo"] = "Resumen Ejecutivo"
    resumen: str = Field(max_length=1800, description="≈250 palabras")
    puntos_clave: list[str] = Field(min_length=1, max_length=5)
    decisiones_o_riesgos: list[str] = Field(default_factory=list)
    impacto_de_negocio: str = ""
    fuentes: list[str] = Field(default_factory=list, description="chunk_id de evidencia del resumen")


class GuionEscena(_Base):
    orden: int
    narracion: str
    apoyo_visual: str = ""
    duracion_seg: int = Field(ge=5, le=600)
    fuentes: list[str] = Field(default_factory=list)
    seccion: str = Field(default="", description="sección del documento de la que sale")


class GuionDeClaseContenido(_Base):
    formato: Literal["Guion de Clase"] = "Guion de Clase"
    duracion_total_min: int = Field(ge=1, le=60)
    escenas: list[GuionEscena] = Field(min_length=1)


class PodcastIntervencion(_Base):
    orden: int
    # Ana conduce y pregunta (voz femenina); Leo explica el documento (voz masculina).
    locutor: Literal["Ana", "Leo"]
    texto: str = Field(min_length=3, max_length=1200)
    fuentes: list[str] = Field(default_factory=list, description="chunk_id de evidencia")
    seccion: str = Field(default="", description="sección del documento de la que sale")


class PodcastContenido(_Base):
    formato: Literal["Podcast"] = "Podcast"
    titulo: str
    duracion_total_min: int = Field(ge=1, le=60)
    intervenciones: list[PodcastIntervencion] = Field(min_length=2, max_length=40)


ContenidoAdaptado = Annotated[
    Union[
        FlashcardsContenido,
        QuizContenido,
        TutorialContenido,
        ResumenEjecutivoContenido,
        GuionDeClaseContenido,
        PodcastContenido,
    ],
    Field(discriminator="formato"),
]


# --- Forma pública (la que devuelve la API) ----------------------------------------------
# El contrato de salida del enunciado no lleva los campos internos: `formato` (ya va en
# metadatos.formato_generado), `fuentes` (chunk_id de trazabilidad) ni `seccion`. Las
# versiones públicas se derivan de los modelos de arriba, así no hay dos definiciones que
# mantener a la par.
_CAMPOS_SOLO_INTERNOS = {"formato", "fuentes", "seccion"}


def _version_publica(modelo: type[BaseModel]) -> type[BaseModel]:
    campos = {}
    for nombre, info in modelo.model_fields.items():
        if nombre in _CAMPOS_SOLO_INTERNOS:
            continue
        anotacion = info.annotation
        argumentos = get_args(anotacion)
        if get_origin(anotacion) is list and argumentos and isinstance(argumentos[0], type) and issubclass(argumentos[0], BaseModel):
            anotacion = list[_version_publica(argumentos[0])]
        info = copy(info)
        info.annotation = anotacion
        campos[nombre] = (anotacion, info)
    return create_model(f"{modelo.__name__}Publico", __config__=ConfigDict(extra="forbid"), **campos)


ContenidoPublico = Union[tuple(_version_publica(m) for m in get_args(get_args(ContenidoAdaptado)[0]))]


def contenido_publico(contenido: BaseModel) -> dict:
    """El contenido sin sus campos internos, en cualquier nivel."""
    def limpiar(valor):
        if isinstance(valor, dict):
            return {k: limpiar(v) for k, v in valor.items() if k not in _CAMPOS_SOLO_INTERNOS}
        if isinstance(valor, list):
            return [limpiar(v) for v in valor]
        return valor

    return limpiar(contenido.model_dump(mode="json"))
