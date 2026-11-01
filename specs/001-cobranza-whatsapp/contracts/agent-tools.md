# Contrato de herramientas y contexto del agente

Un único nodo LangGraph contiene las llamadas OpenAI y el ciclo de herramientas.
El contexto confiable se construye en el servidor: cuenta, inbox, conversación,
mensaje, source_id literal del contacto, sesión, deuda seleccionada, campaign_id y correlación.
Se entrega al modelo solo la porción no secreta necesaria. Grant, PIN y tokens no
son argumentos del modelo ni se escriben en prompts, checkpoints o trazas.

## Herramientas

Ocho herramientas: localización previa al PIN y las siete operaciones de cartera
y atención. Antes del PIN solo se habilitan locate_customer y handoff_human,
con sus resultados limitados; el catálogo financiero exige sesión vigente.

| Nombre | Argumentos del modelo | Precondición y resultado |
|---|---|---|
| locate_customer | phone_e164 o document_type + document_number, excluyentes | Sin requerir PIN; localiza solo por celular o identificación. Devuelve candidate_reference y pista enmascarada, nunca saldos; registra candidato y confirmación pendiente. Buscar otro registro revoca el contexto anterior antes de continuar |
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

El resultado de una orden entrega al modelo un marcador de enlace asociado a su
order_id, sin la capability. El backend sustituye ese marcador por la URL firmada
al preparar la salida autorizada. Checkpoints y trazas conservan el marcador, no
el token; el cliente recibe el enlace real por Chatwoot.

## Secuencia del nodo

1. Cargar contexto no secreto, source_id literal, estado de autorización y selección.
   Sin sesión se permite localización enmascarada, no consulta financiera.
2. Reservar consumo; llamar Responses con herramientas permitidas,
   parallel_tool_calls=false, reasoning.effort=high para gpt-5.6-luna y límites
   del plan. Si la respuesta queda incomplete, no afirmar éxito ni ejecutar una
   llamada a herramienta con argumentos truncados.
3. Validar nombre, argumentos y permisos; ejecutar contra central o integración
   correspondiente; registrar resultado redactado y devolverlo al modelo.
4. Repetir hasta respuesta final o cinco llamadas. Error persistente o límite
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
candidato, se pide tipo y número de documento. Se confirma con pista enmascarada.

El backend registra el candidato confirmado y que espera PIN; procesa la
confirmación explícita y el PIN fuera del LLM. Una respuesta ambigua a la
confirmación pide aclaración y nunca autentica. Mientras espera PIN, solo procesa
el código escrito: audio/imagen provocan una petición de texto sin inferencia.
El turno posterior recibe identity_verified o un fallo seguro, sin PIN ni grant.
El acceso autorizado al registro permite consultar sus deudas, no identifica
necesariamente al interlocutor como su titular.

Al elegir otro cliente se revoca el contexto anterior, aumenta identity_revision,
se limpian historial financiero activo y referencias y se cancelan salidas de
la revisión anterior. Se mantiene thread_id y se exige el PIN del nuevo candidato.
Si el cambio ocurre durante el bucle, se reconstruye la entrada al LLM antes de
continuar. No se mezclan saldos, órdenes ni historial financiero de clientes.

Audio se transcribe; imagen devuelve observaciones, texto visible y referencia de
pago con procedencia marcada como no verificada. Se conserva el mensaje acompañante.
El agente usa verify_payment para contrastar un comprobante aunque la imagen parezca
exitosa. La referencia ajena produce respuesta segura, sin datos del otro cliente.

thread_id = source_id del contacto exactamente como llega. Cuenta/inbox se validan
por separado; conversation_id determina el destino y control humano de cada evento.
El reset borra memoria local y actualiza el corte de eventos, sin modificar esa llave
ni el historial externo de Chatwoot. Los IDs operativos se redactan en trazas/logs
cuando contienen teléfono u otros identificadores personales.
