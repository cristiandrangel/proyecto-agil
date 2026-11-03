# Proyecto Ágil

Repositorio personal de Cristian. Trabajar dentro de este proyecto, independiente de sus wikis.
El remoto personal es git@github-personal:cristiandrangel/proyecto-agil.git.

## Continuidad local

Antes de retomar, lee `.local/RETOMAR.md` si existe: contiene el punto de pausa,
la forma de arrancar y las verificaciones pendientes de este equipo. Es una nota
privada ignorada; no publicarla ni copiar sus datos privados al repositorio.
La guía del evaluador está en `README.md` y la evidencia pública en `docs/evaluacion.md`.
El documento técnico consolidado para la entrega es `docs/arquitectura.md`;
distinguir siempre el prototipo local ejecutado de la propuesta AWS no desplegada.

## Instalación y acompañamiento del evaluador

- Leer primero `README.md` y `docs/emulacion-ec2.md`: contienen requisitos,
  clonación/ZIP, accesos, recorrido y límites reales de la entrega.
- Para una instalación funcional nueva se necesita el archivo privado
  `.env.entrega` proporcionado por quien entrega la prueba. No inventar claves,
  credenciales ni contactos, ni publicar ese archivo.
- Arrancar con `./emulate-ec2.sh up --delivery-file .env.entrega --public`, o
  `.\emulate-ec2.cmd up --delivery-file .env.entrega --public` en Windows.
  `start.sh` corresponde al desarrollo directo anterior, no a esta entrega.
- La preparación del dominio corresponde a quien entrega el proyecto. No pedir
  al evaluador confirmaciones de traspaso ni cambios de DNS en el recorrido.
- Para reanudar la misma instalación usar `up --public` sin volver a importar
  la entrega. Conservar bases, presupuesto y configuración; no resetear ni
  borrar volúmenes para resolver un problema de acceso.
- Acompañar el recorrido desde el README. No lanzar campañas ni enviar mensajes
  por iniciativa del agente; el operador debe iniciar esos pasos deliberadamente.
- `.local/RETOMAR.md` es continuidad privada opcional de este equipo; un clon
  nuevo funciona sin ella y no debe recibir sus datos de estudio.

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

- Las fuentes de contenido son README.md y docs/arquitectura.md. Los HTML de
  docs/site se generan con scripts/build_docs_site.py; no editar su contenido
  manualmente. Regenerarlos al cambiar las fuentes. El workflow de documentación
  también genera y publica solo docs/site en GitHub Pages.
- Los HTML se entregan por separado: cada uno debe abrir sin archivos hermanos,
  imágenes o recursos externos. No enlazar otros HTML ni Markdown del proyecto;
  conservar índices internos, referencias web y accesos a las interfaces.
- En la documentación, usar «API de la central de deudores» en lugar de «API
  central» o «API financiera». Conservar los identificadores internos del código.

- El README es la entrada del evaluador: producto y capacidades, instalación,
  recorrido con acciones/resultados, evidencia y ayuda operativa. Evitar acumular
  historia de correcciones o duplicar explicaciones internas extensas.
- `docs/arquitectura.md` es el entregable técnico autocontenido: incluir allí
  contratos, datos, flujos, decisiones, controles, observabilidad y propuesta AWS.
  No delegar explicaciones necesarias a enlaces a otros archivos del repo.

- Durante el recorrido guiado con Cristian, incorporar al `README.md` cada paso,
  explicación práctica y ajuste acordado, en su sección correspondiente. Incluir
  acciones y resultados esperados; distinguirlos de los resultados realmente
  observados. No copiar credenciales ni datos personales del test al documento público.
- El PRD debe centrarse en el producto; omitir historia de la conversación y del proceso de redacción.

- Distinguir requisitos confirmados, recomendaciones y TBD.
- Citar las fuentes que influyen en cada sección.
- Mantener trazabilidad entre PRD, especificación y criterios de evaluación.
- Diseño de entrega: specs/001-cobranza-whatsapp/. Las tareas de implementación se marcan completas solo con código y verificación.
- Hito interno de desarrollo: lunes 2026-11-02.
- Entrega oficial confirmada: martes 2026-11-03, 23:59 Colombia (America/Bogota).
- .specify/feature.json es estado local ignorado; seleccionar la feature con SPECIFY_FEATURE_DIRECTORY al retomar en otro checkout.

## Campañas de demo

Despacho secuencial, una persona por vez, con progreso persistente. Los destinos
ficticios solo simulan el envío; el contacto del evaluador en modo live habilitado
usa Chatwoot real. Las simulaciones se muestran aparte de los KPI reales.

## Inferencia

Agente principal: gpt-5.6-luna con reasoning.effort=high. La salida total inicial
es 4096 tokens e incluye razonamiento. El presupuesto de IA es USD 10 por instrucción posterior de Cristian.

## Memoria e identificación

thread_id es exactamente el source_id del contacto recibido de Chatwoot, sin
normalización, prefijos propios, hash ni concatenación con otros IDs. El inbox/cuenta
permitidos se verifican por separado. Se inyecta el valor literal al prompt y el
LLM decide si buscar por teléfono o pedir tipo/número de documento; no hay un nodo
previo de clasificación. La central no guarda Business IDs de Meta. Cambiar de
cliente exige nuevo PIN y limpiar el contexto financiero anterior, manteniendo
la misma llave de memoria. El reset elimina checkpoints locales, sin cambiar la llave.
