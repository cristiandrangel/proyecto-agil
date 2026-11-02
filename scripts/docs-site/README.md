# Presentación HTML de los documentos

Las fuentes de contenido siguen siendo `README.md` y `docs/arquitectura.md`.
`build_docs_site.py` genera `docs/site/index.html` y `docs/site/arquitectura.html`,
con CSS, JavaScript, imágenes y diagramas SVG incluidos. Cada documento se puede
abrir sin conexión. La navegación entre documentos requiere guardar ambos en la
misma carpeta; los enlaces al repositorio y a otros sitios requieren Internet.

Requisitos de generación (no necesarios para ejecutar la demo): Python con
`markdown-it-py==3.0.0`, Node.js, Mermaid CLI `11.16.0` y Chrome/Chromium.

```bash
python -m pip install markdown-it-py==3.0.0
npm install --global @mermaid-js/mermaid-cli@11.16.0
python scripts/build_docs_site.py
```

`MMDC_PUPPETEER_CONFIG` admite la ruta de un JSON de configuración Puppeteer
para indicar un navegador instalado. Los SVG intermedios se guardan en
`.local/docs-svg-cache`, fuera del repositorio. Tras editar las fuentes o la
presentación, regenerar los HTML antes de commitear. GitHub Actions también
los regenera y publica únicamente `docs/site` en GitHub Pages.

## Referencia visual

Logo original: https://lla.com/sites/default/files/newlibertylogo.png
Sitio de referencia: https://lla.com/ (consultado el 2 de noviembre de 2026).
Se conservan los colores naranja, rojo, blanco y gris de referencia. El logotipo
identifica al destinatario de la prueba; las páginas se identifican como propuesta
de Cristian Danilo Bolaños Rangel, no como documentación corporativa oficial.
