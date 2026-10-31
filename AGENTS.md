# Proyecto Ágil

Repositorio personal de Cristian. Trabajar dentro de este proyecto, independiente de sus wikis.
El remoto personal es git@github-personal:cristiandrangel/proyecto-agil.git.

## Estado y orden de trabajo

1. La indicación posterior de Cristian del 31 de octubre de 2026 permite construir el PRD integral con el contexto disponible.
2. specs/prd.md es la base de producto; la instrucción posterior de continuar con Spec Kit autoriza especificación y diseño.
3. Conservar la estructura de promptprd.md, distinguir requisitos confirmados, propuestas y TBD, y no atribuir aprobación a decisiones abiertas.
4. Spec Kit oficial 1.0.1 está inicializado para Codex. La feature activa es specs/001-cobranza-whatsapp; seguir spec.md, plan.md y tasks.md.
5. No presentar propuestas de arquitectura como decisiones aprobadas ni como implementación existente.

Las instrucciones directas y posteriores de Cristian prevalecen sobre el prompt y este archivo.
La base acordada es una sola EC2 con todos los componentes propios en contenedores.
El mapa inicial solicitado está en specs/arquitectura-inicial.md; sus detalles de contratos,
capacidad y despliegue se desarrollarán con Spec Kit. La segmentación en servicios
AWS especializados se evaluará después. Chatwoot existente, Meta y OpenAI son externos.
EC2 se elige para arrancar e iterar rápido. La optimización posterior con servicios
especializados e infraestructura como código son planes futuros, no requisitos de esta entrega.

## Fuentes y privacidad

- El repositorio será público: usar datos ficticios y ejemplos sin secretos.
- Nunca versionar entorno real, tokens, claves, códigos de recuperación o dumps.
- La guía del empleador, el workflow original y las imágenes se consultan desde su ubicación local.
- No publicar automáticamente las fuentes ni copiar información de otros proyectos o de las wikis.
- El JSON de n8n es referencia de mecanismo; sus reglas comerciales pertenecen a otro dominio.
- Revisar el contenido exacto preparado para cada commit antes de publicar.

## Documentación

- El PRD debe centrarse en el producto; omitir historia de la conversación y del proceso de redacción.

- Distinguir requisitos confirmados, recomendaciones y TBD.
- Citar las fuentes que influyen en cada sección.
- Mantener trazabilidad entre PRD, especificación y criterios de evaluación.
- Diseño de entrega: specs/001-cobranza-whatsapp/. Las tareas de implementación se marcan completas solo con código y verificación.
- Entrega: lunes 2026-11-02 (America/Bogota), hora pendiente.
- .specify/feature.json es estado local ignorado; seleccionar la feature con SPECIFY_FEATURE_DIRECTORY al retomar en otro checkout.
