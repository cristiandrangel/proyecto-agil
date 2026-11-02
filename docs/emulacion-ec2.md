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
└─ engine aislado (Docker-in-Docker, 8 CPU / 24 GiB)
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
`t2.xlarge`, cuyo catálogo sí tiene 4 vCPU/16 GiB, y verifica los límites reales
Docker. Es una elección para esta emulación; no dimensiona ni recomienda una
familia AWS de producción. El engine exterior está limitado a 8 CPU/24 GiB.

## Requisitos y uso

Probado en Linux x86_64 con Docker Engine, Docker Compose y Bash. Se necesita
virtualización de contenedores privilegiados y acceso a Internet para imágenes y
paquetes oficiales. Reservar al menos 24 GiB de RAM disponibles y 15 GiB de disco
libres; la descarga y compilación consumen espacio adicional según la caché.
No se borra caché ni recursos ajenos. No se garantiza Docker Desktop, macOS,
Windows, rootless Docker ni ARM sin ensayo específico.

Desde la raíz del repositorio:

```bash
./emulate-ec2.sh up
./emulate-ec2.sh status
./emulate-ec2.sh verify
./emulate-ec2.sh restart
```

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

El orden es crear el invitado, generar su entorno interno, aplicar la lista
permitida por stdin SSH, arrancar Compose y verificar salud. Después se ejecuta
un preflight de lectura de OpenAI, Chatwoot y Langfuse. Solo si pasa y se pidió
`--public`, se inicia el conector de ese invitado. No se envían campañas ni se
infieren mensajes al instalar. El operador debe haber detenido el conector del
equipo anterior; el script no puede apagar otro PC ni traslada sus datos.

Para reanudar la misma instalación:

```bash
./emulate-ec2.sh up --public
./emulate-ec2.sh preflight
./emulate-ec2.sh verify --mode live
./emulate-ec2.sh stop
```

`stop` detiene la instancia por EC2 y conserva almacenamiento y configuración.
`up` los recupera. Los logins iniciales de Langfuse no se cambian sobrescribiendo
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
fuentes públicas de Git y prepara un `.env` nuevo desde `.env.example` con secretos
internos aleatorios. Reintentar conserva ese entorno, volúmenes y datos. No lee ni
copia el `.env`, volúmenes ni conversaciones del propietario. El seed es
idempotente y contiene clientes ficticios con contactos simulados.

Las interfaces locales se alcanzan por forwards SSH que escuchan sólo en loopback:

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
