# PRD de Proyecto Ágil: Paso 0

**Fecha:** 31 de octubre de 2026.
**Estado:** revisión con Cristian. No inicia el Segmento 1.
**Propósito:** resolver conflictos de fuentes y de enfoque antes de construir el PRD.

## 1. Fuentes consultadas

| ID | Fuente | Cómo se utiliza |
|---|---|---|
| G | Guía AI Engineer de Liberty Latin America aportada por Cristian; secciones 01 a 06 y entregable de código/demo | Requisitos de la evaluación y contexto del caso |
| C | Conversación de definición funcional con Cristian del 31 de octubre de 2026 | Decisiones explícitas; las aclaraciones posteriores sustituyen las interpretaciones anteriores |
| J | Agente versión final.json, workflow funcional de n8n aportado como referencia | Patrón de entrada, identidad, normalización de audio, memoria y herramientas |
| I | Foto del tablero de arquitectura aportada por Cristian | Boceto conceptual de cartera, pagos, agente, inbox, memoria, observabilidad y entrega |
| P | promptprd.md de este repositorio | Método de co-creación: Paso 0, 13 segmentos y consolidación final en specs/prd.md |
| W | Documentación oficial de WhatsApp, Chatwoot, Floci y AWS consultada en la sesión | Contrastar supuestos técnicos y dependencias; no equivale a pruebas de integración |

Las fuentes G, J e I permanecen fuera del repositorio público. No se publican sus archivos
ni datos operativos del workflow original. No se han aportado estudios de mercado, entrevistas,
benchmarks propios ni datos operativos reales de LLA.

## 2. Conflictos y vacíos que requieren tratamiento

La tabla diferencia contradicciones reales, aclaraciones ya resueltas y datos que faltan.
Un TBD técnico puede esperar al diseño: no toda ausencia bloquea definir el producto.

| # | Tipo de conflicto | Doc A dice… | Doc B dice… | Decisión requerida y recomendación |
|---|---|---|---|---|
| 01 | Posicionamiento | P solicita ICP, buyer personas, competencia, brecha de mercado y triggers de compra | G plantea una solución interna para gestión de clientes de una telco y una evaluación de ingeniería | **Pendiente:** enfocar el PRD en un producto interno telco con demo evaluable. Adaptar comprador a patrocinador/comité, y competencia a alternativas operativas. Alternativa: describir un SaaS comercial; ampliaría alcance sin evidencia aportada. |
| 02 | Horizonte de entrega | P solicita un plan de 30/60/90 días | G requiere entregar documento, prototipo y demo; C no fija fecha límite | **TBD:** fecha de entrega y tiempo disponible. Recomiendo separar calendario real de la prueba y roadmap hipotético 30/60/90 para una implantación posterior. No inventar un plazo de 90 días para el assessment. |
| 03 | Calidad de la evidencia | P pide datos duros, baselines, metas, verbatims y posiciones competitivas | G aporta contexto del ejercicio; C/J/I describen una solución, no mediciones ni investigación | **Pendiente de criterio editorial:** marcar datos de G como contexto de la guía, metas como propuestas y baselines como TBD. Opciones: medir el prototipo, aportar datos reales autorizados o conservar incógnitas. Recomiendo medir el prototipo y conservar TBD de negocio. |
| 04 | Arquitectura objetivo y entorno de prueba | G exige infraestructura propuesta en AWS | C reutiliza Chatwoot fuera de AWS y permite claves de un proveedor LLM para la demo local | **Aclarado por G:** el prototipo puede ser local y no requiere despliegue AWS. Documentar arquitectura objetivo AWS y sustituciones del demo. No presentar el entorno del ASUS como infraestructura productiva de LLA. |
| 05 | Arquitectura condicionada por herramientas | I y C mencionan Docker y explorar emulación con Floci | G prioriza justificar tecnologías según el problema; el diseño técnico todavía no está aprobado | **Criterio recomendado:** elegir servicios AWS por datos, ejecución, operación y SLA; decidir después qué emular. Terraform es opcional. No fijar EC2, ECS o Lambda solo por cobertura del emulador. |
| 06 | Grano de la cartera | C pide una fila por persona y servicio, y servicios múltiples por cliente | El flujo habla de facturas y deudas que pueden repetirse por periodo; G no impone modelo de datos | **Pendiente funcional:** para el MVP, una deuda vencida agregada por contrato/servicio. Alternativas: una fila por factura o detalle de facturas bajo cada servicio. Recomiendo deuda agregada para conservar la tabla simple solicitada; declarar el supuesto. |
| 07 | Semántica del acuerdo | Una oferta del 90% podría interpretarse como abono parcial | C aclaró expresamente que se condona el 10% y se liquida la deuda | **Resuelto:** registrar acuerdo, pago y condonación separados. La condonación se ejecuta al confirmar el pago, no al generar el enlace. No reabrir la decisión como si siguiera ambigua. |
| 08 | Momento de confirmación | El primer recorrido contemplaba confirmación al recibir la notificación del pago | C precisó que el evaluador enviará una captura y el agente consultará el sistema | **Resuelto:** en la demo principal el pago actualiza cartera y produce comprobante; la captura provoca interpretación y consulta. La imagen no modifica ni prueba por sí sola el saldo. |
| 09 | Alcance de la referencia multimodal | J detecta adjuntos y la rama revisada los procesa como audio, con transcripción alternativa | C exige interpretar tanto audio como imágenes | **Brecha de implementación:** clasificar por tipo real; conservar texto acompañante; añadir visión para imágenes. Opciones: preprocesadores especializados por medio o modelo multimodal único. Recomiendo adaptadores separados que entreguen contexto uniforme al mismo agente. |
| 10 | Identidad y revelación de datos | C propone localizar por teléfono o Business User ID y verificar con PIN ficticio | El identificador del canal no demuestra identidad; un Business User ID puede no estar asociado a un teléfono | **TBD:** procedimiento de asociación cuando no hay coincidencia. Opciones: datos semilla asociados previamente, verificación externa o atención humana. Recomiendo identidad de demo preasociada y fallback humano; no revelar cartera antes del PIN. |
| 11 | Pago declarado y handoff | C incluye escalamiento cuando alguien afirma haber pagado y no existe coincidencia | C también exige que el agente procese comprobantes y consulte el sistema | **Aclaración propuesta:** consultar primero. Pago confirmado permite cierre; discrepancia, ausencia persistente o disputa pasa al humano. Un mensaje de “ya pagué” no debe escalar siempre sin intentar verificar. |
| 12 | Categoría de plantilla y alcance | C propone Utility buscando mejor alcance y plantillas ya preparadas para el demo | W establece aprobación, propósito, consentimiento y controles de envío; no garantiza entrega por categoría | **Corrección recomendada:** registrar Utility como categoría buscada, sujeta a aprobación. La creación programática en producción también necesita gestionar aprobación/rechazo antes de usarla. No prometer alcance por elegir categoría. |
| 13 | Elegibilidad del caso y regulación | G pide WhatsApp para facturas vencidas en Panamá | W menciona restricciones sobre debt collection; no se ha validado la clasificación concreta del flujo telco | **Pendiente externo:** validar con Meta/proveedor el caso de facturas propias y revisar privacidad/contacto en Panamá. Para el PRD, explicitar la hipótesis y mantener datos ficticios en el demo; no declarar elegibilidad productiva confirmada. |
| 14 | Presupuesto y ejecución real | C autoriza llamadas reales con claves y presupuesto de IA de USD 5 fuera del repo | Audio, visión, inferencia, reintentos e infraestructura tienen costos distintos; proveedor/límite efectivo son TBD | **TBD:** proveedor y mecanismo de límite. Opciones: límite efectivo del proveedor, control del backend o ambos. Recomiendo ambos cuando existan, con límites por archivo/turno y medición de todas las etapas. El presupuesto de IA no incluye automáticamente AWS ni Meta. |
| 15 | Arranque sencillo y dependencia de Chatwoot | G exige README sin configuración compleja; C exige un recorrido muy claro | El modo WhatsApp necesita dominio, endpoint público, configuración del bot y asociación del número | **Criterio recomendado:** dos recorridos documentados, núcleo local y demo completa por WhatsApp. Mantener WhatsApp como recorrido principal de sustentación; el modo local facilita probar lógica y herramientas. Publicación HTTPS y uso exclusivo del bot quedan TBD técnicos. |
| 16 | Alojamiento de observabilidad | I/C solicitan Langfuse como componente de observabilidad | W muestra que el autoalojamiento incluye web, worker y varios almacenes | **Vacío de dimensionamiento:** incorporar dependencias en el diseño posterior, fijar versiones y comprobar trazas reales. Opciones: autoalojar en local/AWS o usar una instancia externa solo para demo. No tratar Langfuse como un contenedor aislado ya resuelto. |
| 17 | Contexto regional | G sitúa el caso en Panamá y abarca clientes residenciales y empresariales | C usa cédula y ejemplos coloquiales sin fijar país, monedas, documentos o tono | **TBD de negocio:** catálogo de identificación, moneda y tratamiento por tipo de cliente. Recomiendo datos ficticios coherentes con Panamá y campos genéricos; no importar por defecto reglas legales colombianas. |
| 18 | Escala y operación | G describe una base masiva y pide riesgos/métricas | C define un prototipo pequeño sin concurrencia, SLA, volumen ni horario objetivo | **TBD del diseño:** declarar escenarios de volumen y disponibilidad como supuestos. Opciones: piloto acotado, operación regional o múltiples países. Recomiendo diseñar la evolución desde un piloto, sin prometer capacidad no medida. |

Fuentes oficiales de contraste para los puntos 12–16:
[política de WhatsApp](https://business.whatsapp.com/policy),
[AgentBots de Chatwoot](https://app.chatwoot.com/hc/user-guide/articles/1677497472-how-to-use-agent-bots),
[arquitectura de Langfuse](https://langfuse.com/self-hosting),
[Floci AWS](https://github.com/floci-io/floci).

## 3. Acuerdos que ya son requisitos de entrada

Estos puntos proceden de decisiones explícitas de Cristian; no necesitan una nueva aprobación
individual para seguir formando parte del alcance:

- Monorepo público en la cuenta personal y carpeta de trabajo en Documentos.
- PRD primero; después diseño y trabajo con Spec Kit oficial de GitHub.
- Agente real con un único nodo LangGraph, equivalente funcional al AI Agent de n8n.
- Normalización previa de audio e imágenes, memoria PostgreSQL y llamadas reales al LLM.
- Central web pequeña y página web pequeña de pago simulado.
- API de cartera como abstracción de un sistema externo; varios servicios por persona.
- Localización por datos del canal y verificación demostrativa con PIN ficticio.
- Campaña segmentada, con plantillas preparadas previamente para el demo.
- Pago completo, acuerdo desde el 80% con condonación, y handoff por debajo del umbral.
- Casos humanos por disputa, solicitud expresa, identidad no verificable y pago inconsistente.
- Captura del comprobante interpretada por el agente, seguida de consulta autorizada al sistema.
- Chatwoot ya conectado a Meta; dominio de pruebas y cambio del endpoint del bot.
- Observabilidad con Langfuse y recorrido muy explícito para el evaluador en el README.
- Archivo de entorno real fuera del repositorio y presupuesto de IA de USD 5.

## 4. Decisiones que conviene cerrar antes del Segmento 1

### D0-1. Enfoque del PRD

**Recomendación:** producto interno para gestión de cartera telco, aplicado al caso de LLA,
con prototipo de evaluación. Adaptar la plantilla a usuarios, operador, asesor y patrocinador;
no inventar un negocio SaaS ni competidores.

**Alternativa:** PRD comercial de plataforma general de cobranza. Aumenta el alcance y requiere
investigación que todavía no se ha aportado.

### D0-2. Política sobre evidencia faltante

**Recomendación:** distinguir hechos de las fuentes, requisitos de Cristian, supuestos propuestos
y TBD. Medir calidad y desempeño del prototipo; no presentar metas propuestas como resultados reales.

**Alternativa:** incorporar fuentes adicionales antes de redactar contexto y métricas.

### D0-3. Simplificación de cartera

**Recomendación:** una deuda agregada por contrato/servicio en el MVP. El identificador único de fila
es el de la deuda; un cliente puede tener varios contratos. El acuerdo se aplica a la deuda elegida.

**Alternativas:** factura por fila o tabla de facturas asociada al contrato. Se elegirían si el objetivo
de evaluación requiere periodos y aplicación de pagos por factura.

### D0-4. Calendario

**Dato requerido:** fecha de entrega o sustentación, si ya existe. Mientras no se conozca, mantenerla
como TBD. El 30/60/90 puede ser un roadmap hipotético de producción separado de la prueba.

## 5. Pregunta de cierre del Paso 0

¿Apruebas estas recomendaciones del Paso 0, tienes ajustes, o quieres que explore una dirección
diferente? La respuesta habilita comenzar el Segmento 1; no aprueba servicios AWS ni decisiones
técnicas todavía abiertas.

**Siguiente segmento, solo después de la decisión:** One-Liner del Producto + JTBD + Misión.
