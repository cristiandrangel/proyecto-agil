# Modelo de datos y estados

**Estado:** diseño; las tablas y migraciones se crean en implementación.
IDs propios UUID, IDs del canal opacos, timestamps UTC y presentación America/Bogota.
Importes en centavos enteros, currency=USD fijo; sin float ni conversión de moneda.

## Propiedad de datos

- PostgreSQL de cartera: clientes, deudas, identidad autorizada y todos los efectos
  financieros. Solo la API central escribe; backend sin conexión directa a esta base.
- PostgreSQL de memoria: tablas operativas del backend y checkpoints LangGraph
  separados. No es réplica autoritativa del saldo.
- Langfuse: almacenes propios, separados de ambas bases de aplicación.

## Cómo leer el modelo

La pantalla central muestra **una fila por deuda de un servicio de una persona**.
Eso no obliga a repetir los datos personales en la base: `customer` guarda la persona
y `debt` guarda cada deuda. La pantalla combina ambas tablas.

El recorrido principal es: **cliente → deuda → orden de pago → intento → liquidación**.
Si se negocia un descuento, también interviene un **acuerdo**. Crear una orden o aceptar
un acuerdo todavía no modifica el saldo; el pago aprobado y aplicado sí lo hace.

### 1. Cartera y pagos: relaciones principales

En este diagrama, la pata de tres puntas significa «varios» y el círculo significa
«opcional». Por ejemplo, un cliente puede tener varias deudas y una deuda puede no
tener todavía ninguna orden de pago. Se muestran solo los campos principales;
el catálogo posterior conserva el detalle completo.

```mermaid
erDiagram
    CUSTOMER ||--o{ DEBT : "tiene por servicio"
    DEBT ||--o{ AGREEMENT : "puede negociar"
    DEBT ||--o{ PAYMENT_ORDER : "puede generar"
    AGREEMENT o|--o{ PAYMENT_ORDER : "descuento opcional"
    PAYMENT_ORDER ||--o{ PAYMENT_ATTEMPT : "recibe intentos"
    DEBT ||--o| SETTLEMENT : "se liquida una vez"
    PAYMENT_ORDER ||--o| SETTLEMENT : "produce al aplicarse"
    PAYMENT_ATTEMPT ||--o| SETTLEMENT : "origina si se aplica"

    CUSTOMER {
        uuid id PK
        string document_type "Tipo de identificacion"
        string document_number "Numero de identificacion"
        string display_name "Nombre"
        string phone_e164 "Celular editable del evaluador"
        string email
    }
    DEBT {
        uuid id PK
        uuid customer_id FK
        string service_type "Hogar, telefonia, television"
        int balance_cents "Saldo en centavos USD"
        int dias_mora "Campo editable para filtrar"
        string debt_status "Pendiente o liquidada"
    }
    AGREEMENT {
        uuid id PK
        uuid debt_id FK
        int base_cents "Saldo al negociar"
        int offer_cents "Importe ofrecido"
        int expected_discount_cents "Condonacion prevista"
        string status "Propuesto, aceptado, cumplido, vencido"
    }
    PAYMENT_ORDER {
        uuid id PK
        uuid debt_id FK
        uuid agreement_id FK "Opcional para pago con descuento"
        int payable_cents "Importe del enlace de pago"
        int discount_cents "Descuento autorizado"
        string status "Vigente, pagada, vencida"
    }
    PAYMENT_ATTEMPT {
        uuid id PK
        uuid order_id FK
        string decision "Aprobado o rechazado"
        boolean applied "Si tuvo efecto financiero"
    }
    SETTLEMENT {
        uuid id PK
        uuid debt_id FK, UK
        uuid order_id FK, UK
        uuid attempt_id FK
        int received_cents "Dinero recibido"
        int forgiven_cents "Dinero condonado"
    }
```

- **Cliente (`customer`):** identidad y contacto compartidos por todas sus deudas.
  La combinación tipo/número de documento es única; el UUID es la llave interna.
- **Deuda (`debt`):** servicio, saldo y días de mora de esa fila. Tener varias deudas
  no implica enviar varios mensajes iniciales en una campaña.
- **Acuerdo (`agreement`):** registra la oferta y su aceptación. El descuento automático
  permite pagar desde el 80% hasta menos del 100% del saldo; una oferta inferior se escala.
- **Orden (`payment_order`):** contiene lo que se puede pagar mediante un enlace y hasta
  cuándo. El pago total tiene descuento cero y no necesita acuerdo.
- **Intento (`payment_attempt`):** registra cada aprobación o rechazo del simulador.
  Un rechazo no modifica la deuda; se puede volver a intentar mientras la orden siga vigente.
- **Liquidación (`settlement`):** registra el resultado financiero aplicado: recibido y
  condonado. Solo puede existir una por deuda y una por orden en este alcance, sin abonos.

Los campos `customer_id` que también aparecen en acuerdos y órdenes en el catálogo
sirven para validar pertenencia; siempre deben corresponder al dueño de la deuda.
La sesión de identidad y las tablas auxiliares de eventos y comandos se detallan más
abajo: no son nuevas deudas ni pagos.

### 2. Ejemplo: una persona, dos servicios

Ejemplo ficticio en USD: la persona tiene una deuda de hogar de 100 y otra de telefonía
de 60. Acepta pagar 90 por hogar. La condonación de 10 se aplica únicamente cuando se
aprueba y registra el pago. La deuda de telefonía sigue pendiente por 60.

```mermaid
flowchart LR
    C["Cliente ficticio<br/>Una identidad y un celular"]
    H["Deuda hogar<br/>USD 100 · 45 dias de mora"]
    T["Deuda telefonia<br/>USD 60 · 75 dias de mora"]
    A["Acuerdo aceptado<br/>Pagar 90 · condonar 10"]
    O["Orden de pago<br/>Enlace por USD 90"]
    P["Intento aprobado y aplicado"]
    S["Liquidacion<br/>Recibido 90 · condonado 10<br/>Saldo hogar = 0"]
    C --> H
    C --> T
    H --> A --> O --> P --> S
```

Una captura del comprobante ayuda al agente a interpretar lo que dice el usuario.
Para confirmarlo debe consultar la orden y su liquidación en la central; la imagen
por sí sola no cambia ninguno de estos registros.

### 3. Campañas: una persona, un mensaje inicial

Estas tablas viven en la base operativa del backend. Los UUID de clientes y deudas
son referencias a la central mediante su API, **sin claves foráneas entre bases**.

```mermaid
erDiagram
    CAMPAIGN ||--o{ CAMPAIGN_RECIPIENT : "selecciona personas"
    CAMPAIGN o|--o{ BUSINESS_EVENT : "atribuye resultados"

    CAMPAIGN {
        uuid id PK
        json filter_snapshot "Filtros de servicio, mora y cliente"
        json template_snapshot "Plantilla seleccionada"
        string status "Borrador, en ejecucion, completada, cerrada"
        datetime followup_until "Corte de seguimiento"
    }
    CAMPAIGN_RECIPIENT {
        uuid id PK
        uuid campaign_id FK
        uuid customer_id "Referencia a la central"
        json selected_debt_ids "Deudas incluidas en el segmento"
        int position "Orden del envio secuencial"
        string delivery_mode "Simulated o live"
        string send_status "Resultado del envio"
    }
    BUSINESS_EVENT {
        uuid id PK
        string source_key UK "Evita contar el mismo evento dos veces"
        uuid campaign_id FK "Opcional"
        uuid customer_id "Referencia a la central"
        uuid debt_id "Referencia opcional a la central"
        string event_type "Respuesta, pago, acuerdo, escalamiento"
        datetime occurred_at
    }
```

Una campaña puede seleccionar varias deudas de una persona, pero crea **un solo
destinatario por persona**: la combinación `campaign_id + customer_id` es única.
`position` permite recorrerlos uno a uno y retomar el progreso. Los contactos ficticios
se simulan; el del evaluador, habilitado en modo `live`, usa el canal real. Los eventos
permiten calcular contactabilidad y resultados sin contar dos veces el mismo hecho.

### 4. Dónde viven los demás datos

Las flechas siguientes representan intercambios o procesamiento, no claves foráneas.
`conversation_key` identifica la conversación de Chatwoot: no supone una nueva tabla
propia llamada «conversación».

```mermaid
flowchart TB
    CW["Chatwoot externo<br/>Conversacion, mensajes y control pending/open"]
    subgraph CENTRAL["PostgreSQL de cartera · autoridad del saldo"]
        FIN["customer · debt · agreement<br/>payment_order · payment_attempt · settlement"]
        AUTH["identity_session<br/>Validacion de identidad y caducidad"]
        AUX["command_result · central_event<br/>Evitar efectos duplicados y publicar cambios"]
    end
    API["API central<br/>Unico acceso del agente a cartera y pagos"]
    subgraph MEMORY["PostgreSQL operativo y de memoria"]
        CHANNEL["channel_binding · inbox_event · conversation_job<br/>Vincular contacto, recibir y procesar mensajes"]
        CONTEXT["verified_context · checkpoints LangGraph<br/>Identidad validada y memoria del agente"]
        OUTPUT["outbox · human_case<br/>Respuestas pendientes y casos humanos"]
        CAMPAIGNS["campaign · campaign_recipient · business_event<br/>Campanas, progreso y metricas"]
        CONTROL["inference_reservation · central_cursor<br/>Control de gasto y conciliacion de cambios"]
    end
    LF["Langfuse · almacenes propios<br/>Trazas de ejecucion e inferencia"]
    CW --> CHANNEL --> CONTEXT --> OUTPUT --> CW
    CONTEXT -->|"Consulta o comando autorizado"| API
    API --> FIN
    API --> AUTH
    API --> AUX
    API -->|"Eventos de cambios"| CONTROL
    CONTROL --> CAMPAIGNS
    CAMPAIGNS -->|"Despacho secuencial"| OUTPUT
    CONTEXT -.->|"Observabilidad sin secretos"| LF
```

La separación evita que la memoria conversacional se convierta en otra versión del
saldo. El agente puede recordar que alguien dijo «ya pagué», pero solo la central
confirma el pago. Todos los componentes propios siguen en la única EC2 prevista;
la separación del dibujo es entre responsabilidades y bases de datos.

## Sistema central simulado

| Entidad | Campos esenciales | Restricciones y relación |
|---|---|---|
| customer | id, document_type, document_number, display_name, phone_e164, email, customer_type, pin_hash, delivery_mode, test_contact_enabled, contact_version | Documento ficticio único por tipo/número; PIN de fixture se almacena como hash y no se devuelve; delivery_mode simulated por defecto o live para el evaluador; editar teléfono/modo incrementa versión |
| debt | id, customer_id, contract_reference, service_type, original_cents, balance_cents, due_date, dias_mora, debt_status, service_status, version | Cliente con varias deudas; mora entero no negativo; balance >= 0; pendiente con saldo > 0 y liquidada con cero |
| identity_session | id, customer_id, channel_key, token_hash, expires_at, failed_attempts, locked_until | Sin grant válido no se revela cartera; PIN no forma parte de la sesión ni de checkpoints; intentos vinculados también al mensaje para no duplicar por retry |
| agreement | id, customer_id, debt_id, debt_version, base_cents, offer_cents, expected_discount_cents, quoted_at, source_message_id, accepted_at opcional, expires_at, status | Oferta positiva e inferior al saldo; oferta * 100 >= base * 80; descuento previsto no equivale a condonación aplicada |
| payment_order | id, customer_id, debt_id, agreement_id opcional, base_version, base_cents, payable_cents, discount_cents, token_nonce, expires_at, receipt_expires_at, status, idempotency_key | Importe y descuento server-side; status vigente/pagada/vencida; token opaco firmado, derivable al repetir creación, no guardado en logs |
| payment_attempt | id, order_id, decision, applied, created_at, idempotency_key | Aprobado o rechazado; applied indica efecto durable; mismo comando devuelve mismo resultado |
| settlement | id, debt_id, order_id, attempt_id, received_cents, forgiven_cents, applied_at | Único por deuda y orden; recibido + condonado = saldo base; se crea en la transacción que deja balance cero |
| central_event | id, sequence, event_type, customer_id, debt_id, order_id, payload mínimo, created_at | Secuencia creciente; efectos financieros y de contacto publicados durablemente para conciliación del backend |
| command_result | idempotency_key, command_type, request_digest, result_reference, created_at | Misma clave con cuerpo distinto = conflicto; resultado por referencia, sin PIN o secretos en claro |

La fila visible de central es una proyección customer + debt: al editar nombre o
contacto se cambia customer, mientras saldo, servicio y mora pertenecen a debt.
La edición financiera de fixtures solo se permite en modo demo y registra un ajuste
explícito; nunca se presenta como pago recibido ni acuerdo. No se permite tocar una
deuda con orden vigente sin invalidarla y aumentar su versión. Una deuda liquidada
se restaura únicamente mediante reset documentado del escenario.

### Aplicación financiera atómica

1. Recuperar resultado si idempotency_key existe y su digest coincide.
2. Bloquear deuda y orden en orden consistente; validar dueño, versión, vigencia y saldo.
3. Registrar intento y settlement aprobados, pago y condonación, actualizar debt y order,
   marcar agreement cumplido si existe, e insertar central_event en una transacción.
4. Confirmar commit antes de mostrar comprobante. Otro aprobador no puede crear un
   segundo settlement. Ante resultado incierto se consulta por referencia.
5. Un rechazo crea intento sin modificar saldo, orden vigente ni descuento; permite
   otro intento con otra clave mientras la orden no venza.

## Backend: operación y memoria

El esquema del estado del agente y la selección de historial se detallan en
[Estado, memoria y contexto](agent-state.md). Sus variables no crean tablas nuevas:
AsyncPostgresSaver administra los checkpoints; las tablas siguientes guardan
operación, permisos y efectos externos.

| Entidad | Campos esenciales | Restricciones y relación |
|---|---|---|
| campaign | id, filter_snapshot, template_snapshot, created_at, launched_at, closed_at, followup_until, status, launch_key | Draft/running/completed/closed; una campaña activa por persona; segmento conservado para métricas |
| campaign_recipient | id, campaign_id, customer_id, selected_debt_ids, contact_version, position, delivery_mode, destination_binding, conversation_key, send_status | Único (campaign_id, customer_id); posición estable; simulated/sent/failed/uncertain/skipped separados; un mensaje inicial; no usar binding de otra versión del teléfono |
| channel_binding | customer_id, contact_version, account_id, inbox_id, contact_id, source_id, conversation_id | Source_id opaco del inbox correcto; editar contacto invalida vinculación; resolver antes de envío |
| inbox_event | id, account_id, inbox_id, message_id, conversation_id, sender_key, normalized_content, attachments, received_at, status | Unique (account_id, message_id); sin PIN ni payload de credenciales; tipos privados/salidas no generan turno |
| conversation_job | id, event_id, conversation_key, state, attempts, next_attempt_at, last_error | Un trabajo por evento; orden por received_at e id; ejecución bajo lock de conversación |
| verified_context | conversation_key, customer_id, central_grant, expires_at, selected_debt_id | Grant privado solo para adaptador central; no se serializa al modelo o trazas; independiente del checkpoint |
| outbox | id, operation_key, conversation_key, kind, payload_privado, state, channel_message_id, attempts | Unique operation_key; queued/sent/uncertain/cancelled/failed; uncertain no provoca reenvío ciego |
| human_case | id, conversation_key, source_event_id, customer_id, debt_id, reason, origin, offer_cents, verification_summary, status | Clave única por evento/origen; cliente/regla/incidencia; open/closed; nota y cambio Chatwoot reintentables por separado |
| business_event | id, source_key, event_type, campaign_id opcional, customer_id, debt_id opcional, conversation_key, occurred_at | Unique source_key evita duplicar canal o central; evento conserva su origen y significado |
| inference_reservation | id, turn_id, modality, model, price_version, reserved_usd, actual_usd, state, provider_response_id | Decimal para USD de inferencia; reserved/settled/uncertain; reservas atómicas comunes a workers |
| central_cursor | consumer, last_sequence | Avanza al guardar eventos conciliados; no perder pago por respuesta HTTP perdida |
| LangGraph checkpoints | thread_id, checkpoints y writes administrados por AsyncPostgresSaver | Thread = epoch/cuenta/inbox/conversación; no duplicar schema manualmente; setup explícito |

Los grants y la outbox son datos privados operativos del servidor, nunca archivos
versionados ni entradas del modelo. Los mensajes PIN se verifican antes de escribir
texto del evento; se conserva resultado de identidad, no el PIN original.

## Estados independientes

```mermaid
stateDiagram-v2
    state Deuda {
        [*] --> Pendiente
        Pendiente --> Pendiente: Crear orden o aceptar acuerdo
        Pendiente --> Liquidada: Aplicar pago y condonación autorizada
        Liquidada --> Liquidada: Consultar o repetir comando
    }
    state Acuerdo {
        [*] --> Propuesto
        Propuesto --> Aceptado: Confirmación en mensaje posterior
        Propuesto --> Vencido: Caduca sin aceptación
        Aceptado --> Cumplido: Pago aplicado
        Aceptado --> Vencido: Expira sin pago
    }
```

La conversación tiene control externo: pending permite bot, open implica humano;
fuera de pending no se negocia. No se deduce control a partir de una orden o deuda.
Sesiones, acuerdos y órdenes tienen caducidad propia.

## Métricas y atribución

- Progreso: destinatarios procesados/total, simulados y pendientes del lote.
- Simulados: destinatarios ficticios recorridos sin llamadas externas; no son enviados
  ni entregados reales y quedan fuera de cohortes de respuesta y resultado comercial.
- Enviados: mensajes iniciales reales aceptados por el canal; fallos y entrega van aparte.
- Contactados: personas destinatarias con primera respuesta posterior al envío de
  esa campaña y antes de su corte. Un mensaje de preparación anterior no cuenta.
- Contactabilidad: contactados / personas enviadas; sin denominador se muestra N/A.
- Pagó total: settlement con forgiven_cents=0. Acuerdo: descuento aceptado con
  desglose pendiente/cumplido/vencido; dinero condonado solo tras settlement.
- Solicitud humana: origin=cliente; política e incidencia se cuentan por separado.
- Resultado actual por persona/campaña/deuda: pago total, acuerdo cumplido, humano
  activo, acuerdo pendiente, sin resultado al cierre o en gestión, en ese orden.
- Diferentes servicios pueden ocupar distintas categorías; la suma de personas por
  categoría no se presenta como total de personas únicas de campaña.
- Importe recuperado suma received_cents; condonación suma forgiven_cents; nunca
  se suman ambos como efectivo recuperado. Pagos ajenos al segmento no se atribuyen
  a esa campaña aunque el cliente los consulte en la misma conversación.

## Retención y restauración de demo

Datos de aplicación se conservan hasta reset explícito. Adjuntos temporales se
eliminan al terminar su preprocesamiento o al limpiar fallos; no se suben al repo.
El reset restaura solo clientes/deudas de demo, sesiones, conversaciones locales,
órdenes y eventos del escenario, coordinando ambos servicios. No borra gasto, claves
ni trazas reales del proveedor ni modifica el historial de Chatwoot. Nueva campaña
y nuevo epoch local evitan que webhooks antiguos se apliquen al escenario restaurado.
