# DIFF r6 → r6b — dos correcciones de una línea (más opcionales)

Base r6 sellada: `OT07_REVISION_v10r2r6_MIMO` manifiesto
`4fa65e4fe69de4e5408b64e31c1ad65f283980e1569839397481deb268736b6d`
**no se edita**. Este paquete es r6b.

## Fixes obligatorios

### R6-1 — fail-closed real en F6

| | |
|---|---|
| Defecto | `except acl_mod.AclPolicyError: pass` engullía el fail-closed y el flujo publicaba `PUBLICADO_VERIFICADO rc=0` con ACE allow-write / ACL ilegible |
| Fix | ese `except` ahora aborta `ABORTADO_STAGING_RETENIDO` (rc=2), sin publicar |
| Archivo | `src/c5_orquestador.py` (F6) |
| Oráculos | `c5-r6-10b`, `c5-r6-10b-det` + reproducción real en `evidencia_r6b/REPRODUCCION_R6B.json` |

### F-R6-N3-1 — nombres de permisos de `ls -le`

| | |
|---|---|
| Defecto | `DERECHOS_ESCRITURA` solo tenía nombres NFSv4 (`write_data`, `append_data`); `ls -le` imprime `write`, `append` ⇒ ACEs reales no se detectaban |
| Fix | añadir aliases `write`, `append`, `writeattr`, `writeextattr` al conjunto |
| Archivo | `src/c5_acl.py` (`DERECHOS_ESCRITURA`) |
| Oráculos | `c5-r6-09b` + reproducción real `chmod +a 'user:OPERADOR allow write/append'` (detectada=True; `allow read` sigue sin detectarse) |

## Opcionales (misma revisión)

| ID | Cambio |
|---|---|
| R6-2 | Títulos de N2-04/N2-06: no sobreafirman en simulated; la aserción fuerte vive en H1-N2 nativo |
| R6-3 | Eliminado el bloque «Primitivas REALES» duplicado en el header de `c5_helper.c` |
| R6-4 | Documentado en el header del helper que el confinamiento estricto viene de `C5_AUTH_BASE` (strstr del prefijo no basta) |

## Decisión sobre casos Flash c5-r6-09 / c5-r6-10

**Re-ejecutados desde MiMo con runner propio** (la carpeta R2 de Flash es de solo lectura):
- equivalentes `c5-r6-09b` y `c5-r6-10b`/`c5-r6-10b-det` en `tests/harness_r5.py`
- reproducción con `chmod +a` real y `validar_acl` en `evidencia_r6b/REPRODUCCION_R6B.json`
- si Max lo prefiere, Flash puede re-correr su batería completa tras este sello

## Harness

- r6: 48/48 · r6b: **52/52** (+4: `c5-r6-09b`, `c5-r6-10b`, `c5-r6-10b-det`, `R6-4`)
- Conteos dinámicos. Evidencia: `evidencia_r6b/HARNESS_RESULTADOS.json`

## Qué NO cambia

Frontera H-R5-1, re-pin H-R5-2, veredictos H-R5-3, cableado H-R5-4, confinamiento H-R5-5, legacy r4, sin root/USB/arranque.
