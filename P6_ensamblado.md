# P6 – Plantilla de Ensamblado

## FÓRMULA
```
PROMPT FINAL = P1 + P2[x] + P3[y] + P4[z] + CONTEXTO_RAG + INSTRUCCIÓN
```

## PLANTILLA
```
[P1_SYSTEM]

[P2_PERFIL_SELECCIONADO]

[P3_NICHO_SELECCIONADO]

[P4_FORMATO_SELECCIONADO]

# CONTEXTO_RAG
{chunks_recuperados}

# INSTRUCCIÓN FINAL
Genera el contenido en formato {formato} para el perfil {perfil}
en el nicho {nicho}. Devuelve SOLO el JSON del esquema definido.
Sin texto adicional.
```

## VARIABLES
| Variable | Valores |
|---|---|
| `{perfil}` | Principiante · Junior · Líder Técnico · Gestor |
| `{formato}` | Tutorial · Flashcards · Quiz · Resumen · Guion |
| `{nicho}` | Fintech · Salud · E-commerce · General · Tecnología · IA |