# Aplicación en una instancia EC2 emulada

Este perfil ejecuta la aplicación completa y Langfuse dentro de un Linux invitado
creado mediante `RunInstances` de Floci 2.4.0. El invitado es un contenedor Linux
privilegiado con su propio Docker Engine; no es una VM con kernel independiente.
No crea recursos AWS ni requiere una cuenta AWS. El modo local empieza sin
proveedores; el modo de entrega conecta OpenAI, la bandeja TEST de Chatwoot y el
túnel mediante un archivo privado explícito. Ambos ejecutan el mismo stack en el
Docker del invitado.

## Capas y aislamiento

```text
Docker del equipo evaluador
└─ engine aislado (Docker-in-Docker, hasta 8 CPU / 24 GiB)
   ├─ Floci 2.4.0 (API EC2, estado propio)
   └─ Linux invitado creado por RunInstances (4 CPU / 16 GiB)
      └─ Docker Engine propio, socket Unix
         └─ Compose agil-ec2-fixture: aplicación y Langfuse
```

El daemon anfitrión sólo inicia el engine exterior. Floci recibe únicamente el
socket del engine exterior. El invitado no recibe sockets de otros daemons.
Los contenedores de aplicación pertenecen al Docker Engine del invitado; la
verificación comprueba que sus IDs no existen en los daemons anfitrión y exterior.
Los daemons anidados comparten el kernel Linux; `privileged` es un requisito de
este laboratorio, no una frontera de seguridad equivalente a una EC2 real.

Se usa el catálogo de imágenes personalizado soportado por Floci para resolver
`ami-agil-compose` a la imagen local construida desde Docker Official Image
`docker:29-dind` por digest. Su entrypoint inicia Docker y SSH en cada arranque.
Floci inyecta la clave pública SSH y ejecuta UserData, que verifica el daemon.
No se modifica el contenedor desde el anfitrión para añadir privilegios después.

En la imagen fijada, `t3.xlarge` no está en el catálogo completo de capacidades:
Floci acepta ese nombre pero no limita CPU/RAM. Este laboratorio solicita
`t2.xlarge` en x86_64 (4 vCPU/16 GiB) o `m6g.large` en ARM64 (2 vCPU/8 GiB),
ambos presentes en ese catálogo. El tipo se elige con la arquitectura del daemon
Docker, igual que la imagen, y se verifican sus límites reales Docker y cgroup. Es una elección para esta emulación; no dimensiona ni recomienda una
familia AWS de producción. El engine exterior tiene techo de 8 CPU (o las CPU disponibles si hay menos) y
24 GiB. Son límites máximos de cgroup: no se reservan ni se consumen 24 GiB al
arrancar. El invitado conserva los límites correspondientes a su tipo nativo.

## Requisitos y uso

El lanzador admite Docker Engine Linux y Docker Desktop con **Linux containers**,
en daemons **amd64 y arm64**. En macOS (Intel/Apple Silicon) y Linux se usa Bash;
en Windows se usa PowerShell o el wrapper `.cmd`. El equipo sólo necesita Docker
con Compose v2: Python, Git cliente y SSH del control-plane viven en el runner.
Puede usarse un checkout Git o el ZIP completo descargado de GitHub y extraído
en una carpeta local. Para ZIP, `infra/public-source-manifest.txt` enumera las
fuentes públicas transferibles; los archivos privados y los symlinks se excluyen
también si aparecen en esa lista. No admite una carpeta de un daemon remoto.

Validado aquí: entorno completo en Linux x86_64 con Docker Engine y arranque,
integraciones y conversación real en un segundo equipo Mac ARM64 con Docker
Desktop. No se acredita por ello todo el recorrido funcional de la Mac ni el
stack completo en Windows. La selección ARM es nativa (catálogo `arm64` e
imágenes multiarch), sin forzar emulación amd64.

El lanzador aprobó 50 comprobaciones en cada uno de PowerShell 5.1 y 7 sobre
Windows real: rutas, argumentos, rechazos y permisos NTFS. Docker se sustituyó
por un doble; sigue pendiente ejecutar allí el stack completo con Docker Desktop.
La regresión se repite con `./tests/infrastructure/windows-launcher.tests.ps1`
y se automatiza en el workflow de portabilidad Windows.

Preparación de Docker Desktop:

1. Iniciar Docker Desktop y seleccionar Linux containers. El contexto activo local
   se usa automáticamente; se admiten el socket Unix Desktop y el pipe Windows.
2. Tener al menos 4 CPU visibles para el conjunto de servicios. Como punto de partida
   se recomiendan 12 GiB o más de RAM para Docker; no es un mínimo medido. `doctor`
   informa la RAM visible y advierte si es inferior. El máximo exterior de 24 GiB
   no obliga a asignar esa cantidad. Hace falta medir picos con el recorrido real.
3. Dejar al menos 15 GiB libres en el checkout y espacio adicional en el disco de
   la VM Docker para imágenes/volúmenes. `doctor` mide el filesystem del checkout;
   revisar también el límite del disco virtual de Desktop.
4. Permitir el bind de la carpeta del checkout si Desktop solicita compartirla.
   Para Windows usar una carpeta NTFS local y el lanzador Windows, que protege el
   archivo de entrega y `.local/ec2-emulation` con ACL del usuario actual.
5. Permitir contenedores privilegiados y el acceso del runner al socket Docker.
   Si Enhanced Container Isolation o una política corporativa los bloquea, el
   administrador debe habilitar esta carga; el script no modifica esas políticas.
   Rootless Docker no está soportado. No hace falta activar host networking.
6. Mantener libres los puertos locales `2244`, `4567`, `13000`, `18080` y `19090`.
   Si otro servicio ocupa uno, Docker rechazará el bind; identificarlo antes de
   detenerlo y conservar sus datos. Usar una carpeta local fuera de unidades de
   red o sincronización evita que permisos o disponibilidad dependan de ellas.

`doctor` comprueba arquitectura del daemon, CPU, RAM visible, espacio libre del
checkout y modo rootless. No comprueba el espacio libre interno del disco virtual
de Desktop ni garantiza que un firewall, proxy o política corporativa permita
esta carga. El preflight verifica salud y accesos de las integraciones por lectura;
no demuestra entrega de WhatsApp ni una inferencia pagada. Si Meta no entrega la
plantilla, se puede iniciar el chat directamente con el número TEST y continuar.

Los ajustes de recursos y carpetas están en la
[guía oficial de Docker Desktop](https://docs.docker.com/desktop/settings-and-maintenance/settings/).
En Windows con WSL2 la asignación de memoria se gestiona mediante la configuración
WSL. ECI tiene [restricciones adicionales sobre sockets e imágenes locales](https://docs.docker.com/desktop/enterprise/hardened-desktop/enhanced-container-isolation/limitations/).

Desde la raíz del repositorio, Linux/macOS:

```bash
./emulate-ec2.sh doctor
./emulate-ec2.sh up
./emulate-ec2.sh status
./emulate-ec2.sh verify
./emulate-ec2.sh restart
```

Windows, desde PowerShell o CMD:

```powershell
.\emulate-ec2.cmd doctor
.\emulate-ec2.cmd up
.\emulate-ec2.cmd status
.\emulate-ec2.cmd verify
```

También puede ejecutarse `.\emulate-ec2.ps1` directamente si la política local
permite scripts; `.cmd` usa PowerShell con política limitada a ese proceso, sin
cambiar la configuración permanente del equipo. El wrapper acepta las mismas
acciones y argumentos que Bash. Las rutas con espacios se pasan entre comillas;
el archivo de entrega debe permanecer dentro del checkout. `--delivery-file` y
su ruta deben ser argumentos separados.

El runner usa `/workspace` como ruta interna y una red bridge dedicada. En Engine
resuelve el socket del contexto Unix activo; en Desktop usa el socket del daemon
Linux dentro de la VM, independiente del socket/pipe del cliente. Sólo para una
instalación local no estándar puede indicarse `EC2_DOCKER_SOCKET` (ruta del socket
visible para el daemon). No admite Docker remoto por TCP/SSH. No monta archivos
`/etc/passwd` ni `/etc/group` del equipo ni usa `--network host`.

### Entrega con todas las integraciones

Quien entrega prepara un archivo privado `.env.entrega`, con las claves acotadas,
el origen HTTPS, la configuración de TEST y los accesos de las tres interfaces.
Debe usar únicamente las variables permitidas por
`scripts/ec2_live_config.py`. No se entrega el `.env` de desarrollo ni sus bases.
La instalación nueva genera sus propios secretos de bases, sesión, pagos y
Langfuse; el archivo de entrega puede fijar los logins iniciales de central y
Langfuse antes de crear las bases.

```bash
chmod 600 .env.entrega
./emulate-ec2.sh up --delivery-file .env.entrega --public
```

En Windows el equivalente completo es:

```powershell
.\emulate-ec2.cmd up --delivery-file .env.entrega --public
```

El lanzador Windows ajusta el ACL antes de leer la entrega; no interpreta los
modos POSIX ficticios de un bind NTFS como protección. El entorno interno del
invitado sigue usando permisos 0600. El dominio HTTPS y Chatwoot siguen siendo
externos y requieren conectividad y credenciales del archivo privado; no se
crean cuentas, dominios ni bandejas nuevas. El modo fixture local sirve para
probar el arranque sin proveedores; la entrega completa usa el comando anterior.

El orden es crear el invitado, generar su entorno interno, aplicar la lista
permitida por stdin SSH, arrancar Compose y verificar salud. Después se ejecuta
un preflight de lectura de OpenAI, Chatwoot y Langfuse. Solo si pasa y se pidió
`--public`, se inicia el conector de ese invitado. No se envían campañas ni se
infieren mensajes al instalar. El dominio se entrega preparado y se conservan
sus parámetros; el evaluador no necesita coordinar cambios de DNS ni trasladar
datos de otra instalación.

Para reanudar la misma instalación:

```bash
./emulate-ec2.sh up --public
./emulate-ec2.sh preflight
./emulate-ec2.sh verify --mode live
./emulate-ec2.sh stop
```

`stop` detiene la instancia por EC2 y conserva almacenamiento y configuración.
`up` los recupera. Si el engine exterior ya existe con la red anterior, el
lanzador conecta la red de control mediante Docker API, sin recrear ese engine
ni cambiar su volumen. Después puede reemplazar sólo el contenedor de forwards
SSH; el conector público vive dentro del invitado. Esta transición está cubierta
por contratos de comandos, pero no se ejecutó sobre la demo activa durante la
adaptación de portabilidad. Los logins iniciales de Langfuse no se cambian sobrescribiendo
`INIT_*` después de inicializar sus volúmenes: el provisionamiento rechaza ese
cambio para evitar que el archivo muestre una contraseña que la base no usa.

Para habilitar integraciones en un laboratorio ya creado se separan preparación
y aplicación:

```bash
./emulate-ec2.sh configure-live --delivery-file .env.entrega
./emulate-ec2.sh apply-live
./emulate-ec2.sh up --public
```

`configure-live` valida la lista permitida, conserva secretos internos y escribe
el entorno privado de forma atómica. `apply-live` reconstruye backend/worker y
recrea Langfuse web para aplicar el puerto público de medios; no inicia el túnel.
No se aceptan claves internas de bases en el archivo de integraciones. El
presupuesto de una clave reutilizada debe descontar el consumo anterior antes de
iniciar otra base vacía; crear una instalación no renueva el crédito de OpenAI.

`up` crea el engine, arranca Floci, crea la instancia por EC2, transfiere solamente
fuentes públicas de Git o del manifiesto de la entrega ZIP y prepara un `.env` nuevo desde `.env.example` con secretos
internos aleatorios. Reintentar conserva ese entorno, volúmenes y datos. No lee ni
copia el `.env`, volúmenes ni conversaciones del propietario. El seed es
idempotente y contiene clientes ficticios con contactos simulados.

Las interfaces se publican sólo en loopback del equipo mediante un contenedor
SSH en bridge. Dentro de su red Docker el forward escucha en la interfaz del
contenedor; ningún puerto se publica en todas las interfaces del anfitrión:

- Central sin proveedores: [localhost:18080/central](http://localhost:18080/central).
- Langfuse: [localhost:13000](http://localhost:13000).
- MinIO para medios locales: `localhost:19090`.

Las credenciales nuevas están en `.local/ec2-emulation/evaluator.env`, ignorado
por Git y con permiso 0600. Los accesos web figuran al final del archivo. Estos
usuarios y contraseñas corresponden al entorno emulado. El archivo también
permanece dentro del invitado en `/srv/proyecto-agil/app/.env`.

La API Floci escucha en `127.0.0.1:4567` y SSH en `127.0.0.1:2244`. Son puertos
alternativos; el perfil no ocupa los puertos 8080/3000/4566 del entorno existente.
En modo local no se inicia `cloudflared` ni se toca DNS, Chatwoot o el túnel.
Con integraciones, la central se abre por el origen HTTPS exportado, no por el
puerto HTTP local. Langfuse permanece en `localhost:13000`; sus medios se sirven
desde `localhost:19090`, con firmas preservadas al subirlos a MinIO interno.

```bash
./emulate-ec2.sh close-access # Cierra sólo los forwards SSH
./emulate-ec2.sh access       # Reabre interfaces y actualiza el archivo privado
./emulate-ec2.sh cleanup      # Destruye exclusivamente TODO el fixture emulado
```

`cleanup` termina la instancia por EC2 y elimina el proyecto Compose exterior y
su volumen dedicado. Es destructivo para este laboratorio. No usa `docker prune`
ni comandos contra los volúmenes de otros proyectos.

## Prueba aislada de portabilidad

```bash
./emulate-ec2.sh smoke-portability
# Windows: .\emulate-ec2.cmd smoke-portability
./emulate-ec2.sh evals
```

`smoke-portability` crea red/contenedores/imagen con nombres únicos y puertos
loopback aleatorios, comprueba tres forwards SSH y los elimina al terminar. No
crea EC2, no lee `.env`/`.env.entrega`, no inicia cloudflared y no usa proveedores.
La prueba en runner comprueba bridge y configuración de publicaciones; en Linux
se verificaron además peticiones HTTP reales a los puertos loopback desde el
host. No sustituye la validación del stack completo en cada sistema operativo.
`evals` delega al backend del invitado existente; por defecto es offline. Las
opciones se transmiten como argumentos literales y las pruebas pagadas exigen
los flags explícitos documentados en [evals.md](evals.md).

## Qué comprueba la verificación

`verify` comprueba el estado EC2, los servicios saludables, `/health`, `/ready`,
salud de Langfuse, separación de los tres daemons, ausencia de socket exterior en
el invitado, límites efectivos y fixture limpio (13 clientes,14 deudas,
0 liquidaciones/campañas/inbox/outbox/reservas de inferencia). El modo `fixture`
exige esos conteos iniciales; el modo `live` permite campañas y pagos de prueba
existentes y registra sus conteos reales. El preflight de lectura y el recorrido
WhatsApp se comprueban por separado.

`restart` escribe un marcador en una tabla temporal de prueba de PostgreSQL,
detiene y vuelve a iniciar la instancia usando EC2, espera la recuperación de la
aplicación y confirma el mismo marcador. Después elimina la tabla de prueba.
No vuelve a sembrar datos ni regenera secretos durante esa prueba.

El reporte privado queda en `.local/ec2-emulation/verification.json`. Un perfil
arrancado no debe presentarse como verificado antes de completar ese reporte.

## Persistencia y límites

La adaptación Desktop se comprobó el 2026-11-02 mediante `doctor` real en el
runner, contratos de socket/rutas con espacios, claves NTFS simuladas, catálogo
ARM/CRLF y smoke aislado de bridge/SSH/puertos loopback en Linux amd64. La demo
existente no se recreó para esa comprobación. Posteriormente se confirmó el
arranque y la integración conversacional en Mac ARM64; la aceptación completa de
cada plataforma exige también su recorrido funcional y la prueba de persistencia.

Verificado el 2026-11-02 en Linux x86_64: once servicios saludables, fixtures
limpios y persistencia PostgreSQL después de EC2 Stop/Start. También pasó el
comando del evaluador `./emulate-ec2.sh up` al reanudar el mismo invitado,
conservando entorno y datos. El cgroup del invitado mostró `memory.max` de
17179869184 bytes y `cpu.max` de `400000 100000` (4 CPU); una lectura puntual
de `memory.current` fue aproximadamente 2,6 GiB. Esa lectura no es una medición
de picos ni una prueba de capacidad de producción.

Los datos pertenecen a los volúmenes del Docker invitado, almacenados dentro del
engine exterior dedicado. Sobreviven EC2 Stop/Start porque se conserva el mismo
contenedor invitado. Terminate/cleanup destruye este fixture: no hay garantía de
conservación de datos tras terminar la instancia. No se implementa un EBS real ni
se prueban cifrado, snapshots, IOPS, IAM, VPC/security groups efectivos, latencia,
créditos de CPU o capacidad de una instancia AWS. Security groups y block devices
se desactivan en este perfil; el acceso local se controla mediante SSH y loopback.

La [documentación EC2 oficial de Floci](https://floci.io/floci/services/ec2/)
explica el modelo de ejecución. La implementación se contrastó con el
[código exacto de la imagen fijada](https://github.com/floci-io/floci/blob/9be236e2890c2042a6bb819f1a9228be996acd90/src/main/java/io/github/hectorvent/floci/services/ec2/Ec2ContainerManager.java)
y su [catálogo de capacidades](https://github.com/floci-io/floci/blob/9be236e2890c2042a6bb819f1a9228be996acd90/src/main/resources/ec2/instance-type-catalog.yaml).
El procedimiento de [despliegue EC2 real](despliegue-ec2.md) sigue separado y
requiere una comprobación real antes de afirmar que está listo para producción.


## Recuperación avanzada de una restauración

La vía habitual es reintentar la misma restauración desde la central cuando
termine el trabajo activo. Para inspeccionarla por terminal, con un cliente
OpenSSH disponible en el equipo de la demo:

```bash
ssh -i .local/ec2-emulation/id_ed25519 -p 2244 -o UserKnownHostsFile=.local/ec2-emulation/known_hosts root@127.0.0.1
cd /srv/proyecto-agil/app
```

Dentro del invitado:

```bash
docker compose -p agil-ec2-fixture --env-file .env -f infra/compose.yaml exec backend python -m scripts.reset_demo --status
docker compose -p agil-ec2-fixture --env-file .env -f infra/compose.yaml exec backend python -m scripts.reset_demo --confirm RESET_DEMO --operation-key UUID_DE_LA_OPERACION
```

Conserva la misma clave de operación; no ejecutes esto contra el Compose de
desarrollo del anfitrión. El reset tiene etapas persistentes porque las dos
bases no comparten una transacción distribuida. No borres volúmenes para
resolver un error de restauración.
