# Relay del canal de prueba

Se despliega junto al Chatwoot del propietario, en su red Docker existente y sin
puertos publicados. El conector cloudflared existente apunta al mismo servicio.
No entregar su `.env` al evaluador ni incluirlo en el contexto de construcción.

El servidor conserva `CHATWOOT_UPSTREAM_API_TOKEN` (usuario de servicio) y
`CHATWOOT_UPSTREAM_BOT_TOKEN` (AgentBot). Los dos son secretos amplios de Chatwoot:
asignarlos a un inbox no garantiza que su API limite todas las operaciones a él.
`CHATWOOT_RELAY_ACCOUNT_ID` y `CHATWOOT_RELAY_INBOX_ID` fijan la frontera del relay;
no tienen valores predeterminados. La clave compartida debe ser distinta de ambos
tokens. El backend del evaluador recibe sólo esa clave en `CHATWOOT_API_TOKEN` y
`CHATWOOT_CONTACTS_API_TOKEN`, y el mismo origen HTTPS del relay en ambas URLs base.

La lista de operaciones permitidas comprende lectura del inbox, búsqueda exacta
E.164, preparación de contactos y sus bindings/conversaciones; consulta mínima de
una conversación; creación de conversación pendiente con binding existente exacto;
envío de texto, nota privada o plantilla aprobada sin parámetros dinámicos; y
cambio de estado exclusivamente a `open`. Todas las demás rutas se deniegan.
Las lecturas y contactos usan el usuario; las escrituras de conversaciones usan el
bot para conservar el actor y el comportamiento de transferencia. Las respuestas
no incluyen contenido de mensajes, historial, credenciales ni metadatos privados.

Antes de cada escritura se comprueba cuenta, inbox y contacto. Un contacto puede
conservar varios aliases del mismo inbox. Cuando Chatwoot omite `contact_inbox`
en la conversación, el relay también lo omite: no asigna un source supuesto. Si
lo incluye, se valida literalmente contra la vinculación persistida. Para crear
una conversación, el source canónico de `contactable_inboxes` debe ser único y
coincidir exactamente con una vinculación persistida del contacto e inbox.
Los envíos
requieren estado `pending`; el texto público también requiere `can_reply`.
Una plantilla aprobada permite iniciar comunicación fuera de la ventana de texto.
La revalidación y la escritura son llamadas HTTP separadas: los cambios de estado
hechos por operadores externos no forman una transacción con el relay.

Límites globales: 60 solicitudes/minuto en memoria, 10 intentos de crear contactos
por día y 100 intentos de enviar mensajes por día. Las cuotas diarias son separadas,
persisten en `relay_quota` y conservan intentos fallidos o inciertos. No se reintentan
POST automáticamente. Los contactos admiten cuerpos JSON de hasta 2 KiB; los
mensajes hasta 20.000 caracteres y 256 KiB de JSON, incluyendo escape Unicode.
No habilitar múltiples workers: la cuota por minuto y la serialización local usan
el proceso único configurado en el Dockerfile.

La imagen corre sin root, con filesystem de sólo lectura y sin access logs. La
construcción usa `requirements.lock` con hashes; `.dockerignore` excluye secretos,
DB, logs y cachés. Las pruebas de contrato usan exclusivamente HTTP simulado.
