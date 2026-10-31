# Decisiones investigadas

**Fecha:** 2026-10-31. **Contexto:** entrega 2026-11-02; decisiones del plan,
no evidencia de implementación ni acceso a las cuentas externas. Investigación
con documentación primaria; se verifican versiones y disponibilidad al construir.

## R-01. Backend y webs pequeñas

**Decisión:** Python 3.12, FastAPI, Pydantic, HTTPX, SQLAlchemy 2, psycopg 3 y
migraciones Alembic; HTML renderizado con Jinja2, CSS y JavaScript nativo. Un
servicio backend sirve la central y la página de pago; otro expone la API de
cartera simulada. Ambos usan imágenes propias y configuración por entorno.

**Motivo:** compartir lenguaje con LangGraph y evitar un build frontend adicional
para dos interfaces pequeñas. La frontera de cartera sigue siendo HTTP.
**Alternativas:** React/Vite y una API adicional de presentación; añaden herramientas
sin una necesidad funcional actual. No se convierte esta elección en una regla
permanente del producto. Dependencias exactas se fijarán en uv.lock al implementar.
[Plantillas en FastAPI](https://fastapi.tiangolo.com/advanced/templates/).

## R-02. Un nodo LangGraph y persistencia

**Decisión:** START → agent → END. El nodo encapsula un ciclo acotado de Responses
API, validación de herramientas y devolución de sus resultados. El preprocesamiento
de medios es anterior. AsyncPostgresSaver guarda estado por cuenta/inbox/conversación.

**Motivo:** reproduce el agente único solicitado. El límite del grafo no limita
el while dentro del nodo: se impone un máximo de cinco llamadas del agente por turno.
El checkpointer ordinario no confirma cada efecto interno; las herramientas mutantes
son idempotentes y tienen un registro propio independiente del checkpoint.
**Alternativas:** ToolNode y grafo multinodo; no corresponden al alcance solicitado.
[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api),
[memoria](https://docs.langchain.com/oss/python/langgraph/add-memory).

## R-03. Inferencia real con un proveedor

**Decisión:** SDK asíncrono oficial de OpenAI y Responses API; store=false y
contexto explícito persistido por nuestra aplicación. Valores iniciales del plan:
agente y visión gpt-5.6-luna; transcripción de archivos gpt-transcribe. Todos son
configurables; el preflight debe comprobar acceso real antes de la demo.

**Motivo:** la documentación actual describe texto, imagen y function calling en
Luna y transcripción de archivos en Transcribe. No se necesita otro proveedor.
**Alternativas:** los candidatos gpt-4.1-mini y gpt-4o-mini-transcribe aparecen
marcados como deprecated en la documentación consultada; no se eligen para una
integración nueva. Un modelo mayor solo se cambia explícitamente si la evaluación
lo justifica; no se hace fallback automático de mayor costo.
[Modelo de agente/visión](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
[transcripción](https://developers.openai.com/api/docs/models/gpt-transcribe),
[Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses),
[herramientas](https://developers.openai.com/api/docs/guides/function-calling).

## R-04. Presupuesto y límites de la demo

**Decisión:** ledger de gasto persistente con reservas atómicas para todas las
modalidades, máximo dos inferencias concurrentes y corte local conservador en
USD 4.50 frente al presupuesto total de USD 5. Reservar antes de cada solicitud,
liquidar con uso observado y conservar la reserva cuando se desconoce el resultado.
Desactivar reintentos automáticos del SDK y limitar los reintentos propios.
El reset de deudores nunca borra el ledger de consumo.

**Motivo:** un límite por proceso permite exceder el presupuesto con varios workers.
Precios de referencia consultados: Luna USD 0.20 entrada / 1.20 salida por millón
de tokens; Transcribe USD 0.0045/minuto. La tabla de precios debe versionarse y
considerar imágenes, caché, tokens de salida y reintentos. Ante modelo sin precio
configurado no se inicia inferencia. Límite de entrada 12 000 tokens, salida de
agente 800 y extracción visual 400; medios hasta 5 MiB y audio hasta 60 segundos.

**Alternativas:** confiar solo en avisos de facturación o en una API key. La
documentación distingue alertas y hard spend limits; estos últimos pueden aplicarse
con retraso. Configurarlos si la cuenta lo permite complementa el control local,
sin prometer un corte exacto de factura. Estimación y reservas son conservadoras;
el control y su conciliación requieren pruebas con el proveedor.
[Límites del proveedor](https://developers.openai.com/api/docs/guides/spend-limits),
[reservas por ejecución](https://developers.openai.com/cookbook/articles/per_run_spending_controller_responses_api).

## R-05. Propiedad financiera y concurrencia

**Decisión:** PostgreSQL de cartera es el único escritor de deuda, acuerdo, orden,
pago y condonación. El backend accede mediante HTTP; no conecta directamente a esa
base. Los importes se guardan en centavos enteros y USD fijo. El sistema central
bloquea la deuda, comprueba su versión y registra pago, ledger, descuento y saldo
en una transacción. Referencias únicas e idempotency keys impiden doble aplicación.

**Motivo:** conservar consistencia sin una transacción distribuida entre dos bases.
Una oferta usa O * 100 >= S * 80; no hay comparación binaria en coma flotante.
**Alternativas:** duplicar el saldo en memoria o hacer que el LLM lo calcule; ambas
se descartan como autoridad financiera.
[Locks PostgreSQL](https://www.postgresql.org/docs/current/explicit-locking.html).

## R-06. Cola duradera sin otro servicio propio

**Decisión:** tablas operativas en el PostgreSQL de memoria para recepción de
mensajes, outbox, campañas, sesiones y gasto; checkpoints en tablas separadas.
Worker del mismo backend, con dos slots iniciales y exclusión por conversación
mediante advisory lock de sesión en una conexión dedicada. La caída del proceso
libera el lock; estados y claves durables permiten reintentar sin repetir efectos.
No mantener una transacción financiera abierta durante inferencia o red.

**Motivo:** persistir antes de responder al webhook y sobrevivir a reinicios con
pocas dependencias propias. Orden por llegada persistida; no se procesan a la vez
dos turnos de la misma conversación. La deduplicación no depende solo del checkpoint.
**Alternativas:** cola en RAM pierde trabajo; SQS y un broker propio amplían el
alcance inicial. Redis de Langfuse no se comparte como cola de la aplicación.

## R-07. Chatwoot y control existente

**Decisión:** usar Application APIs y adaptador según versión instalada. Solo
mensaje entrante, público, de cuenta e inbox configurados inicia un turno. Dedupe
por account_id y message_id. Consultar estado al comenzar y justo antes de enviar;
solo pending autoriza respuesta. Registrar caso y nota privada y cambiar
explícitamente a open para handoff; el retorno a pending lo realiza el asesor.

**Motivo:** no confundir nota interna o salida del bot con entrada del cliente.
Un timeout de envío deja estado incierto: no se reenvía a ciegas. El protocolo de
consulta y envío no es una operación atómica; una transición externa que coincida
con el envío debe probarse en la instalación existente y registrarse como limitación.
No depender de conversation_status_changed si el AgentBot instalado no lo entrega.
**Alternativas:** responder siempre, basarse solo en memoria o reconstruir Chatwoot;
se descartan por pérdida de control o alcance.
[AgentBots](https://chatwoot.help/hc/user-guide/articles/1677497472-how-to-use-agent-bots),
[mensajes](https://developers.chatwoot.com/api-reference/messages/create-new-message),
[conversación](https://developers.chatwoot.com/api-reference/conversations/conversation-details),
[cambio de estado](https://developers.chatwoot.com/api-reference/conversations/toggle-status).

## R-08. Webhook y adjuntos

**Decisión:** verificar firma HMAC sobre timestamp y bytes originales cuando la
instalación la emita; tolerancia configurable de cinco minutos y deduplicación
persistente. El preflight verifica versión y cabeceras reales: no se presupone
soporte por leer documentación actual. Si no firma, se requiere configurar un
relay autenticado antes de exponer la entrada del bot, sin aceptar eventos anónimos.
El modo local de mensajes simulados es independiente y está desactivado en público.

Las descargas validan hosts y cada redirección, tamaño, tipo real y tiempo; nunca
reenvían una credencial a otro host. Audio se transcribe; imagen produce texto y
referencias no verificados. El PIN en un turno de verificación se intercepta antes
de inferencia, checkpoint o traza. Documentos ficticios y PIN permiten el fallback
sin teléfono; BSUID no se convierte en número.
[Webhooks](https://www.chatwoot.com/hc/user-guide/articles/1677693021-how-to-use-webhooks),
[código AgentBot](https://raw.githubusercontent.com/chatwoot/chatwoot/develop/app/jobs/agent_bots/webhook_job.rb),
[BSUID](https://www.chatwoot.com/hc/user-guide/articles/1788437540-bsuid).

## R-09. Campañas y métricas

**Decisión:** un destinatario por persona y campaña, conservando la lista de deudas
seleccionadas y el segmento del lanzamiento. Despacho secuencial con un solo slot
de campaña y progreso persistente, independiente de la concurrencia conversacional.
Los fixtures se procesan mediante simulación sin invocar canal ni LLM; solo el
contacto live habilitado del evaluador recibe la plantilla real. No se mezclan
simulaciones con métricas reales. Revalidar al enviar. El backend resuelve
contacto y conversación del inbox, sin fabricar source_id. La plantilla inicial
es transaccional y preaprobada; se registra categoría e idioma reales.

**Motivo:** contactabilidad divide personas que responden entre personas enviadas;
no entre mensajes. Aceptación no equivale a entrega. Solicitud humana y pago posterior
pueden coexistir como hitos; los resultados financieros se calculan por deuda.
**Alternativas:** sumar mensajes o estados superpuestos como personas distintas;
se descartan. Utility es la intención de categoría, no una garantía de aprobación
o de alcance. La política del canal sigue pendiente para uso productivo.
[Plantillas](https://www.chatwoot.com/hc/user-guide/articles/1754940076-whatsapp-templates).

## R-10. Una EC2 y Langfuse completo

**Decisión:** Docker Compose con backend, worker, central, dos PostgreSQL propios,
proxy HTTPS y stack oficial compatible de Langfuse, con almacenes separados.
Persistencia en volúmenes sobre EBS. Logs y datos privados permanecen en volúmenes.
La versión de Langfuse y sus imágenes se fijan con la integración probada.

**Motivo:** flexibilidad para arrancar e iterar rápido. El dimensionamiento incluye
web/worker de Langfuse, PostgreSQL, ClickHouse, Redis y objetos; no se promete que
una instancia mínima baste. Se prueba ingestión y consulta de una traza completa.
**Alternativas:** distribuir en Fargate/RDS u otros servicios e IaC; son evolución
futura y no tareas obligatorias de esta entrega.
[EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html),
[Langfuse Compose](https://langfuse.com/self-hosting/deployment/docker-compose).

## R-11. Alcance local de Floci

**Decisión:** perfil local para comprobar APIs de infraestructura EC2, grupo de
seguridad y disco que soporte la versión fijada. Un script explícito apunta solo
al endpoint de Floci y usa credenciales ficticias. Se documentan operaciones y
resultados; el runtime de la demo es Compose, sin crear una segunda capa de
contenedores anidados como requisito.

**Motivo:** separar emulación de APIs, ejecución de aplicación y despliegue AWS real.
RunInstances en un emulador no prueba la red, EBS, kernel ni capacidad de una EC2
real. Si una operación no está cubierta se declara su límite, sin fingir éxito.
**Alternativas:** Terraform o reproducir toda AWS; fuera del alcance inicial.
[EC2 en Floci](https://floci.io/floci/services/ec2/).

## Pendientes operativos que no cambian este diseño

Hora de entrega; dominio y acceso HTTPS; token, cuenta, inbox, firma y versión
Chatwoot; plantilla aprobada; habilitación del destinatario; API key y acceso a
modelos OpenAI. Se verifican en preflight privado antes de demostrar integraciones.
La falta de una credencial no autoriza presentar un modo simulado como integración real.
