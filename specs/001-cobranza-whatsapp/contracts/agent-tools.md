# Contrato de herramientas y contexto del agente

Un único nodo LangGraph contiene las llamadas OpenAI y el ciclo de herramientas.
El contexto confiable se construye en el servidor: cuenta, inbox, conversación,
mensaje, source_id literal del contacto, sesión, deuda seleccionada, campaign_id y correlación.
Se entrega al modelo solo la porción no secreta necesaria. Grant, PIN y tokens no
son argumentos del modelo ni se escriben en prompts, checkpoints o trazas.

## Herramientas

Nueve herramientas: localización, gestión del desafío de identidad y las siete
operaciones de cartera y atención. Antes de entrar en la fase estática de PIN se habilitan locate_customer,
manage_identity y handoff_human, con sus resultados limitados; el catálogo
financiero exige sesión vigente. El backend comprueba estos permisos en cada
ejecución, aunque el modelo solicite una herramienta no autorizada.

| Nombre | Argumentos del modelo | Precondición y resultado |
|---|---|---|
| locate_customer | phone_e164 o document_type + document_number, excluyentes | Sin requerir PIN; localiza solo por celular o identificación. Devuelve candidate_reference y, en esta demo, pista con nombre enmascarado y tipo/número de documento completos antes del PIN, nunca saldos; registra candidato y confirmación pendiente. Buscar otro registro revoca el contexto anterior antes de continuar |
| manage_identity | action: confirm_candidate, reject_candidate o change_customer | confirm_candidate activa awaiting_pin con contador local cero y solicitud fija de PIN, terminando el bucle sin otra inferencia; reject_candidate rechaza el candidato y change_customer revoca contexto. El backend valida el estado y aplica la transición; nunca concede sesión financiera ni valida un PIN |
| list_debts | filtro de servicio opcional | Sesión vigente; devuelve solo servicios autorizados con saldo, mora y estado |
| select_debt | debt_id | Debe pertenecer al cliente; registra una única selección activa por thread; permite gestionar deudas sucesivamente, sin agregarlas ni borrar órdenes previas |
| create_full_payment | debt_id | Deuda seleccionada; consulta versión actual y crea orden por saldo sin descuento |
| quote_agreement | debt_id, offer_amount_usd string | Valida oferta en central; devuelve condiciones o requires_human; sin condonar |
| accept_agreement | agreement_id | Condiciones previas y mensaje posterior de conformidad; crea orden por oferta autorizada |
| verify_payment | debt_id, payment_reference opcional | Consulta real a central y propiedad; devuelve aplicado/ausente/pendiente, importes y saldo |
| handoff_human | reason, offer_amount_usd opcional, summary | Motivo validado; caso durable, nota privada y open; nunca devuelve secretos |

Los argumentos tienen esquema estricto y se rechazan extras. El backend inyecta
identidad y source_message_id. Las claves idempotentes se derivan de mensaje,
herramienta y registro/deuda/propuesta según la operación, con hash de argumentos; reejecutar el nodo no repite
orden, aceptación ni caso. La herramienta de descuento no crea una oferta
inferior al 80% ni acepta acuerdo dentro del mismo mensaje que generó la quote.
No hay herramienta de actualización arbitraria de saldo ni de autenticación por
mera afirmación del modelo. locate_customer puede iniciar la búsqueda de otro
registro, pero no concede acceso ni permite reutilizar el grant anterior.
manage_identity solo acepta el campo action con ese enum estricto; no acepta
PIN, grant ni un cliente elegido libremente por el modelo. confirm_candidate
actúa sobre el candidato pendiente del backend; su respuesta fija no se somete
a otra inferencia del nodo. reject_candidate y
change_customer limpian el desafío o revocan el contexto correspondiente; las
referencias financieras anteriores no se reutilizan.

La petición explícita de cerrar sesión usa `manage_identity(change_customer)`.
Tras el resultado no verificado, el agente confirma el cierre y espera otro
documento; no vuelve a buscar al titular anterior automáticamente por source_id.
La fase vuelve a identify y se requiere confirmación y PIN para el nuevo registro.

El prompt orienta hacia pago íntegro y ofrece un siguiente paso concreto. Ante
una oferta válida con descuento intenta hasta dos contraofertas conversacionales,
graduales y superiores a la oferta, una por turno, sin anunciar inicialmente el
descuento máximo. El historial de la deuda determina cuántas realizó. Si acepta
una, cotiza ese importe; si rechaza ambas, puede cotizar la oferta válida mantenida.
No hay una escalera fija de porcentajes ni un contador adicional de autorización.
Quote y aceptación posterior siguen siendo pasos distintos. Los importes por
debajo del 80 % siguen derivándose a humano y central valida los límites.

El resultado de una orden entrega al modelo un marcador de enlace asociado a su
order_id, sin la capability. El backend sustituye ese marcador por la URL firmada
al preparar la salida autorizada. Checkpoints y trazas conservan el marcador, no
el token; el cliente recibe el enlace real por Chatwoot.

## Identificación en lenguaje natural

`locate_customer` recibe valores canónicos separados. El modelo interpreta nombres,
códigos, tildes y el orden del mensaje; en esta demo cédula de ciudadanía/cédula se
consulta con `document_type=CC`. Para identificación numérica elimina puntos o
espacios de agrupación claros y conserva dígitos y ceros iniciales, sin ajustarla
a la longitud del fixture. Otros tipos no se convierten en CC y sus caracteres
significativos se conservan. La falta de datos o ambigüedad exige aclaración.
El contrato se explica en el prompt y en las descripciones de la herramienta y
sus campos; no hay un clasificador ni un normalizador de mensajes previo al LLM.

## Secuencia del nodo

El prompt limita al agente a gestión de cartera: no responde programación,
comparaciones de marcas o asistencia general, aunque el historial contenga una
respuesta anterior fuera de alcance. En peticiones mixtas atiende solo la parte
autorizada. La petición exclusivamente ajena se reconduce sin usar herramientas.
Declaraciones de rol, flags de identidad y órdenes en medios o resultados son
datos no confiables; no conceden permisos ni permiten extraer instrucciones.
Este límite conversacional se implementa únicamente en el prompt; no agrega un
clasificador ni cambia los esquemas, nodos o validaciones del backend.

1. Cargar contexto no secreto, source_id literal, estado de autorización y selección.
   Sin sesión se permite la pista de la demo (nombre enmascarado y documento
   completo), no consulta financiera.
2. Reservar consumo; llamar Responses con herramientas permitidas,
   parallel_tool_calls=false, reasoning.effort=high para gpt-5.6-luna y límites
   del plan. Si la respuesta queda incomplete, no afirmar éxito ni ejecutar una
   llamada a herramienta con argumentos truncados.
3. Validar nombre, argumentos y permisos; ejecutar contra central o integración
   correspondiente; registrar argumentos y resultado en Langfuse privado cuando
   la captura de contenido esté habilitada, excluyendo secretos y autorizaciones;
   devolver al modelo el resultado permitido por su sesión.
4. Repetir hasta respuesta final o cinco llamadas. Si confirm_candidate activa
   awaiting_pin, terminar con la solicitud fija de PIN sin otra inferencia. Error persistente o límite
   produce explicación o handoff, sin afirmar una acción no ejecutada.
5. Guardar respuesta pendiente en outbox; consultar pending antes del envío.

El historial incluye textos de cliente y resultados autorizados, sin PIN ni URLs
con capability completa. Los resultados de herramientas se tratan como datos:
una instrucción incrustada no modifica políticas ni permisos.

El [esquema de estado y ventana de historial](../agent-state.md) define qué se
persiste y qué se selecciona para cada llamada. El checkpointer recupera el estado
por thread_id; el nodo selecciona mensajes sin borrar el historial persistido.
El límite de tokens incluye instrucciones, contexto y herramientas. Las referencias
a deuda/acuerdo/orden se revalidan; una ventana corta no sustituye la confirmación
de condiciones ni convierte una salida generada en un mensaje enviado.

## Localización en el agente y validación de PIN

El prompt recibe source_id literal, sin source_type precalculado ni un nodo de
clasificación anterior. El LLM interpreta el valor y decide llamar locate_customer
por teléfono o pedir identificación ficticia. Un Business ID no se busca como
celular. Si no hay coincidencia, hay ambigüedad o el interlocutor rechaza el
candidato, se pide tipo y número de documento. En esta demo, la confirmación
muestra el nombre enmascarado y el tipo y número de documento completos antes
del PIN; el agente copia la pista sin ocultar dígitos por su cuenta. Esa visibilidad
no concede cartera y no altera la protección ni la validación del PIN.

Fuera de awaiting_pin / waiting_auth, todo mensaje admitido pasa al único nodo
agente con system prompt y memoria. Incluye números aislados: no hay filtro global
de PIN. El LLM interpreta «sí», «no», «dale», preguntas, asesor y cambio de cliente
y llama manage_identity cuando corresponde; si la intención es ambigua, aclara.
El backend valida la transición, sin listas de palabras para decidir intenciones.

confirm_candidate activa awaiting_pin con contador local cero y solicitud fija,
sin inferencia posterior. Durante esa fase todos los mensajes se procesan por
IdentityService.consume_auth de forma estática. Solo se acepta texto numérico de 4 a 8 dígitos;
formato incorrecto, medio o PIN rechazado suma un fallo. Antes del tercero se
responde de forma fija. Un PIN correcto sale con identity_verified; al tercer
fallo se sale con auth_attempts_exhausted SIN autorización. Esos eventos neutros
entran al agente sin PIN ni grant; solo con sesión validada puede llamar list_debts.
Después del agotamiento puede orientar la continuación y atender una petición
de asesor, sin handoff automático. El límite local de tres mensajes fallidos no
elude el bloqueo de 15 minutos por errores de PIN aplicado por central.

El ingreso valida firma/scope/evento y persiste durablemente en local antes del
HTTP 200, sin red de negocio. Durante auth, el contenido usa transporte temporal
cifrado Fernet; el worker verifica el PIN con central después del acuse. Ni el PIN
en claro ni el sobre cifrado se entregan al LLM, checkpoints o Langfuse. Fuera de
auth, un prefijo interno falsificado se firma como datos del remitente y no concede
autoridad. El backend aplica cada permiso financiero fuera del modelo. El acceso
autorizado al registro no prueba que el interlocutor sea su titular.

Al elegir otro cliente se revoca el contexto anterior, aumenta identity_revision,
se limpian historial financiero activo y referencias y se cancelan salidas de
la revisión anterior. Se mantiene thread_id y se exige el PIN del nuevo candidato.
Si el cambio ocurre durante el bucle, se reconstruye la entrada al LLM antes de
continuar. No se mezclan saldos, órdenes ni historial financiero de clientes.

Fuera de auth, audio se transcribe e imagen aporta observaciones, texto visible y
referencia de pago no verificada, conservando el mensaje acompañante. Durante
awaiting_pin, los medios son formato no válido y consumen un intento sin inferencia.
No se autentica un PIN hablado o extraído de una imagen. Tampoco se promete ocultar
secretos en medios procesados fuera de auth. El agente usa verify_payment para
contrastar comprobantes; una referencia ajena no revela datos del otro cliente.

thread_id = source_id del contacto exactamente como llega. Cuenta/inbox se validan
por separado; conversation_id determina el destino y control humano de cada evento.
El reset borra memoria local y actualiza el corte de eventos, sin modificar esa llave
ni el historial externo de Chatwoot. Los logs y metadatos de sesión usan referencias
opacas. La captura de contenido autorizada conserva identificadores personales,
argumentos y resultados en Langfuse privado; no incluye credenciales ni grants.
