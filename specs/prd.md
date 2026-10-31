# Proyecto Ágil — Product Requirements Document

**Versión:** 0.1, borrador integral para revisión.
**Fecha:** 31 de octubre de 2026.
**Estado:** definición de producto; no implica aprobación de diseño técnico ni aplicación implementada.
**Ámbito:** gestión asistida de cartera telco y prototipo para evaluación técnica.

## 0. Cómo leer este documento

Se consolida el PRD completo por la indicación posterior de Cristian de construirlo con el contexto disponible. Sustituye la revisión obligatoria segmento por segmento como método de elaboración; conserva el contenido de la plantilla original y los hallazgos del [Paso 0](prd-paso-0-conflictos.md).

Se distinguen tres niveles:

- **Confirmado:** instrucción de Cristian o exigencia de la guía.
- **Propuesta:** regla adicional o supuesto de trabajo redactado para completar el producto, pendiente de revisión.
- **TBD:** dato o decisión todavía desconocida. No se inventan resultados, cifras de negocio o garantías de producción.

### 0.1. Fuentes y trazabilidad

| ID | Fuente | Alcance |
|---|---|---|
| G | Guía técnica AI Engineer de Liberty Latin America, secciones 01–06 y entregable de código/demo | Contexto, restricciones, preguntas y evaluación |
| C | Conversación de definición con Cristian del 31 de octubre de 2026 | Requisitos y aclaraciones explícitas del producto |
| J | Workflow de n8n aportado como referencia | Mecanismo de normalización de mensajes, audio, identidad, memoria y herramientas |
| I | Foto del tablero de arquitectura aportada por Cristian | Relación conceptual entre central, pagos, agente, inbox y observabilidad |
| P | [Prompt de construcción del PRD](../promptprd.md) | Estructura de 13 segmentos y tratamiento de vacíos |
| W1 | [Política de WhatsApp](https://business.whatsapp.com/policy) | Condiciones del canal que deben validarse antes de producción |
| W2 | [AgentBots de Chatwoot](https://app.chatwoot.com/hc/user-guide/articles/1677497472-how-to-use-agent-bots) | Integración del bot y transferencia a atención humana |
| W3 | [Autoalojamiento de Langfuse](https://langfuse.com/self-hosting) | Dependencias de observabilidad |

G, J e I son fuentes locales de referencia y no se incorporan como archivos al repositorio público. J pertenece a otro dominio: se reutiliza el patrón, sin importar sus reglas de negocio ni sus datos operativos.

### 0.2. Límites del borrador

La solución empresarial propuesta debe alojarse en AWS; la guía permite que el prototipo se ejecute localmente. El demo usará datos ficticios, pasarela simulada y llamadas reales a IA. La asignación final de servicios AWS, los modelos, la región y el dimensionamiento se resuelven después del PRD. [G, C]

**Supuestos propuestos:** producto interno para una telco; una deuda agregada por contrato/servicio en el MVP; negociación sobre una deuda seleccionada; moneda de los ejemplos USD. Son supuestos explícitos, no decisiones atribuidas a LLA.

## 1. Producto, JTBD y misión

### Definición del producto

Proyecto Ágil ayuda a una telco a gestionar facturas vencidas mediante un agente de IA en WhatsApp. Permite iniciar campañas segmentadas, facilitar pagos o acuerdos autorizados y transferir a un asesor los casos que requieren intervención humana.

### JTBD principal: cliente con deuda

**Cuando** recibo un aviso de una factura vencida o necesito resolver una deuda de uno de mis servicios, **quiero** entender qué debo y acceder a una opción de pago viable, **para** regularizar mi cuenta con claridad y obtener ayuda humana cuando la necesite.

JTBD complementario del operador: cuando tengo una cartera que supera la capacidad de gestión manual, quiero contactar segmentos elegibles y supervisar sus resultados para concentrar al equipo humano en los casos que requieren criterio o autorización adicional.

### Misión

Facilitar la regularización de facturas vencidas mediante conversaciones claras y respetuosas, conectadas con información verificable. Ejecutar las acciones dentro de las reglas autorizadas por el negocio y conservar el contexto al escalar. Hacer visible el resultado económico y la calidad de cada gestión.

**Decisión de enfoque propuesta:** priorizar la resolución de la situación del cliente y la recuperación verificable para la telco. No equiparar éxito con cantidad de mensajes enviados ni con evitar toda atención humana. [G §§01–03, C]

## 2. Contexto y problema

### Situación descrita por la guía

LLA presta servicios de telecomunicaciones a clientes residenciales y empresariales, incluyendo internet, televisión y telefonía en Panamá. El equipo realiza gestiones principalmente por llamada y correo, y en momentos de demanda el volumen supera su capacidad operativa. La guía sitúa WhatsApp como canal estratégico del Proyecto Ágil. [G §§01–02]

La guía menciona aperturas superiores al 90% en WhatsApp frente a 20–30% en correo. Se registran como afirmaciones del contexto del ejercicio, sin verificación de mercado ni baseline propio; no se usan como promesa de entrega, lectura o conversión del producto. [G §01]

### Problemas que aborda

| Actor | Problema | Efecto que buscamos reducir |
|---|---|---|
| Cliente | Aviso de deuda sin explicación suficiente o sin un siguiente paso claro | Fricción para entender el saldo y resolverlo |
| Operador | Más casos que capacidad de contacto y seguimiento manual | Demoras y atención repetitiva |
| Asesor | Casos transferidos sin saldo, oferta o motivo de escalamiento | Repetición de preguntas y pérdida de contexto |
| Negocio | Falta de conexión entre actividad conversacional y pago confirmado | Confusión entre contacto, acuerdo y recaudo |
| Tecnología | Respuestas que podrían actuar sobre información antigua o insuficiente | Errores de saldo, permisos o acuerdos |

Los problemas de capacidad y canal provienen de G; las fricciones específicas y resultados buscados son hipótesis de producto derivadas del recorrido definido en C. No hay entrevistas independientes que las cuantifiquen.

### Por qué ahora

El detonante documentado es la decisión de LLA de explorar agentes en WhatsApp y la necesidad de presentar una solución funcional. La oportunidad consiste en combinar conversación con lectura y escritura controlada de datos. No se atribuye urgencia a una regulación o tendencia adicional no documentada. [G §§01–04]

### Alternativas actuales

- Llamadas y correo con gestión humana: alternativa descrita en G; su limitación de capacidad se plantea en la propia guía.
- Portal de autoservicio: alternativa conceptual que facilita pagar, pero cuya existencia y adopción en LLA son TBD.
- Bot de guion fijo: alternativa conceptual; su cobertura y desempeño no han sido medidos.

## 3. Organización objetivo, usuarios y patrocinadores

Se adapta el concepto de ICP a un producto interno, según la propuesta de enfoque del Paso 0.

| Dimensión | Definición |
|---|---|
| Organización objetivo | Telco con clientes residenciales y empresariales y facturas vencidas |
| Caso de referencia | LLA Panamá |
| Tamaño y volumen de cartera | TBD; la guía describe una base masiva sin cifras operativas |
| Usuarios finales | Clientes con deuda, incluyendo personas con varios servicios |
| Usuarios operadores | Personal autorizado de cartera que segmenta, inicia y supervisa campañas |
| Usuarios asesores | Equipo que recibe excepciones y atiende conversaciones transferidas |
| Patrocinadores | Responsables de cartera/comercial y comité de tecnología; cargos concretos TBD |
| Usuario del prototipo | Evaluador que alterna los roles de operador, cliente y asesor |

### Detonantes y objeciones

| Situación | Necesidad o respuesta propuesta |
|---|---|
| Pico de casos vencidos | Ampliar capacidad de contacto con segmentación y límites operativos |
| Cliente dispuesto a pagar | Explicar deuda, crear orden y guiar al pago |
| Cliente con dificultad de pago | Evaluar una propuesta dentro de una política explícita |
| Temor a descuentos no autorizados | Regla ejecutada por el backend y trazabilidad del acuerdo |
| Temor a perder el control humano | Derivación explícita y suspensión de respuestas automáticas |
| Temor a complejidad de integración | API de cartera simulada que representa la frontera con ERP/CRM |

Son hipótesis y respuestas de diseño de producto, no resultados de entrevistas. No hay verbatims de clientes que permitan validar un ICP comercial; no se fabrican testimonios. [G §§02–05, C]

## 4. Propuesta de valor y diferenciadores

**Propuesta de valor:** convertir un contacto de cartera en una gestión verificable: explicación de la deuda, opción de pago o acuerdo autorizado, confirmación contra el sistema y atención humana cuando corresponda.

Capacidades que la demo debe demostrar, sin afirmar exclusividad de mercado:

1. Manejar varios servicios de una misma persona y seleccionar la deuda a resolver.
2. Interpretar lenguaje libre, notas de voz e imágenes antes de actuar.
3. Consultar sistemas mediante herramientas y aplicar políticas fuera del LLM.
4. Verificar un comprobante contra el registro del pago y su titularidad.
5. Transferir contexto al asesor y permitir inspeccionar la gestión.

### Marco de posicionamiento

No hay competidores ni puntuaciones comparables en las fuentes. El siguiente diagrama define ejes conceptuales y el objetivo del producto; no asigna resultados inventados a empresas o herramientas.

```mermaid
quadrantChart
    title Marco conceptual de posicionamiento
    x-axis Operacion aislada --> Integracion verificable
    y-axis Conversacion rigida --> Conversacion adaptable
    quadrant-1 Objetivo del producto
    quadrant-2 Dialogo sin integracion
    quadrant-3 Gestion fragmentada
    quadrant-4 Integracion con guion fijo
```

**Trade-off propuesto:** privilegiar exactitud, permisos y resolución sobre libertad irrestricta del agente. La brecha descrita es funcional; su tamaño de mercado y diferenciación competitiva siguen como TBD. [C, P §04]

## 5. Cinco casos de uso principales

| ID | Caso y actor | Trigger | Pasos principales | Resultado esperado | KPI asociado |
|---|---|---|---|---|---|
| UC-01 | Campaña segmentada; operador | Hay deudas elegibles | Filtrar; previsualizar; confirmar; enviar plantilla aprobada; revisar resultados | Contactos trazables sin duplicar accidentalmente personas | Entrega y respuesta por campaña |
| UC-02 | Consulta y pago completo; cliente | Responde al aviso | Verificar identidad; consultar servicios; elegir deuda; abrir enlace; pagar y enviar comprobante | Pago completo confirmado mediante consulta al sistema | Importe recuperado y resolución |
| UC-03 | Acuerdo autorizado; cliente | Expresa dificultad y ofrece un importe | Seleccionar deuda; precisar oferta; validar umbral; aceptar acuerdo; pagar y verificar | Liquidación con pago y condonación registrados por separado | Cumplimiento de acuerdos y valor condonado |
| UC-04 | Verificación multimodal; cliente | Envía audio o imagen | Identificar medio; transcribir o interpretar; conservar contexto; consultar herramienta; responder | Interpretación útil seguida de verificación cuando hay una afirmación de pago | Exactitud de extracción y consulta correcta |
| UC-05 | Atención humana; cliente/asesor | Oferta fuera de política, disputa o petición de asesor | Detectar motivo; crear caso; resumir; transferir; suspender negociación automática | Caso visible y atendible con contexto suficiente | Escalamientos correctos y tiempo de toma |

Los casos UC-02 y UC-03 incluyen UC-04 al recibir el comprobante. Las métricas no se consideran resultados obtenidos hasta ejecutar la evaluación. [C]

## 6. Principios de diseño no negociables

Los principios de exactitud y control se derivan de los requisitos confirmados; los detalles de protección siguientes son propuestas de criterio de aceptación.

| Principio | Significado operativo | Manifestación en la interfaz | Conducta prohibida |
|---|---|---|---|
| Verificar antes de confirmar | El sistema de cartera/pagos es la autoridad | Estado confirmado solo después de consultar | Dar una deuda por pagada basándose solo en texto o imagen |
| Permisos fuera del modelo | El backend autoriza lecturas y acciones | El cliente ve solo sus deudas | Usar instrucciones del usuario para saltar autenticación |
| Política financiera ejecutable | Importes y umbrales se validan en código | Acuerdo muestra saldo, pago y condonación | Inventar descuentos o aceptar importes inválidos |
| Atención humana disponible | El cliente puede solicitar ayuda y el sistema debe derivar excepciones | Aviso de transferencia y caso visible en Chatwoot | Seguir negociando mientras un asesor controla el caso |
| Comunicación clara y respetuosa | Explicar opciones sin presión indebida | Lenguaje breve, importes explícitos y siguiente paso | Amenazas, promesas de reactivación no verificadas o exposición innecesaria de datos |
| Evidencia rastreable | Registrar herramientas, resultado y correlación | Evaluador puede contrastar chat, cartera y trazas | Presentar actividad de envío como recaudo |
| Demo honesta | Las simulaciones están identificadas | Comprobante y página indican pago simulado | Presentar la pasarela ficticia como integración financiera real |
| Alcance acotado | Resolver los recorridos acordados con interfaces pequeñas | Central, pago y bandeja existente | Introducir un ERP completo o una nueva plataforma de asesores |

> [!IMPORTANT]
> Un único nodo de agente significa un único responsable conversacional en LangGraph. Puede ejecutar un ciclo de llamadas al LLM y herramientas; el preprocesamiento de medios ocurre antes de ese nodo. No convierte las reglas financieras en decisiones discrecionales del modelo.

## 7. Recorridos de usuario

### 7.1. Cliente: pago completo

1. Recibe una plantilla previamente aprobada asociada a una campaña de prueba.
2. Responde por WhatsApp; el backend obtiene la identidad del canal.
3. El agente localiza un candidato y solicita el PIN ficticio sin revelar aún saldos o datos completos.
4. El backend verifica el PIN y habilita consultas autorizadas.
5. El agente consulta los servicios y el cliente selecciona una deuda.
6. El agente crea una orden por el saldo vigente y entrega su enlace.
7. El cliente abre la página, revisa el importe y aprueba el pago simulado.
8. El simulador registra el pago y aplica el saldo; la página muestra el comprobante.
9. El evaluador obtiene una captura o imagen del comprobante y la envía por WhatsApp.
10. El preprocesador extrae el contexto; el agente consulta el estado del pago y su asociación a la deuda.
11. Si el sistema confirma la liquidación, el agente comunica el resultado. La deuda de otro servicio conserva su saldo.

### 7.2. Operador: campaña y seguimiento

1. Accede a la central con el mecanismo de acceso del demo.
2. Revisa o edita los datos ficticios y las deudas por servicio.
3. Filtra por servicio, tipo de cliente, identificación o estado; los filtros exactos se enumeran en el módulo de campaña.
4. Previsualiza personas únicas, deudas incluidas y exclusiones.
5. Selecciona una plantilla aprobada y confirma el lanzamiento.
6. Observa aceptación de envío, entrega y errores cuando el canal los reporte.
7. Revisa pagos confirmados, acuerdos y casos humanos.
8. Consulta una traza de ejemplo para explicar qué herramientas se ejecutaron.

### 7.3. Cliente: acuerdo y descuento

1. Tras autenticar y seleccionar una deuda, indica que no puede pagar el total.
2. El agente pide el importe concreto y aclara moneda o servicio si hace falta.
3. La herramienta calcula el porcentaje sobre el saldo vigente seleccionado.
4. Si la oferta está entre el 80% y el 100%, comunica el pago acordado y el valor que se condonará al cumplirlo.
5. El cliente confirma la opción y recibe la orden por ese importe.
6. El pago aprobado registra dinero recibido y condonación; la captura posterior conduce a verificarlo.

### 7.4. Interrupción o abandono

1. El cliente abandona después de consultar o de recibir un enlace.
2. La deuda conserva su saldo mientras no exista un pago aplicado.
3. Se conserva el historial útil; autenticación y autorizaciones tienen vigencia independiente de la memoria.
4. Al retomar, el agente consulta el saldo actual y comprueba si la orden sigue vigente.
5. Si la autorización venció, vuelve a verificar al cliente; si la orden venció, ofrece generar otra con el estado vigente.
6. No se envían recordatorios automáticos fuera de las reglas de contacto definidas. Su incorporación futura requiere configuración explícita.

La caducidad de sesión y orden es TBD. Mantener memoria no equivale a mantener una sesión autenticada indefinidamente.

### 7.5. Excepción y atención humana

1. El cliente ofrece menos del 80%, disputa la deuda, pide asesor o presenta una situación que no puede verificarse.
2. Si afirma que ya pagó, el agente intenta consultar antes de concluir que hay discrepancia.
3. El backend crea un caso y una nota privada con motivo, deuda seleccionada, oferta y verificaciones realizadas.
4. Se transfiere la conversación a atención humana y se informa al cliente.
5. El agente suspende sus respuestas automáticas mientras el caso está bajo control humano.
6. El asesor responde desde Chatwoot. Una devolución al bot debe ser explícita y conservar el contexto.

Chatwoot documenta conversaciones en pending para gestión del bot y cambio a open para atención humana; asignación de equipo y tiempos de atención deben configurarse. [W2]

## 8. Alcance del MVP — MoSCoW

### Must Have

| ID | Capacidad | Origen |
|---|---|---|
| M-01 | Dos interfaces web pequeñas: central/campañas y pago simulado | C |
| M-02 | Datos ficticios editables, clientes con varios servicios y API de cartera | C |
| M-03 | Segmentación, previsualización y lanzamiento con plantilla aprobada | C |
| M-04 | Conversación por WhatsApp mediante Chatwoot existente | C y G |
| M-05 | Agente único LangGraph, LLM real y herramientas invocadas realmente | C y G |
| M-06 | Localización por identidad del canal y PIN ficticio para la demostración | C |
| M-07 | Memoria PostgreSQL separada de la base de cartera en el entorno local | C |
| M-08 | Texto, audio e imagen con normalización previa al agente | C |
| M-09 | Pago completo y acuerdo desde el 80% con condonación | C |
| M-10 | Orden, página de aprobación/rechazo y comprobante apto para captura | C |
| M-11 | Consulta del pago tras interpretar la captura y aplicación idempotente al saldo | C; detalle de idempotencia propuesto |
| M-12 | Handoff por excepciones y suspensión del bot bajo control humano | C |
| M-13 | Langfuse con trazas reales de procesamiento, herramientas e inferencia | C |
| M-14 | README reproducible, datos semilla y reinicio de escenarios | C y G |
| M-15 | Repo público personal sin secretos ni fuentes operativas privadas | C |
| M-16 | Documento de arquitectura AWS justificado, diagramas y guion de sustentación | G y C |

### Should Have

- Entrada local de mensajes simulados y archivos para evaluar el núcleo sin cambiar Chatwoot.
- Botón de descarga del comprobante como imagen; la captura manual debe funcionar en todo caso.
- Vista resumida de resultados y enlaces de correlación a trazas.
- Pausa de campaña que impida nuevos envíos aún no ejecutados.
- Comprobación previa de conexión, identidad de demo y disponibilidad del proveedor.
- Grabación corta de respaldo y pruebas de repetición de los recorridos.

### Could Have

- Más reglas de segmentación, horarios y políticas por cartera.
- Reanudación asistida por el operador y seguimiento de acuerdos con recordatorios autorizados.
- Emulación adicional de infraestructura AWS con Floci.
- Infraestructura declarativa si aporta a la entrega y al tiempo disponible.

### Won't Have en esta versión

- Movimiento de dinero real, conciliación bancaria o captura de datos de tarjeta.
- OTP productivo o verificación formal de identidad.
- ERP/CRM completo, administración de todos los ciclos de facturación o contabilidad general.
- Cuotas y planes de pago en varios vencimientos; el acuerdo del MVP es una liquidación con descuento.
- Creación y aprobación dinámica de plantillas en el demo.
- Campañas reales sobre clientes de LLA o bases de terceros.
- Múltiples agentes especialistas, RAG o base vectorial sin necesidad funcional demostrada.
- Garantías de producción, escala o cumplimiento normativo no verificadas.

La preparación para producción contempla creación programática de plantillas con gestión de sus estados; su implementación queda fuera del demo acordado.

## 9. Módulos y requisitos funcionales

### 9.1. Roles y permisos propuestos

| Rol | Puede hacer | Límite |
|---|---|---|
| Cliente autenticado | Consultar sus deudas, proponer importe y acceder a su orden | No accede a central, otras personas o configuración |
| Operador | Editar fixtures y gestionar campañas de prueba | No altera saldos de otras personas desde una conversación de cliente |
| Asesor | Atender casos escalados y registrar su resultado | El bot no negocia en paralelo |
| Evaluador | Ejecutar escenarios y reiniciarlos con el acceso de demo | No necesita credenciales administrativas de producción |
| Procesos internos | Llamar a APIs dentro de su ámbito | La identidad y los permisos se comprueban en cada operación |

La autenticación concreta del operador es TBD. Se propone acceso local restringido o credencial de demo; SSO empresarial queda fuera del prototipo.

### 9.2. Mapa funcional

```mermaid
flowchart TB
    OP["Operador o evaluador"] --> CENTRAL["Central web: cartera y campañas"]
    CENTRAL --> API["API de cartera simulada"]
    CENTRAL --> CAMP["Gestión y envío de campañas"]
    CAMP --> CW["Chatwoot"]
    CW <--> WA["Meta y WhatsApp"]
    CW --> PRE["Entrada y normalización de medios"]
    PRE --> AG["Único agente LangGraph"]
    MEM["Memoria conversacional"] <--> AG
    AG <--> TOOLS["Herramientas autorizadas"]
    TOOLS --> API
    TOOLS --> PAY["Órdenes y pago simulado"]
    TOOLS --> HUM["Transferencia a asesor"]
    HUM --> CW
    AG -->|"Enlace"| WEB["Página web de pago"]
    WEB --> PAY
    PAY --> API
    PRE -.-> OBS["Observabilidad Langfuse"]
    AG -.-> OBS
    TOOLS -.-> OBS
```

El diagrama representa responsabilidades de producto. Su despliegue en servicios AWS se definirá en el diseño posterior, independientemente de la cobertura de Floci.

### 9.3. Requisitos por módulo

| ID | Módulo | Requisito y exposición |
|---|---|---|
| FR-01 | Cartera | Mostrar y editar fixtures en la central: cliente, identificación ficticia, contacto, tipo de cliente, contrato/servicio, saldo, moneda, vencimiento y estados de deuda/servicio separados |
| FR-02 | Cartera | Usar identificador único de deuda/fila y de cliente; identificar a la persona por tipo y número de documento, con varios servicios vinculados |
| FR-03 | Cartera | Exponer consultas y actualizaciones por API; la integración del agente utiliza esa frontera de sistema externo |
| FR-04 | Campañas | Filtrar por servicio, tipo de cliente, tipo de identificación y estado de deuda; previsualizar personas únicas y deudas asociadas |
| FR-05 | Campañas | Excluir pagados, bajas y destinatarios sin habilitación de contacto de prueba; revalidar antes del envío; impedir doble lanzamiento accidental |
| FR-06 | Campañas | Seleccionar plantilla preparada y aprobada; registrar estados de envío y errores sin equiparar aceptación con entrega |
| FR-07 | Canal | Recibir y validar eventos; distinguir entradas del cliente, salidas y notas privadas; deduplicar por identidad de mensaje |
| FR-08 | Identidad | Localizar por teléfono o identificador disponible del canal; comprobar PIN y limitar intentos; no devolver PIN al modelo |
| FR-09 | Autorización | Limitar herramientas a deudas y órdenes del cliente autenticado; renovar verificación cuando corresponda |
| FR-10 | Medios | Procesar texto, audio e imágenes por tipo real; conservar mensaje acompañante y procedencia; manejar archivos no soportados o ilegibles |
| FR-11 | Agente | Interpretar lenguaje libre, aclarar ambigüedades y seleccionar herramientas mediante llamadas reales a un LLM |
| FR-12 | Memoria | Mantener continuidad por conversación y separación entre clientes; la sesión de identidad es independiente de la memoria |
| FR-13 | Política | Validar en código deuda, saldo vigente, moneda y oferta; rechazar importes no positivos o superiores al saldo y aclarar datos ambiguos |
| FR-14 | Acuerdo | Aplicar umbral del 80% a la deuda elegida; presentar condiciones y obtener conformidad antes de emitir la orden con descuento |
| FR-15 | Orden | Crear enlace asociado a una orden con importe autorizado, token opaco y caducidad; impedir que el navegador altere el importe |
| FR-16 | Pago | Simular aprobación/rechazo; registrar y aplicar pago/condonación una sola vez; mostrar resultado y comprobante legible |
| FR-17 | Verificación | Tras recibir la captura, extraer referencia/contexto y consultar pago, titularidad y deuda antes de comunicar liquidación |
| FR-18 | Handoff | Crear caso y nota, transferir conversación y detener respuestas del bot; permitir devolución explícita por un asesor |
| FR-19 | Observabilidad | Registrar trazas correlacionadas del turno, medios, inferencias, herramientas, errores, latencias y uso/costo disponible |
| FR-20 | Entrega | Arranque documentado, seeds, prueba de salud y restauración; distinguir qué es real, ficticio, externo y local |

Las salvaguardas específicas que completan los requisitos confirmados son propuestas verificables del borrador. El diseño elegirá sus mecanismos sin cambiar los límites de producto.

### 9.4. Política financiera propuesta

Sea S el saldo pendiente vigente de la deuda seleccionada y O la oferta, expresados en la misma moneda.

| Condición | Acción |
|---|---|
| S es cero o la deuda está liquidada | Informar que no hay saldo; no crear otro cobro |
| O no es claro, no tiene moneda compatible o refiere a otra deuda | Aclarar antes de actuar |
| O es menor o igual a cero, o mayor que S | Rechazar la propuesta y pedir corrección |
| O es igual a S | Orden de pago completo |
| O es al menos 80% de S y menor que S | Acuerdo con pago O y condonación S menos O |
| O es menor que 80% de S | Atención humana |

Comparar cantidades con precisión monetaria y sin redondeos que autoricen ofertas inferiores al umbral. Ejemplos ficticios con S = USD 100: O = 100, pago completo; O = 90, condonación 10; O = 80, condonación 20; O = 79,99, humano.

La deuda se liquida al aplicar el pago aprobado y la condonación autorizada. Aceptar un acuerdo, abrir un enlace o enviar un comprobante no cambia el saldo.

### 9.5. Estados y concurrencia

Se mantienen conceptos separados: deuda, acuerdo, orden, pago y control de conversación. La nomenclatura exacta de los estados es una propuesta, no un esquema de base ya implementado.

```mermaid
stateDiagram-v2
    [*] --> Pendiente
    Pendiente --> OrdenVigente: Orden completa o acuerdo aceptado
    OrdenVigente --> Pendiente: Rechazo, abandono o vencimiento
    OrdenVigente --> Liquidada: Pago aplicado y condonación si corresponde
    Liquidada --> Liquidada: Evento o comprobante repetido
    Liquidada --> [*]
```

Este diagrama describe el estado funcional del recorrido de una deuda. Durante OrdenVigente, el saldo contable sigue pendiente. Si el pago o el saldo cambian por otro canal, el agente debe consultar el estado nuevo antes de emitir o confirmar condiciones.

El simulador muestra liquidación confirmada únicamente cuando la aplicación al sistema central es durable. Si el pago queda registrado pero su aplicación no se confirma, se muestra una situación pendiente de conciliación y se evita volver a cobrar automáticamente.

### 9.6. Flujo de comprobante

```mermaid
sequenceDiagram
    actor U as Cliente evaluador
    participant P as Página de pago
    participant S as Sistema central
    participant V as Procesamiento de imagen
    participant A as Agente
    U->>P: Aprobar pago simulado
    P->>S: Registrar y aplicar con referencia única
    S-->>P: Estado durable
    P-->>U: Mostrar comprobante
    U->>V: Enviar captura por WhatsApp
    V-->>A: Referencia y contenido interpretado
    A->>S: Consultar pago para cliente y deuda autorizados
    alt Pago aplicado y asociado correctamente
        S-->>A: Liquidación confirmada
        A-->>U: Confirmar resultado
    else Pendiente o inconsistente
        S-->>A: Estado y motivo
        A-->>U: Aclarar, informar espera o transferir
    end
```

### 9.7. Condiciones no funcionales de producto

- El modo principal del demo debe funcionar con WhatsApp real y el número de prueba existente. Un modo local simulado es complemento de evaluación.
- La memoria debe sobrevivir al reinicio de la aplicación cuando se conservan los volúmenes; reiniciar los fixtures debe ser una operación explícita.
- Los reintentos tienen límites y no duplican pagos, condonaciones ni contactos de campaña.
- Los mensajes de una misma conversación se gestionan sin negociaciones simultáneas incoherentes.
- La captura de trazas no debe bloquear indefinidamente la atención si falla la plataforma de observabilidad.
- PIN, tokens y claves no se registran en texto abierto en trazas ni se incorporan al repositorio.
- Solo se descargan adjuntos de orígenes autorizados; límites de tamaño, duración y retención quedan en configuración.
- El presupuesto de IA se contabiliza entre agente, audio, visión y reintentos. El mecanismo de límite efectivo es TBD.
- Disponibilidad, concurrencia objetivo y latencia p95 se establecen después de mediciones; no se promete capacidad sin evidencia.

Langfuse autoalojado tiene varias dependencias, incluyendo web, worker y almacenes de datos. El diseño posterior debe contemplarlas y comprobar que una traza sea consultable, no solo que el endpoint de ingestión responda. [W3]

## 10. Métricas de éxito

### North Star propuesta

**Importe efectivamente recuperado y aplicado a deudas elegibles gestionadas por el sistema, dentro de las reglas autorizadas.**

En el prototipo se calcula sobre pagos ficticios y demuestra trazabilidad. En producción, asociar un pago a una campaña no prueba causalidad; el incremento atribuible requiere un piloto con comparación adecuada.

### Métricas y metas

Todas las metas siguientes son propuestas para revisión. No existen baselines propios de producción.

| Dimensión | Métrica y definición | Baseline | Meta inicial propuesta |
|---|---|---|---|
| Activación del evaluador | Completa arranque y primer recorrido siguiendo README | TBD: primera ejecución externa | Completar todos los pasos sin instrucciones verbales adicionales |
| Contacto | Entregados sobre envíos elegibles; respuestas sobre entregados | TBD en piloto | Medir por segmento; objetivo comercial TBD |
| Recuperación | Pago aplicado, separado de descuento y saldo pendiente | TBD real; fixtures conocidos en demo | Coincidencia exacta con el registro de pagos del demo |
| Acuerdos | Acuerdos cumplidos sobre aceptados; valor condonado | TBD | Reportar cumplimiento y costo de la condonación por separado |
| Continuidad | Retoma una conversación conservando contexto y verificando vigencia | TBD: dataset inicial | Resolver todos los casos de reanudación de la batería de aceptación |
| Calidad factual | Importes, servicio y estado coinciden con la respuesta de herramientas | TBD: evaluación inicial | Cero contradicciones financieras en casos críticos del dataset |
| Seguridad | Acciones o revelaciones fuera de identidad/política autorizada | TBD: evaluación adversarial | Cero en la batería de aceptación |
| Escalamiento | Casos que debían derivarse y efectivamente se derivan | TBD: evaluación inicial | Todos los casos obligatorios de la batería |
| Experiencia | Claridad y utilidad mediante rúbrica humana | TBD | Aprobar cada recorrido crítico; umbral agregado TBD |
| Desempeño | Latencia p50/p95 por texto, audio e imagen | TBD: benchmark | Elegir objetivo después de medir proveedor y entorno |
| Costo | Costo por turno, recorrido y caso resuelto | TBD: llamadas instrumentadas | Mantener la ejecución de evaluación dentro del presupuesto de IA asignado |
| Operación | Errores, reintentos, pendientes y tiempo de atención humana | TBD | Detectar fallos inyectados y mostrar su estado |

La continuidad técnica sustituye a una métrica SaaS de retención en esta fase. El impacto en retención de clientes telco es una hipótesis de piloto, no un resultado atribuible al prototipo. [G §03, C, P §10]

## 11. Plan de evaluación del agente

### Dataset inicial propuesto

Fixtures ficticios que cubran: una persona con dos servicios; otra persona para probar aislamiento; deuda pagada; saldo cambiado; pago aprobado/rechazado; orden vencida; identidad asociada a teléfono y a identificador alternativo.

Mensajes de prueba: texto, ofertas expresadas informalmente, audios claros/ambiguos, comprobantes legibles/ilegibles y capturas con referencia ajena. Ningún dato real de clientes se necesita.

### Batería mínima de aceptación

| ID | Escenario | Resultado exigido | Requisitos |
|---|---|---|---|
| AC-01 | Arranque limpio y carga de fixtures | Interfaces y dependencias listas según README | FR-20 |
| AC-02 | Persona con dos servicios | Consulta autorizada y selección explícita; sin mezclar saldos | FR-01–03, FR-09 |
| AC-03 | PIN incorrecto o no verificado | Sin saldos ni datos completos; manejo de intentos | FR-08–09 |
| AC-04 | Identificador de canal sin coincidencia | Fallback documentado, sin inventar identidad | FR-08 |
| AC-05 | Pago completo | Orden por saldo vigente y aplicación correcta | FR-13, FR-15–16 |
| AC-06 | Oferta del 90% | Condiciones claras; pago 90 y condonación 10 sobre saldo 100 | FR-13–16 |
| AC-07 | Oferta exactamente del 80% | Autorización por el umbral y liquidación tras pago | FR-13–16 |
| AC-08 | Oferta del 79,99% | Escalamiento sin orden automática con ese descuento | FR-13–14, FR-18 |
| AC-09 | Importe ambiguo, negativo, cero o mayor que saldo | Aclaración o rechazo; sin autorización financiera inválida | FR-13 |
| AC-10 | Orden abandonada, vencida o pago rechazado | Conserva saldo y permite retomar de forma coherente | FR-12, FR-15–16 |
| AC-11 | Captura de pago aplicado | Invoca consulta real y confirma el resultado del sistema | FR-10–11, FR-17 |
| AC-12 | Imagen con apariencia de éxito sin pago registrado | No confirma liquidación; consulta y deriva según resultado | FR-17–18 |
| AC-13 | Referencia de otra persona | Sin revelar ni aplicar información ajena | FR-09, FR-17 |
| AC-14 | Evento de pago o captura repetidos | Una sola aplicación; respuesta coherente | FR-07, FR-16–17 |
| AC-15 | Audio más texto acompañante | Contexto conservado y gestión correcta | FR-10–11 |
| AC-16 | Imagen ilegible o medio no soportado | Pide aclaración o deriva; no inventa contenido | FR-10 |
| AC-17 | Solicitud de asesor o disputa de deuda | Caso, resumen y suspensión del bot | FR-18 |
| AC-18 | Conversación ya tomada por humano | Sin respuestas automáticas de negociación | FR-07, FR-18 |
| AC-19 | Reinicio y reanudación | Memoria persistente; validación de sesión y saldo actual | FR-09, FR-12 |
| AC-20 | Campaña con varios servicios del mismo cliente | Destinatario agrupado; sin contactos duplicados por error | FR-04–06 |
| AC-21 | Baja, deuda ya pagada o lanzamiento repetido | Exclusión o deduplicación observable | FR-05–06 |
| AC-22 | Caída del sistema central o del LLM | Sin afirmar éxito; reintento limitado o atención humana | FR-11, FR-16–18 |
| AC-23 | Instrucción maliciosa en chat, imagen o herramienta | No cambia permisos ni reglas de descuento | FR-09–14 |
| AC-24 | Traza y consumo del recorrido | Medios, LLM y herramientas correlacionados sin secretos | FR-19 |

### Método de QA

1. Comprobar invariantes financieros y de autorización mediante verificaciones deterministas.
2. Ejecutar recorridos con herramientas y bases reales del prototipo, manteniendo ficticios los datos.
3. Revisar claridad y utilidad con rúbrica humana: explica saldo, pide lo necesario, ofrece siguiente paso y escala con motivo.
4. Repetir conversaciones críticas con variaciones lingüísticas; registrar modelo, configuración, versión y resultados.
5. Revisar fallos antes de aprobar la demo; una respuesta convincente con saldo incorrecto es un fallo.

No se exige una redacción literal única del LLM. Los criterios se centran en acciones, permisos, exactitud y resultado. El uso de otro LLM como juez es opcional y debe justificar su costo.

### Red-teaming

Intentos de obtener cartera ajena, omitir PIN, fingir rol de operador, forzar descuentos superiores al permitido, cambiar importe del enlace, repetir webhooks, presentar comprobantes falsos o inyectar instrucciones en imágenes. El objetivo es confirmar el límite del backend y el comportamiento de escalamiento.

## 12. Riesgos y mitigaciones

Las probabilidades son estimaciones cualitativas propuestas para priorizar el diseño, no frecuencias medidas.

| Riesgo | Probabilidad | Impacto | Mitigación específica |
|---|---|---|---|
| R-01: saldo, descuento o pago inventado por el modelo | Media | Alto | Herramientas como autoridad, reglas en código, consulta antes de confirmar y pruebas financieras |
| R-02: revelación de cartera ajena o falsa identidad | Media | Alto | Verificación antes de saldos, permisos por cliente/deuda, límites de intentos y pruebas de aislamiento |
| R-03: discrepancia con políticas de Meta o condiciones de contacto en Panamá | Media, pendiente de validación | Alto | Validar elegibilidad, consentimiento y bajas; datos ficticios; aprobación operativa previa a clientes reales |
| R-04: pago aprobado que no se aplica o se aplica dos veces | Media | Alto | Referencias únicas, idempotencia, registro durable, conciliación y estado explícito de incertidumbre |
| R-05: pérdida, duplicación o desorden de eventos | Media | Alto | Persistencia de recepción, deduplicación, secuenciación por conversación y recuperación controlada |
| R-06: asesor y agente responden en paralelo | Media | Alto | Estado de control humano, comprobación antes de envío y transferencia auditable |
| R-07: transcripción o extracción incorrecta | Media | Medio/Alto | Preservar procedencia, pedir aclaración y verificar los campos de pago contra el sistema |
| R-08: indisponibilidad de dependencias o conexión pública del demo | Media | Alto | Health checks, reintentos limitados, modo local complementario y grabación de respaldo |
| R-09: consumo superior al presupuesto o secretos publicados | Media | Alto | Entorno excluido, revisión del commit, límites de uso/archivos, contabilidad y límite efectivo del proveedor cuando exista |
| R-10: demo técnicamente correcta sin valor comercial o demasiado compleja | Media | Alto | Alcance acotado, guion externo reproducible, métricas de pago aplicado y explicación para comité mixto |

WhatsApp exige respetar consentimiento, bajas y reglas de plantillas/ventana de atención. Su política incluye restricciones sobre debt collection; la aplicación concreta al flujo de facturas propias de telco requiere validación. No se declara autorización productiva ni se sustituye análisis legal panameño por supuestos del demo. [W1]

## 13. Plan de entrega y evolución

### 13.1. Entrega real de la prueba por hitos

La fecha límite es TBD. Los hitos se ordenan por dependencia, sin asignar días ficticios:

1. Revisar este PRD y resolver las decisiones que cambian alcance o recorridos.
2. Traducir a especificación, diseño, contratos y tareas con Spec Kit.
3. Construir una primera integración de identidad, consulta de deuda y tool use real.
4. Completar pago, acuerdo, captura, verificación y handoff.
5. Añadir campañas, medios y observabilidad hasta cubrir los Must Have.
6. Ejecutar aceptación, revisar costos y probar el README desde un entorno limpio.
7. Preparar arquitectura AWS, diagramas, decisiones, riesgos, métricas y sustentación.

El orden de construcción es propuesta y puede ajustarse en el plan de Spec Kit. No elimina capacidades Must Have ya acordadas.

### 13.2. Roadmap hipotético de producción 30/60/90

Este roadmap comunica una evolución posible después de la evaluación. No es una fecha comprometida de entrega ni una afirmación de que LLA autorizó un piloto.

| Periodo | Qué se construye o valida | Resultado para decidir |
|---|---|---|
| Días 1–30 | Validación con operaciones, datos, Meta/privacidad; integración de sandbox; política autorizada; dataset y baseline | Viabilidad del canal, datos y controles; alcance de piloto definido |
| Días 31–60 | Piloto acotado en AWS, atención humana, monitoreo, recuperación y seguimiento de pagos reales bajo autorización | Calidad, costos, operación humana y resultados comparables |
| Días 61–90 | Ajustes por evidencia, ampliación controlada de segmentos y pruebas de capacidad/recuperación | Decidir expansión, modificación o detención según valor y riesgo |

El volumen, las metas y la disponibilidad del piloto dependen de datos y aprobación operativa todavía TBD.

## 14. Matriz de cobertura de la evaluación

| Exigencia o pregunta de la guía | Respuesta en el producto | Evidencia prevista |
|---|---|---|
| Saber con quién hablar y qué decir | Cartera, identidad, segmentación, plantillas y contexto verificado | UC-01/02; FR-01–08 |
| Agente interno, herramientas, límites y memoria | Nodo único con LLM real, políticas del backend y PostgreSQL | FR-08–14; trazas y casos AC |
| Leer y escribir sistemas existentes | API de cartera y registro de pago/condonación | FR-03, FR-16–17 |
| Gestión y control | Operador, campañas, política y supervisión humana | §§03, 06, 09 |
| Riesgos y mitigaciones | Validación, idempotencia, fallos, privacidad y recuperación | §§11–12 |
| Métricas de negocio | Pago aplicado, acuerdos, condonación, calidad y costo | §10 |
| Infraestructura propuesta AWS | Diseño posterior justificado, incluyendo canal e IA | Documento de arquitectura pendiente tras revisión del PRD |
| WhatsApp y agente de IA | Chatwoot/Meta y agente LangGraph con inferencia real | Demo principal y trazas |
| Prototipo, README y sustentación | Fixtures, recorridos, ejecución y guion para comité mixto | FR-20 y hitos de entrega |

Se conserva la distinción entre la exigencia mínima de la guía y el MVP ampliado solicitado por Cristian. No se afirma que el prototipo esté construido. [G §§03–06]

## 15. Decisiones pendientes y alternativas

Estas decisiones no impiden redactar el PRD, pero deben cerrarse en el momento indicado.

| ID | TBD | Opciones razonables | Recomendación provisional | Momento de cierre |
|---|---|---|---|---|
| D-01 | Enfoque interno y adaptación de ICP | Producto interno telco; plataforma comercial general | Producto interno aplicado al caso de LLA | Revisión del PRD |
| D-02 | Grano de la deuda | Agregada por contrato; factura por fila; detalle de facturas asociado | Agregada por contrato para el MVP | Antes de modelo de datos |
| D-03 | Moneda e identificaciones de fixtures | USD y tipos de Panamá; catálogo configurable; identificadores puramente de demo | Ejemplos USD y documentos inequívocamente ficticios | Antes de seeds y pantallas |
| D-04 | Fecha límite y tiempo disponible | Fecha de entrega; fecha de sustentación; ambas | Registrar las fechas reales aportadas | Antes de calendarizar tareas |
| D-05 | Proveedor/modelos y límite de USD 5 | API real externa para demo; Bedrock real; adaptadores intercambiables | Elegir por tool use, medios, costo y límite efectivo | Antes de integrar IA |
| D-06 | Asociación del identificador alternativo | Fixture preasociado; verificación externa; handoff | Fixture y fallback humano para el demo | Antes de identidad |
| D-07 | Publicación HTTPS y uso del bot | Entrada temporal; reverse proxy existente; endpoint AWS | Elegir según disponibilidad y documentar restauración/exclusividad | Antes de demo WhatsApp |
| D-08 | Servicios AWS y emulación | Contenedores administrados; piloto en EC2; funciones cuando convenga | Justificar desde requisitos y después seleccionar emulación | Diseño posterior al PRD |
| D-09 | Langfuse y dependencias | Stack local; instancia autoalojada existente; despliegue AWS | Entorno reproducible sin secretos compartidos públicamente | Diseño de observabilidad |
| D-10 | Caducidad y límites | Configuración única de demo; política por campaña; política por cliente | Configuración explícita de demo | Contratos y criterios de aceptación |
| D-11 | Acceso del operador | Restricción local; credencial de demo; identidad empresarial | Acceso sencillo y restringido para el prototipo | Antes de exponer la central |
| D-12 | Retención y capacidad | Sesión de evaluación; piloto acotado; operación regional | Medir demo y separar supuestos de producción | Diseño y piloto |

La elegibilidad con Meta y la revisión de privacidad/contacto son validaciones externas pendientes antes de contactar clientes reales, no decisiones que el LLM o el documento puedan dar por resueltas.

## 16. Recorrido y paquete de entrega para el evaluador

El README final debe indicar requisitos, comandos, variables, URLs, credenciales ficticias, preparación del número y resultados esperados de cada paso.

```mermaid
flowchart LR
    A["Arrancar y cargar fixtures"] --> B["Abrir central"]
    B --> C["Lanzar campaña"]
    C --> D["Conversar y verificar identidad"]
    D --> E{"Recorrido"}
    E --> F["Pago completo"]
    E --> G["Oferta del 90%"]
    E --> H["Oferta menor al 80% o disputa"]
    F --> I["Pagar y enviar captura"]
    G --> I
    I --> J["Agente consulta pago y confirma"]
    H --> K["Atención humana en Chatwoot"]
    J --> L["Ver saldo y trazas"]
    K --> L
    L --> R["Restaurar escenario"]
```

El paquete incluye:

- Código del monorepo público, dependencias y configuración de ejemplo sin secretos.
- Documento de arquitectura AWS con mapa de componentes, secuencias y justificación.
- Diagrama del agente y explicación del preprocesamiento de audio/imágenes.
- Seeds y PIN ficticio, preparación de identidad, reinicio y limpieza del entorno de demo.
- Guion de pago completo, descuento, comprobante, disputa y handoff.
- Pruebas y resultados de aceptación; limitaciones conocidas y consumo observado.
- Explicación de servicios reales, simulados y emulados, sin atribuir equivalencia total a Floci.
- Grabación de respaldo cuando se prepare, y narrativa de decisiones para sustentación.

## 17. Criterio para pasar a Spec Kit

Este borrador permite revisar el producto completo. Antes de iniciar el diseño se confirma el alcance, se corrigen los supuestos que alteren el comportamiento y se priorizan los TBD por dependencia.

La aprobación del PRD no convierte en aprobadas una arquitectura, un proveedor o unas metas que siguen marcadas como propuestas. La especificación posterior debe conservar los IDs funcionales y de aceptación para verificar consistencia.
