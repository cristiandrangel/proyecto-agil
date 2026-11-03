# Evidencia de evaluación

Registro actualizado el **3 de noviembre de 2026**. El código está implementado; las afirmaciones siguientes distinguen pruebas deterministas, ejecución del runtime y recorridos con proveedores reales. Un doble de OpenAI o Chatwoot no demuestra esa integración.

## Referencia de recursos del equipo — 3 de noviembre

El operador confirmó que la Mac usada en la prueba tiene 16 GB de RAM total y
reportó unos 10 minutos de instalación. Docker había informado aproximadamente
7,8 GiB visibles. Esa ejecución respalda la referencia de unos 8 GiB para Docker;
no establece un mínimo universal ni mide picos. Se retiró la recomendación anterior
de 12 GiB y se separó explícitamente la memoria del espacio libre en disco.

El diagnóstico de RAM sigue siendo informativo. Las 40 pruebas dirigidas de
emulación, portabilidad y configuración aprobaron en 0,94 segundos, incluidos
casos de 6, 7,8, 8 y 12 GiB. Se conserva la comprobación de disco y CPU; no se
modificaron límites de contenedores ni la aplicación y no se repitió la suite
integral de 453 pruebas por este cambio del diagnóstico.

## Revisión de instalación en otro equipo — 2 de noviembre

Las 37 pruebas dirigidas de emulación, distribución y portabilidad aprobaron en
0,77 segundos. El smoke aislado de Docker Linux verificó tres forwards SSH sobre
bridge y publicación limitada a loopback, sin usar proveedores ni alterar la
demo activa. Ese smoke corrió dentro del runner: no comprobó HTTP desde el
loopback del anfitrión en esta repetición.

El preflight de la Mac activa confirmó salud de backend/central, acceso de lectura
a la bandeja TEST, modelos configurados y autenticación de Langfuse. No se llamó
al modelo ni se enviaron mensajes desde esa comprobación. El README y la
referencia de emulación distinguen ahora esos resultados de una aceptación
completa de Windows y explican puertos, recursos y límites del diagnóstico.

El lanzador aprobó **50 comprobaciones en Windows PowerShell 5.1 y 50 en
PowerShell 7**, con rutas y permisos NTFS reales y Docker sustituido por un doble.
La [ejecución CI aprobada](https://github.com/cristiandrangel/proyecto-agil/actions/runs/41550987285)
corresponde al código `8358a13`. La ruta se extrajo a una función para probarla;
no se acreditó un defecto previo de separadores. La primera publicación del
workflow rechazó una expresión de shell; la siguiente ejecutó las comprobaciones
pero conservó el código de una falla provocada. Se corrigió el harness y la
corrida posterior aprobó. Ninguna de esas ejecuciones desplegó la demo ni acredita
Docker Desktop completo en Windows. Estas comprobaciones son independientes de
la suite de 453 pruebas y no deben sumarse como si fueran otra corrida integral.

## Mac ARM64, cuotas y presupuesto de evaluación — 2 de noviembre

La revisión `1bc75ce` aprobó **453 pruebas, cero fallos y cero omitidas, en
52,08 segundos**, en Docker aislado con PostgreSQL real y proveedores externos
simulados. Incluye regresiones de selección EC2 ARM/x86, límites cgroup,
cuotas persistentes y gasto. Se corrigieron dos fixtures de pruebas que dependían
de archivos externos al test y una expectativa del límite anterior; la corrida
completa posterior pasó. Los tres avisos de Alembic son deprecaciones existentes.

En un segundo equipo Mac ARM64 se levantó el entorno emulado con la aplicación y
Langfuse. El preflight verificó las integraciones por lectura sin inferencia pagada.
El chat respondió hasta agotar los **100 intentos diarios** del relay compartido;
dos respuestas generadas quedaron fallidas por rechazo del canal. No fue un fallo
del login, de la inferencia ni un límite de Meta.

Por instrucción de Cristian, el relay pasó a **1.000 intentos/día**, conservando
los 100 consumidos. El presupuesto nominal y local de IA pasó a **USD 10**,
conservando el ledger y las reservas. La configuración efectiva en la Mac y el
prompt con definiciones de hogar, telefonía y televisión se comprobaron dentro
del backend. El siguiente mensaje se registró como enviado y Cristian confirmó
que la conversación continuó. No se reenviaron automáticamente los mensajes
fallidos ni se borró la conversación.

Esto acredita arranque e integración conversacional en la Mac, no el recorrido
completo de todos los pagos, medios, retorno y persistencia de ese equipo. Windows
sigue pendiente de ejecución nativa. Los resultados anteriores se conservan como
historia de sus respectivas versiones.

## Recuperación de acuerdos tras autenticar de nuevo — 2 de noviembre

Se detectó que la central conservaba un acuerdo aceptado, pero las consultas de
deudas no lo incluían y seleccionar una deuda limpiaba las referencias locales.
El agente podía afirmar que no había un acuerdo sin haber consultado ese dato.
La lista y el detalle ahora proyectan el acuerdo vigente desde central y la
selección recupera sus referencias y el enlace de una orden válida. La consulta
se hace por página en una sola operación SQL adicional, sin acceso del backend
a la base financiera. No publica capabilities ni tokens al modelo.

Las comprobaciones de propietario, versión, saldo, vencimiento y estados se
aplican al acuerdo y a su orden. Una nueva sesión no extiende plazos ni crea
órdenes. Un acuerdo propuesto conserva la confirmación en otro mensaje; uno
aceptado reutiliza su orden válida. Sin orden reutilizable, no se emite otra por
volver a aceptar. La condonación permanece condicionada al pago aplicado.

La suite completa Docker aislada con PostgreSQL 17 aprobó **447 pruebas, cero
fallos y cero omitidas, en 51,93 segundos**. Los tres avisos de deprecación de
Alembic corresponden a la configuración ya existente de migraciones. Ruff y la
revisión de diferencias aprobaron. Las regresiones cubren logout, cambio a otro titular y regreso con PIN nuevo,
aislamiento, estados vencidos o inconsistentes, recuperación en herramientas y
pago con los importes originales. No se ha ejecutado este nuevo recorrido en
WhatsApp ni una evaluación pagada del modelo para esta revisión.

Se reconstruyeron y actualizaron únicamente central, backend y worker del
invitado activo, conservando bases y conector. El endpoint real de deudas devolvió
el acuerdo aceptado de USD 190 sobre USD 200 con su orden reutilizable. Esto
acredita la consulta financiera, no la respuesta del modelo después de reautenticar.
Los hashes de deudas, acuerdos, órdenes y liquidaciones, los recuentos de trabajos
y salidas y el ledger de inferencia permanecieron iguales antes y después. Las
fuentes desplegadas coinciden con el checkout; readiness público y salud de
Langfuse devolvieron 200 y el preflight solo lectura aprobó sin inferencia ni
escrituras en el canal.

## Portabilidad, evals y contexto — revisión del 2 de noviembre

- **431 pruebas aprobadas, cero fallos y cero omitidas, en 44,26 segundos** en
  la suite Docker aislada con PostgreSQL 17 y proveedores sustituidos por dobles.
  La primera integración detectó que la imagen de pruebas no incluía los nuevos
  lanzadores ni el catálogo; se corrigió su empaquetado y la ejecución posterior
  aprobó toda la batería. Ruff, Bash y validación Compose también aprobaron.
- Lanzadores Bash y Windows PowerShell/CMD, resolución del contexto Docker local,
  red bridge, archivos con espacios/CRLF, claves SSH temporales, ACL de Windows y
  selección de arquitectura del daemon implementados. Las once imágenes
  revisadas ofrecen manifests amd64/arm64. Un ZIP sin `.git` conserva el archivo
  público permitido y excluye los privados ficticios de la prueba de distribución.
- Smoke Docker real y aislado del control-plane: tres forwards SSH, acceso HTTP
  loopback desde el host y desde el runner; sin montar socket ni entorno privado
  en el contenedor de túnel. Los fixtures de ese ensayo se eliminaron.
- El lanzador nuevo reanudó el entorno completo existente sin recrear el engine
  exterior. Los servicios quedaron saludables, los forwards de Langfuse y el
  backend respondieron, y el preflight público aprobó sin inferencia ni mensajes.
  Esto se comprobó en **Linux x86_64 con Docker Engine**. Windows, macOS y ARM
  tienen implementación y comprobaciones de contratos/manifests, pero todavía
  no una ejecución nativa completa en esos equipos.
- [Evals reproducibles](evals.md): **50 snapshots ficticios** versionados,
  validados offline y disponibles dentro del backend de la entrega. El runner
  distingue checks estructurales de revisión semántica humana y utiliza el
  ledger existente si se solicita inferencia. No se ejecutó el modelo con esta
  suite nueva ni se le atribuyen los resultados históricos del prompt.
- Por indicación de Cristian, la entrada del agente pasa a **70.000 tokens por
  llamada**, manteniendo veinte mensajes visibles, grupos de herramientas
  completos y salida de 4.096 tokens. Se aplicó a configuración de ejemplo,
  entrega y backend/worker activos, conservando datos y conector. La lectura
  actual del ledger observó un máximo de **7.257 tokens de entrada** y cero
  trabajos con `context_limit`; no acredita que nunca se haya retirado historial
  antes de inferir. No se hicieron llamadas pagadas para esta revisión.

## Entorno EC2 emulado

El perfil [EC2 emulada](emulacion-ec2.md) creó un invitado Linux mediante
`RunInstances` de Floci 2.4.0 y ejecutó dentro once servicios con Docker propio.
Se comprobaron salud del backend y Langfuse, separación de los motores Docker,
límites efectivos de 4 CPU/16 GiB y persistencia de un marcador PostgreSQL tras
EC2 Stop/Start. El marcador se eliminó al terminar. El fixture inicial contenía 13
personas, 14 deudas y cero campañas, mensajes, liquidaciones o inferencias.
También se detuvo el motor Docker exterior y `./emulate-ec2.sh up` recuperó
la misma instancia y conservó el entorno privado y los datos. Los forwards
volvieron a responder por HTTP después de esa recuperación.

Desde el equipo anfitrión se comprobaron por HTTP ambos accesos: login de central
con CSRF y origen válido, redirección 303 y cartera autenticada 200; login de
Langfuse con sesión autenticada. Estas pruebas no sustituyen un recorrido visual
completo. El test de exclusión de secretos del archivo de fuentes pasó con
`uv run python -m pytest -q tests/unit/test_ec2_emulation.py`.

Es un laboratorio con contenedores privilegiados y kernel compartido, no una VM
AWS ni una validación de EBS o capacidad de producción. Después de ese ensayo
se provisionaron las integraciones privadas y se trasladó el túnel: conector,
backend y worker anteriores detenidos; doce servicios propios en el invitado,
incluido `cloudflared`. No se copiaron datos de estudio ni el `.env` completo del
desarrollador. La clave de IA conserva solo el presupuesto restante del ledger
anterior; la instalación limpia no renueva el límite.

Comprobado en el entorno emulado público el 2 de noviembre:

| Recorrido | Resultado observado |
|---|---|
| HTTPS | Login 303, cookie Secure, cartera/health/ready 200; webhook sin firma 401 y entrada local 403. |
| Proveedores | Preflight por lectura de modelos OpenAI, bandeja TEST y autenticación Langfuse aprobado. |
| Campaña | 12/12 procesados: un envío real entregado, once simulados, cero fallos. Una persona respondió; contactabilidad del 100 % sobre la única persona real contactada. |
| Acuerdo | Hogar USD 100: acuerdo por USD 80, condonación USD 20, aceptación posterior, pago aplicado y saldo cero en PostgreSQL. |
| Comprobante | La imagen llegó y se almacenó en Langfuse. Visión omitió un carácter de la referencia; la consulta exacta devolvió `absent` y el agente derivó a humano pese al pago aplicado. El fallo se conservó en la traza. |
| Corrección | Prompts de visión y agente reforzados: referencia ilegible sin inventar caracteres; tras búsqueda fallida, consultar la misma deuda autenticada sin referencia antes de escalar. Tres casos con LLM real aprobaron la decisión; ninguna herramienta ni mensaje se ejecutó en esa evaluación aislada. |
| Retorno humano | Se registró `returned` con evento de devolución y el nuevo turno consultó cartera: hogar liquidado, telefonía pendiente USD 60. |
| Audio | Una nota de voz real se transcribió y produjo selección de telefonía y enlace de pago íntegro por USD 60. |
| Pago íntegro | Telefonía: USD 60 recibidos, cero condonación, saldo cero. El comprobante nuevo pasó por visión, `verify_payment` devolvió `applied` y el agente confirmó el pago y la ausencia de deudas pendientes. |
| Assets | Dos imágenes y un audio cargados en Langfuse; sus tres URLs firmadas en el puerto 19090 devolvieron 200 y el tamaño almacenado. |
| Trazas | Trece turnos de conversación y tres diagnósticos del prompt: 116 observaciones en 16 trazas, sin observaciones `ERROR`. Se comprobó por API el `verify_payment` final y sus importes. El login real en Chrome quedó visible con el proyecto y las trazas nuevas. |
| Persistencia con integraciones | EC2 Stop/Start conservó los dos pagos, el conjunto de checkpoints, el número de eventos y el gasto registrado, contrastados antes y después. Login HTTPS y preflight volvieron a responder correctamente. |

El comprobante nuevo de telefonía sí pasó por la versión corregida. El caso de
referencia mal leída quedó como evidencia histórica; la recuperación por deuda
se comprobó con tres escenarios del LLM real y con la consulta posterior de la
cartera, sin afirmar que se repitió aquella misma captura. El arranque con archivo
de entrega aplica las credenciales iniciales antes de crear las bases; la
portabilidad a otro PC sigue requiriendo un ensayo en ese equipo.

## Resultados comprobados

- **Última suite Docker aislada: 390 pruebas aprobadas, cero fallos y cero omitidas, en 44,75 segundos**, el 2 de noviembre. Se construyó una imagen nueva con PostgreSQL 17 y red interna, sin credenciales de proveedores. El runner terminó con código 0 y todas las referencias AC presentes. La revisión de esta entrega detectó que el test de ventana conservaba un techo fijo de 4500 tokens, menor que el prompt ampliado; ahora utiliza el límite de producción de 12000 y comprueba conservación del mensaje reciente, pares tool/result y checkpoints completos. La suite anterior de 377 pruebas corresponde al cierre del 1 de noviembre.
- **Infraestructura adicional: 20 pruebas focalizadas aprobadas**, incluido un contenedor Docker creado sin arrancar, sin red y con datos ficticios para contrastar `Config.Env`: barras, apóstrofes y dólares se conservan exactamente en el archivo privado. Ese ensayo del daemon anfitrión vive separado en `tests/infrastructure/`; no se requiere un socket Docker dentro del runner aislado de aceptación.
- Verificación estática de esta revisión aprobada: `uv run ruff check .`, compilación de Python en aplicaciones/paquetes/scripts/migraciones y relay, `bash -n start.sh`, y validación Compose de runtime, pruebas, override EC2 y Floci. Estas comprobaciones no ejecutan un despliegue AWS.
- El [runner](../scripts/run_acceptance.py) ejecutó unitarias, contratos e integración, comprobó que todas las referencias AC de su informe se ejecutaran y produjo evidencia automatizada para AC-01–31. **No marca la aceptación completa como aprobada**: la evidencia manual y live sigue pendiente. Un test omitido, un fallo o una referencia ausente impiden un resultado global correcto.
- `python -m scripts.run_acceptance --live` devolvió bloqueo explícito con código de salida 2. No hay un runner de aceptación real implementado y no se simula su éxito.
- El esquema operativo llega a **backend_0006**, con round-trip 0005/0006, conservación de un caso histórico y paridad de modelos comprobados en la suite. Incluye caché/precio v2, contratos del relay y regresiones de login, entrega, cuotas, catálogos globales y seed numérico con UUID/PIN estables. También cubre contactos con varios aliases, conversaciones sin binding y atribución de respuesta por la misma conversación sin modificar la llave de memoria ni los grants. Las regresiones más recientes cubren confirmación elegida por el agente, fase estática de PIN, transporte cifrado, ACK sin proveedores y nombre enmascarado con documento completo.
- Migración central verificada con PostgreSQL 17: upgrade, comparación sin diferencias frente a los modelos, downgrade y nuevo upgrade. El test está en `test_frozen_alembic_upgrade_downgrade_matches_models`.
- El lanzador `start.sh` tiene nueve pruebas de perfiles, URL y lectura segura de configuración. Se verificó que una cadena de comando dentro del token de `.env` no se ejecuta y que el perfil público precede a `up` solo cuando corresponde.
- Reset probado con dos esquemas reales y AsyncPostgresSaver: tras un fallo de central persiste mantenimiento; repetir la misma operación completa el reset una sola vez, elimina checkpoints de la llave literal y conserva el consumo registrado.
- Se observaron fallos antes de corregir tres riesgos: cursor que veía sequence 2 mientras sequence 1 seguía sin commit; revocación de identidad aún inexistente; y bloqueo PIN que no restauraba tres intentos entre distintos bindings. Las pruebas correspondientes pasaron después de los cambios.

La prueba inicial de Docker con red interna detectó además una descarga implícita de tiktoken en el primer uso, oculta por la caché de desarrollo. La imagen de pruebas ahora precarga `o200k_base` durante el build; la ejecución aislada posterior aprobó las 245 pruebas. Esa descarga es un recurso público del tokenizer y no una inferencia.

## Auditoría ampliada y cierre de sesión de trabajo

Se revisó de solo lectura la conversación TEST de esta sesión, contrastando entradas,
trabajos, salidas, casos humanos y la API paginada de Langfuse. No se enviaron mensajes,
reiniciaron escenarios ni modificaron identidades o saldos durante la auditoría.

| Fuente | Evidencia observada |
|---|---|
| Backend | 62 entradas: 56 completadas y seis de memoria humana pasiva; 56 trabajos completados y 64 salidas `sent`, sin trabajos ni salidas pendientes/fallidos en ese alcance. |
| Langfuse | 56 raíces `conversation`, 392 observaciones en 59 trazas. Tres entregas históricas siguen como raíces separadas, anteriores a la corrección de correlación. No hay padres no nulos ausentes ni observaciones `ERROR` en ese conjunto. |
| Entradas/salidas | 75 generaciones LLM con instrucciones/entrada y respuesta pertinente completada; 35 observaciones de herramientas con argumentos y resultado; 47 ejecuciones del agente con estados anterior y posterior estructurados. No se detectaron marcadores de truncamiento en la captura revisada. |
| Medios | Dos audios con transcripción no vacía y dos imágenes. Los cuatro assets tienen registro de carga y tamaño positivo en la API privada; no se descargaron ni reprodujeron sus bytes durante esta auditoría. |
| Sin inferencia por diseño | Nueve turnos estáticos sin LLM. Las seis entradas humanas pasivas no crearon trabajos, salidas ni trazas de ejecución propias; su texto aparece en el contexto del turno posterior. |
| Retorno humano | Dos devoluciones nuevas con referencia de evento persistida y secuencia asesor → evento de devolución → consulta actual en el input LLM. Ya se acredita el nuevo mecanismo en WhatsApp; los retornos históricos sin referencia no se reconstruyeron. |
| Acuerdo y pago | Cotización del 85 %, aceptación en turno posterior, imagen del comprobante, `verify_payment` aplicado y consulta posterior de cartera. Lectura directa de central confirmó acuerdo cumplido, orden pagada, base USD 200, recibido USD 170, condonado USD 30 y deuda liquidada con saldo cero. |
| Checkpoint PostgreSQL | El último checkpoint del chat contiene el evento final revisado, 12 grupos de mensajes, diez resultados de herramientas y un marcador de devolución humana. Fase `select_debt`, con la verificación del pago en el historial. La lectura usó conexión de solo lectura, sin ejecutar el grafo. |

Esto acredita persistencia y contenido útil de las fuentes revisadas, no corrección
semántica universal ni entrega/lectura final de WhatsApp. Los errores históricos de
identificación coloquial, agotamiento de autenticación y primera devolución humana
quedaron conservados, aunque sus trabajos terminaron sin error técnico. Un handoff
mostró cuatro observaciones de entrega para tres salidas: una fue un intento aplazado
y las otras tres fueron envíos efectivos; no fueron cuatro mensajes enviados.

El recorrido visual guiado por Langfuse se pospuso por decisión de Cristian para
la siguiente sesión. La auditoría técnica anterior sí se completó. El README
incluye el orden para revisar el pago, el acuerdo, el retorno humano, audio y PIN.
Los informes detallados, identificadores reales y datos de contacto permanecen privados.

### Revisión guiada en interfaz — 2 de noviembre de 2026

Cristian abrió Tracing y el último comprobante. Se contrastó el árbol visible con
la instrumentación y los padres persistidos: autenticación, visión, tres llamadas
al modelo dentro del agente, `verify_payment`, `list_debts`, preparación de respuesta
y envío. Se explicó la diferencia entre operación y traza, las pruebas `preflight`,
la outbox y el identificador del mensaje creado en Chatwoot. No se enviaron mensajes
ni se modificaron datos financieros durante esta revisión.

Se considera verificada la conexión y captura de Langfuse para la demo, con los
límites de evidencia descritos. Es una base de observabilidad aplicable a sistemas
empresariales; no certifica disponibilidad, capacidad bajo carga, alertas, retención,
permisos operativos ni evaluación automática continua de una instalación productiva.
El resto del guion visual está disponible para una revisión ampliada; no se declara
que cada asset o variante haya sido inspeccionado visualmente.

### Negociación 95 % → 80 %, condonación y comprobante

El único archivo de aplicación cambiado para esta política fue el system prompt.
Ante una oferta baja intenta primero el 95 % y luego el 80 %, una propuesta por
turno; deriva por debajo del mínimo cuando ambas se rechazaron y mantiene su
oferta inferior. Si mantiene una oferta válida superior al 80 %, la conserva en
vez de conceder una rebaja innecesaria. La solicitud expresa de asesor, disputa
o imposibilidad de verificación mantiene su derivación. Central conserva su mínimo
duro y la aceptación del acuerdo en un mensaje posterior.

La cotización debe explicar que la empresa acepta condonar la diferencia al cumplir
el pago acordado, indicando base, pago y condonación en USD; ese pago liquidará la
deuda, no dejará la parte condonada como saldo. Todo mensaje que entregue un enlace
debe recordar que el pago es simulado y pedir una imagen del comprobante con la
referencia visible al finalizar, para verificarlo con central.

Once escenarios sintéticos con Luna real aprobaron sus comprobaciones estructurales
y revisión manual de las respuestas: oferta inicial baja → 95 %, rechazo → 80 %,
rechazo de ambas → humano, aceptación de cada propuesta → cotización, oferta del
90 % → intento del 95 %, mantenimiento del 90 % → cotización del 90 %, solicitud
expresa de asesor, explicación de la cotización y enlaces íntegro/con acuerdo que
piden comprobante. Once llamadas, USD 0,00881725 estimados, reservas liquidadas.
No se ejecutaron herramientas reales ni escrituras en canal o central.

Ruff y revisión de diferencias aprobados. La suite completa de 377 pruebas es de
una revisión anterior; no se repitió por estos cambios de prompt/documentación.
La nueva política todavía requiere repetición en WhatsApp; el acuerdo real del
85 % anterior no la acredita. Tampoco se acreditan todavía las variantes exactas
del 90 % y 80 %, recibo falso/repetido, caducidad, cierre explícito de sesión,
bloqueo por tres PIN numéricos erróneos o continuidad tras reinicio completo.

## Orientación tras autenticación y explicación de búsquedas

La lectura de un turno real detectó que, tras tres mensajes de formato inválido,
el agente recibió `auth_attempts_exhausted` pero volvió a buscar por el teléfono
de origen y mostró al titular de ese teléfono, en lugar de orientar el reintento
para la otra persona. No se había concedido autorización. La corrección de
comportamiento se realizó exclusivamente en el system prompt: explicar el resultado,
recordar el formato y ofrecer reintento o asesor sin llamadas en ese turno. El
filtro estático, permisos, herramientas y bloqueo de central no se modificaron.

Dos rondas sintéticas con Luna real comprobaron seis escenarios cada una:
agotamiento, agotamiento con aviso de limpieza del contexto, reintento sin documento,
reintento con documento, petición posterior de asesor y autenticación correcta.
La primera cumplió las seis comprobaciones estructurales, pero la revisión manual
rechazó la respuesta al aviso de limpieza porque lo confundió con una petición de
cambiar permisos. Tras aclarar el prompt, la segunda cumplió las seis y explicó
ambos agotamientos con cordialidad, sin herramientas; el reintento sin documento
pidió ese dato, el documento aportado produjo la consulta canónica, el asesor
produjo `handoff_human` y el éxito produjo `list_debts`. Costes estimados por ronda:
USD 0,00379763 y USD 0,00383981; reservas liquidadas.

Otro ajuste del mismo prompt exige explicar el origen real del resultado de
`locate_customer`: teléfono o documento, seguido de Nombre y Documento y su
confirmación. Cuatro casos sintéticos con Luna real comprobaron coincidencia y
resultado vacío por ambos criterios. Los cuatro distinguieron el criterio utilizado,
sin llamadas adicionales ni coincidencias inventadas. El caso de teléfono además
incluyó presentación y contexto de cobranza. Coste estimado: USD 0,00484498,
reservas liquidadas. En la respuesta por documento se observó una variación de
espacios y cantidad de puntos del nombre enmascarado, pese a la instrucción de
copia literal; el documento siguió correcto y no se reveló el nombre completo.
La fidelidad visual exacta de la máscara continúa siendo una limitación observada.

Estos diagnósticos no ejecutaron herramientas ni escribieron en Chatwoot o central;
los resultados de búsqueda fueron ficticios. Falta repetir los nuevos comportamientos
en WhatsApp. Ruff y la revisión de diferencias pasaron; la suite completa de 377
pruebas corresponde a una revisión anterior a estos ajustes de prompt.

## Reinicio para el recorrido del evaluador

El 2026-11-01 se restauró el entorno de desarrollo con los productores detenidos:
13 personas y 14 deudas ficticias, todos los contactos simulados, cero acuerdos,
órdenes, liquidaciones y sesiones de identidad. Campañas, vínculos de canal,
eventos de negocio, casos humanos, entradas, trabajos, salidas y checkpoints
quedaron en cero. La limpieza de entradas y salidas históricas fue una operación
puntual de preparación; el reset habitual conserva esa auditoría.

Se eliminó únicamente la conversación de la demo en la bandeja de test. Las
credenciales, la configuración y el ledger de inferencia se conservaron:
29 reservas históricas y USD 0,0145786447 de consumo registrado. El reinicio no
envió mensajes al canal ni ejecutó inferencia. En una instalación nueva los
volúmenes empiezan vacíos; estos valores de consumo pertenecen al desarrollo.

Se eliminaron selectivamente las 20 trazas de estudio del proyecto demo de
Langfuse. La API aceptó la eliminación y la consulta individual de los 20 IDs
devolvió cero observaciones. Proyecto, usuarios, claves e infraestructura de
archivos se conservaron. Esta limpieza externa fue puntual: el botón habitual
de restauración de la central no borra las trazas de Langfuse ni Chatwoot.

La revisión de captura completa también detectó el alias `central_grant` en el
snapshot de identidad. Se corrigió su redacción tanto en campos estructurados
como en errores de texto. La regresión falló antes del cambio y pasó después:
tres pruebas enfocadas con el SDK real, sin HTTP al proveedor. Las entradas de
negocio y los importes siguen visibles. La suite histórica de 303 casos fue
anterior a esta regresión; las ejecuciones posteriores de 366 y 373 casos sí la incluyen.

## Recorrido WhatsApp revisado: 1 de noviembre, 21:03–21:09 Bogotá

Se revisaron los trece mensajes entrantes posteriores al despliegue de la fase
PIN, sus respuestas en Chatwoot TEST, las dos bases y las observaciones privadas
de Langfuse. La lectura no realizó inferencias, envíos ni cambios en la demo.

- **Identidad:** «Podemos proceder» produjo `manage_identity(confirm_candidate)`
  con una sola generación y solicitud estática. Dos PIN rechazados tuvieron cero
  generaciones; el correcto produjo `identity_verified`, `list_debts` y respuesta
  con hogar USD 100 y telefonía USD 60. La pista nueva mostró documento completo
  y nombre oculto con puntos. No se probó agotamiento ni bloqueo por tres errores.
- **Memoria y selección:** la pregunta sobre mora devolvió 45 y 75 días. «La
  segunda» seleccionó telefonía con `select_debt`, sin pedir repetir su nombre.
- **Pago íntegro:** `create_full_payment` generó orden por USD 60. Central registra
  un intento `rejected` con `applied=false`, luego uno `approved` con `applied=true`,
  una única liquidación de USD 60 y cero condonados. Telefonía quedó liquidada.
- **Imagen y verificación:** la imagen entrante tuvo normalización, una generación
  visual y `verify_payment` con resultado `applied`. El turno completo tuvo tres
  generaciones —visión y dos del agente— y el cierre al cliente fue entregado.
- **Continuidad:** al consultar otra obligación, `list_debts` devolvió hogar
  pendiente por USD 100. La deuda ya liquidada no volvió a presentarse para cobro.
- **Oferta inferior al mínimo:** USD 75 sobre hogar produjo `handoff_human`, caso
  `below_minimum` transferido, nota privada, aviso público entregado y cambio a
  `open`. Cero acuerdos creados; hogar mantiene USD 100. No se observó aún una
  respuesta del asesor, una entrada posterior bajo control humano ni retorno.

La campaña real informa una persona enviada y una que responde (100 %), una deuda
pagada íntegra, USD 60 recibidos, cero condonados, USD 100 pendientes y un
escalamiento automático; solicitudes explícitas de asesor: cero. Otra campaña
procesó once simulados y omitió el destino real por `active_campaign`. Los KPI
de esa segunda campaña no atribuyen el pago ni cuentan simulaciones como contactos.

El ledger de toda esa conversación —incluyendo los tres turnos anteriores al
último despliegue— registra **23 llamadas liquidadas: 22 de agente y una de visión,
USD 0,01156121 estimados**. No es el total del proyecto ni la factura del proveedor.
Los trece turnos nuevos fueron completados sin reintentos de trabajo ni errores
de observación marcados. No se deduce de ello tolerancia a duplicados o caídas.

**Hallazgos de observabilidad:** `manage_identity` se exportó como `tool`, porque
faltaba en el catálogo seguro de etiquetas. Las tres salidas del handoff quedaron
en trazas separadas: la creación directa de su outbox omitía el contexto del padre.
La traza original sí contenía `tool.handoff_human` y las salidas constaban enviadas.
Se corrigió el catálogo de etiquetas y se incorporó el padre al crear las tres
salidas en la misma transacción. Dos regresiones fallaron antes del cambio y
pasaron dentro de la suite completa de 353 casos posterior: SDK real con
exportador en memoria, PostgreSQL, padre conservado tras cerrar la raíz y
reprocesar la solicitud, y entrega de los tres efectos. No reescribe las trazas
existentes; el próximo turno real comprobará la exportación nueva. Las entradas y salidas de las generaciones y
herramientas financieras consultadas sí estaban disponibles.

Siguen pendientes el acuerdo con descuento por WhatsApp, frontera exacta del 80 %,
audio del canal, comprobante falso/ajeno, tres fallos de PIN y cambio de titular,
respuesta humana, silencio del bot en `open`, retorno explícito y reinicio con
memoria. La evidencia anterior de cada sección conserva su fecha y alcance.

## Refuerzo exclusivo del prompt: alcance e inyección

Una captura del usuario mostró respuestas de programación y comparación de marcas.
Se reprodujeron ambas preguntas con la versión anterior: ofreció ayuda de Python
y comparó Coca-Cola con Pepsi. La revisión semántica detectó los dos fallos aunque
el chequeo estructural de herramientas y canarios no los señalaba. Las capturas
privadas con contactos ajenos no se incorporan al repositorio.

El cambio de producción se limita a `agent/prompts.py`: función exclusiva de
cobranza con prioridad sobre proactividad, rechazo sin respuesta parcial de temas
ajenos, confidencialidad, falsos roles de auditor/desarrollador, extracción por
codificación/traducción, autoridad fingida y órdenes en medios/herramientas. El
historial anterior fuera de alcance no amplía funciones. No se añadió un filtro
previo, clasificador, nodo, herramienta ni cambio de permisos o configuración.

La primera variante se evaluó con 22 llamadas: las preguntas de alcance ya se
reconducían y no se filtraron canarios, pero en dos ataques de rol el modelo
proponía una consulta innecesaria. Se explicitó que un ataque sin una petición
legítima no justifica consultar personas o deudas. La versión final obtuvo
**22/22 chequeos estructurales y revisión semántica conforme de las respuestas**:
18 casos de alcance/ataques y cuatro controles de asesor, cierre, pago íntegro y
negociación. El recibo con orden incrustada propuso `verify_payment`; la oferta
de cero propuso derivación, no condonación. La identidad falsa no concedió cartera:
solo propuso iniciar identificación o explicó que hacía falta autenticar.

Las llamadas usaron Luna real en `high`, contexto ficticio y herramientas sin
ejecutar. No hubo mensajes de canal ni escrituras de central. Costes estimados:
comparación previa de dos preguntas, USD 0,00115308; primera variante de 22 casos,
USD 0,00766071; versión final de 22 casos, USD 0,00745703. Todas esas reservas se
liquidaron. Son muestras concretas, no garantía absoluta contra toda inyección.
Los textos que simulan medios son contexto extraído de prueba, no archivos reales
procesados durante esta evaluación. El dataset público es
[agent-security-cases.json](../tests/fixtures/agent-security-cases.json).

La suite Docker aislada aprobó **366 pruebas, cero fallos y cero omitidas, en
41,22 segundos**, incluyendo trece regresiones nuevas sobre los controles
existentes de identidad/argumentos forjados. Se ejecutó sobre el primer refuerzo;
la iteración final añadió únicamente instrucciones al prompt y se verificó en
la evaluación real de 22 casos. Ruff y comprobación de diff pasaron.

**Temperatura comprobada:** una solicitud de diagnóstico con el mismo modelo,
`reasoning.effort=high` y `temperature=0` fue rechazada por la API con HTTP 400,
parámetro `temperature` no soportado. Se conserva la configuración previa sin ese
parámetro. El cliente retuvo conservadoramente USD 0,00791520 de reserva incierta
para ese diagnóstico fallido; no se presenta como consumo facturado ni se libera
para ampliar presupuesto. No se cambió de modelo ni se redujo el razonamiento.

La separación entre instrucciones y datos, ejemplos claros y evaluación de
riesgos sigue la [guía oficial de seguridad para agentes](https://developers.openai.com/api/docs/guides/agent-builder-safety).
La autenticación y las restricciones financieras existentes siguen aplicándose
independientemente del texto generado. Después del despliegue, Cristian confirmó
que repitió las dos pruebas de alcance desde WhatsApp y ambas funcionaron. Esta
confirmación del usuario acredita esos dos casos; no supone una nueva inspección
de sus trazas ni la aprobación de todos los ataques. Las respuestas antiguas no
se modifican.

## Runtime y preflight de lectura

### Audio del canal y continuidad de atención humana

En el último tramo revisado del 1 de noviembre, el agente rechazó una comparación
de vehículos y una pregunta de aritmética sin resolverlas. Después localizó el
registro, solicitó confirmación y PIN, rechazó un intento y aceptó el siguiente.
Mostró hogar con USD 100 pendientes y telefonía liquidada. Una nota de voz real
de WhatsApp, de **5,46 segundos**, pidió revisar telefonía porque al cliente le
habían informado que debía ese servicio. Langfuse mostró transcripción, decisión
`handoff_human(reason=dispute)` y las tres entregas de nota privada, aviso y
`open`, dentro de la misma traza. El caso quedó transferido. Esto acredita audio
del canal y el motivo de esa derivación; todavía no acredita la respuesta de un
asesor ni su continuación con memoria humana.

Se implementó posteriormente el almacenamiento pasivo del diálogo público del
asesor y del cliente durante `open`, sin llamadas al LLM, jobs ni respuestas del
bot. En el próximo turno autorizado se incorporan mensajes con prefijos de actor
al estado y checkpoint, sin duplicados, restringidos a conversación, revisión de
identidad y último reset. Notas privadas y mensajes del bot quedan excluidos.
No se importó el historial humano anterior al cambio. Los adjuntos durante la
atención humana dejan un marcador y no se procesan automáticamente. Siete regresiones nuevas, dentro
de la suite completa de 373 casos, comprobaron deduplicación, scope, revisión,
reset, fase PIN, ausencia de jobs/inferencia al guardar y presencia del diálogo
en la entrada del modelo y el checkpoint al retomar. Los tests de PostgreSQL y
worker usan proveedores dobles y no envían mensajes reales.

El usuario realizó después el retorno real: tres respuestas públicas del asesor
se guardaron sin jobs y aparecieron completas, en orden, en el input del LLM y en
el checkpoint del siguiente turno. Sin embargo, el agente respondió como si la
transferencia histórica siguiera vigente y remitió otra vez al asesor, sin
consultar el saldo. La memoria sí había llegado; faltaba comunicar explícitamente
al modelo el control actual que el backend ya había verificado. La fase enviada
era `select_debt`, así que ese fallo concreto no se explica por una fase de
handoff atascada.

En una primera corrección, posteriormente sustituida por el evento descrito debajo,
se añadió `channel_control=bot` al contexto del servidor después de las
comprobaciones del worker, sin nuevos campos de estado ni autorización por texto.
El prompt diferencia el control actual de un resultado histórico de handoff y
pide una consulta vigente al retomar una pregunta de saldo. También se normaliza
una fase histórica `handoff_requested` al retomar con una deuda seleccionada.
Dos variantes ficticias con Luna real —retorno inicial y continuación tras una
respuesta errónea como la observada— propusieron `list_debts` y respondieron hogar
USD 100 y telefonía liquidada, sin nueva derivación. Fueron cuatro llamadas,
USD 0,00160344 estimados, reservas liquidadas y cero efectos de canal o central;
los resultados de herramientas eran ficticios. La suite completa de 375 pruebas
incluye dos regresiones del retorno aplicado, con y sin deuda seleccionada:
comprueba que una frase del asesor no reactive al bot y que solo el retorno real
entregue el control actual y la fase correcta al modelo. Queda repetir el turno por
WhatsApp después de esta corrección para acreditar la respuesta en el canal.

### Evento de devolución dentro del historial

La versión actual elimina `channel_control` del contexto del servidor y registra
la transición dentro de `messages`, sin añadir campos al esquema de AgentState.
Cuando la reconciliación verifica transferencia aplicada, `open` observado y
`pending` en un mensaje distinto, guarda `returned` y `return_event_id` en la
misma transacción del caso. El evento se reconstruye desde esa referencia y se
incorpora después del diálogo humano y antes de la consulta que retomó el chat,
con prefijo `evento_canal:` e id estable `channel-return:<case_id>`. Sobrevive a un
reinicio anterior al checkpoint y no se duplica al reintentar o en turnos posteriores.
La migración 0006 mantiene nula la referencia de casos históricos ya devueltos;
no se fabrica una fecha o un evento anterior. Scope, revisión de identidad y
reset limitan la recuperación del marcador.

Las dos regresiones de retorno con y sin deuda seleccionada comprueban ahora el
mensaje ordenado, persistencia, deduplicación y ausencia de `channel_control` en
las instrucciones. Se añadieron pruebas de filtrado del evento y de migración.
La primera suite encontró una suposición de orden en un test de entrega del
handoff: con timestamps iguales, podía observar un efecto dependiente aplazado.
Se ajustó el test al polling real, exigiendo tres envíos efectivos únicos y padres
conservados también en los intentos aplazados; la implementación de envío no cambió.
La suite final aprobó **377 casos, cero fallos y cero omitidos**, en 46,35 segundos.

Con Luna real se evaluaron de nuevo retorno y continuación tras una respuesta
errónea, esta vez con el evento en mensajes y sin el indicador en instrucciones.
Ambas variantes consultaron `list_debts`, reconocieron la aclaración del asesor y
respondieron hogar USD 100 y telefonía liquidada. Cuatro llamadas por
USD 0,00174844 estimados, todas liquidadas, usando resultados ficticios de tools,
sin ejecución de herramientas ni escrituras en central o canal. La verificación
WhatsApp de esta nueva representación estaba pendiente en ese momento; la auditoría ampliada al inicio de este documento acredita dos devoluciones posteriores.

### Etiquetas de identidad y tono cordial

La pista actual presenta `Nombre:` y `Documento:` en líneas separadas. Conserva
el nombre enmascarado y el documento completo; no cambia PIN, permisos ni saldos.
Ocho tests existentes de contrato e integración pasaron en 1,66 segundos, incluidos
los límites de ocultación y la validación de PIN con deduplicación. La suite completa
de 377 casos corresponde a la revisión anterior a este cambio de presentación.

El system prompt añade pautas generales de trato: reconocer la intención, explicar
la validación, aceptar correcciones y preguntar por la correspondencia de los datos,
sin términos burocráticos ni respuestas estáticas. La primera variante seguía usando
frases frías y se afinó. En la segunda evaluación con Luna real, retomar un pago
produjo una oferta de ayuda y explicación de privacidad; cambiar de persona reconoció
la nueva gestión antes de mostrar las etiquetas; la consulta de programación se
rechazó y pagar el total propuso `create_full_payment`. Fueron cuatro llamadas por
USD 0,00388266 estimados, liquidadas, sin ejecutar tools ni escribir en el canal o
central. La variante anterior consumió otras cuatro llamadas por USD 0,00388046.
En una respuesta el modelo varió la cantidad de puntos del nombre enmascarado;
la pauta exige copia literal y esa fidelidad visual debe comprobarse también en
el canal. No se observó divulgación del nombre completo ni cambio del documento.
Los ejemplos son ficticios; la captura del usuario con contactos ajenos no se publica.

### Contrato canónico de identificación y separadores

La revisión del turno real con `10000002 cédula` mostró que el modelo envió
`document_type=cédula` y el número correcto. La central almacena `CC` y compara
literalmente, por lo que devolvió cero coincidencias. El registro ficticio de
Bruno sí existía; el fallo fue traducir el tipo al contrato, no la inexistencia
ni un PIN incorrecto. Se corrigieron el prompt y las descripciones de
`locate_customer`, `document_type` y `document_number`: interpretación natural,
códigos canónicos, orden flexible, separadores claros, ceros iniciales, datos
faltantes y ambigüedad. No se añadieron filtros previos, regex de mensajes,
concesiones de identidad ni cambios en la búsqueda de central.

Once casos sintéticos con Luna real pasaron: número antes/después del tipo,
nombre desarrollado, tildes, código en minúscula, puntos y espacios, nueve dígitos,
ceros iniciales, otro tipo y número faltante. `100.203.234` produjo `100203234`,
sin forzar ocho dígitos; `00.100.002` conservó `00100002`. Cédula de extranjería
produjo CE, sin confundirla con CC; esto no afirma que existan fixtures de ese tipo.
El número faltante pidió aclaración sin consulta. Once llamadas liquidadas por
USD 0,00303905 estimados, herramientas solo propuestas, cero escrituras de canal
o central. Además pasaron **28 tests unitarios de contexto y herramientas en
0,40 segundos** y Ruff. La suite completa de 377 casos es anterior a esta
modificación de instrucciones; falta repetir la consulta corregida en WhatsApp.
La captura del usuario permanece privada.

### Ajuste de guía al pago, negociación y cierre de sesión

Después del recorrido, se modificaron el system prompt y la descripción de
`manage_identity`: guiar hacia el pago completo, intentar hasta dos contraofertas
graduales antes de cotizar la oferta inicial y cerrar sesión usando la revocación
existente de `change_customer`. El agente espera el documento del siguiente
titular tras cerrar, manteniendo la misma conversación y fase inicial. El mínimo
del 80 % y la aceptación del acuerdo en un mensaje posterior siguen vigentes.

Se comprobaron **siete escenarios ficticios con Luna real** y herramientas sin
ejecutar: cierre eligió `change_customer`; pago íntegro eligió `create_full_payment`;
ante oferta de USD 90 sobre USD 100, propuso USD 95; tras rechazar USD 95, propuso
USD 92; tras dos rechazos eligió cotizar USD 90; al aceptar USD 95 eligió cotizar
95; después del resultado de cierre respondió pidiendo nueva identificación sin
llamar a una localización automática. Las dos contraofertas tuvieron redacción
natural y no crearon propuestas por su cuenta.

Las siete llamadas quedaron liquidadas por **USD 0,00241969 estimados**. La lectura
de comparación previa usó otras cinco llamadas por USD 0,00159088: ante la primera
oferta de 90, la versión anterior intentaba cotizar inmediatamente ese importe.
No hubo escrituras de canal o central, ni ejecución de las herramientas propuestas.
Los accesos y el ledger fueron los del runtime; entradas, identidades y deudas de
diagnóstico fueron ficticias. Son muestras del comportamiento del prompt, no una
garantía universal ni un recorrido financiero completo por WhatsApp.

Las **21 pruebas unitarias de contexto y tools** pasaron en 0,41 segundos y Ruff
pasó. La suite completa de 353 corresponde a la revisión anterior a estos cambios
de prompt. Backend y worker se actualizaron para la prueba posterior del usuario;
la conversación bajo control humano se conserva hasta su devolución explícita.

### Revisión de confirmación, PIN y acuse del webhook

La suite de 351 casos verifica que una confirmación como «dale» llega al único
nodo y solo activa autenticación mediante `manage_identity(confirm_candidate)`.
Ese resultado termina el turno con la solicitud fija de PIN, sin segunda llamada
al modelo. Durante `awaiting_pin`, formato incorrecto y PIN rechazado incrementan
un contador durable; duplicados no lo incrementan de nuevo. Tras el tercer fallo
se entrega `auth_attempts_exhausted`, sin autorización financiera. Un PIN correcto
entrega `identity_verified`; los fallos de infraestructura no consumen intento.

Las regresiones de webhook comprueban HTTP 200 sin lecturas de Chatwoot, sin
verificación de PIN ni inferencia en el ingreso, incluso si el worker tiene el
lock del thread. Se exige la escritura local durable previa. El transporte de
auth usa Fernet; el worker sustituye el sobre cifrado por el resultado seguro,
sin copiarlo a checkpoint, modelo ni observaciones. Fuera de esa fase no hay
filtro global de números ni protección automática de códigos espontáneos.

La migración `backend_0005` también se verificó por separado en PostgreSQL 17
aislado: upgrade con fila anterior existente y valor inicial cero, comparación
sin diferencias frente a modelos, downgrade conservando la fila y nuevo upgrade.
Después se actualizaron central, backend y worker, todos saludables. La base de
desarrollo informa `backend_0005`; salud/readiness local y pública devolvieron
200 y una comprobación ficticia del helper desplegado devolvió nombre enmascarado
con documento completo. No se reinició la demo ni se enviaron mensajes o llamadas
de inferencia durante esta actualización. El recorrido WhatsApp posterior al
cambio sigue pendiente; estos resultados no acreditan esa aceptación completa.

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

Durante el recorrido guiado por WhatsApp, una captura del usuario mostró la
presentación de Alex, contexto de cobranza, explicación de autenticación y pista
enmascarada antes del PIN. También permitió detectar que los asteriscos de
ocultación interferían con el formato de esa pista. Se cambiaron por `•` en la
central y el prompt pide copiarla literalmente en texto plano. Las seis variantes
del contrato fallaron antes del cambio y la validación posterior aprobó **40
pruebas enfocadas en 16,02 segundos**, con PostgreSQL 17 aislado, sin claves de
proveedores ni red externa. Se comprobó además Ruff. Esto valida el ajuste y la
identidad/finanzas relacionadas; no sustituye la comprobación visual de una nueva
pista por WhatsApp ni acredita todavía el recorrido completo de pagos.

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
`Authorization`, grants, capabilities y tokens de enlaces. El PIN **tecleado durante
`awaiting_pin`** viaja cifrado temporalmente por la cola y se verifica en el worker
antes del modelo; el sobre se sustituye por un resultado seguro, que es lo único
capturado por la traza. Los
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

**Pruebas deterministas de esa revisión:** la suite Docker histórica de captura
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

La columna manual/live conserva anotaciones de distintas etapas del recorrido y
todavía requiere reconciliación completa. Las revisiones fechadas al principio
de este documento y el apartado de auditoría ampliada describen la evidencia
posterior. Si una anotación antigua dice pendiente y una revisión posterior
registra el mismo recorrido, usar esa revisión y su alcance; no interpretar esta
matriz como un inventario actualizado de todos los pendientes ni como aprobación
universal de los 31 criterios.

Todas las referencias de esta tabla se ejecutaron correctamente en la suite Docker registrada. La columna final identifica lo que todavía no acredita esa ejecución.

| AC | Evidencia automatizada ejecutada | Evidencia manual/live y pendientes |
|---|---|---|
| AC-01 | [`test_central_finance::test_frozen_alembic_upgrade_downgrade_matches_models`](../tests/integration/test_central_finance.py)<br>[`test_web_frontends::test_private_console_login_and_csrf_rotation`](../tests/contracts/test_web_frontends.py) | Arranque limpio, login y preflight aprobados en copia aislada del mismo equipo; falta repetir en el equipo del evaluador. |
| AC-02 | [`test_central_finance::test_customer_grants_isolate_debts_and_switch_revokes_prior`](../tests/integration/test_central_finance.py)<br>[`test_agent_context::test_debt_selection_required_and_select_clears_old_refs`](../tests/unit/test_agent_context.py) | WhatsApp: listado y selección de telefonía observados; falta cambio de titular y aislamiento en el canal. |
| AC-03 | [`test_central_finance::test_masked_identity_pin_lock_and_retry_deduplication`](../tests/integration/test_central_finance.py)<br>[`test_backend_identity::test_invalid_pin_media_and_temporary_failure_do_not_reach_agent`](../tests/integration/test_backend_identity.py) | WhatsApp: dos PIN incorrectos sin generaciones y luego uno correcto; falta tercer fallo, bloqueo y formato inválido. Los medios no tienen redacción visual/voz automática. |
| AC-04 | [`test_backend_identity::test_confirm_pin_is_neutral_and_grant_only_in_runtime`](../tests/integration/test_backend_identity.py)<br>[`test_text_journey::test_locate_preserves_only_fresh_masked_tool_after_identity_switch`](../tests/integration/test_text_journey.py) | WhatsApp: confirmación natural y documento completo observados; falta candidato rechazado y cambio de registro. |
| AC-05 | [`test_central_finance::test_full_payment_rejected_then_applied_idempotently_and_reference_isolated`](../tests/integration/test_central_finance.py) | WhatsApp: enlace de telefonía, rechazo, aprobación de USD 60/0, captura y cierre verificado observados. Falta repetición real del mismo pago/captura. |
| AC-06 | [`test_central_finance::test_discount_boundaries_and_accept_only_subsequent_message`](../tests/integration/test_central_finance.py) | 90% local sobre USD 60→54 aprobado y aplicado; faltan comprobante, confirmación posterior del pago y recorrido del canal real. |
| AC-07 | [`test_central_finance::test_discount_boundaries_and_accept_only_subsequent_message`](../tests/integration/test_central_finance.py)<br>[`test_money_policy::test_exact_discount_boundary_and_roundtrip`](../tests/unit/test_money_policy.py) | Oferta USD 80 y explicación/aceptación con el modelo y el canal reales. |
| AC-08 | [`test_central_finance::test_discount_boundaries_and_accept_only_subsequent_message`](../tests/integration/test_central_finance.py)<br>[`test_agent_context::test_handoff_blocks_further_financial_tools_in_same_turn`](../tests/unit/test_agent_context.py) | WhatsApp: oferta USD 75 sobre USD 100 derivó con nota, aviso y open. Falta borde USD 79,99. |
| AC-09 | [`test_central_finance::test_invalid_discount_amounts_do_not_create_orders`](../tests/integration/test_central_finance.py)<br>[`test_money_policy::test_rejects_ambiguous_or_invalid_money`](../tests/unit/test_money_policy.py) | Aclaración del modelo real ante importe ambiguo; la política determinista sí rechaza entradas inválidas. |
| AC-10 | [`test_central_finance::test_unpaid_order_expiry_blocks_capability_and_projects_expired_to_owner`](../tests/integration/test_central_finance.py)<br>[`test_central_finance::test_paid_receipt_survives_charge_expiry_but_no_new_attempt`](../tests/integration/test_central_finance.py) | Rechazo seguido de aprobación observado en la página real; faltan abandono y vencimiento de orden. |
| AC-11 | [`test_media::test_download_pins_resolved_ip_preserves_tls_sni_and_sends_no_credentials`](../tests/integration/test_media.py)<br>[`test_central_finance::test_full_payment_rejected_then_applied_idempotently_and_reference_isolated`](../tests/integration/test_central_finance.py) | Captura de WhatsApp: visión y verify_payment aplicado observados, con respuesta entregada. |
| AC-12 | [`test_central_finance::test_full_payment_rejected_then_applied_idempotently_and_reference_isolated`](../tests/integration/test_central_finance.py)<br>[`test_handoff::test_case_persists_before_ordered_effects_and_duplicate_is_idempotent`](../tests/integration/test_handoff.py) | Imagen aparente de éxito sin pago: decisión y derivación del modelo real. |
| AC-13 | [`test_central_finance::test_customer_grants_isolate_debts_and_switch_revokes_prior`](../tests/integration/test_central_finance.py)<br>[`test_central_finance::test_order_capability_can_be_regenerated_only_under_owner_grant`](../tests/integration/test_central_finance.py) | Captura o referencia ajena en conversación real; la API sí prueba el aislamiento. |
| AC-14 | [`test_central_finance::test_concurrent_orders_settle_exactly_once`](../tests/integration/test_central_finance.py)<br>[`test_queue::test_durable_duplicate_delivery_has_one_job_and_original_destination`](../tests/integration/test_queue.py) | Entrega duplicada real de canal/captura; deduplicación durable y liquidación única sí probadas en PostgreSQL. |
| AC-15 | [`test_media::test_real_audio_duration_enforced_before_transcription`](../tests/integration/test_media.py) | Audio real de 4,994 s transcrito correctamente; faltan nota de voz desde WhatsApp y texto acompañante en ese recorrido. |
| AC-16 | [`test_media::test_magic_rejects_unsafe_or_misleading_image_content`](../tests/integration/test_media.py)<br>[`test_media::test_real_audio_duration_enforced_before_transcription`](../tests/integration/test_media.py) | Comprobante visual del canal verificado; faltan imagen ilegible y audio del canal. MIME/magic y audio inválido se rechazan en pruebas. |
| AC-17 | [`test_handoff::test_case_persists_before_ordered_effects_and_duplicate_is_idempotent`](../tests/integration/test_handoff.py)<br>[`test_handoff::test_private_note_redacts_secrets_and_only_uses_trusted_identity`](../tests/integration/test_handoff.py) | Nota privada, aviso y open observados en Chatwoot; falta respuesta del asesor. |
| AC-18 | [`test_handoff::test_human_takeover_during_inference_cancels_queued_output`](../tests/integration/test_handoff.py)<br>[`test_handoff::test_return_requires_applied_transfer_open_observation_then_new_pending_event`](../tests/integration/test_handoff.py) | Toma humana durante inferencia y retorno explícito en Chatwoot; persiste la carrera externa consulta/envío. |
| AC-19 | [`test_text_journey::test_checkpoint_restart_literal_source_history_and_event_dedupe`](../tests/integration/test_text_journey.py)<br>[`test_central_finance::test_recoverable_two_database_reset_clears_real_checkpoints_preserves_spend`](../tests/integration/test_central_finance.py) | Reinicio de contenedores en conversación real; checkpoints y cambio de identidad sí probados con PostgreSQL y AsyncPostgresSaver. |
| AC-20 | [`test_campaigns::test_person_dedup_stable_snapshot_and_simulations_never_touch_channel`](../tests/integration/test_campaigns.py) | Una plantilla real para la persona con dos deudas observada; otro lote procesó once simulados. |
| AC-21 | [`test_campaigns::test_active_person_excluded_and_close_stops_pending_dispatch`](../tests/integration/test_campaigns.py)<br>[`test_campaigns::test_live_sequential_dispatch_launch_idempotency_and_immutable_outbox_destination`](../tests/integration/test_campaigns.py) | Destino real omitido por active_campaign observado en otro lote; falta repetición del mismo lanzamiento. |
| AC-22 | [`test_text_journey::test_five_tool_responses_stop_and_register_honest_handoff`](../tests/integration/test_text_journey.py)<br>[`test_backend_identity::test_invalid_pin_media_and_temporary_failure_do_not_reach_agent`](../tests/integration/test_backend_identity.py) | Fallo del proveedor/central durante un turno real y comunicación al usuario; fallos deterministas usan dobles. |
| AC-23 | [`test_agent_context::test_pre_pin_catalog_and_strict_tool_schema_never_accept_identity_or_grant`](../tests/unit/test_agent_context.py)<br>[`test_handoff::test_reason_amount_and_tenant_are_validated`](../tests/integration/test_handoff.py) | Tres muestras de inyección con Luna real sin divulgación ni confirmación falsa de pago; falta ampliar ataques y ejecutarlos por el grafo y WhatsApp. Los permisos y esquemas deterministas sí están limitados. |
| AC-24 | [`test_budget::test_concurrent_budget_cutoff_is_atomic`](../tests/integration/test_budget.py)<br>[`test_budget::test_timeout_preserves_amount_and_expired_lease_only_releases_slot`](../tests/integration/test_budget.py)<br>[`test_agent_context::test_payment_capability_never_crosses_model_checkpoint_boundary`](../tests/unit/test_agent_context.py) | Trazas reales de texto, PIN, imagen y finanzas leídas; hallazgos de nombre de tool y padres del handoff registrados. Falta contraste con factura del proveedor. |
| AC-25 | [`test_central_finance::test_operator_contact_shared_version_mora_and_seed_never_overwrites`](../tests/integration/test_central_finance.py)<br>[`test_web_frontends::test_exact_mora_bucket_and_service_filters`](../tests/contracts/test_web_frontends.py) | Edición por navegador y entradas negativas/fraccionarias/vacías de extremo a extremo; persistencia y filtros sí probados. |
| AC-26 | [`test_campaigns::test_mora_buckets_boundaries_and_multiple_services`](../tests/integration/test_campaigns.py) | Lanzamiento real por límites; pruebas deterministas ya comprueban 29/30/59/60 y varios servicios. |
| AC-27 | [`test_metrics::test_metrics_real_cohort_dedup_money_agreement_and_human_milestones`](../tests/integration/test_metrics.py)<br>[`test_metrics::test_active_human_and_expired_agreement_are_current_results_not_milestones`](../tests/integration/test_metrics.py) | API de métricas contrastada con pago USD 60/0 y derivación; faltan acuerdo con descuento y corte real del seguimiento. |
| AC-28 | [`test_central_finance::test_operator_contact_shared_version_mora_and_seed_never_overwrites`](../tests/integration/test_central_finance.py)<br>[`test_campaigns::test_changed_contact_is_skipped_and_unknown_delivery_is_not_resent`](../tests/integration/test_campaigns.py) | Entrega al contacto configurado y localización por ese origen observadas; falta variante de cambio posterior del contacto. |
| AC-29 | [`test_money_policy::test_rejects_ambiguous_or_invalid_money`](../tests/unit/test_money_policy.py)<br>[`test_agent_context::test_pre_pin_catalog_and_strict_tool_schema_never_accept_identity_or_grant`](../tests/unit/test_agent_context.py) | Oferta conversacional en otra moneda y aclaración del modelo real; la API declara USD fijo. |
| AC-30 | [`test_central_finance::test_concurrent_orders_settle_exactly_once`](../tests/integration/test_central_finance.py)<br>[`test_central_finance::test_stale_balance_invalidates_order_and_quote`](../tests/integration/test_central_finance.py) | Demostración con navegador/cliente real; concurrencia y saldo modificado sí están probados con transacciones PostgreSQL. |
| AC-31 | [`test_campaigns::test_live_sequential_dispatch_launch_idempotency_and_immutable_outbox_destination`](../tests/integration/test_campaigns.py)<br>[`test_campaigns::test_person_dedup_stable_snapshot_and_simulations_never_touch_channel`](../tests/integration/test_campaigns.py) | Una campaña entregó al evaluador; otra simuló once y omitió al contacto con campaña activa. La ausencia de llamadas para simulados tiene prueba determinista. |

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
| Inferencia de agente | WhatsApp: confirmación natural, cartera, selección contextual, enlace, verificación de USD 60/0 y handoff observados. Acuerdo USD 60→54 con USD 6 condonados probado antes por entrada local; falta ese acuerdo completo en WhatsApp y contraste con factura. |
| Transcripción y visión | Visión `high` leyó referencia, importe, condonación y estado sin verificación financiera: 1403 tokens de entrada, 136 de salida, 1400 escrituras de caché de 30 minutos y USD 0,0005138 estimados con la tarifa corregida. `gpt-transcribe` transcribió correctamente un audio real de 4,994 segundos. El comprobante de telefonía se procesó y verificó en WhatsApp; falta nota de voz del canal. |
| Chatwoot/WhatsApp | Plantilla, conversación con PIN, pago USD 60, imagen y cierre, nota privada, aviso y cambio a open observados. Faltan audio, respuesta humana, silencio posterior del bot y devolución explícita. |
| Relay del canal | Configuración activa confirmada: ambos clientes usan el mismo relay HTTPS y clave limitada; los tokens de usuario y AgentBot permanecen exclusivamente en ASUS. Backend/worker reconstruidos saludables y preflight posterior completo, sin escrituras ni inferencia. Conversación de prueba: 200 con id/bandeja/estado/`can_reply`, sin binding supuesto. Probes de alcance: bandeja autorizada 200, otra bandeja/cuenta 403 y sin clave 401. Conserva el actor bot y no expone historial. |
| Plantilla de prueba | Verificada mediante `sync_templates` real de Chatwoot: `recordatorio_factura_demo` / `es` / `APPROVED` / `UTILITY`. El `.env` privado ya usa esta plantilla principal. `hello_world` / `en_US` queda como respaldo. Sincronización y aprobación confirmadas; la plantilla del reintento llegó al usuario y figura delivered en Chatwoot. El recorrido de texto, pago y captura está revisado en esta actualización. |
| Langfuse | Tres generaciones reales de audio/visión leídas por API; UI autenticada con trazas de conversación, herramienta y modelo, tokens, coste estimado y errores. Captura conservada como evidencia privada, sin publicarla. La evidencia histórica fue de metadatos, sin prompts ni respuestas completas. El usuario autorizó después captura privada completa y assets de audio/imagen; 303 pruebas incluyen su validación determinista. La captura desplegada se leyó por API y UI con una llamada real y dos archivos ficticios cargados. Se leyeron trece turnos reales recientes, incluida imagen y verificación financiera; los defectos del nombre de manage_identity y correlación del handoff se corrigieron con dos regresiones. Las trazas históricas no cambian. Faltan las variantes pendientes del recorrido. |
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

Este apartado conserva también observaciones históricas de coste y validación
de medios. El estado más reciente del entorno y sus recorridos está en las
revisiones fechadas al comienzo; los importes de smokes anteriores no representan
el saldo disponible actual. Las limitaciones estructurales siguientes se mantienen
mientras no exista evidencia posterior que las resuelva.

Las dos bases no comparten transacción distribuida. El reset mantiene etapas y estado de mantenimiento para reanudar un fallo; no afirma completarse mientras una etapa esté pendiente. El cursor de eventos centrales serializa publicación hasta commit para evitar perder eventos por orden de confirmación.

La consulta de control `pending` y el envío HTTP a Chatwoot son operaciones separadas; las protecciones locales no eliminan una carrera externa sin evidencia de la instalación. Un envío incierto no se repite a ciegas.

Las pruebas de medios validan URL, DNS, IP pública fijada, Host/SNI, redirecciones, cookies, tamaño, magic/MIME y duración. La interpretación de audio e imagen por los proveedores se comprobó por separado; la descarga TLS de medios del canal y su cierre financiero conversacional siguen pendientes. WebM se rechaza si falta `ffprobe` o no se valida duración/audio único. El corte local de USD 4,50 conserva margen frente a USD 5, pero no sustituye la facturación del proveedor ni borra consumos anteriores.

La tarifa local `openai-2026-11-01-cache-v2` separa entrada normal, lectura de caché y escritura de 30 minutos (esta última, 1,25× la entrada normal). Se aplicó un ajuste conservador idempotente de **USD 0,0017003** a los registros anteriores. El saldo local protegido previo al último smoke era **USD 0,0110414647**; el smoke posterior terminó `completed/settled` con 28 tokens de entrada, 5 de salida, caché cero y **USD 0,0000116 estimados** adicionales. Son estimaciones del ledger local, no factura del proveedor.
