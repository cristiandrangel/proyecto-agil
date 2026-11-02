# Proyecto Ágil — Product Requirements Document

**Versión:** 0.2, base de producto para la especificación de entrega.
**Fecha:** 31 de octubre de 2026.
**Estado:** definición de producto; no implica aprobación de diseño técnico ni aplicación implementada.
**Ámbito:** gestión asistida de cartera telco y prototipo para evaluación técnica.

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
| UC-01 | Campaña segmentada; operador | Hay deudas elegibles | Filtrar por servicio, cliente o días de mora; previsualizar; confirmar; enviar plantilla aprobada; revisar resultados | Contactos trazables sin duplicar accidentalmente personas | Entrega y respuesta por campaña y rango de mora |
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
3. El agente recibe el source_id literal en su contexto e interpreta si es teléfono o Business ID. Intenta localizar por celular o pide tipo/número de identificación ficticia; presenta una pista enmascarada para confirmar el registro y pide su PIN. Si el candidato no corresponde, busca otro por identificación.
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
3. Revisa la columna Días de mora de cada deuda y filtra por rango de mora, servicio, tipo de cliente, identificación o estado.
4. Previsualiza personas únicas, deudas incluidas, exclusiones y qué destinos son reales o simulados.
5. Selecciona una plantilla aprobada y confirma el lanzamiento.
6. El sistema recorre los destinatarios uno por uno, sin envíos de campaña en paralelo. Los números ficticios registran un envío simulado sin llamar al canal; el celular del evaluador recibe la plantilla real.
7. Observa progreso, envíos simulados, aceptación real, entrega y errores cuando el canal los reporte.
8. Revisa pagos confirmados, acuerdos y casos humanos.
9. Consulta una traza de ejemplo para explicar qué herramientas se ejecutaron.

### 7.3. Cliente: acuerdo y descuento

1. Tras autenticar y seleccionar una deuda, indica que no puede pagar el total.
2. El agente pide el importe concreto en USD y aclara el servicio si hace falta.
3. Negocia primero el 95% del saldo vigente y, si lo rechaza manteniendo una oferta inferior al mínimo, después el 80%, una propuesta por turno. Si mantiene una oferta superior al mínimo no la rebaja al 80%; si acepta una propuesta, la cotiza.
4. La herramienta valida las condiciones. El agente explica que la empresa acepta condonar la diferencia si paga el importe acordado, con ambos valores en USD; el pago liquidará esa deuda completa.
5. El cliente confirma la opción y recibe la orden por ese importe.
6. El pago aprobado registra dinero recibido y condonación; la captura posterior conduce a verificarlo.

### 7.4. Interrupción o abandono

1. El cliente abandona después de consultar o de recibir un enlace.
2. La deuda conserva su saldo mientras no exista un pago aplicado.
3. Se conserva el historial útil; autenticación y autorizaciones tienen vigencia independiente de la memoria.
4. Al retomar, el agente consulta el saldo actual y comprueba si la orden sigue vigente.
5. Si la autorización venció, vuelve a verificar al cliente; si la orden venció, ofrece generar otra con el estado vigente.
6. No se envían recordatorios automáticos fuera de las reglas de contacto definidas. Su incorporación futura requiere configuración explícita.

Los valores iniciales de demo son 30 minutos para sesión y orden, configurables según la especificación. Mantener memoria no equivale a mantener una sesión autenticada indefinidamente.

La llave de memoria es el source_id del contacto tal como llegó, sin transformaciones
ni otros IDs añadidos. Otro número o identificador mantiene otra memoria. El ID
de conversación de Chatwoot queda asociado a cada evento y respuesta para conservar
el destino correcto. Un interlocutor puede gestionar otro titular con su PIN:
se invalida la sesión previa y se limpia el contexto financiero activo, manteniendo
la llave del canal. La central almacena celulares y documentos, sin Business IDs.

### 7.5. Excepción y atención humana

1. El cliente mantiene una oferta inferior al 80% tras rechazar las propuestas del 95% y 80%, disputa la deuda, pide asesor o presenta una situación que no puede verificarse.
2. Si afirma que ya pagó, el agente intenta consultar antes de concluir que hay discrepancia.
3. El backend crea un caso y una nota privada con motivo, deuda seleccionada, oferta y verificaciones realizadas.
4. Se informa al cliente y se cambia la conversación de pending a open para transferirla a atención humana.
5. El bot solo puede gestionar conversaciones en pending. Al salir de ese estado pierde el control y suspende sus respuestas automáticas.
6. El asesor responde desde Chatwoot. Una devolución al bot debe ser explícita y conservar el contexto.

El mecanismo de control mediante pending ya está resuelto y desplegado en la integración de Chatwoot existente. Se reutiliza: el alcance nuevo es conectar los motivos de escalamiento, registrar el contexto y verificar que el agente respete ese control, incluso si el estado cambia mientras procesa un mensaje. El retorno al bot es una acción explícita que devuelve la conversación a pending y conserva el contexto. La asignación de equipo y los tiempos de atención son configuración operativa. [C, W2]

## 8. Alcance del MVP — MoSCoW

### Must Have

| ID | Capacidad | Origen |
|---|---|---|
| M-01 | Dos interfaces web pequeñas: central/campañas y pago simulado | C |
| M-02 | Datos ficticios editables, clientes con varios servicios, columna de días de mora por deuda y API de cartera | C |
| M-03 | Segmentación por días de mora y otros atributos, previsualización y lanzamiento con plantilla aprobada | C |
| M-04 | Conversación por WhatsApp mediante Chatwoot existente | C y G |
| M-05 | Agente único LangGraph, inferencia real mediante OpenAI y herramientas invocadas realmente | C y G |
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
| M-16 | Arquitectura inicial en una sola EC2 para todos los componentes propios, documentada con diagramas y guion de sustentación; servicios especializados se evalúan después | G y C |
| M-17 | Floci como emulador local de los servicios AWS seleccionados para la demo | C |
| M-18 | Resumen por campaña de envíos, contactabilidad, pagos totales sin condonación, acuerdos con descuento, solicitudes de asesor y casos sin resultado | C |

### Should Have

- Entrada local de mensajes simulados y archivos para evaluar el núcleo sin cambiar Chatwoot.
- Botón de descarga del comprobante como imagen; la captura manual debe funcionar en todo caso.
- Enlaces de correlación entre los resultados de campaña y las trazas.
- Pausa de campaña que impida nuevos envíos aún no ejecutados.
- Comprobación previa de conexión, identidad de demo y disponibilidad del proveedor.
- Grabación corta de respaldo y pruebas de repetición de los recorridos.

### Could Have

- Más reglas de segmentación, horarios y políticas por cartera.
- Reanudación asistida por el operador y seguimiento de acuerdos con recordatorios autorizados.

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

La adopción de infraestructura como código (IaC) y la migración a servicios especializados quedan como planes de evolución futuros, sin requisito de implementación en esta entrega. La herramienta de IaC se elegirá al retomar ese plan. [C]

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

El diagrama representa responsabilidades de producto. Todos los componentes propios se alojarán inicialmente en una sola EC2 mediante contenedores. Chatwoot existente, Meta y OpenAI son integraciones externas. El [mapa de arquitectura inicial](arquitectura-inicial.md) detalla esa distribución; los contratos y tareas se desarrollarán con Spec Kit.

### 9.3. Requisitos por módulo

| ID | Módulo | Requisito y exposición |
|---|---|---|
| FR-01 | Cartera | Mostrar y editar fixtures en la central: cliente, identificación ficticia, contacto, tipo de cliente, contrato/servicio, saldo en USD, vencimiento, días de mora y estados de deuda/servicio separados; la moneda es fija |
| FR-02 | Cartera | Usar identificador único de deuda/fila y de cliente; identificar a la persona por tipo y número de documento, con varios servicios vinculados |
| FR-03 | Cartera | Exponer consultas y actualizaciones por API; la integración del agente utiliza esa frontera de sistema externo |
| FR-04 | Campañas | Filtrar por rangos del campo días de mora, servicio, tipo de cliente, tipo de identificación y estado de deuda; previsualizar personas únicas y deudas asociadas |
| FR-05 | Campañas | Excluir pagados y bajas; permitir destinos ficticios solo en simulación y exigir habilitación para el destino real del evaluador; revalidar antes del envío e impedir doble lanzamiento accidental |
| FR-06 | Campañas | Recorrer personas únicas en orden, una por una, con plantilla preparada y aprobada; registrar simulación, aceptación real, entrega y error por separado, sin doble envío al reanudar |
| FR-07 | Canal | Recibir y validar eventos; distinguir entradas del cliente, salidas y notas privadas; deduplicar por identidad de mensaje |
| FR-08 | Identidad | Inyectar source_id literal al LLM para que elija buscar por celular o pedir identificación, sin clasificador previo; confirmar candidato con pista enmascarada, permitir otro registro y verificar su PIN fuera del modelo, limitando intentos |
| FR-09 | Autorización | Limitar herramientas a deudas y órdenes del cliente autenticado; renovar verificación cuando corresponda |
| FR-10 | Medios | Procesar texto, audio e imágenes por tipo real; conservar mensaje acompañante y procedencia; manejar archivos no soportados o ilegibles |
| FR-11 | Agente | Interpretar lenguaje libre, aclarar ambigüedades y seleccionar herramientas mediante llamadas reales a OpenAI; usar también OpenAI para transcribir audio e interpretar imágenes antes del agente principal |
| FR-12 | Memoria | Usar source_id literal del contacto como thread_id, sin normalizar ni concatenar; conservar destino Chatwoot por evento; cambiar de cliente exige nuevo PIN y limpiar contexto financiero activo; autorización independiente de memoria |
| FR-13 | Política | Validar en código deuda, saldo vigente y oferta en USD; rechazar importes no positivos o superiores al saldo; aclarar datos ambiguos y no convertir otras monedas |
| FR-14 | Acuerdo | Aplicar umbral del 80% a la deuda elegida; presentar condiciones y obtener conformidad antes de emitir la orden con descuento |
| FR-15 | Orden | Crear enlace asociado a una orden con importe autorizado, token opaco y caducidad; impedir que el navegador altere el importe |
| FR-16 | Pago | Simular aprobación/rechazo; registrar y aplicar pago/condonación una sola vez; mostrar resultado y comprobante legible |
| FR-17 | Verificación | Tras recibir la captura, extraer referencia/contexto y consultar pago, titularidad y deuda antes de comunicar liquidación |
| FR-18 | Handoff | Crear caso y nota; usar el control ya desplegado de Chatwoot: solo pending permite al bot responder, open deriva a humano; comprobar el control antes de enviar y permitir devolución explícita por un asesor |
| FR-19 | Observabilidad | Registrar trazas correlacionadas del turno, medios, inferencias, herramientas, errores, latencias y uso/costo disponible |
| FR-20 | Entrega | Arranque documentado, seeds, prueba de salud y restauración; exigir que el evaluador sustituya el teléfono de un cliente ficticio por su propio WhatsApp desde la central antes de lanzar la campaña; distinguir qué es real, ficticio, externo y local |
| FR-21 | Cartera y campañas | Persistir dias_mora como campo entero no negativo en cada fila de deuda; mostrarlo como columna editable en la central, exponerlo en la API y usarlo como origen del filtro por antigüedad |
| FR-22 | Métricas | Mostrar en la central los contadores y tasas de §10 por campaña, con deduplicación por persona, distinción entre solicitud humana y escalamiento automático, y separación entre hitos y resultados al corte |

Las salvaguardas específicas que completan los requisitos confirmados son propuestas verificables del borrador. El diseño elegirá sus mecanismos sin cambiar los límites de producto.

#### Campo Días de mora y filtros

Cada fila de deuda incorpora el campo **dias_mora**, visible como **Días de mora**. Es un dato por deuda/contrato, no un atributo general de la persona. En el demo se guarda en la base de cartera y puede editarse desde la central para representar la información recibida de un ERP/CRM. La API lo devuelve en las consultas de cartera; el agente usa ese dato y no lo estima.

El campo admite enteros mayores o iguales a cero. Cero indica que la obligación no tiene días de atraso; los valores negativos, fraccionarios o vacíos se rechazan al guardar. Los cambios se conservan al recargar y se reflejan en la siguiente previsualización de campaña.

Rangos iniciales propuestos, sin solapamiento:

| Rango visible | Valores incluidos |
|---|---|
| Sin mora | 0 |
| 1–29 días | Desde 1 hasta 29 |
| 30–59 días | Desde 30 hasta 59 |
| 60–89 días | Desde 60 hasta 89 |
| 90–119 días | Desde 90 hasta 119 |
| 120 días o más | Desde 120 |

Los límites son inclusivos tal como se muestran. Así, una deuda de 60 días pertenece a 60–89 y no a 30–59. El operador puede combinar el rango con los otros filtros; una campaña de cartera vencida incluye únicamente deudas con saldo pendiente y al menos un día de mora.

Si una persona tiene un servicio con 45 días y otro con 75, el filtro 30–59 selecciona la deuda del primero. La previsualización distingue las deudas incluidas aunque el destinatario se agrupe por persona. Tras autenticar, el cliente puede consultar sus otros servicios.

En el MVP, la simulación del sistema central mantiene este campo mediante fixtures y edición manual; un cambio de día no lo incrementa automáticamente. La sincronización o cálculo desde vencimiento y fecha de corte se define para una integración real. La selección por rango no cambia por sí sola el umbral del 80% ni autoriza un descuento diferente. [C]

### 9.4. Política financiera propuesta

Todo el MVP opera en dólares estadounidenses (USD): cartera, ofertas, órdenes, pagos, descuentos, comprobantes y métricas monetarias. No hay selección de moneda ni conversión cambiaria. Un importe sin símbolo se interpreta en USD; si el cliente menciona otra moneda se le pide expresar la oferta en USD antes de continuar.

Sea S el saldo pendiente vigente de la deuda seleccionada y O la oferta, ambos expresados en USD.

| Condición | Acción |
|---|---|
| S es cero o la deuda está liquidada | Informar que no hay saldo; no crear otro cobro |
| O no es claro, está expresado en otra moneda o refiere a otra deuda | Aclarar y pedir importe en USD para la deuda elegida antes de actuar |
| O es menor o igual a cero, o mayor que S | Rechazar la propuesta y pedir corrección |
| O es igual a S | Orden de pago completo |
| O es al menos 80% de S y menor que S | Acuerdo con pago O y condonación S menos O |
| O es menor que 80% de S | Negociar 95% y después 80%; si mantiene menos del mínimo tras rechazarlos, atención humana |

Comparar cantidades con precisión monetaria y sin redondeos que autoricen ofertas inferiores al umbral. Ejemplos ficticios con S = USD 100: O = 100, pago completo; O = 90, condonación 10; O = 80, condonación 20; O = 79,99, negociar 95 y luego 80 antes de derivar si mantiene esa oferta.

La deuda se liquida al aplicar el pago aprobado y la condonación autorizada. Aceptar un acuerdo, abrir un enlace o enviar un comprobante no cambia el saldo.

### 9.5. Estados y concurrencia

Un estado indica en qué situación está cada elemento. Crear un enlace no significa haber pagado; aceptar un descuento tampoco significa que se haya liquidado la deuda. Se mantienen conceptos separados para representar esas diferencias:

| Elemento | Situaciones que deben distinguirse |
|---|---|
| Deuda | Pendiente o liquidada; conserva el saldo hasta aplicar el pago |
| Acuerdo | Aceptado pendiente de pago, cumplido o vencido |
| Orden | Vigente, pagada o vencida; abandonar la página no equivale a pagar |
| Intento de pago | Aprobado o rechazado; un rechazo permite reintentar mientras la orden sea válida |
| Conversación | pending permite al bot gestionar; fuera de pending el bot no responde; open corresponde a atención humana |

Los nombres de estados financieros se concretarán en el diseño. Los estados de Chatwoot reutilizan el comportamiento existente.

```mermaid
stateDiagram-v2
    [*] --> Pendiente
    Pendiente --> Pendiente: Enlace creado o acuerdo aceptado
    Pendiente --> Pendiente: Pago rechazado, abandono o vencimiento
    Pendiente --> Liquidada: Pago aplicado y condonación si corresponde
    Liquidada --> Liquidada: Evento o comprobante repetido
    Liquidada --> [*]
```

El diagrama representa solo la deuda. Por ejemplo, sobre USD 100, aceptar pagar USD 90 crea un acuerdo y una orden, pero la deuda sigue pendiente por USD 100. Al aprobar y aplicar el pago, se registran USD 90 recibidos y USD 10 condonados: el saldo queda en cero y la deuda se liquida. Enviar una captura solo provoca una consulta del resultado.

La concurrencia aparece cuando dos acciones ocurren casi al mismo tiempo. El comportamiento esperado es:

- Si el cliente paga mientras el agente prepara otro enlace, se vuelve a comprobar el saldo y no se crea un cobro basado en información anterior.
- Si llegan dos veces la aprobación o el mismo mensaje, su efecto se aplica una sola vez. Esta propiedad se llama idempotencia.
- Si el cliente envía dos mensajes seguidos, se procesa la conversación en orden; distintos clientes sí pueden atenderse en paralelo.
- Si un asesor toma el control mientras el LLM está preparando una respuesta, el bot comprueba el estado antes de enviarla y se detiene al no estar en pending.
- Si dos órdenes intentan liquidar la misma deuda, se verifica su saldo vigente al aplicar el pago; no se admite una segunda liquidación ni una segunda condonación.

La actualización del pago, la condonación y el saldo debe ser consistente: no puede mostrarse una deuda liquidada con un pago sin registrar. La implementación decidirá los mecanismos de transacción, secuenciación y deduplicación.

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
- El presupuesto de IA se contabiliza entre agente, audio, visión y reintentos. El plan define reservas persistentes y corte local conservador; su aplicación efectiva se comprobará al integrar.
- Disponibilidad, concurrencia objetivo y latencia p95 se establecen después de mediciones; no se promete capacidad sin evidencia.

Langfuse autoalojado tiene varias dependencias, incluyendo web, worker y almacenes de datos. El diseño posterior debe contemplarlas y comprobar que una traza sea consultable, no solo que el endpoint de ingestión responda. [W3]

## 10. Métricas de éxito

### North Star propuesta

**Importe efectivamente recuperado y aplicado a deudas elegibles gestionadas por el sistema, dentro de las reglas autorizadas.**

En el prototipo se calcula sobre pagos ficticios y demuestra trazabilidad. En producción, asociar un pago a una campaña no prueba causalidad; el incremento atribuible requiere un piloto con comparación adecuada.

### Embudo de negocio por campaña

La central muestra progreso de destinatarios procesados, envíos simulados, mensajes reales enviados, personas únicas destinatarias reales y personas que respondieron al menos una vez. Los mensajes de campaña aceptados por el canal se cuentan como enviados; entrega y fallo se registran por separado. Los mensajes de seguimiento del bot y del asesor tienen un contador separado para no inflar los envíos de campaña.

Los números ficticios se procesan en el lote como simulados, sin llamadas a Chatwoot/Meta ni inferencia. No se registran como entregados y no entran en el denominador ni en los resultados de la campaña real. La configuración distingue explícitamente destinos simulados y el destino real de prueba; no se deduce que un número es ficticio por su apariencia.

**Contactabilidad = personas destinatarias que respondieron al menos un mensaje / personas destinatarias con al menos un envío de campaña aceptado × 100.** Texto, audio e imagen cuentan como respuesta; varios mensajes de una persona cuentan como un solo contacto. No se divide entre el total de mensajes, porque una persona puede recibir varios. Sin destinatarios enviados, la tasa se muestra como no aplicable.

Entre quienes respondieron se sigue este embudo:

| Métrica | Definición | Tasa |
|---|---|---|
| Saldaron sin condonación | Personas que liquidaron la deuda seleccionada mediante pago del 100%, sin descuento | Personas con pago total / personas que respondieron |
| Lograron acuerdo con condonación | Personas que aceptaron un acuerdo con descuento; se desglosan en pendientes de pago, cumplidos y vencidos | Personas con acuerdo / personas que respondieron |
| Solicitaron atención humana | Personas que pidieron explícitamente un asesor, aunque luego resolvieran su deuda | Personas que solicitaron asesor / personas que respondieron |
| Sin resultado | Personas que respondieron, pero al cierre no liquidaron, no mantienen un acuerdo vigente o cumplido y no tienen atención humana activa | Personas sin resultado / personas que respondieron |

“Saldó la deuda” se reserva en el reporte de negocio al pago completo sin condonación. “Logró un acuerdo” identifica la ruta con descuento. En el registro financiero ambas rutas pueden dejar la deuda liquidada; esa equivalencia contable no mezcla las dos métricas comerciales. La condonación solo se registra al aplicar el pago aprobado del acuerdo. Un acuerdo aceptado sin pago aparece como pendiente, sin importe recuperado ni condonado todavía. [C]

Los escalados automáticos por política, disputa o incidencia se muestran por separado de las solicitudes expresas del cliente. Cada caso registra su motivo y origen. La métrica de solicitudes humanas es un hito histórico y puede coexistir con un pago posterior; no se suman los hitos como si fueran personas distintas.

Como resumen del resultado actual de cada caso se usa una sola categoría: pago total sin condonación, acuerdo cumplido con condonación, atención humana activa, acuerdo pendiente de pago, sin resultado al cierre o en gestión. Se prioriza una liquidación aplicada; si no la hay, un caso humano activo precede a un acuerdo pendiente. Un acuerdo vencido o un caso humano cerrado sin pago ni acuerdo vigente termina sin resultado al cierre. Los casos sin respuesta se muestran aparte, fuera del grupo contactado. La ventana de seguimiento y el criterio temporal de cierre se fijan en D-10; hasta entonces, un caso activo no se etiqueta como fracaso.

La unidad operativa es persona, campaña y deuda seleccionada. Si un cliente tiene varios servicios se muestran los resultados por deuda y un total de personas únicas por categoría, sin presentar la suma de categorías como un total de personas: podría pagar íntegramente un servicio y negociar otro. Las tasas utilizan siempre destinatarios de la misma campaña y periodo.

Cada envío, respuesta, acuerdo, solicitud, derivación y pago se vincula a campaña, persona, conversación y deuda cuando corresponda. En la demo se mantiene una sola campaña activa por persona para evitar atribuir una respuesta a varias campañas. Los datos conservan el segmento utilizado al lanzar la campaña.

Como métricas monetarias se muestran USD efectivamente recibidos, USD condonados y saldo pendiente por separado. No se suma la condonación al dinero recuperado. No hay baselines reales ni metas comerciales inventadas; la aceptación exige que los contadores coincidan con los eventos y pagos del escenario.

### Métricas técnicas y de calidad

Estas métricas complementan el embudo comercial y se observan mediante trazas y evaluación:

| Dimensión | Medición y criterio de aceptación |
|---|---|
| Activación del evaluador | Completa preparación del número, arranque y recorridos con el README, sin instrucciones verbales adicionales |
| Continuidad | Retoma contexto y verifica identidad y saldo vigentes en todos los casos de reanudación |
| Calidad factual | Importes, servicio y estado coinciden con herramientas; cero contradicciones financieras en casos críticos |
| Seguridad | Cero acciones o revelaciones fuera de identidad o política autorizada en la batería |
| Escalamiento | Se derivan todos los casos obligatorios y se respeta el control pending existente |
| Experiencia | La revisión humana valida claridad, siguiente paso y explicación del resultado en cada recorrido crítico |
| Desempeño | Medir latencia p50/p95 por texto, audio e imagen; fijar objetivos después del benchmark |
| Costo | Contabilizar agente, audio, visión y reintentos por turno y recorrido frente al presupuesto de USD 10 |
| Operación | Detectar errores, reintentos y pendientes; registrar tiempo bajo atención humana |

El impacto en retención de clientes telco es una hipótesis de piloto, no un resultado atribuible al prototipo. [G §03, C, P §10]

## 11. Plan de evaluación del agente

### Dataset inicial propuesto

Fixtures ficticios que cubran: una persona con dos servicios y distintos días de mora; otra persona para probar aislamiento; deuda pagada; saldo cambiado; pago aprobado/rechazado; orden vencida; identidad asociada a teléfono y a identificador alternativo. Incluir deudas en los límites 0, 29, 30, 59, 60, 89, 90, 119 y 120 días para verificar la segmentación.

Mensajes de prueba: texto, ofertas expresadas informalmente, audios claros/ambiguos, comprobantes legibles/ilegibles y capturas con referencia ajena. Ningún dato real de clientes se necesita.

### Batería mínima de aceptación

| ID | Escenario | Resultado exigido | Requisitos |
|---|---|---|---|
| AC-01 | Arranque limpio y carga de fixtures | Interfaces y dependencias listas según README | FR-20 |
| AC-02 | Persona con dos servicios | Consulta autorizada y selección explícita; sin mezclar saldos | FR-01–03, FR-09 |
| AC-03 | PIN incorrecto o no verificado | Sin saldos ni datos completos; manejo de intentos | FR-08–09 |
| AC-04 | Business ID, formato desconocido, celular sin coincidencia o candidato rechazado | LLM recibe source_id literal, pide identificación y confirma candidato enmascarado; sin inventar teléfono ni identidad | FR-08 |
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
| AC-18 | Conversación fuera de pending, incluso durante una inferencia | Sin respuestas automáticas; retorno explícito a pending conserva contexto | FR-07, FR-18 |
| AC-19 | Reinicio y reanudación | Memoria por source_id literal; sesión y saldo vigentes; destino correcto con varios chats; cambio de cliente limpia contexto y exige nuevo PIN | FR-09, FR-12 |
| AC-20 | Campaña con varios servicios del mismo cliente | Destinatario agrupado; sin contactos duplicados por error | FR-04–06 |
| AC-21 | Baja, deuda ya pagada o lanzamiento repetido | Exclusión o deduplicación observable | FR-05–06 |
| AC-22 | Caída del sistema central o del LLM | Sin afirmar éxito; reintento limitado o atención humana | FR-11, FR-16–18 |
| AC-23 | Instrucción maliciosa en chat, imagen o herramienta | No cambia permisos ni reglas de descuento | FR-09–14 |
| AC-24 | Traza y consumo del recorrido | Medios, LLM y herramientas correlacionados sin secretos | FR-19 |
| AC-25 | Columna Días de mora por deuda | Edición persistente, API con el mismo valor y rechazo de datos negativos, fraccionarios o vacíos | FR-01, FR-21 |
| AC-26 | Campaña por antigüedad y límites de rango | El filtro 30–59 incluye 30 y 59, excluye 29 y 60, y conserva solo el servicio elegible de una persona; pagados y cero días no reciben campaña de vencidos | FR-04–05, FR-21 |
| AC-27 | Embudo con mensajes repetidos, pago íntegro y acuerdo con descuento | Una persona contactada por campaña; pago total sin condonación separado de acuerdo pendiente/cumplido; solicitud humana diferenciada de escalamiento automático; contadores coinciden con eventos | FR-06–07, FR-14, FR-16, FR-18, FR-22 |
| AC-28 | Evaluador cambia el teléfono de un cliente ficticio | Cambio persistente y compartido por sus servicios; campaña llega a su WhatsApp y la consulta encuentra al mismo cliente | FR-01–02, FR-08, FR-20 |
| AC-29 | Oferta menciona una moneda distinta de USD | Pide oferta en USD; no convierte ni crea una orden en otra moneda | FR-13 |
| AC-30 | Pago concurrente con nueva orden y dos intentos de liquidación | Saldo revalidado, sin segundo cobro ni doble condonación; resultado consistente en cartera y pagos | FR-13, FR-15–16 |
| AC-31 | Lote con varios números ficticios y el número real del evaluador | Procesamiento secuencial y reanudable; ficticios solo simulados, sin llamadas al canal; un envío real al evaluador; progreso visible y métricas reales sin simulados | FR-04–07, FR-20, FR-22 |

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

La entrega es el lunes **2 de noviembre de 2026**, zona America/Bogota; la hora está pendiente. Los hitos se ordenan por dependencia:

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
| Saber con quién hablar y qué decir | Cartera, días de mora, identidad, segmentación, plantillas y contexto verificado | UC-01/02; FR-01–08, FR-21 |
| Agente interno, herramientas, límites y memoria | Nodo único con LLM real, políticas del backend y PostgreSQL | FR-08–14; trazas y casos AC |
| Leer y escribir sistemas existentes | API de cartera y registro de pago/condonación | FR-03, FR-16–17 |
| Gestión y control | Operador, campañas, política y supervisión humana | §§03, 06, 09 |
| Riesgos y mitigaciones | Validación, idempotencia, fallos, privacidad y recuperación | §§11–12 |
| Métricas de negocio | Envíos, contactabilidad, pago total sin condonación, acuerdos con descuento, solicitudes humanas y casos sin resultado | §10; FR-22; AC-27 |
| Infraestructura propuesta AWS | Una EC2 con contenedores, almacenamiento persistente y conexiones externas explícitas | [Mapa de arquitectura inicial](arquitectura-inicial.md); diseño detallado posterior |
| WhatsApp y agente de IA | Chatwoot/Meta y agente LangGraph con inferencia real | Demo principal y trazas |
| Prototipo, README y sustentación | Fixtures, recorridos, ejecución y guion para comité mixto | FR-20 y hitos de entrega |

Se conserva la distinción entre la exigencia mínima de la guía y el MVP ampliado solicitado por Cristian. No se afirma que el prototipo esté construido. [G §§03–06]

## 15. Decisiones pendientes y alternativas

Una sola EC2 para todos los componentes propios, USD como única moneda, OpenAI para la inferencia del prototipo, Floci para emulación local y el control existente de Chatwoot mediante pending son decisiones fijadas. La tabla recoge únicamente lo que falta concretar.

Floci ejecuta localmente la emulación de los servicios AWS que se seleccionen; no sustituye el diseño de la aplicación ni decide qué servicios convienen en AWS. Debe distinguirse la ejecución de contenedores y PostgreSQL locales de las APIs efectivamente ejercitadas contra Floci. La cobertura de cada servicio y el despliegue real se verifican por separado. [W7]

La EC2 inicial ejecutará mediante Docker Compose las dos webs, el backend y agente, la API del sistema central simulado, PostgreSQL de cartera, PostgreSQL de memoria y Langfuse con sus dependencias. Los datos persistentes usarán volúmenes separados respaldados por EBS. Chatwoot se reutiliza donde ya está desplegado; Meta y OpenAI permanecen externos. No se exige inicialmente ECS, Lambda, RDS ni separar componentes entre máquinas. [C, W8]

La elección de EC2 prioriza flexibilidad para arrancar e iterar rápido. Después se evaluará una migración a servicios especializados para optimizar costo total y operación con evidencia de uso. El ahorro se validará antes de migrar. IaC queda como plan futuro y no condiciona la aceptación de esta entrega. [C]

La separación lógica se conserva dentro de la máquina: conexión al sistema central por API, configuración de conexiones por entorno y datos fuera de las imágenes. Esto facilita una evolución posterior, sin garantizar una migración automática: mover bases, almacenamiento, redes, credenciales y despliegue requiere validación. Una sola máquina concentra el fallo y los recursos; la capacidad se medirá con el stack completo, incluido Langfuse. [C]

| ID | TBD | Opciones razonables | Recomendación provisional | Momento de cierre |
|---|---|---|---|---|
| D-01 | Validación posterior del enfoque en un piloto | La entrega aplica el producto interno al caso telco | Sin bloquear la demo con investigación comercial adicional | Después de la prueba |
| D-02 | Detalle de facturas en una evolución | La especificación usa saldo agregado por contrato/servicio | Mantener una fila por deuda de servicio en la demo | Después del MVP |
| D-03 | Catálogo concreto de fixtures | La especificación exige documentos inequívocamente ficticios y USD fijo | Definir valores semilla al implementar; sin documentos reales | Implementación de seeds |
| D-04 | Hora límite y eventual sustentación | Entrega lunes 2026-11-02; hora y sustentación por confirmar | Organizar trabajo para el lunes sin inventar una hora | Antes de la entrega |
| D-05 | Acceso efectivo a modelos y verificación del control de USD 10 | Modelos y reservas de gasto definidos en el plan, configurables | Probar permisos, calidad y consumo con entorno privado; sin asumir acceso por documentación | Integración y preflight |
| D-06 | Forma real de identidad recibida del canal | Fallback de identificación ficticia y PIN definido en la especificación | Verificar teléfono/BSUID del payload y derivar si no se logra autenticar | Integración Chatwoot |
| D-07 | Publicación HTTPS y uso del bot | Entrada temporal; reverse proxy existente; endpoint AWS | Elegir según disponibilidad y documentar restauración/exclusividad | Antes de demo WhatsApp |
| D-08 | Tamaño, región, disco y red de la única EC2; alcance verificable de Floci | Dimensionar el stack completo y documentar APIs de infraestructura emuladas | Una máquina con Docker Compose y almacenamiento persistente; segmentación en otros servicios fuera del alcance inicial | Diseño y medición previa al despliegue |
| D-09 | Versión y configuración de Langfuse y dependencias | Stack oficial compatible con la integración elegida | Autoalojado en la misma EC2; reproducible localmente, con datos aislados | Diseño de observabilidad |
| D-10 | Validación de límites iniciales de demo | Sesión y orden 30 minutos; seguimiento de campaña 24 horas; corte manual explícito | Valores configurables del plan; comprobar comportamiento antes de entregar | Pruebas de aceptación |
| D-11 | Acceso del operador | Restricción local; credencial de demo; identidad empresarial | Acceso sencillo y restringido para el prototipo | Antes de exponer la central |
| D-12 | Retención y capacidad | Sesión de evaluación; piloto acotado; operación regional | Medir demo y separar supuestos de producción | Diseño y piloto |

La elegibilidad con Meta y la revisión de privacidad/contacto son validaciones externas pendientes antes de contactar clientes reales, no decisiones que el LLM o el documento puedan dar por resueltas.

## 16. Recorrido y paquete de entrega para el evaluador

El README final debe indicar requisitos, comandos, variables, URLs, credenciales ficticias, preparación del número y resultados esperados de cada paso. El ejemplo de campaña incluye revisar la columna Días de mora, seleccionar 30–59 y comprobar qué deudas y personas entran al segmento.

Antes de lanzar la campaña, el evaluador abre un cliente ficticio en la central y reemplaza su teléfono por su propio número de WhatsApp, con código de país y formato internacional. El contacto pertenece a la persona: sus filas de servicio comparten el cambio. Se guarda y se comprueba en la previsualización que la campaña se dirigirá a ese número. El README explica también cualquier habilitación previa del destinatario que requiera el canal de prueba. El número real permanece en el entorno local y no se publica en los fixtures del repositorio.

OpenAI se configura con una API key privada en el entorno. El preprocesamiento transcribe audio o interpreta imágenes y entrega ese contexto al único agente principal, que realiza las llamadas a herramientas. No se requiere un proveedor distinto para cada modalidad; sí modelos y permisos compatibles. [W4–W6]

```mermaid
flowchart LR
    A["Arrancar y cargar fixtures"] --> B["Abrir central"]
    B --> N["Cambiar teléfono de cliente por WhatsApp del evaluador"]
    N --> C["Previsualizar y lanzar campaña"]
    C --> D["Conversar y verificar identidad"]
    D --> E{"Recorrido"}
    E --> F["Pago completo"]
    E --> G["Oferta del 90%"]
    E --> H["Menos del 80% tras negociar o disputa"]
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
- Seeds y PIN ficticio; edición del teléfono por el evaluador antes de la campaña; preparación de identidad, reinicio y limpieza del entorno de demo.
- Guion de pago completo, descuento, comprobante, disputa y handoff.
- Pruebas y resultados de aceptación; limitaciones conocidas y consumo observado.
- Explicación de servicios reales, simulados y emulados, sin atribuir equivalencia total a Floci.
- Grabación de respaldo cuando se prepare, y narrativa de decisiones para sustentación.

## 17. Criterio para pasar a Spec Kit

La [especificación de entrega](001-cobranza-whatsapp/spec.md) y su [plan técnico](001-cobranza-whatsapp/plan.md) desarrollan esta base de producto con Spec Kit. Los supuestos configurables se registran allí; los accesos externos pendientes se validan durante la integración.

Los FR-01–22 y AC-01–31 se conservan en la especificación, las tareas y la futura evidencia. Redactar estos artefactos no demuestra que la implementación ni sus pruebas estén terminadas.

## 18. Referencias y supuestos de alcance

### Referencias

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
| W4 | [OpenAI: llamadas a herramientas](https://developers.openai.com/api/docs/guides/function-calling) | Inferencia y ejecución de herramientas por la aplicación |
| W5 | [OpenAI: transcripción de audio](https://developers.openai.com/api/docs/guides/speech-to-text) | Normalización de audio antes del agente |
| W6 | [OpenAI: visión](https://developers.openai.com/api/docs/guides/images-vision) | Interpretación de capturas e imágenes |
| W7 | [Floci: integración local con herramientas AWS](https://floci.io/floci/getting-started/terraform/) | Emulación local separada de recursos AWS reales |
| W8 | [Amazon EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html) | Máquina virtual, disco EBS y controles de red del despliegue inicial |

G, J e I son fuentes locales de referencia y no se incorporan como archivos al repositorio público. J pertenece a otro dominio: se reutiliza el patrón, sin importar sus reglas de negocio ni sus datos operativos.

### Alcance y supuestos

La solución empresarial propuesta debe alojarse en AWS; la guía permite que el prototipo se ejecute localmente. El demo usará datos ficticios, pasarela simulada, emulación local con Floci y llamadas reales a OpenAI. La inferencia de OpenAI es una dependencia externa del prototipo; el documento de arquitectura debe explicitar su encaje con la exigencia de infraestructura AWS, sin presentar la API de OpenAI como un servicio AWS. La base inicial es una sola EC2 con contenedores y persistencia en EBS. Los modelos, la región, el dimensionamiento y los detalles de despliegue se resuelven en el diseño. Los servicios especializados quedan para una evolución posterior. [G, C]

**Supuestos propuestos:** producto interno para una telco; una deuda agregada por contrato/servicio en el MVP; negociación sobre una deuda seleccionada. Son supuestos explícitos, no decisiones atribuidas a LLA.
