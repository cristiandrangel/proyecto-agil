# Despliegue de demo en una EC2

Estado: procedimiento preparado y Compose validado localmente. **No se ha creado
una EC2, montado un EBS real ni publicado un túnel con este procedimiento.** La
base acordada es una sola EC2; tamaño, región y costo se eligen al ejecutar.
El stack incluye backend, worker, central, dos PostgreSQL y los almacenes de
Langfuse. Una máquina mínima no se considera capacidad demostrada; medir RAM,
disco, CPU y latencia con el stack completo antes de elegir el tamaño definitivo.

## Referencia de coste y entrega emulada

Consulta de precios del 2 de noviembre de 2026: Linux/Unix On-Demand en
US East (Northern Virginia), según la [tabla oficial T3](https://aws.amazon.com/ec2/instance-types/t3/).
Los totales siguientes son cálculos con 730 horas/mes, sin descuentos ni impuestos.

| Instancia | vCPU / RAM | USD/hora | 10 horas | 730 horas |
|---|---|---|---|---|
| t3.large | 2 / 8 GiB | 0,0835 | 0,84 | 60,96 |
| t3.xlarge | 4 / 16 GiB | 0,1670 | 1,67 | 121,91 |
| t3.2xlarge | 8 / 32 GiB | 0,3341 | 3,34 | 243,89 |

Son precios de cómputo base; almacenamiento, tráfico, direcciones públicas y posibles
créditos de CPU adicionales se evalúan aparte. La [guía Compose de Langfuse](https://langfuse.com/self-hosting/deployment/docker-compose)
recomienda al menos 4 cores y 16 GiB para su despliegue en VM. t3.xlarge es por ello
un candidato inicial para medir la demo completa, no capacidad garantizada ni elección
aprobada para producción. Una medición puntual local de los doce contenedores observó
aproximadamente 2,7 GiB de memoria reportada por Docker; no prueba picos de arranque,
compilación, ingestión ni comportamiento bajo un límite de memoria menor.

Como referencia de [EBS gp3](https://aws.amazon.com/ebs/pricing/), a USD 0,08 por
GB-mes, 100 GB representan USD 8/mes adicionales. El cómputo On-Demand se factura
hasta detener o terminar la instancia; los volúmenes conservados siguen facturándose.
Las llamadas de IA y el canal se presupuestan por separado.

La emulación local prevista utiliza recursos del equipo evaluador y no contrata
una EC2 real. El objetivo discutido es ensayar el despliegue ejecutable del stack,
además del smoke de APIs ya existente. Aún no se implementó ni verificó ese arranque
dentro de una instancia emulada; no presentarlo como resultado ya conseguido.

## Preparar el host y la persistencia

Crear manualmente una EC2 Linux con Docker Engine y Compose v2 instalados; comprobar
`docker version` y `docker compose version`. Seguir la instalación oficial de
[Docker para Ubuntu](https://docs.docker.com/engine/install/ubuntu/) si se usa esa
distribución. El usuario de operación debe poder usar Docker.

Usar EBS cifrado para los datos persistentes. Se recomienda un volumen de datos
independiente del disco de sistema, con conservación al terminar la instancia.
La capacidad se dimensiona después de medir PostgreSQL, ClickHouse y objetos.
El grupo de seguridad necesita acceso administrativo restringido; con Cloudflare
Tunnel no hace falta abrir los puertos de aplicación a Internet. PostgreSQL,
central, Floci, ClickHouse y Redis permanecen internos. Las interfaces locales de
Langfuse/MinIO se consultan mediante SSH, sin publicarlas en el túnel de cobranza.

Adjuntar el EBS a la misma zona de disponibilidad. Identificar el dispositivo con
`lsblk -f` y `sudo file -s /dev/DISPOSITIVO`; los nombres NVMe pueden diferir del
nombre solicitado al adjuntar. **Formatear únicamente un volumen nuevo vacío**;
uno restaurado desde snapshot conserva su filesystem. Montarlo en
`/srv/proyecto-agil/data`, y registrar su UUID en `/etc/fstab`. La guía oficial de
[EBS en Linux](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-using-volumes.html)
detalla identificación, montaje y persistencia tras reinicio.

Antes de crear directorios o arrancar contenedores:

```bash
mountpoint -q /srv/proyecto-agil/data
findmnt /srv/proyecto-agil/data
sudo install -d /srv/proyecto-agil/data/central /srv/proyecto-agil/data/memory
sudo install -d /srv/proyecto-agil/data/langfuse-postgres /srv/proyecto-agil/data/redis
sudo install -d -o 101 -g 101 /srv/proyecto-agil/data/clickhouse /srv/proyecto-agil/data/clickhouse-logs
sudo install -d -o 65532 -g 65532 /srv/proyecto-agil/data/minio
```

Los UID 101 de ClickHouse y 65532 de MinIO corresponden a las imágenes fijadas;
revisarlos al actualizar imágenes. PostgreSQL y Redis preparan sus permisos desde
sus entrypoints. Configurar una dependencia de montaje para Docker, para no
arrancar sobre un directorio vacío del disco de sistema si EBS no está montado:
crear `/etc/systemd/system/docker.service.d/agil-storage.conf` con:

```ini
[Unit]
RequiresMountsFor=/srv/proyecto-agil/data
```

Aplicar `sudo systemctl daemon-reload`; planificar el reinicio de Docker si ya
está ejecutando otros contenedores. Comprobar el montaje después de reiniciar el
host. El override usa volúmenes Docker de tipo bind bajo ese filesystem y limita
los logs a tres archivos de 10 MiB por contenedor.

## Arranque limpio para un evaluador

Clonar este repositorio público en el host. Copiar `.env.example` a `.env`, completar
secretos propios y ejecutar `chmod 600 .env`. No copiar la base de trabajo del
propietario, dumps, historial de conversaciones ni sus credenciales. El evaluador
puede usar sus propias claves de OpenAI y Chatwoot; todos los clientes ficticios
empiezan en modo `simulated`, y habilita su propio contacto desde la central.
Una instalación vacía no demuestra que una clave compartida tenga USD 5 disponibles:
el límite local sólo conoce el consumo registrado por este despliegue.

Valores públicos para este perfil:

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://cobranza.agenx-dev-test.work
ENABLE_LOCAL_MESSAGE_ENDPOINT=false
AGIL_DATA_ROOT=/srv/proyecto-agil/data
```

La `.env` real también debe contener el resto de `.env.example`. Conservar
`DEMO_MODE=true` para el simulador de pagos y la edición de fixtures. La entrada
local de mensajes queda deshabilitada en producción. Mantener la URL pública igual
en backend y worker: participa en formularios, origen/CSRF y enlaces de pago.

Desde la raíz del checkout, siempre usar **los dos** archivos Compose:

```bash
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.ec2.yaml config --quiet
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.ec2.yaml up -d --build
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.ec2.yaml ps
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.ec2.yaml exec backend python -m scripts.seed
curl --fail http://127.0.0.1:8080/health
curl --fail http://127.0.0.1:8080/ready
```

El bootstrap aplica migraciones y prepara los checkpoints. `seed` crea únicamente
fixtures públicos por la API autenticada de central. No garantiza conectividad de
WhatsApp ni llama a OpenAI. `ready` comprueba dependencias propias; los recorridos
externos requieren el opt-in y la evidencia descritos en
[quickstart](../specs/001-cobranza-whatsapp/quickstart.md).

## HTTPS y cambio de equipo

El conector `cloudflared` existe en Compose bajo el perfil `public` y consume
`CLOUDFLARE_TUNNEL_TOKEN` privado. Tener el archivo no inicia ningún túnel: el
perfil normal no ejecuta ese servicio. Configurar en Cloudflare el hostname
`cobranza.agenx-dev-test.work` con origen `http://backend:8000`, desde la red de
Compose. No apuntarlo a `localhost:8080` dentro del contenedor del conector.

Antes de mover el hostname entre PC y EC2, detener el conector del host anterior;
comprobar que no queda activo y después iniciar el siguiente:

```bash
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.ec2.yaml --profile public up -d cloudflared
```

Mantener **un solo conector activo** durante esta demo evita repartir webhooks y
solicitudes de pago entre dos bases divergentes. Verificar `/health`, login,
webhook y enlaces desde HTTPS una vez activo. El cambio de equipo y el dominio se
describen en [dominio-demo.md](dominio-demo.md); este procedimiento no crea túneles,
registros DNS ni recursos AWS automáticamente. El flujo sigue el modelo de
[túneles administrados con Docker](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/).

## Conservación, respaldo y restauración

Para una actualización rutinaria conservar el EBS y los volúmenes. No usar
`docker compose down -v` como reset. El reset de escenario mantiene consumo y
reservas inciertas, elimina memoria local y restaura fixtures mediante la API:

```bash
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.ec2.yaml exec backend python -m scripts.reset_demo --confirm RESET_DEMO
```

Ante fallo del reset, consultar `--status` y reanudar con el mismo `--operation-key`;
el mantenimiento persistido impide seguir usando un escenario a medio restaurar.
No borrar el ledger para desbloquear el presupuesto.

Para un respaldo consistente del **despliegue existente**, detener el conector y
todos los contenedores de ese proyecto, conservando los volúmenes; tomar un
snapshot EBS cifrado desde AWS y esperar a que termine. Guardar aparte el commit,
las imágenes fijadas, la configuración privada y las claves de cifrado/firma que
hagan falta para recuperar los datos. Restaurar ese snapshot en un EBS de la misma
zona de la nueva EC2, montarlo con el UUID correspondiente y arrancar el mismo
commit con los dos archivos Compose. Revisar migraciones, `/ready`, progreso de
colas/outbox, consumo e incertidumbres antes de reabrir el conector. Una respuesta
externa incierta se concilia; no se reenvía a ciegas.

El snapshot consistente conserva conjuntamente cartera, checkpoints, outbox,
reservas y Langfuse. Migrar un despliegue que comparte la misma clave de inferencia
exige conservar `inference_reservation`; iniciar otra memoria vacía pierde el
control de gasto previo. Un respaldo del propietario es privado y **no** se entrega
al evaluador como fixture. La recuperación real de EBS debe ensayarse en AWS; no se
marca aprobada por el smoke de Floci. Consultar la
[guía de snapshots EBS](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-creating-snapshot.html).

## Floci: alcance y comprobación local

El perfil separado fija la imagen oficial de Floci por digest de índice
`sha256:5ee85db604c4aa74ac76e07ea5cc83086f37bb472bf3dbb97e34019e48efae9c`,
verificado el 2026-11-01; la imagen reporta Floci 2.4.0. Se ejecuta sin socket Docker,
con `FLOCI_SERVICES_EC2_MOCK=true`; la API es real del emulador, pero las instancias
son registros simulados. La [documentación EC2 de Floci](https://floci.io/floci/services/ec2/)
explica esa diferencia entre modo mock y ejecución de contenedores invitados.

```bash
docker compose -p agil-floci-smoke -f infra/compose.floci.yaml --profile floci up -d floci
uv run python -m scripts.smoke_floci --endpoint http://127.0.0.1:4566
docker compose -p agil-floci-smoke -f infra/compose.floci.yaml --profile floci down
```

El endpoint es obligatorio en cada cliente SDK, y el runner sólo admite loopback o
el servicio Compose `floci`, con credenciales ficticias explícitas. Un endpoint AWS
se rechaza antes de abrir un cliente. El script crea recursos con identificador
propio y los limpia en orden inverso; no consume perfiles AWS del host.

Verificado localmente el 2026-11-01: zonas, VPC/subnet/grupo de seguridad,
Run/DescribeInstances, volumen gp3 cifrado, attach/detach y limpieza. El intento de
CreateSnapshot devuelve `UnsupportedOperation` en este perfil y el reporte lo
muestra como `unsupported`: resultado global `passed_with_limitations`, sin
atribuir una restauración exitosa. No se comprueban VM, filesystem, conectividad
real, IOPS, permisos AWS ni capacidad EC2. El perfil tampoco envía WhatsApp,
infiere con OpenAI ni conecta Cloudflare. El procedimiento de
[Docker Compose de Floci](https://floci.io/floci/configuration/docker-compose/)
sirve como referencia para ampliar futuras pruebas; no sustituye el ensayo real.
