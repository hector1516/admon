"""Comprueba que los assets estáticos no se vayan de peso (Admon).

- **Falla** si `public/autos/` tiene PNG, si una imagen de esa carpeta pasa de
  MAX_KB o si falta el `.webp` de algún slug de `getAutoImage()`.
- **Avisa** (sin fallar) de las demás imágenes pesadas: esas vienen subidas por
  el usuario o se sirven desde la base y se tratan en otra fase.

Uso:  python scripts/check_assets.py     (sale con 1 si falla)
"""
import io
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.path.join(RAIZ, "public")
AUTOIMAGE = os.path.join(RAIZ, "src", "lib", "autoImage.js")

MAX_KB = 200
RASTER = (".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif")
CONTROLADAS = ("autos",)


def imagenes():
    for raiz, _, ficheros in os.walk(PUBLIC):
        for f in ficheros:
            if f.lower().endswith(RASTER):
                ruta = os.path.join(raiz, f)
                yield ruta, os.path.getsize(ruta) / 1024


def slugs_de_autos():
    texto = io.open(AUTOIMAGE, encoding="utf-8").read()
    bloque = re.search(r"available\s*=\s*\[(.*?)\]", texto, re.S)
    if not bloque:
        return None
    return re.findall(r"'([^']+)'", bloque.group(1))


def main():
    problemas = []
    avisos = []

    for ruta, kb in imagenes():
        rel = os.path.relpath(ruta, PUBLIC).replace(os.sep, "/")
        controlada = rel.split("/")[0] in CONTROLADAS
        if controlada and kb > MAX_KB:
            problemas.append(f"{rel}: {kb:.0f} KB (máximo {MAX_KB} KB)")
        elif not controlada and kb > MAX_KB:
            avisos.append(f"{rel}: {kb:.0f} KB (fuera de las carpetas controladas)")

    slugs = slugs_de_autos()
    if slugs is None:
        problemas.append("no pude leer la lista `available` de src/lib/autoImage.js")
    else:
        for slug in slugs:
            if not os.path.isfile(os.path.join(PUBLIC, "autos", f"{slug}.webp")):
                problemas.append(f"falta public/autos/{slug}.webp")
        for f in sorted(os.listdir(os.path.join(PUBLIC, "autos"))):
            if f.lower().endswith((".png", ".jpg", ".jpeg")):
                problemas.append(f"public/autos/{f}: quedó el original sin convertir")

    for a in avisos:
        print(f"[AVISO] {a}")
    for p in problemas:
        print(f"[PESO ] {p}")
    print(f"\n{len(problemas)} problemas, {len(avisos)} avisos" if problemas or avisos else "\nAssets OK")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
