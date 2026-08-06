"""Build a static documentation site from the repository's own Markdown.

No generator dependency, no theme package, no network at build or view time:
the docs are the root Markdown files this repository already maintains, and the
site is those files rendered to self-contained HTML with an index. A docs site
that needs a toolchain rots the moment the toolchain does; this one needs the
standard library.

Usage: python scripts/godmode_docs_site.py [--out docs-site]
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

SOURCES = (
    "README.md", "GODMODE.md", "GODMODE_PRIVACY.md", "GODMODE_SECURITY.md",
    "GODMODE_ACCEPTANCE.md", "THREAT-MODEL.md", "GOVERNANCE.md",
    "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "CHANGELOG.md",
)

_STYLE = (
    "body{max-width:52rem;margin:2rem auto;padding:0 1rem;"
    "font-family:system-ui,sans-serif;line-height:1.6;color:#222}"
    "pre{background:#f4f4f4;padding:.8rem;overflow-x:auto;border-radius:4px}"
    "code{background:#f4f4f4;padding:.1rem .3rem;border-radius:3px}"
    "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:.3rem .6rem}"
    "nav{border-bottom:1px solid #ddd;margin-bottom:1.5rem;padding-bottom:.5rem}"
    "nav a{margin-right:.9rem}"
    "@media(prefers-color-scheme:dark){body{background:#111;color:#ddd}"
    "pre,code{background:#1e1e1e}td,th{border-color:#444}}"
)

_INLINE = (
    (re.compile(r"\*\*(.+?)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)"), r"<em>\1</em>"),
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)"), r'<a href="\2">\1</a>'),
)


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    for pattern, replacement in _INLINE:
        escaped = pattern.sub(replacement, escaped)
    # Internal .md links point at the rendered page instead.
    return re.sub(r'href="\./?([A-Za-z0-9_.-]+)\.md"', r'href="\1.html"', escaped)


def render(markdown: str) -> str:
    out: list[str] = []
    lines = markdown.splitlines()
    index = 0
    in_list = False
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            if in_list:
                out.append("</ul>")
                in_list = False
            block: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                block.append(lines[index])
                index += 1
            out.append("<pre><code>" + html.escape("\n".join(block)) + "</code></pre>")
            index += 1
            continue
        if line.startswith("|") and index + 1 < len(lines) and set(lines[index + 1].replace("|", "").strip()) <= {"-", " ", ":"}:
            if in_list:
                out.append("</ul>")
                in_list = False
            header = [c.strip() for c in line.strip("|").split("|")]
            out.append("<table><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in header) + "</tr>")
            index += 2
            while index < len(lines) and lines[index].startswith("|"):
                cells = [c.strip() for c in lines[index].strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
                index += 1
            out.append("</table>")
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            if in_list:
                out.append("</ul>")
                in_list = False
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
        elif line.lstrip().startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(line.lstrip()[2:])}</li>")
        elif line.strip():
            if in_list:
                out.append("</ul>")
                in_list = False
            # HTML passthrough for the README's centered header block.
            if line.lstrip().startswith("<"):
                out.append(line)
            else:
                out.append(f"<p>{_inline(line)}</p>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
        index += 1
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def build(project: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    present = [name for name in SOURCES if (project / name).is_file()]
    nav = "<nav>" + "".join(
        f'<a href="{Path(name).stem}.html">{Path(name).stem.replace("_", " ")}</a>'
        for name in ["index.md"] + present if name != "index.md"
    ) + "</nav>"
    for name in present:
        body = render((project / name).read_text(encoding="utf-8"))
        page = (f"<!doctype html><meta charset='utf-8'>"
                f"<title>Godmode - {Path(name).stem}</title>"
                f"<style>{_STYLE}</style>{nav}{body}")
        (out / f"{Path(name).stem}.html").write_text(page, encoding="utf-8")
    listing = "".join(
        f'<li><a href="{Path(n).stem}.html">{Path(n).stem.replace("_", " ")}</a></li>'
        for n in present
    )
    (out / "index.html").write_text(
        f"<!doctype html><meta charset='utf-8'><title>Godmode documentation</title>"
        f"<style>{_STYLE}</style><h1>Godmode documentation</h1>"
        f"<p>Rendered offline from the repository's own Markdown; nothing loads from anywhere.</p>"
        f"<ul>{listing}</ul>", encoding="utf-8")
    return {"pages": len(present) + 1, "out": str(out)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="docs-site")
    parser.add_argument("--project", default=".")
    arguments = parser.parse_args()
    result = build(Path(arguments.project), Path(arguments.out))
    print(f"built {result['pages']} pages into {result['out']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
