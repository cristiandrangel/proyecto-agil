<!--
Sync Impact Report
Version change: plantilla sin ratificar -> 1.0.0 (adopción inicial).
Principios: siete principios concretos reemplazan los ejemplos de la plantilla.
Added sections: Restricciones de entrega; Flujo de desarrollo y verificación.
Removed sections: ejemplos y marcadores sin contenido del proyecto.
Follow-up TODOs: ninguno. Las plantillas oficiales no se modifican.
-->
# Proyecto Ágil Constitution

## Core Principles

### I. Verdad financiera en el sistema central

El backend DEBE validar saldo vigente, titularidad, oferta y estado antes de crear
una orden o aplicar un pago. Todos los importes son USD con precisión monetaria.
El descuento automático solo admite ofertas desde el 80% e inferiores al 100% del
saldo elegido. Pago y condonación DEBEN registrarse por separado y aplicarse una
sola vez. Una captura, un enlace o un acuerdo aceptado no liquidan una deuda.

### II. Identidad y control humano fuera del LLM

El sistema DEBE verificar el PIN ficticio antes de revelar cartera y limitar las
herramientas al cliente y deuda autorizados. El PIN no se devuelve al modelo.
El bot solo gestiona conversaciones pending y DEBE comprobar ese control antes
de enviar. Las disputas, ofertas inferiores al 80%, solicitudes de asesor y casos
no verificables se derivan con contexto. Se reutiliza el control existente de
Chatwoot; retornar al bot requiere una acción explícita.

### III. Un agente real con herramientas verificables

El responsable conversacional DEBE ser un único nodo LangGraph que encapsule el
ciclo de llamadas reales a OpenAI y herramientas. Audio e imágenes se normalizan
antes de ese nodo. La imagen de un comprobante DEBE provocar una consulta del
registro de pago y titularidad; nunca autoriza por sí sola una confirmación.
La memoria conversacional DEBE persistir y permanecer separada de la cartera.

### IV. Entrega pequeña, completa y reproducible

El alcance inicial DEBE ejecutarse en una sola EC2 con Docker Compose, con todas
las aplicaciones y datos propios en esa máquina y Chatwoot existente, Meta y
OpenAI como dependencias externas. El mismo proyecto DEBE poder evaluarse
localmente. La central y el pago son webs pequeñas; se conserva la frontera HTTP
con la cartera simulada. La entrega DEBE cubrir los recorridos completos antes
de añadir capacidades opcionales. IaC y migración a servicios especializados son
planes futuros, sin obligación de implementarlos para la prueba.

### V. Trazas y métricas que se puedan contrastar

La implementación DEBE correlacionar campañas, personas, conversaciones, órdenes,
pagos y trazas de Langfuse. Debe medir contactabilidad por personas únicas y
separar pago íntegro sin condonación de acuerdos con descuento, sus estados,
solicitudes de asesor y escalados automáticos. El costo de inferencia DEBE incluir
agente, audio, visión y reintentos. El presupuesto asignado a IA es USD 5; el plan
DEBE establecer controles de consumo y explicar sus límites.

### VI. Datos ficticios y secretos privados

El repositorio público DEBE contener solo fixtures ficticios, configuración de
ejemplo y artefactos revisados. Claves, PIN de sesión, tokens, entorno real,
archivos recibidos, trazas privadas y fuentes originales no se publican.
El evaluador DEBE sustituir el teléfono de un cliente ficticio por su WhatsApp
en la central. Ese contacto se guarda en su entorno y se comparte entre los
servicios de la misma persona; nunca se incorpora a los seeds públicos.

### VII. Verificación proporcional al riesgo

El trabajo DEBE mantener trazabilidad con los FR y AC del PRD. Las reglas
financieras, identidad, aislamiento, idempotencia y concurrencia requieren
pruebas deterministas y de integración relevantes. Los recorridos con LLM real,
WhatsApp y medios requieren evidencia de ejecución; un mock no demuestra esa
integración. No se exige una redacción literal del modelo ni pruebas triviales
que repliquen código o cambios visuales de bajo impacto.

## Restricciones de entrega

- Fecha de entrega: lunes 2026-11-02, zona America/Bogota; hora por confirmar.
- Un monorepo personal público; la infraestructura inicial concentra el fallo en
  una máquina y su dimensionamiento debe medirse con Langfuse incluido.
- Pago simulado, PIN ficticio y datos semilla; sin dinero real ni OTP productivo.
- Floci emula las operaciones AWS locales expresamente verificadas. Arrancar
  Compose no demuestra emulación del aprovisionamiento de EC2 ni paridad AWS.
- Plantillas de WhatsApp preaprobadas para la demo. Su clasificación depende de
  Meta; no se garantiza alcance comercial por elegir una categoría.
- El README DEBE guiar preparación del celular, campaña, PIN, pago, captura,
  descuento, atención humana, audio, métricas, trazas y restauración.

## Flujo de desarrollo y verificación

El PRD y la arquitectura inicial son las entradas de producto. Antes de código,
la especificación DEBE definir comportamientos y aceptación; el plan DEBE resolver
contratos, datos y dependencias; las tareas DEBEN mostrar el orden de construcción.
Se registran supuestos configurables y accesos externos pendientes sin inventar
credenciales, resultados ni acuerdos de producción. Cada incremento se verifica
con checks adecuados. No se marcan tareas de implementación como terminadas
por haber redactado sus documentos. Antes de publicar se revisa el contenido
exacto del commit y se conserva la identidad personal configurada.

## Governance

Las instrucciones directas posteriores de Cristian prevalecen. Las modificaciones
a estos principios se documentan con motivo y efecto sobre especificación, plan
y tareas. La versión aumenta MAJOR si se eliminan o cambian incompatiblemente
principios, MINOR al añadir obligaciones y PATCH en aclaraciones sin cambio de
alcance. La revisión de cada plan comprueba cumplimiento; una excepción debe
explicitar el principio afectado, motivo y alcance antes de implementarse.

**Version**: 1.0.0 | **Ratified**: 2026-10-31 | **Last Amended**: 2026-10-31
