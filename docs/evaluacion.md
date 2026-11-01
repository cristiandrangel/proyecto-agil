# Evidencia de evaluación

Registro actualizado el **1 de noviembre de 2026**. El código está implementado; las afirmaciones siguientes distinguen pruebas deterministas, ejecución del runtime y recorridos con proveedores reales. Un doble de OpenAI o Chatwoot no demuestra esa integración.

## Resultados comprobados

- **Suite Docker aislada: 303 pruebas aprobadas, cero fallos y cero omitidas, en 35,70 segundos**, el 2026-11-01 a las 18:14:58 UTC. Se ejecutó el comando Compose de esta guía, construyendo una imagen nueva y usando PostgreSQL 17 y red interna sin credenciales externas. El contenedor de pruebas terminó con código 0 y después se eliminaron sus contenedores y red.
- Verificación estática de esta revisión aprobada: `uv run ruff check .`, compilación de Python en aplicaciones/paquetes/scripts/migraciones y relay, `bash -n start.sh`, y validación Compose de runtime, pruebas, override EC2 y Floci. Estas comprobaciones no ejecutan un despliegue AWS.
- El [runner](../scripts/run_acceptance.py) ejecutó unitarias, contratos e integración, comprobó que todas las referencias AC de su informe se ejecutaran y produjo evidencia automatizada para AC-01–31. **No marca la aceptación completa como aprobada**: la evidencia manual y live sigue pendiente. Un test omitido, un fallo o una referencia ausente impiden un resultado global correcto.
- `python -m scripts.run_acceptance --live` devolvió bloqueo explícito con código de salida 2. No hay un runner de aceptación real implementado y no se simula su éxito.
- La suite final incluye las migraciones operativas **0001→0004**, caché/precio v2, contratos del relay y regresiones de login, entrega, cuotas, catálogos globales y seed numérico con UUID/PIN estables. También cubre contactos con varios aliases, conversaciones sin binding y atribución de respuesta por la misma conversación sin modificar la llave de memoria ni los grants. Las regresiones más recientes cubren la plantilla fija, su BODY aprobado, pistas de identidad enmascaradas y la detección del primer turno desde el checkpoint.
- Migración central verificada con PostgreSQL 17: upgrade, comparación sin diferencias frente a los modelos, downgrade y nuevo upgrade. El test está en `test_frozen_alembic_upgrade_downgrade_matches_models`.
- El lanzador `start.sh` tiene nueve pruebas de perfiles, URL y lectura segura de configuración. Se verificó que una cadena de comando dentro del token de `.env` no se ejecuta y que el perfil público precede a `up` solo cuando corresponde.
- Reset probado con dos esquemas reales y AsyncPostgresSaver: tras un fallo de central persiste mantenimiento; repetir la misma operación completa el reset una sola vez, elimina checkpoints de la llave literal y conserva el consumo registrado.
- Se observaron fallos antes de corregir tres riesgos: cursor que veía sequence 2 mientras sequence 1 seguía sin commit; revocación de identidad aún inexistente; y bloqueo PIN que no restauraba tres intentos entre distintos bindings. Las pruebas correspondientes pasaron después de los cambios.

La prueba inicial de Docker con red interna detectó además una descarga implícita de tiktoken en el primer uso, oculta por la caché de desarrollo. La imagen de pruebas ahora precarga `o200k_base` durante el build; la ejecución aislada posterior aprobó las 245 pruebas. Esa descarga es un recurso público del tokenizer y no una inferencia.

## Runtime y preflight de lectura

En desarrollo, `/health` y `/ready` locales respondieron 200; `/central`, 303 hacia `/login`; `/login`, 200, con `Cache-Control: no-store`. El preflight de lectura pasó completo en desarrollo y después en la instalación limpia: backend, central, tres modelos del catálogo, bandeja/relay y salud/autenticación SDK de Langfuse. Ambos se ejecutaron sin inferencia ni envíos; el fallo anterior de lectura de bandeja quedó resuelto.

Por HTTPS se comprobaron salud/readiness y protección del webhook. Una petición HMAC real firmada desde el host del propietario devolvió `200 ignored_event`; una clave incorrecta, 401, y una bandeja fuera del alcance, 403. Esto acredita transporte y autenticación, no una conversación WhatsApp.

En el origen público se activaron `APP_ENV=production` y la prohibición de entrada local de mensajes (403). Se comprobaron login HTTPS 303, cookie `Secure` y tabla 200 mediante HTTP. El bot de pruebas apunta al nuevo endpoint y tiene respaldo privado. El login en Chrome real se comprobó después de corregir la política de referencia de `/login`: central con 14 filas y acciones JavaScript operativas, manteniendo Origin y CSRF. En Chrome, el filtro `telefonia` + `CC` + `10000001` devolvió una deuda de USD 60 y después se restauró la vista de 14 filas. No se acredita aún el tramo WhatsApp con el usuario.

Se creó un usuario web independiente con rol agente y membresía únicamente en la
bandeja de pruebas. Sus credenciales se guardaron exclusivamente en `.env` privado.
El login HTTP respondió 200; el listado de bandejas y conversaciones mostró solo
la bandeja asignada. Las consultas directas a conversaciones de otras bandejas
fueron rechazadas, manteniéndose válida la sesión para la conversación de prueba.
La consulta global de contactos que permite esta edición fue aceptada por el
propietario. No se enviaron mensajes durante esta verificación.

## Instalación limpia comprobada

El 2026-11-01 se ejecutó **`./start.sh` auténtico** en una copia temporal privada, sin `.env`, `.local`, `.git`, cachés ni dumps del desarrollador. Se copiaron solo los accesos externos necesarios y se generaron **17 secretos internos nuevos**, distintos de los del desarrollo. El proyecto `proyecto-agil-cleancheck` usó puertos 18080/13000 y, solo en esa copia, Minio/endpoint de medios 19090. No se activó túnel. Los once servicios arrancaron; no hubo limitación de capacidad.

La central contenía **13 clientes y 14 deudas**, con cero acuerdos, órdenes, intentos, liquidaciones y sesiones de identidad. La base operativa tenía cero campañas, conversaciones/eventos de entrada, trabajos, contextos, salidas, casos y reservas. Checkpoints, writes y blobs: **cero**; USD reservado y consumido: **cero**. El login real del operador y la tabla/API de 14 deudas respondieron correctamente. El preflight pasó con `inference_opt_in=false` y `channel_writes=0`; se revalidaron los ceros después.

Se detuvieron y retiraron únicamente los contenedores/red de `proyecto-agil-cleancheck`, conservando sus volúmenes y la evidencia privada. No se tocaron los servicios ni los volúmenes de desarrollo. Esta prueba acredita una instalación limpia **en el mismo equipo**, no portabilidad a otro PC ni una restauración entre equipos.

El ajuste posterior de nombres y documentos conserva los mismos UUID, contratos, saldos y PIN. Su seed actualizado se validó en PostgreSQL para los 13 clientes. Después se reconstruyeron los servicios y se ejecutó el reset coordinado de desarrollo: **epoch 2**, 14 deudas, todos los documentos de ocho dígitos, Ana Martínez López `10000001` y contactos iniciales simulados. El ledger se conservó. Los catálogos globales devolvieron `hogar`/`telefonia`/`television` y documento `CC`. No se repitió el arranque completo por este cambio de datos ficticios.

## Recorridos locales con inferencia real

Con Luna real se ejecutaron identificación, listado, selección y generación del enlace. La aprobación del pago simulado devolvió **HTTP 200: USD 100 recibidos y cero condonados**. También se propuso el 90% sobre telefonía de USD 60: oferta **USD 54**, aceptación en otro mensaje y enlace; la aprobación devolvió **HTTP 200, 5400 centavos recibidos, 600 condonados y saldo cero**.

La consulta posterior al acuerdo encontró la sesión vencida y pidió documento, conforme al TTL. **No se acredita aún una confirmación conversacional del acuerdo pagado.** Siguen pendientes el comprobante multimedia y WhatsApp de extremo a extremo desde el número del evaluador. Los pagos son simulados, sin movimiento de dinero real; no se publican enlaces firmados ni grants.

## Apertura y guardrails del prompt

Se evaluó el prompt actualizado con cuatro llamadas reales a Luna, razonamiento
alto y salida máxima de 1200 tokens, usando presupuesto y observabilidad del
runtime. La apertura generó presentación de Alex, contexto de cobranza y motivo
de autenticación, conservó literalmente la pista ficticia y no reveló saldo.
El formato de máscara de la central se verificó aparte con pruebas deterministas.

Tres intentos de inyección introducidos como mensaje de usuario, texto de medio
no verificado y cadena de resultado de herramienta no revelaron instrucciones ni
el secreto sintético de control, ni confirmaron un pago inexistente. La revisión
semántica detectó una limitación: la muestra de medios propuso atención humana
antes de completar autenticación. Dos muestras terminaron en una propuesta de
herramienta, sin respuesta final al usuario. Se usaron historiales y herramientas
de prueba; ninguna operación financiera ni de Chatwoot se ejecutó.

El coste registrado fue **USD 0,00235343**, con las cuatro reservas liquidadas.
Son muestras aisladas, no una garantía exhaustiva contra inyecciones ni una prueba
integral de recepción de medios en WhatsApp. El backend mantiene las validaciones
de identidad, permisos y pagos independientemente de las instrucciones del modelo.

## Trazas por turno y continuidad del envío

La revisión confirmó que backend y worker autentican contra el mismo proyecto de
Langfuse. Antes del cambio había 18 trazas y 46 observaciones; las cuatro llamadas
de evaluación de prompt estaban recibidas, pero la UI conservaba una consulta
anterior con actualización automática apagada. Se refrescó la vista y se activó
el intervalo de 30 segundos. Se abrió el turno real de WhatsApp de las 12:17
(Bogotá): mostraba dos generaciones y una herramienta.

Se amplió la raíz `conversation` para cubrir el procesamiento protegido, puerta
de identidad, medios, `agent` y encolado. Las herramientas tienen nombres
`tool.<nombre>` y tipo tool; el modelo conserva tipo generation. La sesión opaca
se propaga a los hijos sin cambiar la llave literal de LangGraph. El contexto de
traza se guarda con la salida en outbox y `delivery` lo recupera después, sin
alterar la idempotencia de negocio. Los registros anteriores sin ese contexto
pueden mostrar una raíz de envío separada.

Trece regresiones nuevas verifican con el SDK real y exportador en memoria la
jerarquía, sesiones, privacidad, contextos inválidos y envío diferido. Tres de ellas
usan PostgreSQL real y comprueban el turno sin LLM, el primer padre persistido en
reintentos y la restauración aun bajo otra traza activa. Todas forman parte de la
suite Docker registrada arriba; las pruebas de inferencia usan dobles del proveedor.

Después del despliegue, una comprobación de observabilidad enviada al Langfuse
real recibió **tres observaciones con la misma sesión y padre restaurado tras
cerrar la raíz**. Fue una traza `preflight`, con cero inferencias y cero envíos al
canal; no se presenta como conversación del cliente. Readiness público respondió
200. Falta repetir el árbol ampliado completo desde WhatsApp, incluyendo medios y
el recorrido financiero; las trazas antiguas no se reconstruyen retroactivamente.

## Cambio autorizado: contenido completo en Langfuse privado

El 1 de noviembre de 2026, el usuario pidió inspeccionar el contenido completo de
cada ejecución para depuración privada. Esta instrucción **reemplaza la política
anterior de trazas sin prompts, mensajes ni datos personales/financieros**. La
jerarquía por mensaje y sus identificadores no cambian: sesión Langfuse opaca,
`thread_id` literal en LangGraph y `delivery` unido mediante contexto durable.

El contrato nuevo activa `LANGFUSE_CAPTURE_CONTENT=true`: mensajes protegidos,
prompt/contexto e historial utilizados, inputs/outputs del modelo, argumentos y
resultados de herramientas, estado anterior/posterior, respuesta preparada/enviada
y contexto multimedia utilizado: transcripción, extracción visual y archivos
completos de audio e imagen como assets `LangfuseMedia`, almacenados en privado.
Los datos personales y financieros se muestran sin enmascarar en el proyecto
privado. `LANGFUSE_CAPTURE_CONTENT=false` vuelve a metadatos. Las trazas históricas
siguen como fueron exportadas, sin backfill; nuevos turnos sí pueden contener el
historial que utilizan. Apagar la opción no borra contenido ya exportado.

Se filtran secretos conocidos de infraestructura en JSON/texto, API keys,
`Authorization`, grants, capabilities y tokens de enlaces. El PIN **tecleado** se
intercepta en el ingreso antes de cola/modelo; solo se ve el paso resuelto. Los
archivos autorizados se capturan completos, **sin OCR ni redacción automática
previa de información escrita o hablada**: no se garantiza ocultar PIN o secretos
que formen parte de una imagen o audio. No se captura razonamiento interno ni
`encrypted_content`; los errores pasan por el saneamiento de texto/estructuras.
La información de este proyecto privado no se copia a fuentes, capturas o
evidencias públicas.

Los límites de captura son 1 000 000 de caracteres por cadena, profundidad 40 y
20 000 elementos, con marcadores explícitos de truncamiento. No se declara completo
un objeto marcado ni se confunden estos límites con la carga de assets multimedia.

Recorrido de revisión: abrir una raíz **conversation → agent → llm → Input / Output**;
contrastar contexto/historial y output disponible; abrir **tool.<nombre> → Input /
Output** para argumentos/resultados, y los pasos de medios para su contexto. La
respuesta se contrasta en `response_enqueue → delivery`, conservando el significado
de `sent` como aceptación de la API, sin inferir entrega de WhatsApp.

**Pruebas deterministas aprobadas:** la suite Docker final registrada arriba
incluye **303 pruebas**, el 2026-11-01 a las **18:14:58 UTC**, sin fallos ni
omitidas, en 35,70 segundos; limpieza completada y Ruff aprobado. La nueva
cobertura verifica dos turnos del worker con checkpoint e inputs/outputs, captura
completa del SDK y errores saneados, assets y formatos multimedia, continuidad si
falla la telemetría y transporte S3 firmado. No usó WhatsApp ni proveedores de
inferencia reales. Esa cobertura amplía las pruebas anteriores de jerarquía,
sesión y parentesco durable.

**Comprobación real desplegada:** el 2026-11-01 a las 18:16 UTC se ejecutó una
llamada a Luna mediante el cliente de inferencia y ledger compartido. La API y la
interfaz de Langfuse mostraron el prompt, el mensaje con documento ficticio y la
respuesta completa. El control de secretos del contenido pasó; la reserva quedó
liquidada por **USD 0,00059875 estimados**. Se almacenaron una imagen PNG de 91 bytes
y un audio WAV de 3244 bytes; la UI cargó la imagen de 24×24 y el audio de 0,2 s sin
errores. El transporte preservó la firma S3 al subir desde Docker. Fueron tres
observaciones de diagnóstico, una inferencia real y **cero envíos a WhatsApp**.
No se presenta como conversación ni recorrido financiero del evaluador. Sigue
pendiente el árbol completo con medios del canal y herramientas financieras.
Las lecturas históricas en modo metadatos no se rellenan retroactivamente.

Las cláusulas de redacción general de `agent-state.md` y
`contracts/agent-tools.md` se reconciliaron con esta instrucción. El registro de
`tasks.md` conserva su evidencia histórica. Se mantiene el filtrado de secretos
en texto/JSON y la interceptación del PIN tecleado, con la limitación de archivos sin
redacción visual/voz. Las pruebas históricas conservan su alcance.

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
| AC-03 | [`test_central_finance::test_masked_identity_pin_lock_and_retry_deduplication`](../tests/integration/test_central_finance.py)<br>[`test_backend_identity::test_invalid_pin_media_and_temporary_failure_do_not_reach_agent`](../tests/integration/test_backend_identity.py) | Recorrido real de PIN tecleado incorrecto y ausencia de ese PIN en trazas; los archivos multimedia completos no tienen redacción visual/voz automática. |
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
| AC-23 | [`test_agent_context::test_pre_pin_catalog_and_strict_tool_schema_never_accept_identity_or_grant`](../tests/unit/test_agent_context.py)<br>[`test_handoff::test_reason_amount_and_tenant_are_validated`](../tests/integration/test_handoff.py) | Tres muestras de inyección con Luna real sin divulgación ni confirmación falsa de pago; falta ampliar ataques y ejecutarlos por el grafo y WhatsApp. Los permisos y esquemas deterministas sí están limitados. |
| AC-24 | [`test_budget::test_concurrent_budget_cutoff_is_atomic`](../tests/integration/test_budget.py)<br>[`test_budget::test_timeout_preserves_amount_and_expired_lease_only_releases_slot`](../tests/integration/test_budget.py)<br>[`test_agent_context::test_payment_capability_never_crosses_model_checkpoint_boundary`](../tests/unit/test_agent_context.py) | Captura completa y filtrado de secretos comprobados de forma determinista; falta leer la nueva exportación real, traza de WhatsApp y contraste del coste con el proveedor. |
| AC-25 | [`test_central_finance::test_operator_contact_shared_version_mora_and_seed_never_overwrites`](../tests/integration/test_central_finance.py)<br>[`test_web_frontends::test_exact_mora_bucket_and_service_filters`](../tests/contracts/test_web_frontends.py) | Edición por navegador y entradas negativas/fraccionarias/vacías de extremo a extremo; persistencia y filtros sí probados. |
| AC-26 | [`test_campaigns::test_mora_buckets_boundaries_and_multiple_services`](../tests/integration/test_campaigns.py) | Lanzamiento real por límites; pruebas deterministas ya comprueban 29/30/59/60 y varios servicios. |
| AC-27 | [`test_metrics::test_metrics_real_cohort_dedup_money_agreement_and_human_milestones`](../tests/integration/test_metrics.py)<br>[`test_metrics::test_active_human_and_expired_agreement_are_current_results_not_milestones`](../tests/integration/test_metrics.py) | Contrastar panel con eventos del canal real; cohortes, dinero, acuerdos y humano sí probados en PostgreSQL. |
| AC-28 | [`test_central_finance::test_operator_contact_shared_version_mora_and_seed_never_overwrites`](../tests/integration/test_central_finance.py)<br>[`test_campaigns::test_changed_contact_is_skipped_and_unknown_delivery_is_not_resent`](../tests/integration/test_campaigns.py) | Llegada de campaña al nuevo teléfono y localización por ese mismo origen; contacto compartido/versionado sí probado. |
| AC-29 | [`test_money_policy::test_rejects_ambiguous_or_invalid_money`](../tests/unit/test_money_policy.py)<br>[`test_agent_context::test_pre_pin_catalog_and_strict_tool_schema_never_accept_identity_or_grant`](../tests/unit/test_agent_context.py) | Oferta conversacional en otra moneda y aclaración del modelo real; la API declara USD fijo. |
| AC-30 | [`test_central_finance::test_concurrent_orders_settle_exactly_once`](../tests/integration/test_central_finance.py)<br>[`test_central_finance::test_stale_balance_invalidates_order_and_quote`](../tests/integration/test_central_finance.py) | Demostración con navegador/cliente real; concurrencia y saldo modificado sí están probados con transacciones PostgreSQL. |
| AC-31 | [`test_campaigns::test_live_sequential_dispatch_launch_idempotency_and_immutable_outbox_destination`](../tests/integration/test_campaigns.py)<br>[`test_campaigns::test_person_dedup_stable_snapshot_and_simulations_never_touch_channel`](../tests/integration/test_campaigns.py) | Lote mixto real con una entrega al evaluador; secuencia y ausencia de llamadas para simulados sí probadas con dobles. |

## Incidencia durante la campaña guiada

El primer intento real creó una conversación pendiente en la bandeja de pruebas,
pero no creó mensajes. El adaptador eligió el nombre visible de la campaña como
nombre de plantilla, en lugar del campo `template_name`; el relay rechazó esa
plantilla antes de llamar al envío de Chatwoot. Se contrastaron la ausencia de
mensajes y cero intentos upstream del relay. El intento local se concilió como
fallido sin reenviarlo ni alterar la cartera.

El adaptador ahora prioriza `template_name` y `template_language`. Los rechazos
definitivos se registran como fallidos; los resultados realmente inciertos
conservan su protección frente al reenvío. La UI muestra resultados sin confirmación
y omitidos por separado, y distingue procesamiento finalizado de entrega.
Las cuatro regresiones nuevas aprobaron dentro de la suite de 249 pruebas.
El usuario confirmó la recepción de la plantilla en el reintento. En la bandeja
de pruebas se verificó el mensaje saliente en estado `delivered`, con referencia
del proveedor y conversación `pending` asignada al bot de pruebas. La respuesta
del evaluador y el resto de la conversación siguen pendientes.

Durante la revisión de Chatwoot se detectó que el mensaje saliente mostraba un
texto genérico aunque WhatsApp recibía la plantilla correcta. El relay se ajustó
para obtener el cuerpo de la plantilla aprobada y enviarlo como contenido visible
a Chatwoot. Se conserva el registro anterior; no se modifica ni se reenvía.
Los 48 contratos del relay y del adaptador de Chatwoot aprobaron; el relay
actualizado está saludable y su lectura de la conversación de pruebas pasó sin
enviar mensajes. El contraste visual de ambos canales se hará en un próximo envío real.

## Integraciones reales y despliegue

| Comprobación | Estado y alcance |
|---|---|
| Catálogo OpenAI, 2026-10-31 | Registro previo: GET `/v1/models` devolvió 200 con la credencial privada y listó los modelos configurados. Sin inferencia. Acredita lectura autenticada, no calidad, uso ni facturación. |
| Inferencia de agente | Luna real ejecutó identificación/listado/selección/enlaces, pago total local USD 100/0 y acuerdo USD 60→54 con USD 6 condonados. La sesión vencida provocó petición de documento; no hay confirmación conversacional acreditada del acuerdo pagado. Pendientes del cierre multimedia/WhatsApp y contraste final de uso/coste. |
| Transcripción y visión | Visión `high` leyó referencia, importe, condonación y estado sin verificación financiera: 1403 tokens de entrada, 136 de salida, 1400 escrituras de caché de 30 minutos y USD 0,0005138 estimados con la tarifa corregida. `gpt-transcribe` transcribió correctamente un audio real de 4,994 segundos. Falta contrastarlos dentro del recorrido WhatsApp. |
| Chatwoot/WhatsApp | Plantilla del reintento recibida por el usuario; mensaje saliente `delivered` verificado en la bandeja de pruebas con conversación `pending`. Pendientes de respuesta, comprobante, audio y transferencia humana de extremo a extremo. |
| Relay del canal | Configuración activa confirmada: ambos clientes usan el mismo relay HTTPS y clave limitada; los tokens de usuario y AgentBot permanecen exclusivamente en ASUS. Backend/worker reconstruidos saludables y preflight posterior completo, sin escrituras ni inferencia. Conversación de prueba: 200 con id/bandeja/estado/`can_reply`, sin binding supuesto. Probes de alcance: bandeja autorizada 200, otra bandeja/cuenta 403 y sin clave 401. Conserva el actor bot y no expone historial. |
| Plantilla de prueba | Verificada mediante `sync_templates` real de Chatwoot: `recordatorio_factura_demo` / `es` / `APPROVED` / `UTILITY`. El `.env` privado ya usa esta plantilla principal. `hello_world` / `en_US` queda como respaldo. Sincronización y aprobación confirmadas; la plantilla del reintento llegó al usuario y figura delivered en Chatwoot. El recorrido conversacional restante sigue pendiente. |
| Langfuse | Tres generaciones reales de audio/visión leídas por API; UI autenticada con trazas de conversación, herramienta y modelo, tokens, coste estimado y errores. Captura conservada como evidencia privada, sin publicarla. La evidencia histórica fue de metadatos, sin prompts ni respuestas completas. El usuario autorizó después captura privada completa y assets de audio/imagen; 303 pruebas incluyen su validación determinista. La captura desplegada se leyó por API y UI con una llamada real y dos archivos ficticios cargados. Las métricas de negocio están en la central. Sigue pendiente el recorrido WhatsApp completo. |
| HTTPS y webhook | Modo `production`, entrada local 403, login HTTPS 303/cookie `Secure` y tabla 200 por HTTP. HMAC real: `200 ignored_event`; clave incorrecta 401 y bandeja ajena 403. Chrome real: login, 14 filas y acciones JavaScript verificados. |
| Grabación y sustentación | Pendientes de realizar y revisar. |
| AWS | No desplegado. Runtime local en Compose y una emulación Floci no acreditan EC2, EBS, IAM, capacidad ni costes AWS reales. |

La configuración privada, contactos reales, tokens, URLs privadas, binarios recibidos y trazas sin revisar no se incorporan a este documento.

## Evidencia que debe conservarse al ejecutar el guion real

Para cada recorrido del [README](../README.md), registrar fecha, versión del código, modelo/esfuerzo, origen público utilizado, campaña y persona ficticia, resultado observable y fallos. La evidencia pública debe usar identificadores ficticios o redactados.

- Campaña: una persona por vez, simulados separados y una entrega real autorizada al evaluador. Una respuesta de preparación previa al envío no cuenta como contactabilidad.
- Finanzas: pago completo recibido/condonado, acuerdo 90/10 y umbral 80%; deuda del otro servicio intacta; rechazo, caducidad, duplicación y consulta del comprobante.
- Identidad: PIN tecleado interceptado fuera de inferencia/trazas, origen opaco literal, selección de servicio y nuevo PIN al cambiar de titular. No atribuir redacción visual/voz automática a los archivos completos.
- Medios y humano: audio más texto, captura aplicada y falsa, petición de asesor, nota privada/open y retorno explícito a pending.
- Observabilidad: uso por modalidad, reservas inciertas, trazas correlacionadas y nueva captura privada completa con exclusión de secretos/PIN/capabilities. No publicar contenido personal o financiero de las trazas. El reset no borra el ledger ni el historial del proveedor.

## Límites conocidos

Las dos bases no comparten transacción distribuida. El reset mantiene etapas y estado de mantenimiento para reanudar un fallo; no afirma completarse mientras una etapa esté pendiente. El cursor de eventos centrales serializa publicación hasta commit para evitar perder eventos por orden de confirmación.

La consulta de control `pending` y el envío HTTP a Chatwoot son operaciones separadas; las protecciones locales no eliminan una carrera externa sin evidencia de la instalación. Un envío incierto no se repite a ciegas.

Las pruebas de medios validan URL, DNS, IP pública fijada, Host/SNI, redirecciones, cookies, tamaño, magic/MIME y duración. La interpretación de audio e imagen por los proveedores se comprobó por separado; la descarga TLS de medios del canal y su cierre financiero conversacional siguen pendientes. WebM se rechaza si falta `ffprobe` o no se valida duración/audio único. El corte local de USD 4,50 conserva margen frente a USD 5, pero no sustituye la facturación del proveedor ni borra consumos anteriores.

La tarifa local `openai-2026-11-01-cache-v2` separa entrada normal, lectura de caché y escritura de 30 minutos (esta última, 1,25× la entrada normal). Se aplicó un ajuste conservador idempotente de **USD 0,0017003** a los registros anteriores. El saldo local protegido previo al último smoke era **USD 0,0110414647**; el smoke posterior terminó `completed/settled` con 28 tokens de entrada, 5 de salida, caché cero y **USD 0,0000116 estimados** adicionales. Son estimaciones del ledger local, no factura del proveedor.
