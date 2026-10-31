# Cómo usamos Spec Kit

Spec Kit es un conjunto de plantillas, scripts e instrucciones para el agente de
programación. No es el bot de cobranza ni una dependencia del producto en ejecución.
Instalación utilizada: Specify CLI 1.0.1, integración Codex, skills y scripts Bash.
Fuente: [github/spec-kit](https://github.com/github/spec-kit).

## Carpetas y responsabilidades

| Ruta | Qué contiene | Cuándo se usa |
|---|---|---|
| `.agents/skills/` | Procedimientos oficiales para el agente: constitution, specify, plan, tasks, implement, analyze, converge y ayudas | Al ejecutar cada etapa de desarrollo |
| `.specify/templates/` | Formatos reutilizables; no son especificaciones terminadas | Los comandos los resuelven como punto de partida |
| `.specify/scripts/bash/` | Preparación y comprobación de rutas y documentos | Inicio de especificación, plan, tareas y validación |
| `.specify/memory/constitution.md` | Principios propios del proyecto | Antes de planificar o modificar capacidades |
| `.specify/workflows/` | Definición del flujo instalado | Orquestación de etapas de Spec Kit |
| `.specify/init-options.json` y manifests | Versión y configuración de integración | Reproducir o actualizar la instalación |
| `.specify/feature.json` | Puntero local a la feature activa, ignorado por git | Retomar trabajo en este checkout |
| `specs/prd.md` | Producto, recorridos y requisitos previos a instalar Spec Kit | Fuente de alcance y decisiones |
| `specs/arquitectura-inicial.md` | Distribución inicial en una EC2 | Restricción y mapa del despliegue |
| `specs/001-cobranza-whatsapp/` | Resultado aplicado a esta entrega: especificación, diseño, contratos y tareas | Construcción y verificación de la funcionalidad |

La CLI está instalada fuera del repositorio. `.agents/` contiene instrucciones
para desarrollar; `apps/backend/.../agent/` contendrá después el agente de cobranza.

## Documentos de esta entrega

1. [Constitución](../.specify/memory/constitution.md): reglas que no puede ignorar el diseño.
2. [Especificación](../specs/001-cobranza-whatsapp/spec.md): comportamiento y aceptación.
3. [Investigación](../specs/001-cobranza-whatsapp/research.md): decisiones, motivos y alternativas.
4. [Plan](../specs/001-cobranza-whatsapp/plan.md): diseño técnico y estructura del código.
5. [Datos](../specs/001-cobranza-whatsapp/data-model.md) y [contratos](../specs/001-cobranza-whatsapp/contracts/): estados e interfaces entre sistemas.
6. [Guion](../specs/001-cobranza-whatsapp/quickstart.md): cómo se demostrará el resultado.
7. [Tareas](../specs/001-cobranza-whatsapp/tasks.md): 56 trabajos pendientes en orden de construcción.

La instalación y estos documentos están preparados. La aplicación, las pruebas
reales y la infraestructura aún no están implementadas. El checklist de requisitos
marcado revisa la calidad del documento; no certifica software funcionando.
El diseño visual detallado de las dos webs se concreta al implementar sus vistas
pequeñas, conservando los campos y acciones del contrato.

## Retomar el trabajo

Desde la raíz del repo:

```bash
export SPECIFY_FEATURE_DIRECTORY=specs/001-cobranza-whatsapp
.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

En Codex se utilizan las skills `$speckit-constitution`, `$speckit-specify`,
`$speckit-plan`, `$speckit-tasks` y `$speckit-implement`. Son instrucciones para el
agente, no comandos Bash. Revisar coherencia con `$speckit-analyze` y contrastar
el código construido con `$speckit-converge`; ninguno sustituye los recorridos reales.

Los documentos evolucionan con decisiones nuevas: actualizar primero el requisito
que cambia, después diseño/tareas y finalmente verificar el código afectado. No
se requiere reinstalar Spec Kit para cada cambio ni ejecutar todas las ayudas
opcionales si no aportan a la entrega.
