# Proyecto Ágil

Agente de cobranza por WhatsApp con central de deudores y pago simulado.
[Repositorio personal público](https://github.com/cristiandrangel/proyecto-agil).

**Entrega:** lunes 2 de noviembre de 2026, America/Bogota; hora por confirmar.
**Estado:** Spec Kit inicializado; especificación y diseño técnico preparados.
**La aplicación todavía no está implementada.** No hay despliegue AWS ni pruebas
reales del flujo completadas en esta fase.

## Producto y arquitectura

- [PRD](specs/prd.md), con FR-01–22 y AC-01–31.
- [Arquitectura inicial: una sola EC2, con Mermaid](specs/arquitectura-inicial.md).
- [Dominio fijo y cambio de equipo con Cloudflare Tunnel](docs/dominio-demo.md).
- [Análisis inicial de conflictos](specs/prd-paso-0-conflictos.md).
- [Prompt original del PRD](promptprd.md).

Una EC2 con Docker Compose aloja las webs, backend/agente, API central simulada,
PostgreSQL de cartera y memoria separados y Langfuse con sus dependencias. Chatwoot
existente, Meta y OpenAI son externos. EC2 permite arrancar e iterar rápido;
servicios especializados e infraestructura como código son planes futuros.
Floci valida APIs AWS locales y se distingue del runtime de la aplicación.

## Spec Kit y diseño

[Guía de carpetas y funcionamiento](docs/spec-kit.md).

- [Constitución del proyecto](.specify/memory/constitution.md).
- [Especificación funcional](specs/001-cobranza-whatsapp/spec.md).
- [Plan técnico y estructura prevista](specs/001-cobranza-whatsapp/plan.md).
- [Decisiones investigadas](specs/001-cobranza-whatsapp/research.md).
- [Modelo de datos y estados](specs/001-cobranza-whatsapp/data-model.md).
- [Estado del agente, source_id literal y memoria](specs/001-cobranza-whatsapp/agent-state.md).
- [Contratos entre sistemas](specs/001-cobranza-whatsapp/contracts/).
- [56 tareas de implementación pendientes](specs/001-cobranza-whatsapp/tasks.md).
- [Guion de validación previsto](specs/001-cobranza-whatsapp/quickstart.md).

Instalación: Spec Kit 1.0.1, integración Codex con skills. En un nuevo checkout:

```bash
export SPECIFY_FEATURE_DIRECTORY=specs/001-cobranza-whatsapp
.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

## Próximo trabajo

Implementar las tareas empezando por consulta y pago íntegro por texto. Completar
campaña, acuerdo, captura, audio, humano y métricas; después ejecutar la batería
con integraciones reales y registrar evidencia. La prioridad organiza construcción,
no elimina capacidades de la entrega. El README ejecutable se completará con los
comandos verificados; el quickstart actual señala sus comandos de aplicación como futuros.

El evaluador pondrá su WhatsApp en el teléfono de un cliente ficticio desde la central,
lanzará la campaña con despacho uno por uno —simulado para números ficticios y
real solo para su contacto habilitado— y recorrerá PIN, deuda, pago, captura y consulta real. Podrá repetir
con descuento, atención humana y medios, inspeccionar métricas/trazas y restaurar.

La memoria usa exactamente el source_id del contacto recibido, sin transformarlo.
El LLM recibe ese valor y decide buscar por celular o pedir identificación; el PIN
se valida fuera del modelo. La cuenta/inbox se verifican por separado. Cada evento
y salida conservan el conversation_id de Chatwoot para responder al chat correcto,
aunque varias conversaciones del mismo origen compartan memoria. Gestionar otro
titular exige su PIN y limpiar el contexto financiero activo.

## Configuración privada

El entorno real, tokens, claves, datos recibidos y fuentes originales no se publican.
Se aportarán mediante configuración privada al integrar. Los seeds y el PIN de demo
son ficticios; el número real del evaluador queda en su entorno. Las claves nunca
se envían por chat ni se incluyen en el repo.

La plantilla [.env.example](.env.example) contiene las variables previstas para la
implementación. Completar en el `.env` privado OpenAI, Chatwoot, plantilla y dominio;
las claves internas del entorno local ya se generaron sin incluirlas en el repo.
El teléfono del evaluador se configura desde la central cuando esté implementada.
La aplicación y la validación de esta configuración siguen pendientes de construcción.
