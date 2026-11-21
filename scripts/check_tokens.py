#!/usr/bin/env python3
"""check_tokens.py — falla si un color de la paleta aparece hardcodeado.

Lee los tokens de `src/app.css` (que genera y sincroniza ECCSA-Shell) y busca
esos mismos hex en los componentes. Si están escritos a mano, es que alguien
esquivó el token: se cambia el diseño en el shell y esa pantalla se queda atrás.

Uso:  python3 scripts/check_tokens.py [--verbose]
Sale 1 si encuentra alguno.
"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_CSS = os.path.join(RAIZ, "src", "app.css")
SRC = os.path.join(RAIZ, "src")

# --color-x: #RRGGBB  (también acepta #RGB)
TOKEN = re.compile(r"--color-[a-z0-9-]+\s*:\s*(#[0-9a-fA-F]{3,8})\s*;")
BLOQUE_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)
COMENTARIO = re.compile(r"<!--.*?-->", re.S)
HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")


def expandir(h):
    h = h.upper()
    if len(h) == 4:  # #RGB -> #RRGGBB
        return "#" + "".join(c * 2 for c in h[1:])
    return h


def paleta():
    if not os.path.isfile(APP_CSS):
        print(f"AVISO: no existe {APP_CSS}; no se puede comprobar", file=sys.stderr)
        return {}
    texto = open(APP_CSS, encoding="utf-8", errors="replace").read()
    return {expandir(h): h for h in TOKEN.findall(texto)}


def main():
    verbose = "--verbose" in sys.argv
    tokens = paleta()
    if not tokens:
        return 0
    violaciones = []
    revisados = 0
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist")]
        for f in files:
            if not f.endswith(".svelte"):
                continue
            p = os.path.join(root, f)
            revisados += 1
            s = open(p, encoding="utf-8", errors="replace").read()
            # Sustituir por saltos de línea (no borrar) para no mover los números.
            s = BLOQUE_SCRIPT.sub(lambda m: "\n" * m.group(0).count("\n"), s)
            s = COMENTARIO.sub(lambda m: "\n" * m.group(0).count("\n"), s)
            for i, linea in enumerate(s.splitlines()):
                for h in HEX.findall(linea):
                    clave = expandir(h)
                    if clave in tokens:
                        violaciones.append(
                            f"{os.path.relpath(p, RAIZ)}:{i + 1}  {h} "
                            f"(usar var(--color-...))")
    if violaciones:
        print(f"FAIL: {len(violaciones)} colores de la paleta hardcodeados "
              f"en {revisados} componentes:")
        for v in violaciones[:60]:
            print("  " + v)
        if len(violaciones) > 60:
            print(f"  ... y {len(violaciones) - 60} más")
        return 1
    if verbose:
        print(f"OK: 0 colores hardcodeados en {revisados} componentes "
              f"({len(tokens)} tokens revisados)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
