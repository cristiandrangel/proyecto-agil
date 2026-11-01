# Proyecto Ágil

Demo de cobranza por WhatsApp con una central editable, un agente con herramientas y una página de pago simulado. Todos los importes son USD; no se mueve dinero real.

El código y las pruebas automatizadas están implementados. Se ejecutó con inferencia real de Luna el recorrido local de identificación, listado de deudas, selección y generación de enlace; después se aplicó un pago simulado de USD 100 sin condonación con respuesta HTTP 200. También se ejecutó un acuerdo local: saldo USD 60, oferta USD 54 aceptada en otro mensaje y pago aplicado con USD 6 condonados. Audio y visión se ejecutaron con proveedores reales y se leyeron registros de Langfuse. Siguen pendientes el envío del comprobante por WhatsApp, su verificación financiera conversacional, el recorrido de extremo a extremo con el usuario, la grabación y la sustentación. No se ha desplegado en AWS. El detalle por AC-01–31 está en [evaluación](docs/evaluacion.md).

## Arrancar con Docker

Se necesita Docker con Compose v2, una terminal Bash y conexión a Internet. No hace falta instalar Python, uv, PostgreSQL ni Node en el equipo. Langfuse incluye varios servicios; el primer arranque descarga imágenes y aplica migraciones.

1. Abre la carpeta del proyecto en una terminal.
2. Coloca el archivo privado de configuración entregado como `.env`, junto a este README. Para preparar otro entorno, copia `.env.example` y completa los accesos externos `OPENAI_*`, `CHATWOOT_*`, plantilla y hosts de medios. No publiques ese archivo.
3. Si el archivo habilita el túnel público, detén primero el conector del equipo anterior: solo puede haber un equipo activo. Ejecuta:

```bash
./start.sh
```

El script completa únicamente los secretos internos ausentes y conserva los valores existentes. Después construye y arranca los contenedores. Si el `.env` entregado configura un origen HTTPS y contiene el token del túnel, activa también `cloudflared` automáticamente; ese conector es necesario para usar el origen público de esa configuración. Al terminar imprime la URL exacta de la central. Las migraciones y los checkpoints se preparan automáticamente. La central carga fixtures **solo si su base está vacía**: reiniciar no reemplaza teléfonos, pagos ni acuerdos.

Abre `/central` en el origen configurado en `PUBLIC_BASE_URL`. En modo local (`APP_ENV=local`, `PUBLIC_BASE_URL=http://localhost:8080`), es [localhost:8080/central](http://localhost:8080/central). Si el archivo entregado usa HTTPS, comprueba que el conector esté activo y abre ese origen público: el login y las cookies deben usar el mismo origen configurado. El usuario y la contraseña están en `OPERATOR_USERNAME` y `OPERATOR_PASSWORD` de `.env`; el usuario de ejemplo es `evaluador`. Langfuse está en [localhost:3000](http://localhost:3000), con las credenciales privadas `LANGFUSE_INIT_USER_EMAIL` y `LANGFUSE_INIT_USER_PASSWORD`.

En la configuración HTTPS se activó `APP_ENV=production` y se deshabilitó la entrada local de mensajes (403). Se verificaron el login HTTPS (303), la cookie `Secure` y la tabla (200). El login en Chrome real también pasó: central con 14 filas y acciones JavaScript operativas.

La configuración activa y la del evaluador usan el relay acotado: `CHATWOOT_BASE_URL` y `CHATWOOT_CONTACTS_BASE_URL` apuntan al mismo relay; `CHATWOOT_API_TOKEN` y `CHATWOOT_CONTACTS_API_TOKEN` usan su misma clave limitada. Los tokens de usuario y AgentBot de Chatwoot permanecen exclusivamente en el host ASUS del propietario. Backend y worker están saludables y el preflight actual pasó sin inferencia ni escrituras de canal. El relay restringe cuenta, bandeja y operaciones, conserva al bot como actor y no ofrece lectura del historial de mensajes.

Se comprobó un arranque limpio mediante `./start.sh` en una copia privada aislada del mismo equipo: 13 clientes, 14 deudas y cero pagos, acuerdos, conversaciones, checkpoints y consumo. El login y el preflight de lectura pasaron. Esto no acredita todavía la ejecución en otro PC.

La instalación del evaluador usa por defecto el proyecto Compose `proyecto-agil` y volúmenes nuevos. El entorno de desarrollo puede usar `COMPOSE_PROJECT_NAME=agil-desarrollo` en su `.env` ignorado. Para una evaluación limpia, omite esa variable o define `COMPOSE_PROJECT_NAME=proyecto-agil`. No copies volúmenes, dumps, conversaciones ni contactos del entorno del desarrollador: la cartera inicial se crea desde los fixtures públicos.

Para revisar estado y diagnósticos sin mostrar la configuración privada:

```bash
docker compose --env-file .env -f infra/compose.yaml ps
docker compose --env-file .env -f infra/compose.yaml logs --tail=80 backend worker central
```

El preflight consulta disponibilidad, acceso a modelos y bandeja, y autenticación de Langfuse; no genera inferencia ni envía mensajes:

```bash
docker compose --env-file .env -f infra/compose.yaml exec backend python -m scripts.preflight --base-url http://localhost:8000
```

Un preflight correcto acredita esas consultas de lectura. La integración de mensajes y los recorridos comerciales se comprueban por separado.

## Datos y PIN de la demo

**PIN ficticio de todos los clientes: `2468`.** Se almacena como hash y se verifica fuera del modelo. La sesión dura 30 minutos; tres errores bloquean la identidad durante 15 minutos.

| Persona ficticia | Documento | Servicios y saldo inicial |
|---|---|---|
| Ana Martínez López | CC `10000001` | `hogar`: USD 100, 45 días; `telefonia`: USD 60, 75 días |
| Bruno Torres Gómez | CC `10000002` | `hogar`: USD 200, 35 días; sirve para probar aislamiento |
| Carla Rojas Díaz | CC `10000003` | `hogar`: saldo cero |
| Diego Castro Ruiz | CC `10000004` | `hogar`: USD 85, versión 2 |

Todos los nombres y documentos son ficticios. Los documentos tienen ocho dígitos. Las personas de los límites de mora 0, 29, 30, 59, 60, 89, 90, 119 y 120 usan el documento `20000000 + días` (por ejemplo, `20000120`). La pantalla muestra una fila por deuda; nombre y contacto pertenecen a la persona y se comparten entre sus servicios.

## Preparar el WhatsApp del evaluador

1. En la central, filtra por `10000001` y edita el contacto de Ana. Sustituye su teléfono por tu WhatsApp con código de país. Elige `live` y habilita el contacto de prueba. Comprueba que ambas filas comparten el teléfono y la nueva versión de contacto. Deja los demás clientes en `simulated`.
2. En el entorno privado, verifica que `CHATWOOT_ACCOUNT_ID` y `CHATWOOT_INBOX_ID` correspondan a la bandeja de pruebas y que su bot apunte a esta aplicación. No cambies una bandeja de producción. El número del evaluador debe estar habilitado para la prueba en Meta cuando corresponda.
3. La plantilla principal verificada mediante `sync_templates` de Chatwoot es **`recordatorio_factura_demo`**, idioma **`es`**, estado **`APPROVED`** y categoría **`UTILITY`**. El `.env` privado entregado ya la configura. Usa esos mismos valores en `CHATWOOT_TEMPLATE_NAME`, `CHATWOOT_TEMPLATE_LANGUAGE`, `CHATWOOT_TEMPLATE_CATEGORY` y en el formulario de campaña. `hello_world` / `en_US` queda como respaldo; no es la opción principal.
4. Si hace falta crear el contacto o abrir la conversación de prueba, envía primero un mensaje de preparación al número de prueba. Mantén la conversación en `pending` para el bot. La respuesta de preparación anterior al envío de campaña queda fuera de su contactabilidad.
5. Comprueba la entrada HTTPS antes de esperar mensajes externos.

El origen previsto es **`https://cobranza.agenx-dev-test.work`**. La configuración y verificación del túnel se documentan en [dominio de demo](docs/dominio-demo.md). Se verificaron HTTPS, salud/readiness y rechazo de un webhook sin autenticación en el entorno de desarrollo. Esto no demuestra la entrega de WhatsApp; el evaluador aún debe ejecutar el recorrido desde su contacto.

Con el `.env` privado entregado configurado para HTTPS, `./start.sh` activa el conector automáticamente. Para activarlo manualmente después de preparar el túnel y configurar `PUBLIC_BASE_URL`:

```bash
docker compose --env-file .env -f infra/compose.yaml --profile public up -d cloudflared
```

Solo puede haber **un equipo activo** conectado al mismo túnel. Antes de cambiar de PC o pasar a EC2, detén el conector anterior. El hostname no transporta las bases: una instalación nueva comienza con fixtures, salvo que se planifique una restauración explícita.

## Campaña y pago completo

1. Selecciona el rango **30–59 días** y estado pendiente. Previsualiza el segmento: Ana aporta solo `hogar`; su deuda de telefonía tiene 75 días. Cada persona aparece una sola vez aunque tenga varios servicios elegibles.
2. Guarda la campaña con la plantilla aprobada y su idioma exacto. Lanza la secuencia una vez. El worker recorre una persona por vez y conserva el progreso. Los contactos ficticios se muestran como **simulados**, sin llamadas al canal ni a OpenAI; solo el contacto `live` habilitado puede recibir el envío real.
3. Responde desde WhatsApp. Confirma la pista enmascarada o indica tipo y número de documento ficticio. Si el origen llega como un identificador desconocido, puedes usar `CC 10000001`. Escribe `2468` cuando se solicite el PIN y elige explícitamente el servicio `hogar`.
4. Pide pagar el saldo completo. Abre el enlace y pulsa **Simular aprobación**. El recibo debe mostrar USD 100 recibidos, cero condonados y saldo cero. La telefonía conserva USD 60.
5. Envía una captura del recibo por WhatsApp. La confirmación del bot debe basarse en una consulta del pago y la deuda autorizada; una imagen, por sí sola, no liquida una deuda.

La orden cobra el importe fijado por la central y vence a los 30 minutos. Rechazar un intento mantiene el saldo. Un recibo pagado puede consultarse mediante su enlace firmado durante 24 horas después del pago; ese permiso no permite otro cobro.

## Acuerdo, medios y atención humana

Restaura el escenario entre recorridos financieros. Sobre la deuda de USD 100, ofrece **USD 90**, espera la propuesta y acepta en **otro mensaje**. Antes de aprobar el pago, la deuda sigue en USD 100. Al pagarlo, el recibo muestra USD 90 recibidos y USD 10 condonados. Repite con USD 80 para probar el umbral exacto. Una oferta de USD 79,99 exige atención humana; no genera una orden automática con ese descuento. Solo se admite USD, sin conversiones.

Para atención humana, pide un asesor o disputa la deuda. Deben quedar un caso y una nota privada, y Chatwoot pasa a `open`. El bot permanece detenido mientras exista control humano. El asesor devuelve la conversación a `pending` de forma explícita para reanudarla. La comprobación de estado y el envío son dos peticiones externas: una toma humana simultánea requiere verificar la carrera residual en la instalación real.

Envía una nota de voz de hasta 60 segundos y un texto acompañante; ambos deben aportar contexto. Envía después una captura ilegible y una imagen con apariencia de comprobante sin haber pagado: se debe pedir aclaración o consultar el registro, sin inventar éxito. Los medios admitidos son PNG/JPEG/WebP y audio OGG/WAV/MP3; WebM solo se acepta si el contenedor dispone de `ffprobe` y permite validar su duración. El límite es 5 MiB por archivo. Los medios no se procesan durante una solicitud de PIN.

## Métricas y trazas

La campaña muestra procesados, pendientes, simulados, envíos reales, errores y resultados. Los simulados quedan fuera del denominador de contactabilidad. Un pago completo tiene condonación cero; un acuerdo distingue pendiente, cumplido y vencido. Dinero recibido y condonado se presentan separados. Las solicitudes de asesor del cliente se distinguen de derivaciones automáticas.

En Langfuse, revisa los spans correlacionados de texto, herramientas, audio e imagen, con tokens, coste estimado y errores. Se verificaron tres generaciones reales de audio/visión por API y trazas de conversación, herramienta y modelo en la UI autenticada. No se almacenan prompts ni respuestas completas; las métricas de negocio se consultan en la central. No deben aparecer PIN, grants, tokens, contactos completos ni archivos. El ledger local comparte reservas entre modalidades y workers: presupuesto total USD 5 y corte conservador USD 4,50; un resultado incierto conserva su reserva. Restablecer la demo no borra ese consumo ni los cargos del proveedor.

## Restaurar y repetir

Desde la central, abre **Restaurar escenario de demo** y escribe `REINICIAR DEMO`. También puede ejecutarse:

```bash
docker compose --env-file .env -f infra/compose.yaml exec backend python -m scripts.reset_demo --confirm RESET_DEMO
```

El reinicio activa mantenimiento y bloquea nuevos trabajos. Si hay uno en curso, pide reintentar la misma operación cuando termine. Después elimina checkpoints y autorizaciones locales, restaura la cartera y fija un nuevo corte operativo. Conserva el ledger de inferencia, las trazas del proveedor y el historial externo de Chatwoot. Después vuelve a editar el teléfono y modo `live` de Ana antes de otra campaña.

Si falla una dependencia o hay trabajo activo, el mantenimiento queda visible y no se afirma éxito. Consulta la operación pendiente y reintenta con **la misma UUID**:

```bash
docker compose --env-file .env -f infra/compose.yaml exec backend python -m scripts.reset_demo --status
docker compose --env-file .env -f infra/compose.yaml exec backend python -m scripts.reset_demo --confirm RESET_DEMO --operation-key UUID_DE_LA_OPERACION
```

Las etapas se guardan para reanudar. Las dos bases no comparten una transacción distribuida. No uses `down -v` como reinicio de demo: eliminaría volúmenes persistentes y también el consumo guardado.

Para detener la instalación conservando datos:

```bash
docker compose --env-file .env -f infra/compose.yaml stop
```

## Ejecutar las pruebas sin servicios externos

La última ejecución registrada aprobó **245 pruebas, sin fallos ni omisiones**, el 1 de noviembre de 2026 a las 16:20 UTC.

La batería usa PostgreSQL 17 real, esquemas aislados y dobles de los proveedores. Se ejecuta en un proyecto Docker separado, sin puertos publicados, sin montar `.env` ni compartir volúmenes del runtime. La red de pruebas es interna:

```bash
docker compose -p proyecto-agil-tests -f infra/compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -p proyecto-agil-tests -f infra/compose.test.yaml down
```

El contenedor ejecuta `scripts.run_acceptance`: no llama a IA ni mensajería y falla si hay pruebas omitidas, fallos o evidencia referenciada sin ejecutar. Su informe distingue evidencia automatizada de aceptación real pendiente. `--live` está bloqueado explícitamente porque este runner no implementa los recorridos reales. Las pruebas normales tampoco acreditan AWS ni la entrega de WhatsApp.

## Diseño y despliegue

Una sola máquina ejecuta backend, worker, central y PostgreSQL separados para cartera y memoria, además de Langfuse. Chatwoot, Meta y OpenAI son externos. La central es el único escritor financiero. La memoria usa el `source_id` literal; cada salida conserva la conversación de origen. Cambiar de cliente exige otro PIN, revoca la autorización anterior y limpia el contexto financiero.

- [PRD y aceptación](specs/prd.md), [arquitectura](specs/arquitectura-inicial.md) y [plan técnico](specs/001-cobranza-whatsapp/plan.md).
- [Modelo de datos](specs/001-cobranza-whatsapp/data-model.md), [contratos](specs/001-cobranza-whatsapp/contracts/) y [tareas](specs/001-cobranza-whatsapp/tasks.md).
- [Evidencia y límites](docs/evaluacion.md), [dominio de demo](docs/dominio-demo.md) y [Spec Kit](docs/spec-kit.md).

La EC2, su capacidad, backup/restauración y la entrada HTTPS deben verificarse antes de afirmar un despliegue. Floci solo valida las operaciones locales de AWS expresamente ejercitadas; ejecutar la aplicación no prueba aprovisionamiento de EC2 ni paridad con AWS.
