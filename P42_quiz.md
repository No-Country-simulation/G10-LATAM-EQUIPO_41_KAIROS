# P4.2 – Formato: Quiz Interactivo

## PROPÓSITO
Evaluación con retroalimentación explicativa.

## REGLAS
- Cantidad: entre 5 y 8 preguntas.
- Cada pregunta: 4 opciones (A, B, C, D). Solo 1 correcta.
- Los distractores deben ser plausibles, no absurdos.
- Cada justificación cita el fragmento del contexto.
- El `distractor_analisis` explica por qué cada opción incorrecta falla.

## ESQUEMA JSON
```json
{
  "titulo": "...",
  "preguntas": [
    {
      "enunciado": "pregunta clara",
      "opciones": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "respuesta_correcta": "A",
      "justificacion": "por qué es correcta, citando el contexto",
      "distractor_analisis": "por qué las otras son incorrectas"
    }
  ],
  "puntaje_total": 8,
  "tiempo_estimado_min": 10
}
```