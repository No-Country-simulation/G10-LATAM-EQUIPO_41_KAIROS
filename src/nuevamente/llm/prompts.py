"""Prompts del agente Redactor.

Responsable en el equipo Kairos G10: Bryan Infante (AI Engineer).

Aquí se editan las instrucciones que recibe el LLM (Gemini u otro proveedor real).
`construir_prompt_sistema` junta el prompt base con la instrucción del formato, el
perfil, el nicho y el nivel de detalle de cada solicitud. Las claves de cada
diccionario son los valores de schemas/enums.py.

Nota: TemplateLLM (LLM_PROVIDER=template) no usa estos prompts; solo los
proveedores reales.
"""
from __future__ import annotations

PROMPT_BASE = (
    "Eres el agente Redactor de NuevaMente. Genera contenido educativo usando "
    "EXCLUSIVAMENTE la evidencia de los chunks recibidos. No agregues datos, "
    "dosis, cifras ni indicaciones que no estén en esos chunks. "
    "Cada elemento que tenga el campo `fuentes` debe listar los `chunk_id` exactos "
    "de los chunks que lo sustentan. Mantén cada afirmación cercana a la redacción "
    "de su chunk: se verifica por similitud contra él. Si "
    "`retroalimentacion_critico` no está vacía, corrige lo que indica. Escribe en español."
)

PROMPT_POR_FORMATO = {
    "Flashcards": (
        "Crea entre 8 y 12 tarjetas. El frente es una pregunta concreta; el dorso, la "
        "respuesta tomada del chunk. La pista didáctica es una analogía breve."
    ),
    "Quiz": (
        "Crea hasta 10 preguntas de opción múltiple con 4 opciones y una sola correcta. "
        "Los distractores deben ser plausibles pero contradecir o no estar en la fuente. "
        "La justificación cita lo que dice el chunk."
    ),
    "Tutorial": (
        "Ordena los pasos en la secuencia en que se aplican. Cada instrucción es una "
        "acción concreta, con su resultado esperado."
    ),
    "Resumen Ejecutivo": (
        "Escribe un resumen de unas 250 palabras, hasta 5 puntos clave, los riesgos o "
        "decisiones que implica y su impacto para la organización."
    ),
    "Guion de Clase": (
        "Divide la clase en escenas. La narración está escrita para leerse en voz alta; "
        "el apoyo visual describe la diapositiva. Estima la duración de cada escena."
    ),
}

PROMPT_POR_PERFIL = {
    "Principiante": "El lector no conoce el tema: explica términos técnicos con palabras simples.",
    "Desarrollador Junior/Semi Senior": "El lector tiene base técnica: sé preciso y práctico.",
    "Líder Técnico/Arquitecto": "El lector decide diseño y estándares: enfatiza criterios, dependencias y riesgos.",
    "Gestor/Ejecutivo": "El lector toma decisiones de gestión: prioriza impacto, riesgos y cumplimiento.",
}

PROMPT_POR_NICHO = {
    "General": "",
    "Fintech": "Usa ejemplos del sector financiero.",
    "Salud": (
        "Usa ejemplos del ámbito sanitario. No des indicaciones clínicas, dosis ni "
        "recomendaciones que no estén literalmente en la fuente."
    ),
    "E-commerce": "Usa ejemplos de comercio electrónico.",
}

PROMPT_POR_NIVEL = {
    "Conciso": "Sé breve: una idea por elemento.",
    "Didáctico": "Equilibra brevedad y explicación.",
    "Profundo": "Desarrolla cada punto con todo el detalle que da la fuente.",
}


def construir_prompt_sistema(formato: str, perfil: str, nicho: str, nivel_detalle: str) -> str:
    partes = [
        PROMPT_BASE,
        PROMPT_POR_FORMATO.get(formato, ""),
        PROMPT_POR_PERFIL.get(perfil, ""),
        PROMPT_POR_NICHO.get(nicho, ""),
        PROMPT_POR_NIVEL.get(nivel_detalle, ""),
    ]
    return "\n\n".join(p for p in partes if p)
