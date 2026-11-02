# Evals reproducibles y evidencia real

Sí existieron pruebas de prompt con el modelo real durante el estudio. Eran
scripts de diagnóstico privados, ejecutados con escenarios ficticios, y sus
resúmenes se conservan localmente. Ahora hay un catálogo público reproducible
con **50 snapshots ficticios**, un runner y un reporte JSON + Markdown.
La reproducción fija entradas y registra configuración; no garantiza texto idéntico
entre respuestas probabilísticas del modelo.
El runner nuevo todavía **no tiene resultados de comportamiento LLM real**:
la validación offline comprueba el catálogo, sin inferencia.

## Tres tipos de evidencia

| Tipo | Entrada / ejecución | Lo que acredita | Límite |
| --- | --- | --- | --- |
| Tests deterministas | `tests/unit`, `tests/contracts`, `tests/integration`; dobles de proveedores y PostgreSQL desechable | Contratos, permisos, PIN estático, dinero, persistencia, presupuesto, idempotencia, efectos de handoff | No prueban obediencia del modelo ni entrega WhatsApp |
| Evals de comportamiento | `evals/cases.json` + `scripts/run_evals.py --live`; prompt y catálogo de tools reales, una inferencia por caso | La siguiente decisión del modelo ante un snapshot, con argumentos y rúbrica | No ejecutan tools, decodifican medios ni recorren el agente completo |
| Recorrido real | Evaluador en WhatsApp, Chatwoot, central, ledger y trazas | Interacción con el canal, medios reales, pago simulado registrado, retorno humano y persistencia observados | Evidencia puntual; no aceptación universal de todos los escenarios |

`scripts/run_acceptance.py` sigue ejecutando pytest y relacionando 31 criterios
con evidencia determinista. Su opción `--live` está bloqueada deliberadamente.
La suite de evals usa otro comando para que estas evidencias no se confundan.

## Catálogo público

Todos los nombres, documentos, teléfonos, UUID, saldos, medios descritos y
resultados de tools del catálogo son ficticios. No se copiaron contactos,
conversaciones ni trazas reales. Los resultados de tools incluidos son fixtures,
no consultas al backend ni resultados generados durante la nueva ejecución.

| Grupo | Casos | Qué revisar |
| --- | ---: | --- |
| Seguridad / alcance | 22 | Desvío de dominio, suplantación de roles, extracción de prompt, historial obsoleto, instrucciones en resultados/medios, controles legítimos |
| Identidad | 6 | Confirmación/rechazo natural, documento canónico, agotamiento neutral, reintento, éxito informado por backend |
| Selección / persona | 3 | Una obligación a la vez, selección explícita, cambio de persona sin arrastrar acceso |
| Negociación | 8 | 95% → 80%, una propuesta por turno, rechazar ambas, aceptar 95/80, conservar oferta90, asesor explícito |
| Condonación | 2 | Base/pago/condonado/saldo condicionado al cumplimiento y aceptación en turno posterior |
| Enlaces | 2 | Preservar marcador, recordar pago simulado y pedir imagen del comprobante con referencia |
| Comprobantes | 3 | Referencia OCR dudosa → consulta con null; absent → humano; applied → cartera actual |
| Medios | 1 | Transcripción de audio como contexto sin autoridad; imagen y recibo también cubiertos en seguridad |
| Humano | 2 | Disputa y retorno confirmado por backend con consulta fresca |
| Sesión | 1 | Confirmar logout ya revocado sin volver a localizar al titular |

El PIN escrito por el usuario **no forma parte de los inputs al modelo**.
Los casos de identidad usan eventos neutrales `identity_verified` y
`auth_attempts_exhausted` con contexto de servidor. Los mensajes de la fase
`awaiting_pin`, tres intentos, bloqueos y exclusión de telemetría se verifican en
los tests deterministas del backend. La suite rechaza snapshots de esa fase.

Las secuencias 95→80, cotización→aceptación y OCR→fallback están representadas
por snapshots independientes. Los pasos anteriores están preparados como
historia; el runner evalúa una sola continuación. **No es una ejecución
multiturno del agente**. Tampoco evalúa la calidad acústica de una transcripción
ni la lectura visual de una imagen; eso requiere medios reales y otro recorrido.

## Ejecutar offline, sin coste

Desde la raíz, basta Python 3.12; no se requieren `.env` ni librerías del proyecto:

```bash
python -m scripts.run_evals --output .local/evals/offline.json
python -m scripts.run_evals --case negotiation-first-low
```

También funciona sin Python instalado en el host:

```bash
docker run --rm --network none \
  --mount "type=bind,src=$PWD,dst=/work,readonly" \
  --workdir /work python:3.12-slim \
  python -m scripts.run_evals
```

La imagen debe estar disponible antes de usar `--network none`. El contenedor
solo lee los archivos públicos montados que utiliza el runner; no carga `.env`.
Offline valida IDs únicos, referencias emparejadas de tools, catálogo no vacío,
contexto de identidad, argumentos de fixtures según schemas actuales y expectativas compatibles con permisos. Produce hashes
del prompt y catálogo, conteos por categoría y una fila `not_run` por caso.
Código de salida 0 significa catálogo válido; **no significa que el LLM pasó**.

## Ejecutar modelo real, solo por decisión explícita

No se ejecuta automáticamente al lanzar tests ni arrancar la aplicación. Requiere
`--live`, `--allow-paid-inference`, un techo monetario y un archivo de reporte.
Ejemplo desde la raíz del checkout; se ejecuta dentro del backend del invitado
existente y conserva su configuración y ledger:

```bash
./emulate-ec2.sh evals --case receipt-ocr-fallback
./emulate-ec2.sh evals --live --allow-paid-inference --max-cost-usd 0.05 \
  --case receipt-ocr-fallback --output /app/.local/evals/receipt.json
```

En Windows PowerShell:

```powershell
.\emulate-ec2.ps1 evals --case receipt-ocr-fallback
.\emulate-ec2.ps1 evals --live --allow-paid-inference --max-cost-usd 0.05 --case receipt-ocr-fallback --output /app/.local/evals/receipt.json
```

El primer comando es offline. El segundo **sí consume IA**; no ejecutarlo para
validar instalación ni como parte automática de la demo. El forwarding no
arranca otra instalación, crea ledger ni habilita live por sí solo.

Para el stack Compose directo de desarrollo, ejecutar el mismo módulo con
`docker compose --env-file .env -f infra/compose.yaml exec -T backend ...`.
Los contenedores deben haberse construido con la revisión que incluye el catálogo.
El reporte del ejemplo permanece dentro del contenedor; copiarlo antes de
recrearlo si se desea conservarlo. Desde el invitado:

```bash
mkdir -p .local/evals
docker compose -p agil-ec2-fixture --env-file .env -f infra/compose.yaml \
  cp backend:/app/.local/evals/receipt.json .local/evals/receipt.json
docker compose -p agil-ec2-fixture --env-file .env -f infra/compose.yaml \
  cp backend:/app/.local/evals/receipt.md .local/evals/receipt.md
chmod 600 .local/evals/receipt.json .local/evals/receipt.md
```

En una instalación con entorno Python local configurado, también puede usarse
`python -m scripts.run_evals` con los mismos flags y `--env-file` del runtime
existente. **No crear otra base ni reiniciar el ledger para obtener crédito**:
las inferencias de eval también consumen el presupuesto compartido. La
configuración de entrega que descuenta gasto anterior debe conservarse.

Se usa `BackendSettings`, `InferenceClient`, las tarifas/versiones vigentes del
backend, `BudgetService` y el ledger PostgreSQL existente. No se crea ni migra
una base. El techo del comando limita adicionalmente la suma de reservas
conservadoras de esta ejecución; no aumenta crédito global ni sustituye su
control atómico. Puede detener la suite antes de agotar el importe cobrado real.
Solo se permite una inferencia por caso, en orden, sin reintentos del runner;
un error detiene las siguientes. Los casos no ejecutados quedan `not_run`.

El runner inicializa la observabilidad existente y crea spans `preflight`/`llm`.
Si Langfuse está deshabilitado o no configurado, el reporte lo indica con
`langfuse_initialized=false`; no afirma que hubo trazas. No implementa datasets,
experiments, jueces automáticos ni evaluación nativa de Langfuse.
No crea `Runtime`, clientes de central/canal ni `ToolRuntime`, y nunca ejecuta
las funciones pedidas por el modelo. Solo escribe reservas/liquidaciones de IA,
telemetría configurada y reportes locales. El coste reportado se consulta por los
eventos de esta ejecución, sin atribuirle consumo concurrente de WhatsApp.

## Leer y revisar el resultado

- `catalog_validation=valid`: contrato de casos válido.
- `structural_status=checks_passed`: herramientas permitidas, esquema estricto,
  argumentos esperados exactos, importes decimales, null explícito del fallback,
  canarios prohibidos y marcador de enlace intacto según el caso.
- `structural_status=failed/error`: revisar violaciones o fallo técnico;
  los errores no incluyen cuerpos privados de excepciones.
- `semantic_status=pending_manual_review`: leer respuesta y rúbrica en JSON;
  **no se convierte en aprobado aunque los checks estructurales pasen**.
- `not_run`: no hay salida del modelo para ese caso.

Registrar la revisión humana en un archivo local separado, con `run_id`, hash
del prompt, caso, criterio, aprobado/rechazado y justificación. Conservar fallos
y excepciones, sin reemplazarlos por resultados posteriores. El runner no
calcula tasa de aprobación semántica ni una nota global. Una salida 0 en live
solo indica ausencia de fallo mecánico detectado; aún requiere revisión.

El JSON guarda respuesta/llamadas sanitizadas, evento, modelo, reasoning effort,
límites de tokens, versión de tarifa, hashes, coste real liquidado y reserva
pendiente si hubo incertidumbre. El Markdown muestra un resumen presentable.
Ambos se crean con permisos 0600. Mantenerlos en `.local/`, ignorado por Git, y
revisarlos antes de compartir: una salida del modelo puede contener instrucciones
adversariales repetidas. No publicar `.env`, trazas, PIN ni reportes privados.

## Qué existía antes de esta suite

Los siguientes son **resúmenes históricos de diagnósticos**, conservados localmente
y contrastados con la evidencia documentada en [evaluacion.md](evaluacion.md).
No son resultados del runner nuevo ni ejecuciones sobre sus 50 casos actuales.
No sumar estas cantidades como tasa global: algunos escenarios y revisiones se
repitieron durante correcciones del prompt.

| Diagnóstico previo | Evidencia registrada | Límite |
| --- | --- | --- |
| Seguridad / alcance | 22 casos, 22 checks estructurales, 22 inferencias; USD0.00745703 | Revisión semántica separada; no ejecución de tools |
| Orientación de autenticación | 6 casos, 6 checks, 6 inferencias; USD0.00383981 | Eventos neutrales; no prueba del PIN real |
| Explicación de búsquedas | 4 inferencias; USD0.00484498 | Revisión humana de explicación; limitación visual de máscara registrada |
| Negociación 95→80 / enlaces | 11 casos, 11 checks, 11 inferencias; USD0.00881725 | Snapshots ficticios; no recorrido WhatsApp de esa ejecución |
| Retorno humano | 4 inferencias; USD0.00174844 | Diagnóstico con tools simuladas; no acciones del canal |
| Recuperación tras OCR | 3 casos, checks registrados correctos; USD0.0022939 | Resultados ficticios de verify; no lectura de imagen en esa prueba |

Estos diagnósticos registran cero herramientas efectivamente ejecutadas y cero
escrituras en central/canal. Los primeros cinco resúmenes registran liquidación
completa en el ledger; el último resumen informa coste y checks, sin un campo
`all_settled`, por lo que no se añade esa afirmación desde el resumen.

El estudio también produjo recorridos reales con identificación, pago simulado,
comprobantes, audio, derivación y retorno humano, y verificaciones financieras
posteriores. Sus trazas incluyeron fallos semánticos aunque el job estuviera
`completed` y sin nivel `ERROR`; una traza técnicamente sana no garantiza una
respuesta correcta. El detalle público de lo observado, sus correcciones y
faltantes está en [evaluacion.md](evaluacion.md) y el recorrido en
[README.md](../README.md). No se publican los datos originales para reproducirlo.

## Verificar el harness

```bash
uv run pytest tests/unit/test_evals.py -q
uv run ruff check scripts/run_evals.py tests/unit/test_evals.py
```

Estos tests usan dobles y archivos temporales. Comprueban aislamiento offline,
opt-in, exclusión del PIN estático, expectativas financieras exactas, fallback
null, techo sobre el ledger existente, no ejecución de tools, estados semánticos
honestos y parada tras error sin filtrar cuerpos privados. No consumen IA.
