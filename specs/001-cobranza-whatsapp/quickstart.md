# Quickstart técnico

**Estado, 2 de noviembre:** implementación ejecutable con Floci y proveedores
reales. El recorrido guiado del evaluador vive en el [README](../../README.md);
la evidencia y sus límites en [evaluación](../../docs/evaluacion.md). Se usan datos
ficticios y no se mueve dinero real.

## Lo que ya se puede revisar

Spec Kit 1.0.1 está instalado e inicializado para Codex. La constitución vive en
`.specify/memory/constitution.md`; esta funcionalidad está en
`specs/001-cobranza-whatsapp/`. En un checkout nuevo puede seleccionarse con:

```bash
export SPECIFY_FEATURE_DIRECTORY=specs/001-cobranza-whatsapp
.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

El puntero `.specify/feature.json` es local y se ignora en git. La rama actual
es main; no se exige una rama con el nombre de la feature.

## Preparación privada para la demo

Requisitos: Linux x86_64, Docker Engine con Compose v2, Bash, puertos locales y
memoria/disco suficientes según [EC2 emulada](../../docs/emulacion-ec2.md).
El archivo privado de entrega proporciona las integraciones y los accesos UI.
El conector del equipo anterior debe estar detenido antes de activar el nuevo.

1. Colocar `.env.entrega` junto al README, sin secretos internos ni datos de estudio.
2. Usar exclusivamente las claves de integración y UI permitidas por el helper.
3. Conservar el mismo hostname y un solo conector; no se modifican otras bandejas.
4. Descontar el consumo previo si se reutiliza la misma clave de OpenAI.
5. Obtener el entorno efectivo y los accesos al final de
   `.local/ec2-emulation/evaluator.env` después del arranque.

## Arranque de entrega

Desde la raíz del repositorio:

```bash
chmod 600 .env.entrega
./emulate-ec2.sh up --delivery-file .env.entrega --public
./emulate-ec2.sh preflight
./emulate-ec2.sh verify --mode live
```

Los entrypoints aplican migraciones y preparan checkpoints antes de readiness.
El preflight normal no envía mensajes ni consume inferencia. El arranque no lanza
campañas: ese paso se hace en la central. Reanudar con
`./emulate-ec2.sh up --public` conserva datos y configuración.

Endpoints: central `https://cobranza.agenx-dev-test.work/central`, pago bajo `/p/`,
Langfuse en `http://localhost:13000` y `/health`, `/ready` sin secretos.
Se usan HTTPS y las rutas públicas definidas en
[contrato de aplicación](contracts/application.md); bases y Floci son internos.

## Recorrido A: campaña y pago completo

1. Entrar como operador con la credencial privada de demo.
2. Elegir el cliente ficticio con dos servicios y sustituir su teléfono por el
   propio WhatsApp, con código de país. Guardar y verificar ambas filas.
3. Seleccionar Live para habilitar ese contacto de prueba en una sola acción; los demás fixtures
   permanecen simulated. Si el canal lo requiere, habilitar el destinatario en Meta.
   Si Chatwoot necesita un mensaje de preparación para crear la asociación,
   enviarlo antes de la campaña; ese mensaje no cuenta como respuesta posterior.
4. Filtrar 30–59 días y revisar personas y deudas elegibles. Seleccionar la plantilla
   ya aprobada y lanzar una vez. Ver avanzar el lote uno por uno: ficticios como
   simulados sin envío real; solo el evaluador recibe WhatsApp. Confirmar que las
   simulaciones no inflan envíos reales ni el denominador de contactabilidad.
5. Responder, confirmar el candidato o indicar otra identificación, introducir el PIN
   ficticio que indique el README y seleccionar servicio.
   El PIN se entrega al backend, nunca se registra en trazas ni se pasa al modelo.
6. Pedir enlace, aprobar el pago simulado y comprobar USD recibidos, cero condonados
   y saldo cero únicamente en el servicio elegido.
7. Hacer captura del comprobante y enviarla por WhatsApp. Verificar respuesta
   basada en consulta real y su traza; el segundo servicio conserva su saldo.

## Recorrido B: acuerdo y descuento

Restaurar el escenario antes de probar otra ruta financiera. Sobre deuda de USD 100,
ofrecer 90, aceptar condiciones en el mensaje siguiente y pagar. Antes del pago
se ve acuerdo pendiente con deuda de 100; después, 90 recibidos y 10 condonados.
Repetir el envío del comprobante: no aplica otro pago. Repetir con oferta de 80
para comprobar el límite exacto.

## Recorrido C: humano

Restaurar; ofrecer 79,99 sobre 100, disputar o pedir asesor. Comprobar caso, nota
privada y open en Chatwoot. Enviar otro mensaje: el bot permanece detenido.
El asesor responde y devuelve pending expresamente; se conserva contexto y se
comprueba el saldo vigente. Probar toma humana mientras el modelo procesa; registrar
el comportamiento real y la limitación de carrera entre consulta y envío externos.

## Recorrido D: audio, imagen y fallos

Enviar una nota de voz y texto acompañante; comprobar interpretación. Enviar imagen
ilegible, recibo sin pago y referencia de otra persona: pedir aclaración o consulta,
sin confirmar un pago inexistente ni revelar datos ajenos. Inyectar caída de central
para comprobar que no se inventa éxito. En modo local se permiten fixtures para
las condiciones de error; el guion real debe incluir audio e imagen del canal.

## Métricas, trazas y evidencia

Revisar envíos, personas que respondieron, contactabilidad, pago total sin descuento,
acuerdos pendientes/cumplidos, solicitudes humanas, derivaciones automáticas y
sin resultado al cierre. Inspeccionar traza de texto, audio e imagen y gasto acumulado.
Cerrar una campaña de prueba para mostrar resultados al corte.

Comandos objetivo de verificación, tras implementarse:

```bash
docker compose --env-file .env -f infra/compose.yaml exec backend uv run pytest
docker compose --env-file .env -f infra/compose.yaml exec backend python -m scripts.run_acceptance
```

Pruebas deterministas no gastan ni envían. La batería real se activa explícitamente;
registrar AC-01–31 como aprobado/fallido/bloqueado y evidencia en docs/evaluacion.md,
con modelo, configuración, fecha y limitaciones. No afirmar aprobado porque haya un mock.

## Restauración y Floci

El comando objetivo `python -m scripts.reset_demo --confirm` dentro del contenedor
restaura escenarios locales, invalida sesiones, elimina checkpoints/writes y cambia
epoch como metadato junto con la fecha de corte. thread_id sigue siendo source_id
literal, sin prefijos nuevos. Nunca borra ledger
de gasto ni historial externo. No usar `down -v` como reset rutinario: elimina datos
persistentes, incluido consumo si se usa sobre todos los volúmenes.

El perfil `infra/compose.floci.yaml` y `python -m scripts.smoke_floci` ejercitan solo
APIs locales seleccionadas, con endpoint explícito y credenciales ficticias. Se
registran operaciones soportadas y límites; no se presenta como despliegue AWS real.
La EC2 real se despliega con instrucciones propias, sin IaC obligatorio.
