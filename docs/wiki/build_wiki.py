"""Verzia reportu pre DokuWiki: python docs/wiki/build_wiki.py

1. Kazdy mermaid diagram z docs/odovzdanie1.md vykresli do PNG (lokalny Chromium + mermaid.min.js).
2. Report prevedie pandocom do syntaxe DokuWiki, diagramy nahradi obrazkami a odkazy na kod
   na GitHube nahradi obycajnym textom.

Vystup: docs/wiki/odovzdanie1.dokuwiki a obrazky docs/wiki/img/*.png (nahrat do media managera
v tom istom namespace ako stranka).
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parent / "odovzdanie1.md"
OUT = ROOT / "odovzdanie1.dokuwiki"
IMG = ROOT / "img"
BUILD = ROOT / "build"  # snap Chromium nevidi skryte priecinky ani /tmp, preto docasne subory tu
MERMAID_JS = Path.home() / ".vscode/extensions/shd101wyy.markdown-preview-enhanced-0.8.40/crossnote/dependencies/mermaid/mermaid.min.js"
CHROMIUM = shutil.which("chromium") or "/snap/bin/chromium"

# mena obrazkov v poradi, v akom su diagramy v reporte
NAMES = ["architektura", "crawler", "spracovanie_url", "extraktor", "stavba_indexu",
         "cli_kaskada", "vyhladavanie", "podobne_kapely"]
PREFIX = "odovzdanie1_"

MERMAID = re.compile(r"```mermaid\n(.*?)```", re.S)
CODE_LINK = re.compile(r"\[([^\]]+)\]\(https://github\.com/K-o-m-A/vinf/(?:blob|tree)/[^)]+\)")

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>body {{ margin: 0; padding: 24px; background: white; display: inline-block; }}</style>
<script src="mermaid.min.js"></script></head><body><div id="out"></div><script>
mermaid.initialize({{ startOnLoad: false, theme: "default", flowchart: {{ useMaxWidth: false }},
                      sequence: {{ useMaxWidth: false }}, fontFamily: "Arial, sans-serif" }});
mermaid.render("d", {code}).then(r => {{ document.getElementById("out").innerHTML = r.svg; }});
</script></body></html>"""


def render(code, png):
    html = BUILD / "diagram.html"
    html.write_text(PAGE.format(code=json.dumps(code)), encoding="utf-8")
    shot = BUILD / "shot.png"
    subprocess.run([CHROMIUM, "--headless", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=2", "--window-size=3200,4000",
                    "--virtual-time-budget=8000", f"--screenshot={shot}", html.as_uri()],
                   check=True, capture_output=True)
    # oreze biely okraj a necha 20 px
    subprocess.run(["convert", str(shot), "-trim", "+repage", "-bordercolor", "white",
                    "-border", "20", str(png)], check=True)


def png_width(path):
    # sirka PNG je v hlavicke IHDR na bajtoch 16-19
    return int.from_bytes(path.read_bytes()[16:20], "big")


def main():
    text = REPORT.read_text(encoding="utf-8")
    diagrams = MERMAID.findall(text)
    assert len(diagrams) == len(NAMES), f"v reporte je {len(diagrams)} diagramov, mien je {len(NAMES)}"

    BUILD.mkdir(exist_ok=True)
    IMG.mkdir(exist_ok=True)
    shutil.copy(MERMAID_JS, BUILD / "mermaid.min.js")
    for code, name in zip(diagrams, NAMES):
        render(code, IMG / f"{PREFIX}{name}.png")
        print("diagram", name)
    shutil.rmtree(BUILD)

    # diagram -> znacka, ktoru pandoc nechá ako text; po prevode ju nahradi obrazok
    names = iter(NAMES)
    text = MERMAID.sub(lambda m: f"\nDIAGRAM{next(names).upper()}\n", text)
    text = CODE_LINK.sub(r"\1", text)
    wiki = subprocess.run(["pandoc", "-f", "gfm", "-t", "dokuwiki", "--wrap=none"],
                          input=text, capture_output=True, text=True, check=True).stdout
    for name in NAMES:
        # obrazok je v 2x rozliseni, na wiki sa zobrazi v polovicnej sirke (najviac 900 px)
        width = min(900, png_width(IMG / f"{PREFIX}{name}.png") // 2)
        wiki = wiki.replace(f"DIAGRAM{name.upper()}", f"{{{{{PREFIX}{name}.png?{width}&nolink|}}}}")
    # dlhe a stredne pomlcky (aj "---", z ktoreho DokuWiki urobi dlhu pomlcku) -> obycajna "-"
    wiki = wiki.replace("—", "-").replace("–", "-").replace("---", "-")
    OUT.write_text(wiki, encoding="utf-8")
    print("hotovo:", OUT)


if __name__ == "__main__":
    main()
