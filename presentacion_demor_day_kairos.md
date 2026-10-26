# Speech del Demo Day — NuevaMente

*El conocimiento de su organización, al nivel de cada persona, sin inventar nada.*

**Equipo Kairos G10** (G10-LATAM-equipo 41) · Hackathon ONE G10 (Oracle Next Education y Alura)
**Duración:** 5 minutos exactos · **Nicho:** Salud · **Versión de la app:** 1.5

**Oradores:**
* **Juan Pablo Calla** — Project Manager (bloques 1, 3 y 6)
* **Diana Dure** — QA Tester (bloques 2, 4 y 5)

**Aplicación en línea:** [g10-latam-equipo-41-kairos.onrender.com](https://g10-latam-equipo-41-kairos.onrender.com/)

> Lo que va entre corchetes son acciones en pantalla y no se lee. Las ejecuta Darío.

## Distribución del tiempo

| # | Bloque | Minuto | Duración | Orador |
|---|---|---|---|---|
| 1 | El gancho y el problema | 0:00 | 0:42 | Juan Pablo Calla |
| 2 | La solución y el diferencial | 0:42 | 0:48 | Diana Dure |
| 3 | Demo en vivo | 1:30 | 1:10 | Juan Pablo Calla |
| 4 | Cómo funciona por dentro | 2:40 | 0:45 | Diana Dure |
| 5 | Resultados | 3:25 | 0:42 | Diana Dure |
| 6 | Equipo, impacto y cierre | 4:07 | 0:53 | Juan Pablo Calla |

## Criterios del jurado y dónde se cubren

| Criterio | Bloque | Orador |
|---|---|---|
| El problema identificado | 1 · El gancho y el problema | Juan Pablo |
| La solución desarrollada | 2 · La solución | Diana |
| Cómo funciona el proyecto | 3 · Demo y 4 · Por dentro | Juan Pablo y Diana |
| Las principales funcionalidades | 2 · La solución y 3 · Demo | Diana y Juan Pablo |
| Cómo trabajaron como equipo | 6 · Equipo | Juan Pablo |
| Resultados o avances alcanzados | 5 · Resultados | Diana |
| Impacto o valor que genera | 6 · Impacto y cierre | Juan Pablo |

## Cumplimiento de las reglas del Demo Day

| Regla | Cómo se cumple |
|---|---|
| ✓ Respetar los 5 minutos | Tiempos por bloque que suman 5:00, ensayo con cronómetro y plan B para la demo |
| ✓ Todos los integrantes preparados | Los cinco tienen un rol, suplencias y preguntas del jurado asignadas |
| ✓ Centrarse en el proyecto | Todo el texto habla del producto, su funcionamiento y sus resultados |
| ✓ Organizar quién presenta cada parte | Orador por bloque, pantalla a cargo de Darío y cambios de orador sin silencios |
| ✓ Ingresar con anticipación | Checklist: entrar al evento 15 minutos antes y quedar atentos a la organización |
| ✓ Presentación preparada | Guion de pantallas con cada imagen y pestaña en orden, abiertas 30 minutos antes |

## Roles del equipo

Hablan dos personas, pero los cinco integrantes conocen el pitch completo y tienen una tarea durante la presentación.

| Integrante | Rol en el proyecto | Tarea en el Demo Day | Suplente |
|---|---|---|---|
| Juan Pablo Calla | Project Manager | Orador de los bloques 1, 3 y 6. Modera las preguntas del jurado y le pasa la palabra a quien corresponde. | Ethan |
| Diana Dure | QA Tester | Oradora de los bloques 2, 4 y 5. Responde preguntas de calidad y seguridad. | Gaspar |
| Darío Higuera Moreno | Ingeniero de IA · Interfaz | Comparte la pantalla y maneja la demo mientras Juan Pablo habla. Tiene el video de respaldo. Responde preguntas de IA y fidelidad. | Ethan (pantalla) |
| Ethan Espinoza Acosta | Backend · Agentes | Suplente de Juan Pablo. Responde preguntas de agentes, API, costos y despliegue. | — |
| Gaspar Martínez Paiva | Data Engineer · ML | Suplente de Diana. Responde preguntas de datos, RAG y Oracle Cloud. | — |

## Guion de pantallas

Darío deja todo abierto en este orden antes de empezar.

| Bloque | Qué se muestra | Archivo o pestaña |
|---|---|---|
| 1 | Pantalla de inicio de la app | Aplicación en Render (o p01_inicio.jpg) |
| 2 | Opciones de perfil, formato y sector | Aplicación en Render (o p07_opciones_y_aviso_salud.jpg) |
| 3 | Demo: subir, generar, pestaña Fidelidad | Pestaña A: app en Render · Pestaña B: Resumen Ejecutivo ya generado · Pestaña C: video del Guion de Clase |
| 4 | Flujo de agentes | docs/entregables/Flujo_Agentes_Kairos.jpg |
| 5 | Evidencias de pruebas | docs/pruebas/evidencias/01_pruebas_automatizadas.png y grafico_fidelidad_ia.svg |
| 6 | Equipo, enlaces y lema | Diapositiva final con nombres, roles, enlace a la app y al repositorio |

---

## 1. El gancho y el problema · 0:00 a 0:42 · Juan Pablo

[Pantalla: Portada de NuevaMente (pantalla quieta, sin animaciones)]

*[Dos segundos de silencio. Mirar al jurado antes de hablar]*

“¿Cuánto tarda su equipo en convertir un manual de cuarenta páginas en una capacitación para cada persona que lo necesita? Días. A veces, semanas.

Soy Juan Pablo Calla, Project Manager de Kairos G10.

En un hospital, ese manual es el protocolo de bioseguridad. La enfermera que acaba de ingresar, el técnico y la directora que firma la auditoría necesitan aprenderlo de forma distinta. La inteligencia artificial ya puede hacer ese trabajo en minutos, pero tiene un problema: inventa. Y en salud, una respuesta inventada cuesta mucho más que tiempo.”

**Mensaje clave:** Hay un dolor real y costoso, y la IA actual no es confiable para resolverlo.

## 2. La solución y el diferencial · 0:42 a 1:30 · Diana

[Pantalla: Interfaz con perfiles y formatos]

“Soy Diana Dure, QA Tester, y mi trabajo es desconfiar. Por eso les presento NuevaMente: una IA que no puede inventar sin que lo detectemos.

Le das un documento, en PDF, Word o incluso escaneado, y en minutos lo convierte en material para cuatro perfiles, desde quien recién empieza hasta el gerente, y seis formatos: tutorial, flashcards, quiz, resumen ejecutivo, video narrado y podcast. Además se adapta al sector, al nivel de detalle y al idioma.

La diferencia es esta: cada afirmación se verifica contra el documento original. Si no tiene respaldo, no se aprueba. No les pedimos que confíen en la IA; les damos cómo comprobarla.”

**Mensaje clave:** No es otro generador con IA: es uno que demuestra de dónde sale cada dato.

## 3. Demo en vivo · 1:30 a 2:40 · Juan Pablo

[Pantalla: Aplicación en línea en Render]

“Esto no es una maqueta: está en línea ahora mismo.

*[Darío sube el protocolo de bioseguridad]*

Subo nuestro protocolo de bioseguridad. Perfil: principiante. Formato: flashcards. Sector: salud.

*[Clic en Generar; se ve la barra de progreso]*

Mientras avanza, cuatro agentes leen el documento, lo dividen por secciones, buscan la evidencia de cada una y redactan.

*[Mostrar las flashcards y abrir la pestaña Fidelidad]*

Aquí están las flashcards. Y esta es la pestaña que nos diferencia: fidelidad, cien por ciento. Todo está respaldado por el documento: cada afirmación se comparó con el fragmento del que dice venir.

*[Cambiar a la pestaña con el Resumen Ejecutivo ya generado]*

Mismo documento, ahora para la directora: un resumen ejecutivo con puntos clave, riesgos y recomendaciones.

*[Mostrar el video del Guion de Clase y los botones de descarga]*

Y para quien aprende escuchando, un video con voz natural. Todo se descarga en Word, PDF o PowerPoint.”

**Mensaje clave:** La promesa se cumple frente al jurado: mismo documento, distinta persona, cero datos inventados.

## 4. Cómo funciona por dentro · 2:40 a 3:25 · Diana

[Pantalla: Diagrama del flujo de agentes]

“¿Cómo lo garantizamos? Con agentes que se vigilan entre sí, orquestados con LangGraph. El Planificador organiza, el Investigador busca la evidencia, el Redactor escribe con Google Gemini y el Crítico revisa cada frase.

Si una frase no tiene respaldo, vuelve al Redactor con la indicación de qué corregir. Y el juez final solo la aprueba si presenta una cita que existe palabra por palabra en el documento; eso lo comprueba el código, no la confianza. En salud, el umbral es 0,90.

Y si Gemini se cae, la aplicación no se cae: cambia a otro proveedor o a su modo local.”

**Mensaje clave:** La confianza está en la arquitectura, no en la suerte.

## 5. Resultados · 3:25 a 4:07 · Diana

[Pantalla: Evidencias de pruebas y escenarios de demo]

“Como QA, les traigo números.

Tres casos reales de salud: inducción de personal clínico, capacitación regulatoria y auditoría de protocolos. Los tres aprobados, con fidelidad de 1,00, 1,00 y 0,92.

Doscientas noventa y cinco pruebas automatizadas, todas en verde, incluidas pruebas con documentos maliciosos que intentan darle órdenes a la IA.

Cumplimos 16 de los 18 puntos del enunciado. Y está en producción en un servidor gratuito de 512 megas: para que entrara, optimizamos el video de 78 a 9 segundos de procesamiento. Cada cifra que les doy tiene su evidencia en el repositorio.”

**Mensaje clave:** Resultados medidos y comprobables, no promesas.

## 6. Equipo, impacto y cierre · 4:07 a 5:00 · Juan Pablo

[Pantalla: Equipo, enlaces y lema final]

“Lo construimos en cinco sprints de una semana, con Jira y una rama de GitHub por sprint. Gaspar en datos, Ethan en backend y agentes, Darío en IA e interfaz, Diana en calidad. Dos integrantes dejaron el equipo en el camino; redistribuimos roles y seguimos entregando cada semana.

¿Qué significa esto? Que un hospital, un banco o cualquier empresa puede convertir su documentación en capacitación para cada persona en minutos, no en semanas. En cualquier sector que no se puede permitir un error.

*[Pausa breve]*

La IA ya sabe escribir. Lo que faltaba era poder confiar en lo que escribe.

NuevaMente: el conocimiento de su organización, al nivel de cada persona, sin inventar nada.

Gracias. Somos Kairos G10.”

**Mensaje clave:** Impacto claro y una frase final que el jurado recuerde.

---

## Preguntas probables del jurado

Respuestas cortas, de 15 a 20 segundos cada una.

**¿En qué se diferencia de pedirle lo mismo a ChatGPT?** · *Diana*

ChatGPT no demuestra de dónde sale cada dato. NuevaMente verifica cada afirmación contra el documento, rechaza lo que no tiene respaldo y entrega el material listo en seis formatos y para cuatro perfiles.

**¿Qué pasa si la IA inventa algo igual?** · *Darío*

El Crítico lo detecta y lo devuelve al Redactor. Si después de los reintentos sigue sin respaldo, el material no se aprueba y el score lo muestra. El juez solo acepta citas que existen textualmente en el documento.

**¿Cuánto cuesta operarla?** · *Ethan*

Hoy corre en el plan gratuito de Render y con la cuota gratuita de Gemini. Si Gemini no responde, usa otros proveedores o el modo local, así que no depende de un solo servicio.

**¿Usan Oracle Cloud?** · *Gaspar*

Sí. La integración con OCI Object Storage está en el código y el despliegue en OCI Compute tiene script, systemd y nginx listos. Mientras se registra la llave de API en la cuenta, la app guarda en un respaldo local y lo indica en la respuesta.

**¿Es segura con documentos sensibles?** · *Diana*

El documento se trata siempre como datos, nunca como instrucciones, y lo probamos con documentos maliciosos. La demo usa un protocolo propio, sin datos de pacientes.

**¿Cómo procesan documentos largos o escaneados?** · *Gaspar*

Se dividen en secciones con solapamiento y se indexan con embeddings de Gemini; los PDF escaneados pasan por OCR. El Investigador busca la evidencia sección por sección, por eso cubre todo el documento.

**¿Cómo se coordinan los agentes?** · *Ethan*

Con un grafo de LangGraph: cada agente es un nodo y el Crítico puede devolver el trabajo al Redactor. Un caché opcional reutiliza material ya aprobado para ahorrar llamadas a la IA.

**¿Qué sigue después de la hackathon?** · *Juan Pablo*

Completar la verificación en OCI, ampliar los sectores y llevar un piloto a una institución de salud real para medir las horas de capacitación ahorradas.

## Checklist del día

### El día anterior

- [ ] Ensayo completo con los cinco, con cronómetro y compartiendo pantalla, al menos dos veces seguidas en 5:00.
- [ ] Generar y dejar guardados el Resumen Ejecutivo y el video del Guion de Clase con el protocolo de bioseguridad.
- [ ] Grabar un video de la demo (unos 70 segundos) como plan B.
- [ ] Repasar las preguntas del jurado: cada integrante practica en voz alta las que le tocan.

### 30 minutos antes

- [ ] Abrir la app en Render para que esté activa (la primera carga tarda cerca de un minuto).
- [ ] Darío deja las pestañas en el orden del guion de pantallas y cierra todo lo demás.
- [ ] Silenciar notificaciones del sistema, correo y chats en la computadora que comparte pantalla.

### 15 minutos antes

- [ ] Entrar al evento y quedar atentos a las indicaciones de la organización.
- [ ] Probar micrófono, cámara y compartir pantalla.
- [ ] Confirmar orden de oradores y suplentes por el chat interno del equipo.

### Durante la presentación

- [ ] Una sola persona habla a la vez; los demás con micrófono apagado.
- [ ] Si la demo tarda más de 10 segundos, Darío cambia al video de respaldo sin comentarlo.
- [ ] Si un orador pierde la conexión, entra su suplente desde el mismo bloque.

### En las preguntas

- [ ] Juan Pablo recibe la pregunta y nombra a quien responde.
- [ ] Respuestas de 15 a 20 segundos, con un dato concreto. Si no se sabe algo, decirlo y explicar cómo se resolvería.

## Claves para ganar

* Los primeros 10 segundos deciden la atención: decir la pregunta inicial de memoria, mirando al jurado.
* Velocidad: unas 140 palabras por minuto. El texto tiene unas 600 palabras; con las pausas y las acciones de la demo da 5:00.
* Ensayar al menos cinco veces con cronómetro. Si se pasan, recortar la frase del video en el bloque 3. Nunca acelerar el cierre.
* Plan B de la demo: tener el material ya generado en otra pestaña y un video grabado de la demo. Si algo tarda, cambiar sin comentarlo.
* Abrir la aplicación 5 minutos antes para que Render esté activo; en el plan gratuito la primera carga tarda cerca de un minuto.
* Cambio de orador sin silencio: quien termina mira a su compañera o compañero, y quien sigue empieza de inmediato.
* Decir los números despacio y con pausa: 1,00 · 295 pruebas · de 78 a 9 segundos. Son lo que el jurado anota.
* La frase final se dice lento, mirando al jurado, y se espera un segundo antes del “Gracias”.

## Enlaces

* [Aplicación en línea](https://g10-latam-equipo-41-kairos.onrender.com/)
* [Repositorio en GitHub](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS)
* [Backlog en Jira](https://dielidube.atlassian.net/jira/software/projects/SCRUM/boards/1/backlog)
