# Feature Specification: Demo de cobranza por WhatsApp

**Feature Branch**: `main` (sin extensión de ramas; feature `001-cobranza-whatsapp`)
**Created**: 2026-10-31
**Status**: Especificación y diseño disponibles; implementación pendiente.
**Input**: PRD integral y aclaraciones de Cristian; entrega lunes 2026-11-02,
America/Bogota, hora pendiente. Véanse [PRD](../prd.md) y
[arquitectura inicial](../arquitectura-inicial.md).

## User Scenarios & Testing *(mandatory)*

Todas las historias forman parte de la entrega. La prioridad determina el orden
para obtener un recorrido funcional temprano; P2 no significa opcional.
Cada historia puede validarse con escenarios semilla sin depender de haber
recorrido manualmente todas las anteriores.

### User Story 1 - Consultar y pagar una deuda completa (Priority: P1)

Como cliente, quiero identificarme, elegir uno de mis servicios y pagar la deuda
completa, para recibir una confirmación contrastada con el sistema central.

**Why this priority**: Es el recorrido principal que demuestra lectura, escritura
y una acción real del agente sobre sistemas, con dinero simulado.

**Independent Test**: Iniciar conversación con un cliente semilla, validar PIN,
elegir servicio, aprobar el pago y pedir verificación del resultado. El sistema
deja saldo cero exclusivamente en la deuda seleccionada.

**Acceptance Scenarios**:

1. **Given** una persona con dos servicios pendientes, **When** se identifica
   correctamente, **Then** ve sus servicios y elige una deuda sin mezclar saldos.
2. **Given** identidad sin verificar o PIN incorrecto, **When** pide cartera,
   **Then** no se revelan saldos ni información de otras personas.
3. **Given** una deuda de USD 100, **When** solicita el enlace y aprueba el pago,
   **Then** se registran USD 100 recibidos, cero condonados y saldo cero.
4. **Given** un pago rechazado o enlace vencido, **When** vuelve a consultar,
   **Then** la deuda conserva el saldo y recibe una siguiente acción coherente.
5. **Given** un evento repetido o dos intentos simultáneos de liquidación,
   **When** se procesan, **Then** el pago y la liquidación tienen efecto una vez.
6. **Given** source_id de contacto literal, **When** llegan mensajes desde distintas
   conversaciones de Chatwoot con ese valor, **Then** comparten memoria, se procesan
   en serie y cada respuesta vuelve a la conversación del evento que la originó.
7. **Given** un candidato rechazado o un Business ID, **When** el interlocutor
   aporta otra identificación, **Then** puede gestionar ese registro solo tras su
   PIN, sin arrastrar saldos ni referencias del cliente anterior.

### User Story 2 - Preparar contacto y lanzar una campaña (Priority: P1)

Como evaluador que hace de operador, quiero poner mi WhatsApp en un deudor
ficticio, elegir cartera por servicio y mora y lanzar una campaña, para recibir
y responder el aviso en mi propio teléfono.

**Why this priority**: Conecta la central editable con el canal real de la demo.

**Independent Test**: Editar un cliente con varios servicios, filtrar 30–59 días,
previsualizar destinatarios, lanzar y comprobar el mensaje y sus estados.

**Acceptance Scenarios**:

1. **Given** un cliente ficticio con dos servicios, **When** el evaluador cambia
   su teléfono, **Then** ambas filas comparten el contacto guardado y el siguiente
   aviso se dirige a ese número habilitado para pruebas.
2. **Given** deudas de 29, 30, 59 y 60 días, **When** filtra 30–59, **Then** solo
   entran 30 y 59 con saldo pendiente; los ficticios se simulan y el destino real
   exige habilitación de contacto de prueba.
3. **Given** varios servicios elegibles de una persona, **When** lanza campaña,
   **Then** recibe un solo aviso inicial asociado a las deudas del segmento.
4. **Given** el mismo lanzamiento repetido, **When** se reintenta, **Then** no se
   duplica el envío; aceptación, entrega y fallo se muestran por separado.

5. **Given** un lote con números ficticios y el del evaluador, **When** inicia
   campaña, **Then** procesa una persona a la vez, registra simulación sin llamar
   al canal para los ficticios y envía realmente solo al evaluador. El progreso
   se conserva al reiniciar y lo simulado no cuenta como contacto real.

### User Story 3 - Negociar un acuerdo con descuento (Priority: P1)

Como cliente que no puede pagar el total, quiero ofrecer un importe y conocer
las condiciones del descuento antes de aceptarlas.

**Why this priority**: Expone la política de autorización y diferencia pago total
de recuperación con condonación.

**Independent Test**: Sobre USD 100 probar ofertas 90, 80 y 79,99; las primeras
permiten acuerdo, la última requiere humano. Pagar 90 deja 90 recibidos y 10
condonados. Un acuerdo sin pago conserva pendiente la deuda de 100.

**Acceptance Scenarios**:

1. **Given** oferta de USD 90 sobre USD 100, **When** confirma condiciones,
   **Then** recibe orden por 90 y conoce que se condonarán 10 al pagar.
2. **Given** oferta exactamente del 80%, **When** confirma y paga, **Then** se
   liquida con pago y descuento separados.
3. **Given** oferta inferior al 80%, **When** rechaza las propuestas del 95% y
   después del 80% manteniendo su oferta inferior, **Then** se deriva a humano
   sin autorizar automáticamente ese descuento. Si acepta una propuesta, se cotiza
   y requiere confirmación posterior antes del enlace.
4. **Given** importe ambiguo, no positivo, superior al saldo o en otra moneda,
   **When** lo ofrece, **Then** se aclara o rechaza antes de emitir una orden.
5. **Given** saldo cambiado desde la oferta, **When** intenta pagar o generar
   otro enlace, **Then** se revalida la deuda y no se usa un saldo anterior.

### User Story 4 - Gestionar audio e imágenes y verificar comprobantes (Priority: P1)

Como cliente, quiero hablar por nota de voz y enviar una captura del pago para
que el agente comprenda el contexto y verifique qué quedó registrado.

**Why this priority**: Es parte del recorrido demostrable exigido para esta demo.

**Independent Test**: Con pago semilla aplicado y sin aplicar, enviar audio,
comprobante válido, imagen ilegible y referencia ajena; contrastar las consultas
realizadas y las respuestas.

**Acceptance Scenarios**:

1. **Given** audio con texto acompañante, **When** lo envía, **Then** se conserva
   el contexto de ambos y se aclaran las partes que no se entienden.
2. **Given** una captura del pago aprobado en la web, **When** la envía por
   WhatsApp, **Then** el agente consulta pago, titularidad y deuda antes de
   confirmar; el evaluador puede contrastar esa verificación.
3. **Given** imagen que parece un pago sin registro aplicado, **When** pide
   confirmación, **Then** el agente no afirma liquidación y explica el estado.
4. **Given** referencia de otra persona o archivo ilegible/no soportado,
   **When** se procesa, **Then** no se revelan datos ajenos ni se inventa contenido.

### User Story 5 - Recibir atención humana con contexto (Priority: P1)

Como cliente, quiero que un asesor tome el caso cuando lo solicito, disputo la
deuda o mi situación excede lo que el agente puede resolver.

**Why this priority**: La excepción es una salida funcional del producto.

**Independent Test**: En conversación semilla pedir asesor, disputar y ofrecer
menos del 80% tras rechazar la negociación del 95% y 80%; inspeccionar motivo y resumen privados. Cambiar el control durante
una respuesta y comprobar que el bot se detiene.

**Acceptance Scenarios**:

1. **Given** solicitud de asesor, disputa, oferta no autorizada o fallo persistente,
   **When** se deriva, **Then** se informa al cliente y el asesor recibe motivo,
   deuda, oferta y verificaciones sin PIN ni claves.
2. **Given** afirmación de pago previo, **When** puede consultarse el sistema,
   **Then** se intenta verificar antes de declarar una discrepancia.
3. **Given** una conversación fuera de pending, **When** llega otro mensaje o
   termina una respuesta preparada, **Then** no se envía respuesta automática.
4. **Given** atención humana, **When** el asesor devuelve expresamente el control
   a pending, **Then** se retoma con contexto y se revalida la información vigente.

### User Story 6 - Inspeccionar resultados y reproducir la evaluación (Priority: P2)

Como evaluador, quiero entender los resultados de campaña y los pasos del agente,
restaurar escenarios y ejecutar la prueba siguiendo el README.

**Why this priority**: Permite verificar el resultado sin explicaciones verbales.

**Independent Test**: Cargar eventos conocidos, comprobar contadores y tasas,
inspeccionar trazas de un turno y restaurar el entorno con el guion documentado.

**Acceptance Scenarios**:

1. **Given** una persona que responde cinco mensajes a una campaña, **When** se
   calculan métricas, **Then** cuenta como una sola persona contactada.
2. **Given** pagos completos y acuerdos con descuento, **When** consulta resultados,
   **Then** se separan pago íntegro sin condonación, acuerdo pendiente y cumplido,
   dinero recibido, condonado y saldo pendiente.
3. **Given** solicitudes de asesor y derivaciones automáticas, **When** consulta
   métricas, **Then** se distingue su origen aunque luego haya un pago.
4. **Given** un caso abierto sin resolución y uno cerrado sin resultado,
   **When** consulta resultados al corte, **Then** no se etiqueta el caso abierto
   como fracaso ni se mezcla con personas que nunca respondieron.
5. **Given** entorno limpio y configuración privada, **When** sigue el README,
   **Then** puede preparar su celular y reproducir pago, acuerdo, comprobante,
   audio, atención humana, inspección y restauración.

### Edge Cases

- Identificador del canal sin coincidencia: pedir identificación ficticia y PIN;
  asociar la sesión solo si se verifican. Si no es posible, derivar sin revelar cartera.
- Contacto compartido por clientes distintos: no elegir identidad por teléfono
  ambiguo; pedir identificación y PIN antes de consultar datos.
- Tres PIN incorrectos: bloquear nuevos intentos durante 15 minutos y ofrecer asesor.
- Mensajes repetidos, privados o enviados por el propio bot: no iniciar otro turno.
- Reinicio: conservar conversación y eventos pendientes sin conservar indefinidamente
  la autorización; volver a comprobar sesión, saldo y control humano.
- Dos mensajes del mismo source_id, incluso en diferentes conversaciones Chatwoot:
  respetar su orden y conservar el destino de cada salida; otros threads pueden avanzar.
- source_id ausente: no inventar una llave ni usar el identificador externo del mensaje.
- Dos órdenes para una deuda o pago mientras se prepara enlace: una sola liquidación
  con saldo actual y sin una segunda condonación.
- Archivo excesivo, origen no permitido, medio ilegible o fallo de inferencia:
  explicar el problema, limitar reintentos y ofrecer alternativa o atención humana.
- Instrucciones en chat, imagen o resultados de consulta no cambian permisos,
  identidad, umbral financiero ni estado de control humano.
- Fallo de observabilidad: no bloquear indefinidamente atención ni inventar una traza.
- Pago cuya aplicación no puede confirmarse: informar pendiente de verificación;
  no mostrar liquidación ni crear automáticamente un segundo cobro.

## Requirements *(mandatory)*

### Functional Requirements

Los IDs conservan la numeración del PRD; no se crea un segundo catálogo paralelo.

- **FR-01**: La central DEBE mostrar y editar clientes y deudas por servicio, con
  contacto, identificación ficticia, tipo de cliente, saldo en USD, vencimiento,
  días de mora y estados separados de deuda y servicio.
- **FR-02**: Cada deuda DEBE tener ID propio y pertenecer a un cliente identificado
  por tipo y número de documento, con contacto compartido por sus servicios.
- **FR-03**: El agente DEBE consultar cartera y registrar efectos financieros
  mediante la integración con el sistema central simulado, con resultados verificables.
- **FR-04**: El operador DEBE filtrar por mora, servicio, tipo de cliente,
  identificación y estado y previsualizar personas únicas y deudas seleccionadas.
- **FR-05**: Las campañas DEBEN excluir pagos completos y bajas; los números
  ficticios solo se simulan y el destino real exige habilitación de prueba.
  Se revalida elegibilidad antes de enviar y se evitan duplicados.
- **FR-06**: Las campañas DEBEN recorrer los destinatarios uno por uno, con
  plantillas preaprobadas y progreso persistente. Se separan envíos simulados,
  aceptación real, entrega y error; se continúa con el siguiente tras registrar
  un fallo o resultado incierto, sin repetir automáticamente este último.
- **FR-07**: El canal DEBE distinguir mensajes entrantes, salidas y notas privadas,
  deduplicar e impedir negociaciones simultáneas incoherentes en una conversación.
- **FR-08**: El LLM DEBE recibir el source_id literal y decidir buscar por teléfono
  o pedir identificación ficticia, sin clasificación previa. Un candidato se confirma
  con pista enmascarada y se verifica su PIN fuera del modelo antes de revelar cartera.
  Rechazar al candidato permite buscar otro registro; se limitan intentos.
- **FR-09**: Todas las consultas y acciones DEBEN limitarse al cliente autenticado;
  conocer una referencia de otra persona no concede acceso.
- **FR-10**: Audio, imagen y texto DEBEN conservar contexto y procedencia y
  producir una aclaración cuando no puedan interpretarse con confianza suficiente.
- **FR-11**: Las decisiones conversacionales DEBEN usar inferencia real y
  herramientas ejecutadas realmente; las reglas financieras no dependen del modelo.
- **FR-12**: La memoria DEBE usar como thread_id el source_id literal del contacto,
  sin normalización ni concatenaciones. Cambiar de identificador abre otra memoria;
  cambiar de cliente exige nuevo PIN y limpiar contexto financiero activo. Cada
  respuesta conserva el conversation_id de su evento; recordar no concede acceso.
- **FR-13**: Las ofertas DEBEN validarse contra saldo vigente, deuda y USD;
  importes no positivos o superiores al saldo se rechazan, sin conversiones monetarias.
- **FR-14**: Un acuerdo automático DEBE ofrecerse solo desde el 80% e inferior
  al total y exigir conformidad con pago y condonación antes de emitir orden.
- **FR-15**: El enlace DEBE identificar una orden con importe autorizado y
  caducidad; el cliente no puede alterar el importe desde la web.
- **FR-16**: El simulador DEBE aprobar o rechazar, registrar dinero y descuento
  por separado y liquidar una sola vez; el comprobante debe indicar que es simulado.
- **FR-17**: Una captura DEBE provocar la consulta del pago y su asociación al
  cliente y deuda; nunca confirma por sí sola que la deuda esté liquidada.
- **FR-18**: El sistema DEBE registrar motivo y resumen privado al derivar,
  respetar el control pending existente y requerir retorno explícito al bot.
- **FR-19**: El evaluador DEBE poder inspeccionar turno, interpretación de medios,
  herramientas, resultados, errores, latencia y consumo sin secretos en los registros.
- **FR-20**: La entrega DEBE guiar arranque, edición del teléfono del cliente por
  el del evaluador, recorridos y restauración, diferenciando componentes reales,
  simulados y emulados. La modalidad de entrega acordada el 2 de noviembre es
  un despliegue ejecutable en EC2 emulada mediante Floci: debe crear una instancia
  Linux y ejecutar allí el stack propio, comprobar salud y persistencia tras
  reiniciar, y comenzar con datos ficticios limpios. No basta con simular la
  respuesta de creación de la instancia ni con ejecutar el stack del host.
  La prueba se aislará de la demo existente y no aprovisionará AWS real.
- **FR-21**: Días de mora DEBE ser un entero no negativo editable por deuda;
  el filtro 30–59 incluye ambos extremos y excluye 29 y 60.
- **FR-22**: La central DEBE mostrar envíos, personas únicas, contactabilidad,
  pago total sin condonación, acuerdos y su cumplimiento, solicitudes humanas,
  escalados automáticos, casos en gestión y casos cerrados sin resultado.

### Key Entities *(include if feature involves data)*

- **Cliente**: Identidad ficticia, contacto, tipo de cliente y verificación de demo;
  tiene varios servicios y no se duplica al editar su teléfono.
- **Deuda de servicio**: Obligación agregada por contrato, saldo, mora, vencimiento
  y estado; es la unidad financiera del acuerdo y de la liquidación.
- **Campaña y destinatario**: Segmento al lanzamiento, personas y deudas elegibles,
  plantilla y eventos de envío y respuesta.
- **Conversación y sesión verificada**: Contexto y control del canal, con autorización
  temporal independiente del historial conversacional.
- **Acuerdo**: Oferta aceptada con descuento previsto, caducidad y cumplimiento.
- **Orden e intento de pago**: Importe autorizado, enlace, vigencia e intentos;
  una aprobación aplicada tiene un comprobante asociado.
- **Registro financiero**: Pago y condonación efectivos, referencias únicas y saldo.
- **Caso humano**: Motivo, origen de derivación, resumen privado y control del asesor.
- **Evento de gestión y traza**: Evidencia de envío, respuesta, herramienta,
  acuerdo, pago y consumo, relacionada con el caso sin exponer secretos.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-01**: El evaluador reproduce los seis recorridos y restaura los escenarios
  siguiendo el README, sin instrucciones verbales adicionales.
- **SC-02**: En los casos de aceptación financiera, USD 100 pagados íntegramente
  dejan cero condonado; pagar USD 90 bajo acuerdo deja USD 10 condonados y saldo cero.
- **SC-03**: El 100% de ofertas mantenidas inferiores al 80% tras rechazar la negociación
  del 95% y 80%, disputas y solicitudes de asesor de la batería generan derivación; cero envíos automáticos iniciados cuando la
  comprobación de control indica que la conversación está fuera de pending.
- **SC-04**: Cero liquidaciones basadas solo en una captura, revelaciones de cartera
  ajena o aplicaciones duplicadas en los casos de aceptación críticos.
- **SC-05**: Cada turno de texto, audio e imagen del guion tiene evidencia consultable
  de procesamiento y herramientas; los importes comunicados coinciden con el sistema.
- **SC-06**: Los contadores coinciden con los eventos conocidos. Como prueba
  ilustrativa, diez destinatarios enviados y cuatro personas que responden producen
  40% de contactabilidad aunque una de ellas envíe cinco mensajes.
- **SC-07**: La evaluación registra el consumo de agente, audio, imagen y reintentos
  frente a USD 5 y detiene nuevas llamadas cuando su control local agota el presupuesto.
- **SC-08**: Los 31 casos AC-01 a AC-31 del PRD tienen resultado y evidencia antes
  de declarar la entrega verificada; ningún resultado se presupone por documentarlo.

## Assumptions

- La entrega es el lunes 2026-11-02. La hora exacta sigue siendo un dato de agenda;
  no bloquea especificación y no autoriza prometer entrega a una hora inventada.
- Una deuda es el saldo vencido agregado por contrato, no una factura individual.
  Se usa un catálogo de identificación ficticia claramente marcado como demo.
- Los datos de cartera y días de mora se mantienen por fixtures y edición manual.
- Los fixtures empiezan en modo simulated y solo el contacto marcado como evaluador
  se habilita en live. La edición de su celular permite elegir ese modo en el mismo
  formulario. No se infiere el modo por el formato del teléfono ni se contactan
  números ficticios. Los KPI de contacto usan solo destinatarios reales.
- La demo tiene una campaña activa por persona y una deuda seleccionada por gestión;
  varios servicios pueden producir resultados distintos sin duplicar contactos.
- El despliegue acepta una cuenta/inbox configurados, con memoria por source_id
  literal y destino por evento. No fusiona identidades del canal. El mismo usuario
  puede gestionar otro titular con su PIN; la cartera no guarda Business IDs.
- El reset elimina checkpoints y escrituras locales y fija una fecha de corte,
  sin cambiar la llave de memoria. epoch se conserva solo como control del escenario.
- Valores iniciales configurables: sesión verificada de 30 minutos, orden/acuerdo
  de 30 minutos y ventana de seguimiento de campaña de 24 horas. El operador puede
  cerrar una campaña para demostrar resultados al corte, sin alterar eventos previos.
- Casos humanos activos se muestran como tales; cerrarlos sin pago ni acuerdo vigente
  deja sin resultado al corte. La solicitud de asesor permanece como hito histórico.
- El número del evaluador y la plantilla deben estar habilitados en el canal de
  prueba. Dominio y configuración privada de Chatwoot se aportarán al integrar.
- El control pending ya está desplegado en Chatwoot; se integra y verifica su uso.
- La infraestructura inicial y las dependencias confirmadas se detallan en el plan;
  IaC y migración a servicios especializados permanecen fuera de esta entrega.
- Los casos de aceptación completos se mantienen en [PRD §11](../prd.md#11-plan-de-evaluación-del-agente).
  Sus IDs AC-01–31 se conservan en pruebas, tareas y evidencia.
- Se exigen pruebas relevantes de reglas financieras, identidad, aislamiento,
  idempotencia y concurrencia, más recorridos reales de canal e inferencia. No
  se exige una frase literal del modelo ni pruebas triviales del diseño visual.
