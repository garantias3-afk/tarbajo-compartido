# PLAN_COLOCACION — v10r2r2 (coherente con el código sellado)

Este documento describe **exactamente** `colocacion_v2/colocar_candidato.sh` v3
y `place_helper.py` de esta revisión. Si algo no está en ese código, no es un
requisito operativo aprobado.

## Identidad pineada (nunca del candidato)

| Campo | Valor |
|---|---|
| PKG | `/var/tmp/ot07_E2R1_candidato.gMdKSX/InstallAssistant.pkg` |
| PKG_BYTES | 13654790295 |
| PKG_SHA256 | `ecc36bf172105f8c3325ceeb4e5ab8cc297260be806eac10b21b784ff40d8173` |
| Firma | `pkgutil --check-signature` → `signed Apple Software` + `Apple Root CA` |
| Inventario ref | `evidencia_impl/inv_extracted_app.json` (cadena PKG) |
| **NO se usa** | `APP_MANIFIESTO.txt` ni `shasum --check` |

**I-5:** PKG y app viven en `/var/tmp`. El script **falla antes de efectos** si no
existen (`I5_PKG_AUSENTE` / `I5_APP_AUSENTE`). No se reconstruyen por nombre ni fecha.

## Política C-5 (gate ANTES de cualquier efecto)

| Modo | ¿Implementada? | Comportamiento |
|---|---|---|
| `REQUIERE_DECISION_C5` (default) | — | **Bloquea** `C5_NO_DECIDIDA` |
| `root` | **NO** | **Bloquea** `C5_NO_IMPLEMENTADA` (B-1: nunca publica primero) |
| `aceptar_usuario` | Sí (aceptación del operador) | Pasa el gate; queda en `C5_MODO` |
| otro / vacío | — | **Bloquea** `C5_INVALIDA` |

Protección `root` (`chown -R -h root:wheel` + `chmod -R go-w`) está **preparada
en comentario** y requiere decisión escrita de OPERADOR + re-auditoría antes de
activarse. Hoy **no** hay protección de propiedad implementada: si se elige
`aceptar_usuario`, el bundle queda `OPERADOR:wheel` y `createinstallmedia`
correría como root desde ese árbol — límite que debe constar en la evidencia de E.

## Secuencia real del script

0. **C-5 gate** (`place_helper c5-gate`) — aborta sin tocar nada.
0b. **I-5** inputs PKG/app existentes y no-symlink.
1. PKG: bytes, SHA-256 pineado, `pkgutil --check-signature` (RC, `LC_ALL=C`, sin pipe).
2. Origen + **inventario exacto** (`inventory`/`compare-inv`) vs referencia PKG.
3. **Espacio vivo** (`space-check`): `du -sk` RC validado, entero `>0`, +2 GiB
   reserva, `df` RC validado; cualquier herramienta fallo ⇒ aborta (B-2).
4. Destino inexistente; padre `dirname` real no-symlink; `same-fs` (`st_dev`).
5. Staging `mktemp -d` en `/private/var/tmp`; `ditto`; inventario staging == origen.
6. Re-check destino/padre.
7. **`rename-excl`** = `renamex_np(RENAME_EXCL|RENAME_NOFOLLOW_ANY)` vía ctypes.
   RC 0 = movido; **errno** (17 EEXIST, 62 ELOOP, …) = fallo sin anidar. Sin `mv -n`.
8. Inventario final == origen. Limpieza de temporales propios (error de limpieza
   se reporta, no se silencia).
9. Si modo=root → falla `NO_ACTIVO` (no implementado).

## Sudo

**Cero sudo activos** en el script actual. Las líneas `sudo` son comentarios de
la futura protección C-5. `sudo -v` y lock de etapa son responsabilidad del
operador de E, no de este script.

## Espacio

Medido en vivo (`du` origen + 2 GiB vs `df` del padre destino). **Sin** constante
38 GiB como suficiencia universal. El pico de la cadena completa (PKG+expansión+
staging) se documenta en FUENTE; el gate vinculante es `space-check`.

## Pruebas asociadas

`tests/test_correcciones_b_i.py` (B-1/B-2/I-1 conductuales),
`tests/test_place_v10r2r1.py` (rename_excl, C-5, inventario),
`tests/test_colocacion_v2.py` (flujo sintético). Ver `MATRIZ_M1_M10.md`.
