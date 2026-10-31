# Contrato de integración Chatwoot

**Dependencia existente:** Chatwoot conectado a Meta. Este proyecto cambia el
endpoint del bot para la demo e integra el control pending/open ya desplegado.
Ningún acceso o envío real se ha ejecutado durante esta planificación.

## Configuración y preflight

Entorno privado: base URL, account_id, inbox_id, token de Application API,
CHATWOOT_AUTH_SCHEME=api_access_token|bearer, secreto de webhook o relay, plantilla,
idioma y dominio del endpoint. La versión instalada define el esquema admitido;
Bearer aparece documentado desde v4.19.0. No enviar los dos headers por defecto.
Se valida token, cuenta, inbox, adjuntos y plantilla con la instancia real.

## Entrada

`POST /webhooks/chatwoot` consume bytes originales antes de normalizar JSON.
Cuando esté disponible, verificar `X-Chatwoot-Signature` como HMAC SHA256 del
contenido `{timestamp}.{raw_body}` y `X-Chatwoot-Timestamp`, comparación constante
y tolerancia de cinco minutos. `X-Chatwoot-Delivery` ayuda al diagnóstico; el dedupe
principal sigue siendo account_id + message_id. Una instalación sin firma necesita
relay autenticado configurado; no se habilita una entrada pública anónima.

Normalizar event, id de mensaje, account/inbox/conversation, sender/contact,
content, message_type, private, created_at y attachments según el payload real.
Solo message_created entrante y público del inbox/cuenta esperado inicia turno.
Actualizar entrega con eventos soportados sin tratar estados como nuevo mensaje.
Notas privadas, salidas propias y otros inbox no entran al agente.

Adjuntos: id, file_type, content_type, data_url y tamaño si existe. Descargar en el
backend verificando destino y cada redirect; no copiar tokens a otro host. El tipo
real y límites prevalecen sobre extensión y metadata. Guardar mensaje normalizado
y trabajo antes de ACK; PIN se intercepta sin persistir el texto secreto.
Eventos creados antes del epoch de reset no inician turnos del escenario nuevo.

## Control y salida

- GET `/api/v1/accounts/{account}/conversations/{conversation}` al iniciar y antes
  de enviar; exigir status=pending e inbox correcto. Comprobar can_reply según canal.
- POST `.../conversations/{conversation}/messages` para salida, message_type=outgoing
  y private=false. Nota de handoff usa private=true y contiene motivo y contexto.
- POST `.../conversations/{conversation}/toggle_status` con status=open explícito.
  El asesor devuelve pending; el bot no retoma por un temporizador.

No depender solo de eventos de cambio de estado: AgentBot puede no entregarlos.
Persistir caso e impedir salidas propias antes de nota y transferencia. Las
operaciones se reintentan por separado; una salida con timeout incierto no se
reenvía a ciegas. GET y POST no son atómicos: verificar el mecanismo existente
frente a cambio humano durante inferencia y reportar la carrera residual de red.

## Campaña al teléfono editado por el evaluador

Antes de este adaptador, el despachador recorre el lote secuencialmente. Si el
destino es simulated, registra el resultado local y continúa sin invocar estas
APIs. Solo el contacto live del evaluador habilitado llega a los pasos siguientes.

1. Obtener teléfono y contact_version actuales de central; invalidar binding previo
   si cambia la versión. No reutilizar una conversación por customer_id solamente.
2. GET `/api/v1/accounts/{account}/contacts/search?q={phone}`; paginar y comparar
   coincidencia exacta del teléfono normalizado, sin tomar el primer resultado.
3. Si falta, POST `.../contacts` con inbox_id, phone_number, name ficticio e identifier
   propio. Identifier no es source_id. Normalizar el envelope según preflight.
4. GET `.../contacts/{contact}/contactable_inboxes`; elegir inbox e identidad de
   destino correctos. Source_id es opaco: no se fabrica ni se convierte BSUID en teléfono.
5. GET `.../contacts/{contact}/conversations`; reutilizar solo conversación correcta
   y elegible. No recuperar automáticamente una bajo atención humana.
6. Si corresponde, POST `.../conversations` con source_id resuelto, inbox_id,
   contact_id y status=pending. Si la instalación no prepara la asociación por API,
   el README pide al evaluador un mensaje inicial de preparación; ese mensaje
   anterior no cuenta como respuesta a la campaña posterior.
7. POST mensaje con template_params: nombre, idioma, categoría y variables reales
   de plantilla aprobada. No iniciar con un texto libre fuera de ventana.
8. Guardar ID y aceptación; entrega se informa solo con evidencia posterior.

La plantilla se intenta clasificar como Utility por su intención transaccional,
sin promociones en el primer aviso. Meta determina la clasificación y aprobación;
no se promete mayor alcance ni éxito de entrega por elegir la categoría.

## Fuentes primarias

[Webhooks](https://www.chatwoot.com/hc/user-guide/articles/1677693021-how-to-use-webhooks),
[buscar contactos](https://developers.chatwoot.com/api-reference/contacts/search-contacts),
[crear contacto](https://developers.chatwoot.com/api-reference/contacts/create-contact),
[inboxes contactables](https://developers.chatwoot.com/api-reference/contacts/get-contactable-inboxes),
[crear conversación](https://developers.chatwoot.com/api-reference/conversations/create-new-conversation),
[mensajes](https://developers.chatwoot.com/api-reference/messages/create-new-message),
[BSUID](https://www.chatwoot.com/hc/user-guide/articles/1788437540-bsuid).
