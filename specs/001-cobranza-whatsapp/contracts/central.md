# Contrato de la API central simulada

**Propósito:** frontera HTTP del ERP/CRM de demo; único escritor financiero.
Rutas internas en la red de contenedores, nunca expuestas directamente al navegador.
JSON; moneda USD fija; importes de respuesta en centavos enteros; UUID propios.
Prefijo `/internal/v1`. Health público interno `/health` y `/ready`.

## Autorización, consistencia y errores

`Authorization: Bearer <service-token>` identifica un servicio. Tokens distintos
para operador y agente. Consultas y comandos conversacionales exigen además
`X-Customer-Grant` válido: el cliente se deriva de ese grant, no de un argumento
que el LLM elija. Operador puede listar/editar fixtures; no existe un bypass de
operador accesible desde las herramientas del agente.

Comandos mutantes usan `Idempotency-Key`. Misma clave y cuerpo devuelven el resultado
original; cuerpo distinto devuelve 409. El recibo de una orden aplicada puede consultarse con firma válida durante 24 horas
tras el pago, aunque hayan vencido los 30 minutos para cobrar. Esa excepción no
permite crear otro intento ni consultar otra orden.

El PIN se usa transitoriamente y nunca se
guarda en command_result. Cambios financieros incluyen `expected_version`.
Los IDs de correlación y mensaje se añaden desde contexto del servidor.

Error común: `code`, `message` seguro, `retryable`, `correlation_id`.
400/422 datos inválidos, 401/403 identidad o permiso, 404 inexistente o ajeno sin
confirmar su existencia, 409 conflicto de versión/clave/estado, 410 orden o grant
vencido para la acción solicitada, 423 identidad temporalmente bloqueada y 503 dependencia no disponible.

## Identidad y cartera

| Método/ruta | Entrada | Respuesta y permisos |
|---|---|---|
| POST /identity/locate | phone_e164 o channel_identifier, inbox_id | Solo candidate_count y pista enmascarada; sin saldo, PIN ni datos completos; actor agente |
| POST /identity/verify | referencia de candidato o documento ficticio, pin, channel_key, source_message_id | customer_id, display_name, grant_token, expires_at; PIN no se devuelve ni entra al modelo; tres intentos y bloqueo |
| GET /debts | filtros de mora, servicio, tipo de cliente, documento y estado; paginación | Operador: filas customer+debt; agente: solo sus deudas por grant, sin pin_hash |
| GET /debts/{id} | grant para agente | Saldo vigente, mora, servicio, estado y version; 404 uniforme para deuda ajena |
| PATCH /customers/{id} | campos editables, expected_contact_version | Nombre/contacto compartidos; teléfono normalizado; contact_version aumenta y emite evento contact_changed |
| PATCH /debts/{id} | campos demo y expected_version | Mora entero >= 0, servicio y vencimiento; ajustes de saldo explícitos, sin atribuirlos a pago; invalida órdenes incompatibles |

Las respuestas de operador incluyen únicamente identificación ficticia y campos
necesarios. Editar teléfono no mueve conversaciones existentes de Chatwoot; el
backend debe resolver nuevamente el destino con la versión de contacto devuelta.

## Acuerdos, órdenes y pagos

| Método/ruta | Entrada | Resultado |
|---|---|---|
| POST /agreements/quote | debt_id, offer_amount_usd decimal string, expected_version; source_message_id desde servidor | Quote con base_cents, offer_cents, discount_cents, porcentaje y expiry; <80% devuelve requires_human sin crear acuerdo autorizado |
| POST /agreements/{id}/accept | expected_version; source_message_id de confirmación | Exige propuesta previa vigente y confirmación en mensaje posterior; marca aceptado y crea/reutiliza orden por importe acordado |
| POST /orders | debt_id, expected_version | Orden de pago completo por saldo actual; descuento solo mediante acuerdo aceptado |
| GET /orders/{id} | grant o capability de esa orden | Estado, importe y vencimiento; datos mínimos para la página |
| POST /orders/{id}/attempts | capability, decision approved/rejected | Server dicta importe; aprobación aplica pago y descuento en transacción; rechazo conserva saldo; respuesta solo tras commit |
| GET /payments/verify | grant más payment_reference opcional y debt_id | applied/absent/pending más importes, referencia y estado de deuda autorizados; referencia ajena no revela datos |
| GET /events?after={sequence}&limit={n} | actor de reconciliación del backend | Eventos ordenados con cursor, únicos y durables; no incluye secretos |

Una oferta es string decimal en USD, con hasta dos decimales. Se convierte con
Decimal a centavos; rechazo de exceso de precisión, cero, negativos, >saldo y
otra moneda. Comparación `offer_cents * 100 >= base_cents * 80`.
El token de pago es una firma opaca derivada de order_id aleatorio, nonce y expiry
con clave privada del sistema central. Permite regenerar el mismo enlace al
reintentar creación sin guardar el token completo en logs o en el resultado público.

Ejemplo de pago aplicado, enteramente ficticio:

```json
{
  "payment_reference": "DEMO-PAY-0001",
  "status": "applied",
  "currency": "USD",
  "received_cents": 9000,
  "forgiven_cents": 1000,
  "balance_cents": 0,
  "debt_status": "liquidada",
  "simulated": true
}
```

No se acepta importe del formulario de pago. Se bloquea deuda y orden; se comprueban
saldo y versión; settlement único registra pago, descuento y evento en el mismo
commit. Si otra orden ya liquidó, no hay segundo efecto. Un request de aplicación
incierto se consulta por referencia/idempotency key antes de repetir o cobrar.

## Administración de escenarios

`POST /demo/seed` y `POST /demo/reset` son internos, solo actor operador y modo demo.
Reset exige confirmación explícita y coordina epoch y limpieza operativa del backend;
no elimina presupuesto de inferencia ni historial externo. Fixtures: persona con
dos servicios, otra persona aislada, pagado, saldo cambiado y límites de mora.
