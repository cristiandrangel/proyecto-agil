# Contrato del backend y las dos webs

**Estado:** rutas previstas para implementar. Un origen público HTTPS y rutas
separadas. Las vistas no exponen credenciales de OpenAI, Chatwoot ni API central.

## Operador

Login por credencial privada de demo y sesión HttpOnly; CSRF y validación de Origin
en mutaciones. HTTPS en público, cookies Secure; modo local explícito para HTTP.

| Método/ruta | Uso |
|---|---|
| GET /central | Tabla por deuda/servicio; contacto compartido, mora, filtros, campañas y métricas |
| GET, POST /login | Formulario y sesión de operador; no confundir con PIN del deudor |
| POST /logout | Cerrar sesión |
| GET /api/debts | Proyección autorizada desde central; filtros y paginación |
| PATCH /api/customers/{id} | Editar contacto/nombre; invalidar binding al cambiar contact_version |
| PATCH /api/debts/{id} | Cambiar fixture de deuda/mora según permisos y versión |
| POST /api/campaigns/preview | Filtros → personas únicas, deuda elegible, destino enmascarado y exclusiones |
| POST /api/campaigns | Guardar snapshot y configuración de plantilla aprobada |
| POST /api/campaigns/{id}/launch | Idempotency-Key; reservar destinatarios y encolar; no implica entrega |
| POST /api/campaigns/{id}/close | Fijar corte explícito; detener nuevos envíos pendientes y conservar eventos |
| GET /api/campaigns/{id} | Estado de destinatarios, send/failed/uncertain y mensajes asociados |
| GET /api/campaigns/{id}/metrics | Contadores, personas únicas, tasas, categorías e importes USD |
| POST /api/demo/reset | Solo modo demo y confirmación explícita; nunca borra consumo |

Mora: 0, 1–29, 30–59, 60–89, 90–119, 120+. Vista previa muestra qué deuda de cada
persona entra al segmento. Al enviar se revalida, sin expandir silenciosamente el
segmento a nuevas deudas. Un pago o baja posterior puede excluir al destinatario.

## Pago público simulado

| Método/ruta | Uso |
|---|---|
| GET /p/{order_id}?token={capability} | Página con servicio, monto USD, vigencia y aviso de simulación |
| POST /api/payments/{order_id}/attempts | Token y decision approved/rejected; Idempotency-Key estable por intento |
| GET /p/{order_id}/receipt?token={capability} | Resultado legible, referencia, importes y fecha; apto para captura |

El backend obtiene condiciones de central; no confía en importes editados en el
navegador. No mostrar documento completo ni contacto. La aprobación actualiza la
cartera sin enviar automáticamente un cierre al WhatsApp: el evaluador envía la
captura y el agente verifica. Enlace vencido no cobra; aprobación repetida no duplica.
El comprobante sigue accesible tras el pago con la misma capability validada y
alcance limitado a esa orden; vence el permiso de cobrar, no la consulta del recibo
aplicado durante 24 horas tras el pago.

## Canal, modo local y salud

- `POST /webhooks/chatwoot`: firma o relay verificado, cuenta/inbox permitidos y
  recepción durable; el detalle está en [Chatwoot](chatwoot.md).
- `POST /api/demo/messages`: autenticación de operador, solo modo local; inyecta
  texto/adjunto de prueba al mismo pipeline, con identidad ficticia y origen marcado.
  No está habilitado en el despliegue público.
- `GET /health`: proceso disponible sin exponer secretos.
- `GET /ready`: dependencias propias disponibles, sin inferencias pagadas ni envíos.
- Preflight por script: resultados de configuración y conectividad redactados;
  `--live` hace pruebas de inferencia y canal elegidas explícitamente.

Errores tienen code, message seguro, retryable y correlation_id. No se devuelve
traceback, PIN, grant, token de servicio o respuesta cruda del proveedor.

## Métricas

Cada respuesta incluye campaign_id, as_of, cohort, messages_sent, delivered_known,
failed, unique_sent, unique_replied, contactability_pct (null si unique_sent=0),
paid_full_without_discount, agreements_accepted/pending/fulfilled/expired,
human_requests, automatic_escalations, ongoing, no_result_closed, received_cents,
forgiven_cents y outstanding_cents. Cifras por deuda y personas únicas se etiquetan
por separado; las categorías de hitos no se suman como personas distintas.
