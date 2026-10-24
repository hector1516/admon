# Reglas de actualización — admon

Cómo se despliega **admon**. Mismo proceso que las otras cinco apps: la imagen la
construye la CI **en la nube** y Arcane es el único que administra el contenedor.

## Las tres reglas

1. **Tú haces el código y el push. Nada más.**
2. **La CI construye y publica.** El servidor no compila.
3. **El operador da `Update` en Arcane.** Sin ese paso, la imagen nueva existe pero
   nadie la aplica.

## Cómo actualizar

```
1. Modificas el código
2. git commit + git push origin master
3. CI construye en ubuntu-latest y publica en ghcr.io/hector1516/admon
4. Arcane → Projects → admon → Updates → Update
```

## Dónde mirar

| | |
|---|---|
| Paquete | `admon` |
| Imagen | `ghcr.io/hector1516/admon` |
| Repositorio | [hector1516/admon](https://github.com/hector1516/admon) |
| Workflow | `.github/workflows/build-image.yml` |
| Jobs | build |
| Puertos | 8103 → 8000 (uvicorn) |
| Salud | GET /health (200) |
| ¿Toca el servidor? | Sí |

## Comprobar que salió bien

Antes de ir a Arcane, mira que los jobs estén en verde:

```
https://github.com/hector1516/admon/actions
```

build-image.yml · build

Arcane: `https://docker.ecc-sa.com.mx` → **Projects → admon → Updates**.
Ahí debe aparecer la imagen nueva con un digest distinto. Ahí es donde aplicas.

Si el job `deploy` aparece (cuando existe), el mensaje
`ATENCION: lo administra Arcane: no lo recreo` es **correcto**, no un error: el guard
impide que la CI toque el contenedor.

## Qué NO hacer

- **No** ejecutar `docker run`, `docker rm`, `docker restart` ni `docker cp` sobre el
  contenedor. Arcane es el dueño; si le quitas el contenedor, el Project queda roto.
- **No** correr `/opt/apps/_lib/run_app.sh admon` — es el camino legacy y recrea por
  fuera de Arcane.
- **No** hacer `docker compose up -d` con el mismo directorio del Project.
- **No** cambiar el nombre del paquete a `${{ github.repository }}` si el repo y el
  paquete se llaman distinto (ver notas de admon).
- **No** compilar en el servidor. Para eso está `ubuntu-latest`.

## Qué pasa si algo sale mal

**El workflow falla.** No toques el contenedor. Lee el log en GitHub Actions; el
servidor sigue con la imagen anterior y Arcane nunca vio nada.

**El contenedor no arranca tras el `Update`.** En Arcane: *Logs*. Para volver atrás,
revierte el commit en GitHub, deja que la CI publique la versión anterior y da
`Update` otra vez.

**Arcane no muestra actualización.** Comprueba en el server que la imagen se puede
bajar:

```bash
docker manifest inspect ghcr.io/hector1516/admon:latest && echo OK || echo BLOQUEADO
```

Si sale `BLOQUEADO` o `unauthorized`, el paquete está **privado**. Es la causa más
frecuente. Ver la sección siguiente.

## Paquetes: dos cosas que hay que saber

**El paquete hereda la visibilidad del repo.** Nace privado si el repo es privado.
Cambiar el repo a público *después* no arregla un paquete ya creado.

**`GITHUB_TOKEN` solo publica a paquetes enlazados al repo.** Un paquete creado con
push manual nunca queda enlazado, y el push falla con `write_package denied` aunque
los permisos del YAML estén correctos. La cura: borrar el paquete y dejar que la CI
lo recree.

## Notas de admon

`admon` es la app más crítica: es la que usan los clientes. Con cuidado
extra al hacer rollback.

Su Dockerfile arma el frontend (Vite) en una etapa `node:20-alpine` dentro del mismo
build. Antes el `npm run build` corría en el servidor; moverlo a la nube fue lo que
liberó CPU y RAM de la máquina.

El job `deploy` baja el tag **por sha** (`IMAGE_REF`), no `:latest`, para que dos
builds en paralelo no se pisen. Es la única de las seis con este detalle.

---

_estandarizado el 2026-10-08 junto a admon, mailbox, dashboard, colaboradores,
workersadmon y field._
