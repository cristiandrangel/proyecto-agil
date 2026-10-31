# Proyecto Ágil

**Estado:** definición del PRD, anterior al diseño técnico y a la implementación.

[Repositorio público en la cuenta personal de Cristian](https://github.com/cristiandrangel/proyecto-agil).

## Documentos

- [Prompt y proceso de construcción del PRD](promptprd.md).
- [Paso 0: análisis de conflictos, acuerdos y vacíos](specs/prd-paso-0-conflictos.md).
- [PRD integral — borrador 0.1 para revisión](specs/prd.md).

El PRD está consolidado en **specs/prd.md**. Por indicación posterior de Cristian,
se construyó el borrador completo con los datos conocidos y los pendientes explícitos.
Después de revisarlo se aplicará [Spec Kit](https://github.com/github/spec-kit).

## Pendientes de documentación

- Revisar el PRD integral y resolver los supuestos que cambian el comportamiento.
- Elaborar el mapa de componentes y servicios AWS con diagramas Mermaid solicitado.
- Derivar la especificación, el plan y las tareas mediante Spec Kit.
- Implementar y completar el README ejecutable con el recorrido del evaluador.

Todavía no hay aplicación ejecutable ni infraestructura desplegada.
Floci se usará para emulación local y OpenAI para la inferencia real del prototipo.
Los servicios AWS concretos y el uso de Terraform se definirán en el diseño.
El control del bot mediante conversaciones pending ya existe en el Chatwoot externo.

## Entrega futura para el evaluador

El README ejecutable documentará arranque, entorno privado, datos ficticios, verificación
de identidad, edición del teléfono de un cliente ficticio por el WhatsApp del evaluador,
campaña, pago completo sin condonación, acuerdo con descuento, captura del comprobante, consulta del pago,
audio, imágenes, escalamiento humano, observabilidad y restauración de los escenarios.

El repositorio no contendrá claves reales, códigos de recuperación ni las fuentes privadas
aportadas como referencia.
