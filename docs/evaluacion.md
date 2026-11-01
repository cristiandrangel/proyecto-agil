# Evidencia de evaluación

Registro actualizado el **1 de noviembre de 2026**. El código está implementado; las afirmaciones siguientes distinguen pruebas deterministas, ejecución del runtime y recorridos con proveedores reales. Un doble de OpenAI o Chatwoot no demuestra esa integración.

## Resultados comprobados

- **Suite Docker aislada: 245 pruebas aprobadas, cero fallos y cero omitidas, en 33,04 segundos**, el 2026-11-01 a las 16:20 UTC. Se ejecutó el comando Compose de esta guía, construyendo una imagen nueva y usando PostgreSQL 17 y red interna sin credenciales externas. El contenedor de pruebas terminó con código 0 y después se eliminaron sus contenedores y red.
- Verificación estática de esta revisión aprobada: `uv run ruff check .`, compilación de Python en aplicaciones/paquetes/scripts/migraciones y relay, `bash -n start.sh`, y validación Compose de runtime, pruebas, override EC2 y Floci. Estas comprobaciones no ejecutan un despliegue AWS.
- El [runner](../scripts/run_acceptance.py) ejecutó unitarias, contratos e integración, comprobó que todas las referencias AC de su informe se ejecutaran y produjo evidencia automatizada para AC-01–31. **No marca la aceptación completa como aprobada**: la evidencia manual y live sigue pendiente. Un test omitido, un fallo o una referencia ausente impiden un resultado global correcto.
- `python -m scripts.run_acceptance --live` devolvió bloqueo explícito con código de salida 2. No hay un runner de aceptación real implementado y no se simula su éxito.
- La suite final incluye las migraciones operativas **0001→0004**, caché/precio v2, 20 contratos del relay y regresiones de login, entrega, cuotas, catálogos globales y seed numérico con UUID/PIN estables. También cubre contactos con varios aliases, conversaciones sin binding y atribución de respuesta por la misma conversación sin modificar la llave de memoria ni los grants.
- Migración central verificada con PostgreSQL 17: upgrade, comparación sin diferencias frente a los modelos, downgrade y nuevo upgrade. El test está en `test_frozen_alembic_upgrade_downgrade_matches_models`.
- El lanzador `start.sh` tiene nueve pruebas de perfiles, URL y lectura segura de configuración. Se verificó que una cadena de comando dentro del token de `.env` no se ejecuta y que el perfil público precede a `up` solo cuando corresponde.
- Reset probado con dos esquemas reales y AsyncPostgresSaver: tras un fallo de central persiste mantenimiento; repetir la misma operación completa el reset una sola vez, elimina checkpoints de la llave literal y conserva el consumo registrado.
- Se observaron fallos antes de corregir tres riesgos: cursor que veía sequence 2 mientras sequence 1 seguía sin commit; revocación de identidad aún inexistente; y bloqueo PIN que no restauraba tres intentos entre distintos bindings. Las pruebas correspondientes pasaron después de los cambios.

La prueba inicial de Docker con red interna detectó además una descarga implícita de tiktoken en el primer uso, oculta por la caché de desarrollo. La imagen de pruebas ahora precarga `o200k_base` durante el build; la ejecución aislada posterior aprobó las 245 pruebas. Esa descarga es un recurso público del tokenizer y no una inferencia.

## Runtime y preflight de lectura

En desarrollo, `/health` y `/ready` locales respondieron 200; `/central`, 303 hacia `/login`; `/login`, 200, con `Cache-Control: no-store`. El preflight de lectura pasó completo en desarrollo y después en la instalación limpia: backend, central, tres modelos del catálogo, bandeja/relay y salud/autenticación SDK de Langfuse. Ambos se ejecutaron sin inferencia ni envíos; el fallo anterior de lectura de bandeja quedó resuelto.

Por HTTPS se comprobaron salud/readiness y protección del webhook. Una petición HMAC real firmada desde el host del propietario devolvió `200 ignored_event`; una clave incorrecta, 401, y una bandeja fuera del alcance, 403. Esto acredita transporte y autenticación, no una conversación WhatsApp.

En el origen público se activaron `APP_ENV=production` y la prohibición de entrada local de mensajes (403). Se comprobaron login HTTPS 303, cookie `Secure` y tabla 200 mediante HTTP. El bot de pruebas apunta al nuevo endpoint y tiene respaldo privado. El login en Chrome real se comprobó después de corregir la política de referencia de `/login`: central con 14 filas y acciones JavaScript operativas, manteniendo Origin y CSRF. En Chrome, el filtro `telefonia` + `CC` + `10000001` devolvió una deuda de USD 60 y después se restauró la vista de 14 filas. No se acredita aún el tramo WhatsApp con el usuario.

## Instalación limpia comprobada

El 2026-11-01 se ejecutó **`./start.sh` auténtico** en una copia temporal privada, sin `.env`, `.local`, `.git`, cachés ni dumps del desarrollador. Se copiaron solo los accesos externos necesarios y se generaron **17 secretos internos nuevos**, distintos de los del desarrollo. El proyecto `proyecto-agil-cleancheck` usó puertos 18080/13000 y, solo en esa copia, Minio/endpoint de medios 19090. No se activó túnel. Los once servicios arrancaron; no hubo limitación de capacidad.

La central contenía **13 clientes y 14 deudas**, con cero acuerdos, órdenes, intentos, liquidaciones y sesiones de identidad. La base operativa tenía cero campañas, conversaciones/eventos de entrada, trabajos, contextos, salidas, casos y reservas. Checkpoints, writes y blobs: **cero**; USD reservado y consumido: **cero**. El login real del operador y la tabla/API de 14 deudas respondieron correctamente. El preflight pasó con `inference_opt_in=false` y `channel_writes=0`; se revalidaron los ceros después.

Se detuvieron y retiraron únicamente los contenedores/red de `proyecto-agil-cleancheck`, conservando sus volúmenes y la evidencia privada. No se tocaron los servicios ni los volúmenes de desarrollo. Esta prueba acredita una instalación limpia **en el mismo equipo**, no portabilidad a otro PC ni una restauración entre equipos.

El ajuste posterior de nombres y documentos conserva los mismos UUID, contratos, saldos y PIN. Su seed actualizado se validó en PostgreSQL para los 13 clientes. Después se reconstruyeron los servicios y se ejecutó el reset coordinado de desarrollo: **epoch 2**, 14 deudas, todos los documentos de ocho dígitos, Ana Martínez López `10000001` y contactos iniciales simulados. El ledger se conservó. Los catálogos globales devolvieron `hogar`/`telefonia`/`television` y documento `CC`. No se repitió el arranque completo por este cambio de datos ficticios.

## Recorridos locales con inferencia real

Con Luna real se ejecutaron identificación, listado, selección y generación del enlace. La aprobación del pago simulado devolvió **HTTP 200: USD 100 recibidos y cero condonados**. También se propuso el 90% sobre telefonía de USD 60: oferta **USD 54**, aceptación en otro mensaje y enlace; la aprobación devolvió **HTTP 200, 5400 centavos recibidos, 600 condonados y saldo cero**.

La consulta posterior al acuerdo encontró la sesión vencida y pidió documento, conforme al TTL. **No se acredita aún una confirmación conversacional del acuerdo pagado.** Siguen pendientes el comprobante multimedia y WhatsApp de extremo a extremo desde el número del evaluador. Los pagos son simulados, sin movimiento de dinero real; no se publican enlaces firmados ni grants.

## Reproducción sin dependencias externas

```bash
docker compose -p proyecto-agil-tests -f infra/compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -p proyecto-agil-tests -f infra/compose.test.yaml down
```

El [Compose de pruebas](../infra/compose.test.yaml) tiene PostgreSQL 17 independiente, almacenamiento temporal, red interna y ningún puerto publicado. La [imagen de pruebas](../infra/Dockerfile.test) instala las dependencias de desarrollo fijadas en `uv.lock`; no recibe `.env` ni credenciales de proveedores. El proyecto explícito `proyecto-agil-tests` evita reutilizar el nombre del runtime privado.

El runner usa exclusivamente `-m 'not live'`. El estado de cada fila describe **evidencia automatizada parcial**, no un AC comercial aprobado de extremo a extremo. Los identificadores completos de pruebas son también parte del informe JSON que emite el runner.

## Matriz AC-01–31

Todas las referencias de esta tabla se ejecutaron correctamente en la suite Docker registrada. La columna final identifica lo que todavía no acredita esa ejecución.

| AC | Evidencia automatizada ejecutada | Evidencia manual o live pendiente |
|---|---|---|
| AC-01 | [`test_central_finance::test_frozen_alembic_upgrade_downgrade_matches_models`](../tests/integration/test_central_finance.py)<br>[`test_web_frontends::test_private_console_login_and_csrf_rotation`](../tests/contracts/test_web_frontends.py) | Arranque limpio, login y preflight aprobados en copia aislada del mismo equipo; falta repetir en el equipo del evaluador. |
| AC-02 | [`test_central_finance::test_customer_grants_isolate_debts_and_switch_revokes_prior`](../tests/integration/test_central_finance.py)<br>[`test_agent_context::test_debt_selection_required_and_select_clears_old_refs`](../tests/unit/test_agent_context.py) | Repetir en WhatsApp; identificación, listado y selección ya se ejecutaron con Luna real mediante entrada local. |
| AC-03 | [`test_central_finance::test_masked_identity_pin_lock_and_retry_deduplication`](../tests/integration/test_central_finance.py)<br>[`test_backend_identity::test_invalid_pin_media_and_temporary_failure_do_not_reach_agent`](../tests/integration/test_backend_identity.py) | Recorrido real de PIN incorrecto; ausencia de datos financieros y de PIN en trazas. |
| AC-04 | [`test_backend_identity::test_confirm_pin_is_neutral_and_grant_only_in_runtime`](../tests/integration/test_backend_identity.py)<br>[`test_text_journey::test_locate_preserves_only_fresh_masked_tool_after_identity_switch`](../tests/integration/test_text_journey.py) | Repetir en WhatsApp y probar candidato rechazado; origen opaco ficticio y documento ya se ejercitaron con inferencia real mediante entrada local. |
| AC-05 | [`test_central_finance::test_full_payment_rejected_then_applied_idempotently_and_reference_isolated`](../tests/integration/test_central_finance.py) | Pago local simulado aplicado con HTTP 200 y USD 100/0 confirmado; faltan entrega del enlace por WhatsApp, comprobante multimedia y cierre conversacional. |
| AC-06 | [`test_central_finance::test_discount_boundaries_and_accept_only_subsequent_message`](../tests/integration/test_central_finance.py) | 90% local sobre USD 60→54 aprobado y aplicado; faltan comprobante, confirmación posterior del pago y recorrido del canal real. |
| AC-07 | [`test_central_finance::test_discount_boundaries_and_accept_only_subsequent_message`](../tests/integration/test_central_finance.py)<br>[`test_money_policy::test_exact_discount_boundary_and_roundtrip`](../tests/unit/test_money_policy.py) | Oferta USD 80 y explicación/aceptación con el modelo y el canal reales. |
| AC-08 | [`test_central_finance::test_discount_boundaries_and_accept_only_subsequent_message`](../tests/integration/test_central_finance.py)<br>[`test_agent_context::test_handoff_blocks_further_financial_tools_in_same_turn`](../tests/unit/test_agent_context.py) | Oferta USD 79,99 y transferencia real a humano; quote y handoff están probados por separado. |
| AC-09 | [`test_central_finance::test_invalid_discount_amounts_do_not_create_orders`](../tests/integration/test_central_finance.py)<br>[`test_money_policy::test_rejects_ambiguous_or_invalid_money`](../tests/unit/test_money_policy.py) | Aclaración del modelo real ante importe ambiguo; la política determinista sí rechaza entradas inválidas. |
| AC-10 | [`test_central_finance::test_unpaid_order_expiry_blocks_capability_and_projects_expired_to_owner`](../tests/integration/test_central_finance.py)<br>[`test_central_finance::test_paid_receipt_survives_charge_expiry_but_no_new_attempt`](../tests/integration/test_central_finance.py) | Abandono, rechazo y reanudación desde la página y conversación reales. |
| AC-11 | [`test_media::test_download_pins_resolved_ip_preserves_tls_sni_and_sends_no_credentials`](../tests/integration/test_media.py)<br>[`test_central_finance::test_full_payment_rejected_then_applied_idempotently_and_reference_isolated`](../tests/integration/test_central_finance.py) | Captura real y llamada posterior a verify_payment; normalización y consulta se prueban por separado con dobles de inferencia. |
| AC-12 | [`test_central_finance::test_full_payment_rejected_then_applied_idempotently_and_reference_isolated`](../tests/integration/test_central_finance.py)<br>[`test_handoff::test_case_persists_before_ordered_effects_and_duplicate_is_idempotent`](../tests/integration/test_handoff.py) | Imagen aparente de éxito sin pago: decisión y derivación del modelo real. |
| AC-13 | [`test_central_finance::test_customer_grants_isolate_debts_and_switch_revokes_prior`](../tests/integration/test_central_finance.py)<br>[`test_central_finance::test_order_capability_can_be_regenerated_only_under_owner_grant`](../tests/integration/test_central_finance.py) | Captura o referencia ajena en conversación real; la API sí prueba el aislamiento. |
| AC-14 | [`test_central_finance::test_concurrent_orders_settle_exactly_once`](../tests/integration/test_central_finance.py)<br>[`test_queue::test_durable_duplicate_delivery_has_one_job_and_original_destination`](../tests/integration/test_queue.py) | Entrega duplicada real de canal/captura; deduplicación durable y liquidación única sí probadas en PostgreSQL. |
| AC-15 | [`test_media::test_real_audio_duration_enforced_before_transcription`](../tests/integration/test_media.py) | Audio real de 4,994 s transcrito correctamente; faltan nota de voz desde WhatsApp y texto acompañante en ese recorrido. |
| AC-16 | [`test_media::test_magic_rejects_unsafe_or_misleading_image_content`](../tests/integration/test_media.py)<br>[`test_media::test_real_audio_duration_enforced_before_transcription`](../tests/integration/test_media.py) | Visión real interpretó un comprobante; faltan imagen ilegible y medios del canal. MIME/magic y audio inválido sí se rechazan en pruebas. |
| AC-17 | [`test_handoff::test_case_persists_before_ordered_effects_and_duplicate_is_idempotent`](../tests/integration/test_handoff.py)<br>[`test_handoff::test_private_note_redacts_secrets_and_only_uses_trusted_identity`](../tests/integration/test_handoff.py) | Nota privada, cambio a open y respuesta humana en la bandeja real. |
| AC-18 | [`test_handoff::test_human_takeover_during_inference_cancels_queued_output`](../tests/integration/test_handoff.py)<br>[`test_handoff::test_return_requires_applied_transfer_open_observation_then_new_pending_event`](../tests/integration/test_handoff.py) | Toma humana durante inferencia y retorno explícito en Chatwoot; persiste la carrera externa consulta/envío. |
| AC-19 | [`test_text_journey::test_checkpoint_restart_literal_source_history_and_event_dedupe`](../tests/integration/test_text_journey.py)<br>[`test_central_finance::test_recoverable_two_database_reset_clears_real_checkpoints_preserves_spend`](../tests/integration/test_central_finance.py) | Reinicio de contenedores en conversación real; checkpoints y cambio de identidad sí probados con PostgreSQL y AsyncPostgresSaver. |
| AC-20 | [`test_campaigns::test_person_dedup_stable_snapshot_and_simulations_never_touch_channel`](../tests/integration/test_campaigns.py) | Campaña real con varios servicios; agrupación y simulaciones sí verificadas con dobles del canal. |
| AC-21 | [`test_campaigns::test_active_person_excluded_and_close_stops_pending_dispatch`](../tests/integration/test_campaigns.py)<br>[`test_campaigns::test_live_sequential_dispatch_launch_idempotency_and_immutable_outbox_destination`](../tests/integration/test_campaigns.py) | Exclusiones/lanzamiento repetido visibles en una campaña real y el canal configurado. |
| AC-22 | [`test_text_journey::test_five_tool_responses_stop_and_register_honest_handoff`](../tests/integration/test_text_journey.py)<br>[`test_backend_identity::test_invalid_pin_media_and_temporary_failure_do_not_reach_agent`](../tests/integration/test_backend_identity.py) | Fallo del proveedor/central durante un turno real y comunicación al usuario; fallos deterministas usan dobles. |
| AC-23 | [`test_agent_context::test_pre_pin_catalog_and_strict_tool_schema_never_accept_identity_or_grant`](../tests/unit/test_agent_context.py)<br>[`test_handoff::test_reason_amount_and_tenant_are_validated`](../tests/integration/test_handoff.py) | Inyección adversaria con el modelo real; los permisos y esquemas deterministas sí están limitados. |
| AC-24 | [`test_budget::test_concurrent_budget_cutoff_is_atomic`](../tests/integration/test_budget.py)<br>[`test_budget::test_timeout_preserves_amount_and_expired_lease_only_releases_slot`](../tests/integration/test_budget.py)<br>[`test_agent_context::test_payment_capability_never_crosses_model_checkpoint_boundary`](../tests/unit/test_agent_context.py) | Tres generaciones reales leídas por API sin entradas/salidas; faltan traza de WhatsApp, revisión completa y contraste del coste estimado con el proveedor. |
| AC-25 | [`test_central_finance::test_operator_contact_shared_version_mora_and_seed_never_overwrites`](../tests/integration/test_central_finance.py)<br>[`test_web_frontends::test_exact_mora_bucket_and_service_filters`](../tests/contracts/test_web_frontends.py) | Edición por navegador y entradas negativas/fraccionarias/vacías de extremo a extremo; persistencia y filtros sí probados. |
| AC-26 | [`test_campaigns::test_mora_buckets_boundaries_and_multiple_services`](../tests/integration/test_campaigns.py) | Lanzamiento real por límites; pruebas deterministas ya comprueban 29/30/59/60 y varios servicios. |
| AC-27 | [`test_metrics::test_metrics_real_cohort_dedup_money_agreement_and_human_milestones`](../tests/integration/test_metrics.py)<br>[`test_metrics::test_active_human_and_expired_agreement_are_current_results_not_milestones`](../tests/integration/test_metrics.py) | Contrastar panel con eventos del canal real; cohortes, dinero, acuerdos y humano sí probados en PostgreSQL. |
| AC-28 | [`test_central_finance::test_operator_contact_shared_version_mora_and_seed_never_overwrites`](../tests/integration/test_central_finance.py)<br>[`test_campaigns::test_changed_contact_is_skipped_and_unknown_delivery_is_not_resent`](../tests/integration/test_campaigns.py) | Llegada de campaña al nuevo teléfono y localización por ese mismo origen; contacto compartido/versionado sí probado. |
| AC-29 | [`test_money_policy::test_rejects_ambiguous_or_invalid_money`](../tests/unit/test_money_policy.py)<br>[`test_agent_context::test_pre_pin_catalog_and_strict_tool_schema_never_accept_identity_or_grant`](../tests/unit/test_agent_context.py) | Oferta conversacional en otra moneda y aclaración del modelo real; la API declara USD fijo. |
| AC-30 | [`test_central_finance::test_concurrent_orders_settle_exactly_once`](../tests/integration/test_central_finance.py)<br>[`test_central_finance::test_stale_balance_invalidates_order_and_quote`](../tests/integration/test_central_finance.py) | Demostración con navegador/cliente real; concurrencia y saldo modificado sí están probados con transacciones PostgreSQL. |
| AC-31 | [`test_campaigns::test_live_sequential_dispatch_launch_idempotency_and_immutable_outbox_destination`](../tests/integration/test_campaigns.py)<br>[`test_campaigns::test_person_dedup_stable_snapshot_and_simulations_never_touch_channel`](../tests/integration/test_campaigns.py) | Lote mixto real con una entrega al evaluador; secuencia y ausencia de llamadas para simulados sí probadas con dobles. |

## Integraciones reales y despliegue

| Comprobación | Estado y alcance |
|---|---|
| Catálogo OpenAI, 2026-10-31 | Registro previo: GET `/v1/models` devolvió 200 con la credencial privada y listó los modelos configurados. Sin inferencia. Acredita lectura autenticada, no calidad, uso ni facturación. |
| Inferencia de agente | Luna real ejecutó identificación/listado/selección/enlaces, pago total local USD 100/0 y acuerdo USD 60→54 con USD 6 condonados. La sesión vencida provocó petición de documento; no hay confirmación conversacional acreditada del acuerdo pagado. Pendientes del cierre multimedia/WhatsApp y contraste final de uso/coste. |
| Transcripción y visión | Visión `high` leyó referencia, importe, condonación y estado sin verificación financiera: 1403 tokens de entrada, 136 de salida, 1400 escrituras de caché de 30 minutos y USD 0,0005138 estimados con la tarifa corregida. `gpt-transcribe` transcribió correctamente un audio real de 4,994 segundos. Falta contrastarlos dentro del recorrido WhatsApp. |
| Chatwoot/WhatsApp | Preflight de lectura completo aprobado. Pendientes de campaña entregada, respuesta, comprobante, audio y transferencia humana de extremo a extremo desde el número del evaluador. |
| Relay del canal | Configuración activa confirmada: ambos clientes usan el mismo relay HTTPS y clave limitada; los tokens de usuario y AgentBot permanecen exclusivamente en ASUS. Backend/worker reconstruidos saludables y preflight posterior completo, sin escrituras ni inferencia. Conversación de prueba: 200 con id/bandeja/estado/`can_reply`, sin binding supuesto. Probes de alcance: bandeja autorizada 200, otra bandeja/cuenta 403 y sin clave 401. Conserva el actor bot y no expone historial. |
| Plantilla de prueba | Verificada mediante `sync_templates` real de Chatwoot: `recordatorio_factura_demo` / `es` / `APPROVED` / `UTILITY`. El `.env` privado ya usa esta plantilla principal. `hello_world` / `en_US` queda como respaldo. La sincronización y aprobación están confirmadas; la entrega de una campaña por WhatsApp sigue pendiente. |
| Langfuse | Tres generaciones reales de audio/visión leídas por API; UI autenticada con trazas de conversación, herramienta y modelo, tokens, coste estimado y errores. Captura conservada como evidencia privada, sin publicarla. No registra prompts ni respuestas completas. Las métricas de negocio están en la central. T049 comprobada; sigue pendiente la traza del recorrido WhatsApp completo. |
| HTTPS y webhook | Modo `production`, entrada local 403, login HTTPS 303/cookie `Secure` y tabla 200 por HTTP. HMAC real: `200 ignored_event`; clave incorrecta 401 y bandeja ajena 403. Chrome real: login, 14 filas y acciones JavaScript verificados. |
| Grabación y sustentación | Pendientes de realizar y revisar. |
| AWS | No desplegado. Runtime local en Compose y una emulación Floci no acreditan EC2, EBS, IAM, capacidad ni costes AWS reales. |

La configuración privada, contactos reales, tokens, URLs privadas, binarios recibidos y trazas sin revisar no se incorporan a este documento.

## Evidencia que debe conservarse al ejecutar el guion real

Para cada recorrido del [README](../README.md), registrar fecha, versión del código, modelo/esfuerzo, origen público utilizado, campaña y persona ficticia, resultado observable y fallos. La evidencia pública debe usar identificadores ficticios o redactados.

- Campaña: una persona por vez, simulados separados y una entrega real autorizada al evaluador. Una respuesta de preparación previa al envío no cuenta como contactabilidad.
- Finanzas: pago completo recibido/condonado, acuerdo 90/10 y umbral 80%; deuda del otro servicio intacta; rechazo, caducidad, duplicación y consulta del comprobante.
- Identidad: PIN fuera de inferencia y trazas, origen opaco literal, selección de servicio y nuevo PIN al cambiar de titular.
- Medios y humano: audio más texto, captura aplicada y falsa, petición de asesor, nota privada/open y retorno explícito a pending.
- Observabilidad: uso facturable por modalidad, reservas inciertas, trazas correlacionadas y redacción. El reset no borra el ledger ni el historial del proveedor.

## Límites conocidos

Las dos bases no comparten transacción distribuida. El reset mantiene etapas y estado de mantenimiento para reanudar un fallo; no afirma completarse mientras una etapa esté pendiente. El cursor de eventos centrales serializa publicación hasta commit para evitar perder eventos por orden de confirmación.

La consulta de control `pending` y el envío HTTP a Chatwoot son operaciones separadas; las protecciones locales no eliminan una carrera externa sin evidencia de la instalación. Un envío incierto no se repite a ciegas.

Las pruebas de medios validan URL, DNS, IP pública fijada, Host/SNI, redirecciones, cookies, tamaño, magic/MIME y duración. La interpretación de audio e imagen por los proveedores se comprobó por separado; la descarga TLS de medios del canal y su cierre financiero conversacional siguen pendientes. WebM se rechaza si falta `ffprobe` o no se valida duración/audio único. El corte local de USD 4,50 conserva margen frente a USD 5, pero no sustituye la facturación del proveedor ni borra consumos anteriores.

La tarifa local `openai-2026-11-01-cache-v2` separa entrada normal, lectura de caché y escritura de 30 minutos (esta última, 1,25× la entrada normal). Se aplicó un ajuste conservador idempotente de **USD 0,0017003** a los registros anteriores. El saldo local protegido previo al último smoke era **USD 0,0110414647**; el smoke posterior terminó `completed/settled` con 28 tokens de entrada, 5 de salida, caché cero y **USD 0,0000116 estimados** adicionales. Son estimaciones del ledger local, no factura del proveedor.
