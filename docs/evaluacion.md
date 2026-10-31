# Evidencia de evaluación

## Verificación parcial de credencial OpenAI — 2026-10-31

- La clave se leyó desde el `.env` privado, sin imprimirla ni copiarla al repo.
- GET /v1/models devolvió HTTP 200 con autenticación aceptada.
- Los modelos configurados para agente, visión y transcripción aparecen en el catálogo devuelto.
- El archivo `.env` continúa excluido de git.
- No se ejecutó inferencia, transcripción ni análisis de imágenes en esta comprobación.

Esto acredita acceso autenticado al catálogo. No acredita una respuesta generada,
saldo de facturación, límite de gasto aplicado ni cumplimiento de AC-01–31.
La integración completa y sus casos siguen pendientes de implementación y ejecución.

## Configuración elegida

Agente principal gpt-5.6-luna, reasoning.effort=high. Salida total inicial 4096 tokens
incluyendo razonamiento. La documentación admite ese esfuerzo; una prueba real de
calidad, latencia, uso y herramientas sigue pendiente. No se sustituirá el modelo
ni se cambiará el esfuerzo sin registrar la decisión.
