"""Build offline HTML documents from the canonical Markdown sources.

Requires markdown-it-py==3.0.0 and Mermaid CLI 11.16.0 (mmdc).
Set MMDC_PUPPETEER_CONFIG to a Puppeteer JSON config when needed.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import mimetypes
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/site"
TEMPLATES = ROOT / "scripts/docs-site"
REPO = "https://github.com/cristiandrangel/proyecto-agil"


def project_document_link(href):
    """Attachments retain section anchors and web references, never sibling files."""
    if not href or href.startswith("#"):
        return False
    parsed = urlsplit(href)
    if not parsed.scheme or parsed.scheme == "file":
        return True
    if parsed.hostname == "cristiandrangel.github.io":
        return parsed.path == "/proyecto-agil" or parsed.path.startswith("/proyecto-agil/")
    return parsed.hostname == "github.com" and parsed.path.startswith(
        ("/cristiandrangel/proyecto-agil/blob/", "/cristiandrangel/proyecto-agil/raw/")
    )


def embedded(path):
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode()


def slug(text):
    text = re.sub(r"[`*_]", "", text).lower()
    return "".join(c for c in text if c.isalnum() or c in " -").replace(" ", "-")


def diagrams(sources):
    blocks = list(
        dict.fromkeys(
            block
            for source in sources
            for block in re.findall(r"^```mermaid\n(.*?)^```", source, re.M | re.S)
        )
    )
    cache = ROOT / ".local/docs-svg-cache"
    cache.mkdir(parents=True, exist_ok=True)
    config = {
        "theme": "base",
        "themeVariables": {
            "primaryColor": "#fff0e7",
            "primaryTextColor": "#282b30",
            "primaryBorderColor": "#f96321",
            "lineColor": "#626970",
            "secondaryColor": "#f3f3ef",
            "tertiaryColor": "#ffffff",
            "fontFamily": "Arial",
            "fontSize": "16px",
        },
    }

    def render(block):
        key = hashlib.sha256((block + json.dumps(config)).encode()).hexdigest()
        target = cache / (key + ".svg")
        if not target.exists():
            with tempfile.TemporaryDirectory() as temp:
                inp = Path(temp) / "diagram.mmd"
                inp.write_text(block)
                cfg = Path(temp) / "config.json"
                cfg.write_text(json.dumps(config))
                args = ["mmdc", "-i", str(inp), "-o", str(target), "-c", str(cfg), "-b", "white"]
                if os.environ.get("MMDC_PUPPETEER_CONFIG"):
                    args += ["-p", os.environ["MMDC_PUPPETEER_CONFIG"]]
                subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return block, target.read_text()

    with ThreadPoolExecutor(max_workers=2) as pool:
        return dict(pool.map(render, blocks))


def build(source_path, filename, label, title, subtitle, svgs):
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    source = source_path.read_text()
    # The README navigation row belongs to GitHub. A mailed attachment has its
    # own section index and must not depend on a second document being present.
    if source_path == ROOT / "README.md":
        source = "\n".join(line for line in source.splitlines() if not line.startswith("[Guía web]("))
    tokens = md.parse(source)
    headings, counts = [], {}
    number = 0
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            text = tokens[i + 1].content
            ident = slug(text)
            n = counts.get(ident, 0)
            counts[ident] = n + 1
            if n:
                ident += "-" + str(n)
            token.attrSet("id", ident)
            if token.tag in ("h2", "h3"):
                headings.append((token.tag, text, ident))
        if token.type == "fence" and token.info.strip() == "mermaid":
            number += 1
            svg = svgs[token.content]
            # Each standalone Mermaid render starts with the same IDs. Namespace
            # references so arrowheads, labels and CSS remain local to each SVG.
            ids = re.findall(r'\bid="([^"]+)"', svg)
            for ident in sorted(set(ids), key=len, reverse=True):
                unique = f"d{number}-{ident}"
                svg = svg.replace(f'id="{ident}"', f'id="{unique}"')
                svg = re.sub(r"#" + re.escape(ident) + r"(?![\w-])", "#" + unique, svg)
            svg = re.sub(r"<\?xml.*?\?>", "", svg)
            section = headings[-1][1] if headings else "Arquitectura"
            caption = html.escape(f"Diagrama {number} · {section}")
            token.type = "html_block"
            token.tag = ""
            token.content = f'<figure class="diagram" id="diagrama-{number}"><div class="diagram-bar"><strong>{caption}</strong><button type="button" data-expand aria-label="Ampliar diagrama {number}">Ampliar ↗</button></div><div class="diagram-preview" data-expand>{svg}</div><div class="diagram-note">Abre para ampliar, desplazar o descargar el diagrama en SVG.</div></figure>'
        hidden_links = []
        for child in token.children or []:
            if child.type == "link_open":
                href = child.attrGet("href") or ""
                hidden_links.append(project_document_link(href))
                child.hidden = hidden_links[-1]
            elif child.type == "link_close" and hidden_links:
                child.hidden = hidden_links.pop()
            if child.type == "image":
                path = (source_path.parent / child.attrGet("src")).resolve()
                child.attrSet("src", embedded(path))
                child.attrSet("loading", "lazy")
    content = md.renderer.render(tokens, md.options, {})
    content = content.replace("<table>", '<div class="table-wrap"><table>').replace(
        "</table>", "</table></div>"
    )
    toc = "".join(
        f'<a class="{"sub" if tag == "h3" else ""}" href="#{ident}">{html.escape(text)}</a>'
        for tag, text, ident in headings
    )
    options = "".join(
        f'<option value="{ident}">{html.escape(text)}</option>'
        for tag, text, ident in headings
        if tag == "h2"
    )
    logo = embedded(OUTPUT / "assets/liberty-latin-america.png")
    css = (TEMPLATES / "style.css").read_text()
    js = (TEMPLATES / "viewer.js").read_text()
    nav = f'<span class="button active" aria-current="page">{html.escape(label)}</span>'
    download_name = "guia-proyecto-agil.html" if filename == "index.html" else "arquitectura.html"
    page = f'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="{html.escape(subtitle)}"><title>{label} · Proyecto Ágil · Cristian Bolaños</title><link rel="icon" href="{logo}"><style>{css}</style></head>
<body><a class="skip" href="#contenido">Saltar al documento</a><header class="topbar"><a class="brand" href="#contenido"><img src="{logo}" alt="Liberty Latin America"><span><strong>Proyecto Ágil</strong><small>AI Engineer · Prueba técnica</small></span></a><nav class="topnav" aria-label="Documento">{nav}<a class="button repo-link" href="{REPO}">Repositorio ↗</a><button data-print>Imprimir</button></nav><div class="progress" aria-hidden="true"></div></header>
<div class="layout"><aside class="sidebar"><span class="eyebrow">{label}</span><h2>En este documento</h2><nav aria-label="Índice de secciones">{toc}</nav><select class="mobile-index" aria-label="Ir a una sección"><option value="">Ir a una sección…</option>{options}</select><div class="sidebar-footer">Preparado por<br><b>Cristian Danilo<br>Bolaños Rangel</b><br>3 de noviembre de 2026<br><br>Propuesta del candidato para<br>Liberty Latin America.</div></aside>
<main id="contenido"><section class="hero"><span class="eyebrow">Liberty Latin America / {label}</span><h1>{title}</h1><p>{subtitle}</p><div class="meta"><span><b>Cristian Danilo Bolaños Rangel</b></span><span>AI Engineer</span><span>Noviembre 2026</span></div><div class="hero-actions"><a class="button primary" href="#{headings[0][2]}">Comenzar lectura ↓</a><button class="button" data-download-html="{download_name}">Descargar HTML</button></div></section><article>{content}</article><footer>Proyecto Ágil · Propuesta de Cristian Danilo Bolaños Rangel para la prueba técnica.<br>Identidad visual y logotipo de referencia: <a href="https://lla.com/">Liberty Latin America</a>. Esta es una entrega del candidato, no una publicación corporativa.<br>Documento autocontenido: los estilos, diagramas e imágenes están incluidos para su lectura sin conexión.</footer></main></div>
<dialog id="diagram-viewer" aria-labelledby="viewer-title"><div class="viewer-head"><strong id="viewer-title">Diagrama</strong><div class="viewer-controls"><button id="zoom-out" aria-label="Alejar">−</button><span id="zoom-value" aria-live="polite">100%</span><button id="zoom-in" aria-label="Acercar">+</button><button id="fit">Ajustar</button><button id="actual-size">100%</button><button id="download-svg">SVG ↓</button><button id="close-viewer" aria-label="Cerrar diagrama">Cerrar ×</button></div></div><div class="viewport"><div class="canvas"></div></div><div class="viewer-foot">Arrastra para desplazarte · Rueda o pellizco para zoom · + / − para ampliar · Esc para cerrar</div></dialog><script>{js}</script></body></html>'''
    (OUTPUT / filename).write_text(page)
    print(f"{filename}: {number} diagrams, {len(headings)} sections, {len(page.encode()):,} bytes")


def main():
    sources = [ROOT / "README.md", ROOT / "docs/arquitectura.md"]
    svgs = diagrams([p.read_text() for p in sources])
    build(
        sources[0],
        "index.html",
        "Guía del evaluador",
        "De la cartera<br>a la conversación.",
        "Instala la solución, vive el recorrido desde tu WhatsApp y comprueba los resultados de un agente de cobranza con herramientas e inferencia reales.",
        svgs,
    )
    build(
        sources[1],
        "arquitectura.html",
        "Documento técnico",
        "Una conversación.<br>Un sistema completo.",
        "Arquitectura, datos, decisiones y controles de Proyecto Ágil. Del primer contacto al pago verificado, con continuidad humana y observabilidad por turno.",
        svgs,
    )


if __name__ == "__main__":
    main()
