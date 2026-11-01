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

## Accesos web del evaluador

El archivo privado `.env` reúne los accesos necesarios para usar las interfaces.
No se copian contraseñas en este README ni en el repositorio público.

| Interfaz | URL en `.env` | Usuario en `.env` | Contraseña en `.env` |
|---|---|---|---|
| Central de deudores | `PUBLIC_BASE_URL` + `/central` | `OPERATOR_USERNAME` | `OPERATOR_PASSWORD` |
| Langfuse | `LANGFUSE_PUBLIC_URL` | `LANGFUSE_INIT_USER_EMAIL` | `LANGFUSE_INIT_USER_PASSWORD` |
| Chatwoot de pruebas | `CHATWOOT_UI_URL` | `CHATWOOT_UI_EMAIL` | `CHATWOOT_UI_PASSWORD` |

El acceso web de Chatwoot usa un usuario propio con rol agente, asignado únicamente
a la bandeja de pruebas, y es distinto de la clave del relay. La edición instalada
permite consultar contactos de la cuenta; la restricción de bandeja se aplica a las
conversaciones. Abre Chatwoot en una ventana privada para probar ese usuario sin
cerrar la sesión del propietario. No necesita entrar a la administración de
Cloudflare ni a la cuenta AWS del propietario: el túnel utiliza su token de ejecución
privado.

## Datos y PIN de la demo

**PIN ficticio de todos los clientes: `2468`.** Se almacena como hash y se verifica fuera del modelo. La sesión dura 30 minutos; tres errores bloquean la identidad durante 15 minutos.

| Persona ficticia | Documento | Servicios y saldo inicial |
|---|---|---|
| Ana Martínez López | CC `10000001` | `hogar`: USD 100, 45 días; `telefonia`: USD 60, 75 días |
| Bruno Torres Gómez | CC `10000002` | `hogar`: USD 200, 35 días; sirve para probar aislamiento |
| Carla Rojas Díaz | CC `10000003` | `hogar`: saldo cero |
| Diego Castro Ruiz | CC `10000004` | `hogar`: USD 85, versión 2 |

Todos los nombres y documentos son ficticios. Los documentos tienen ocho dígitos. Las personas de los límites de mora 0, 29, 30, 59, 60, 89, 90, 119 y 120 usan el documento `20000000 + días` (por ejemplo, `20000120`). La pantalla muestra una fila por deuda; nombre y contacto pertenecen a la persona y se comparten entre sus servicios.

## 1. Abrir la central de deudores

1. Abre [la central](https://cobranza.agenx-dev-test.work/central).
   Si se entregó otro origen, usa la URL que imprime `./start.sh`.
2. Inicia sesión con `OPERATOR_USERNAME` y `OPERATOR_PASSWORD` del `.env` privado.
3. Localiza la tabla **Cartera y contacto**. Cada fila representa una deuda de un
   servicio, y una persona puede aparecer en varias filas.

**Comprobar:** en una instalación limpia hay 14 deudas de 13 personas. Todos los
contactos comienzan simulados. Ana Martínez López tiene dos deudas:

| Documento | Servicio | Saldo | Mora |
|---|---|---:|---:|
| CC 10000001 | hogar | USD 100 | 45 días |
| CC 10000001 | telefonia | USD 60 | 75 días |

## 2. Poner el WhatsApp del evaluador en un deudor

1. En **Tipo de documento**, selecciona `CC`; en **Número de documento**, escribe
   `10000001`. Deja mora, servicio y estado sin restringir.
2. Pulsa **Aplicar filtros**. Deben aparecer las dos deudas de Ana.
3. En cualquiera de esas filas, pulsa **Contacto**.
4. En **Celular E.164**, reemplaza el teléfono ficticio por tu WhatsApp con `+`
   y código de país, sin espacios. No cambies nombre ni documento: interpretarás
   a Ana durante la prueba.
5. Selecciona **Live · evaluador autorizado**. Esa opción habilita el contacto
   para envíos reales; **Simulado · sin envío externo** los deshabilita.
6. Pulsa **Guardar cambios**.

**Comprobar:** las dos filas de Ana muestran el mismo teléfono, modo **Live** y
contacto habilitado. El contacto se comparte entre servicios. Las demás personas
deben seguir simuladas. Todavía no has lanzado una campaña.

Si Meta limita los destinatarios del número de prueba, el WhatsApp utilizado debe
estar autorizado allí. Si ya hay una conversación con ese número, quien tenga
acceso a la bandeja de pruebas debe comprobar que esté en `pending` para el bot.
Una conversación en `open` pertenece a atención humana.

## 3. Filtrar la cartera y previsualizar la campaña

1. Borra **Número de documento** y deja **Tipo de documento** en **Todos los tipos**
   para incluir también deudores simulados en el segmento.
2. Selecciona estos filtros y pulsa **Aplicar filtros**:

   | Filtro | Valor |
   |---|---|
   | Mora | 30–59 días |
   | Servicio | hogar |
   | Estado | Pendiente |

3. Pulsa **Previsualizar segmento** en **Preparar una campaña**.
4. Revisa personas únicas, deudas elegibles y modo de contacto.

**Comprobar:** Ana aparece una sola vez y su deuda elegible es hogar. Telefonía
queda fuera por servicio y mora. Solo Ana está habilitada para un envío real;
las demás personas se procesarán como simuladas.

## 4. Guardar y lanzar la campaña

1. Escribe un nombre reconocible, por ejemplo `Evaluación · pago completo`.
2. Comprueba la plantilla preconfigurada `recordatorio_factura_demo` y el idioma
   `es`. Se muestran como información fija; no se eligen ni se editan. El aviso
   explica que en producción la creación se integraría con la API de Meta o del
   proveedor y el envío esperaría la aprobación. La demo utiliza una ya aprobada.
3. Pulsa **Guardar campaña**. Guardar todavía no envía mensajes.
4. Revisa el segmento y pulsa **Lanzar secuencia** una vez.
5. Observa el progreso y los resultados: se actualizan automáticamente cada tres
   segundos mientras la pestaña está visible. **Actualizar** permite consultarlos
   también de inmediato.

**Comprobar:** el despacho avanza una persona por vez, los destinos ficticios se
registran como simulados y la plantilla llega a tu WhatsApp. Los simulados no
envían mensajes externos ni consumen IA. No relances una campaña para compensar
una entrega incierta: consulta primero el resultado del destinatario.

En los próximos envíos, el texto del mensaje registrado en Chatwoot debe coincidir
con el cuerpo de la plantilla aprobada que recibe el WhatsApp. El relay obtiene
ese texto del catálogo de plantillas; no genera una versión alternativa.

El estado de envío y el acuse de entrega son distintos. Si Chatwoot omite el
estado exacto, no se debe presentar como entregado o leído. La recepción en el
WhatsApp del evaluador es una comprobación adicional del recorrido.

## 5. Responder e identificarse

1. Abre Chatwoot con `CHATWOOT_UI_URL`, `CHATWOOT_UI_EMAIL` y
   `CHATWOOT_UI_PASSWORD` del `.env` privado. Puedes usar una ventana de incógnito
   para conservar otra sesión abierta.
2. En **Conversaciones**, abre la bandeja de pruebas. Junto al título, cambia el
   filtro **Abiertas** a **Pendientes**. Las conversaciones gestionadas por el bot
   están en `pending` y no aparecen bajo el filtro de abiertas.
3. Abre la conversación correspondiente al WhatsApp que configuraste en la central.
   Déjala bajo control de **Alex TEST**, sin pulsar **Tomar el control**.
4. Responde a la plantilla desde tu WhatsApp, por ejemplo: `Hola, quiero revisar
   mi deuda`.
5. Comprueba en Chatwoot que aparezcan tu mensaje entrante y la respuesta del bot.
6. Si el agente encuentra una pista de identidad y pregunta si corresponde a ti,
   confírmala. Si solicita documento, escribe `CC 10000001`.
7. Cuando pida el PIN, escribe **2468**. Es el PIN ficticio de la demo.
8. Selecciona explícitamente el servicio **hogar**.

**Comprobar:** antes del PIN no revela el detalle financiero. Después de
autenticarte, puedes gestionar las deudas de Ana, una a la vez. El PIN se verifica
fuera del LLM. Si caduca la sesión de 30 minutos, debe volver a autenticarte.

## 6. Completar un pago sin descuento

1. Escribe: `Quiero pagar los USD 100 completos del servicio hogar. Dame el enlace`.
2. Abre el enlace que entrega el agente. Comprueba el servicio e importe.
3. Pulsa **Simular aprobación**.
4. Revisa el comprobante y vuelve a la central. Aplica nuevamente los filtros
   de `CC 10000001`, sin restringir estado, servicio ni mora.

**Comprobar:** el recibo muestra USD 100 recibidos, USD 0 condonados y saldo USD 0.
Hogar figura liquidada; telefonía conserva USD 60. Editar un saldo manualmente
no sustituye esta prueba: el pago debe originarse en la página simulada.

La orden vence a los 30 minutos. El enlace de un recibo pagado puede consultarse
durante 24 horas después del pago; no permite cobrar otra vez.

## 7. Enviar el comprobante al agente

1. Toma una captura del comprobante de la página de pago, evitando incluir la
   barra de direcciones: contiene un enlace privado.
2. Envíala por WhatsApp con un texto como `Ya pagué; verifica este comprobante`.
3. Espera la respuesta y contrasta el resultado con la central.

**Comprobar:** el agente interpreta la imagen y consulta el sistema para confirmar
el pago. La imagen por sí sola no autoriza a marcar una deuda como pagada. No debe
aplicar un segundo pago al recibir otra vez el mismo comprobante.

## 8. Revisar resultados y observabilidad

1. Mantén abierta la página de la campaña: sus métricas se actualizan cada tres
   segundos. Puedes pulsar **Actualizar** para una consulta inmediata. Actualmente
   la selección de campaña no se recupera al recargarla.
2. Contrasta envíos reales y simulados, personas que respondieron, contactabilidad
   y pagos completos sin descuento. Una respuesta previa a la campaña no cuenta
   como respuesta de esa campaña.
3. Abre [Langfuse local](http://localhost:3000) e inicia sesión con
   `LANGFUSE_INIT_USER_EMAIL` y `LANGFUSE_INIT_USER_PASSWORD` del `.env`.
4. Revisa las trazas del horario de la prueba: llamadas al modelo, interpretación
   de imagen, herramientas —incluida `verify_payment`—, latencias, tokens,
   coste estimado y errores.

**Comprobar:** los simulados quedan fuera de la contactabilidad real. El pago de
USD 100 cuenta como pago completo sin descuento. Langfuse no muestra prompts ni
respuestas completas, PIN, claves o enlaces privados; la conversación se consulta
en WhatsApp o en la bandeja de pruebas de Chatwoot.

El presupuesto de IA es USD 5, con un corte local conservador en USD 4,50. Las
reservas de resultados inciertos se conservan; el coste mostrado es estimado y
no reemplaza la facturación del proveedor.

## 9. Repetir con los otros caminos

Para cada escenario financiero independiente, usa **Restaurar escenario de demo**
y confirma `REINICIAR DEMO`. Esto restaura cartera y memoria local; después debes
repetir la configuración del teléfono de Ana y preparar otra campaña. No borra
consumo de IA, trazas ni historial externo de Chatwoot. Si hubo atención humana,
la devolución a `pending` debe ser explícita por quien atienda la bandeja.

| Escenario | Qué hacer sobre hogar, USD 100 | Qué comprobar |
|---|---|---|
| Acuerdo con descuento | Ofrecer USD 90, esperar la propuesta, aceptarla en otro mensaje y pagar desde su enlace. | Antes del pago sigue debiendo USD 100; al pagar se reciben USD 90 y se condonan USD 10. Cuenta como acuerdo cumplido. |
| Límite permitido | Ofrecer USD 80, aceptar después y pagar. | Se permite el acuerdo al 80%; recibe USD 80 y condona USD 20. |
| Oferta inferior al límite | Ofrecer USD 79,99. | No concede ese descuento automáticamente; crea el caso y deriva a humano. |
| Petición de asesor | Pedir hablar con una persona. | Nota privada y cambio a `open` en la bandeja de pruebas; el bot deja de responder mientras atiende el humano. |
| Audio | Enviar una nota de voz breve solicitando revisar hogar. | Entiende el contenido y mantiene identidad y servicio; la transcripción aparece como operación en Langfuse. |
| Comprobante sin pago | Enviar una imagen que afirme éxito sin haber aprobado el pago del escenario actual. | Consulta el sistema y no confirma una liquidación inexistente. |
| Imagen ilegible | Enviar una captura borrosa o sin datos legibles. | Pide aclaración o un comprobante legible, sin inventar valores. |
| Pago rechazado | Abrir una orden y simular rechazo. | La deuda conserva su saldo. |
| Aislamiento | Solicitar gestionar a Bruno, `CC 10000002`. | Exige confirmar esa identidad y su PIN; la autorización anterior de Ana no permite consultar sus deudas. |

Para verificar atención humana se necesita una persona con acceso a la bandeja
de pruebas de Chatwoot; el login de la central no concede ese acceso. No cambiar
bandejas de producción. Los audios admiten hasta 60 segundos y los archivos hasta
5 MiB; se admiten imágenes PNG/JPEG/WebP y audio OGG/WAV/MP3. WebM requiere que
el contenedor pueda validar duración y audio mediante `ffprobe`. No se procesan
medios mientras se solicita el PIN.

## Registro del recorrido

Anota cada resultado después de ejecutarlo. Un guion escrito o una prueba
automatizada no reemplaza esta comprobación por el canal real.

| Escenario | Resultado observado | Fecha / versión | Incidencia o evidencia revisada |
|---|---|---|---|
| Apertura y preparación de contacto | Pendiente | — | — |
| Campaña y respuesta | Plantilla recibida; respuesta pendiente | 2026-11-01 | Recepción confirmada por el usuario y estado delivered comprobado en Chatwoot. El primer intento fallido se conserva como incidencia. |
| Identificación y pago completo | Pendiente | — | — |
| Imagen y verificación del pago | Pendiente | — | — |
| Acuerdo 90% y límite 80% | Pendiente | — | — |
| Atención humana y retorno al bot | Pendiente | — | — |
| Audio y excepciones de comprobante | Pendiente | — | — |
| Métricas y trazas | Pendiente | — | — |

Las evidencias públicas deben ocultar teléfonos reales, accesos, PIN enviados y
URLs privadas. No incorporar `.env`, capturas sin revisar ni historial personal
al repositorio. Al terminar, deshabilita el contacto live o restaura la demo.

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

La última ejecución registrada aprobó **249 pruebas, sin fallos ni omisiones**, el 1 de noviembre de 2026 a las 16:45 UTC.

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
