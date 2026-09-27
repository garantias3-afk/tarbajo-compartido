# DIFF r4 → r5 — resumen del delta

Base r4 (solo lectura, sellado): `OT07_REVISION_v10r2r4` manifiesto
`17dafa9390342cc857f5721be8e1604f6c5df7434267b0c5d3f611a1f7cc2b41`.
P5r (prototipo sintético): manifiesto `b3cad248…1b7f5`.
Este paquete r5 es **copia nueva**; no se modifican sellados históricos.

## Qué cambia y por qué

| Área | r4 / P5r | r5 | Motivo (criterio) |
|---|---|---|---|
| Protección | `chown -R -h` en comentario tras rename (§8); `aceptar_usuario` | **Dirección B**: F3–F10 con frontera ANTES de publicar; helper C con `lchown(2)` real | OT punto 2; N1/N2 |
| Referencias abiertas | no resueltas | inodos finales creados dentro de frontera controlada por el helper; fd previo no alcanza el objeto consumido | N2; 04_AJUSTES §3 |
| Primitivas | pseudocomando `lchown -R -h`; RESOLVE_BENEATH mencionado | `lchown(2)`, `fchmodat`, `openat`, `fstatat+AT_UNIQUE`, `renamex_np(RENAME_EXCL\|RENAME_NOFOLLOW_ANY)`, `acl_*`; RESOLVE_BENEATH **no** se porta | 04_AJUSTES §1–2; N4 |
| Constantes | — | `RENAME_NOFOLLOW_ANY=0x10` verificado en `sys/stdio.h` (el intento 0x80 falló EINVAL) | N4; BUILD.md |
| ACL | ciega / registro | `c5_acl.py` leer/validar/normalizar/rechazar; separar escritura vs eliminación; deny-write como defensa en profundidad | N3; 04_AJUSTES §4–5 |
| Ancla | hash del archivo | C-1: snapshot único + hash externo fijo + evidencia autenticada; `DELEGADA` si solo archivo+hash | N5; OT punto 4 |
| Bootstrap | sudo de python/bash | `c5_bootstrap.py` identifica binario/intérprete/deps/hash dentro de frontera; helper C único binario H1 | N0; OT punto 7 |
| Estados | HB-3 en P5r | conservado `_verdict_por_estado`; RC=3 limpieza; EEXIST sin anidar | N6 |
| Errata codesign_cim | puntero vacío sin puntuar | `docs/INDICE_HISTORICO_R5.md` lo puntúa: vacío = no acreditado | OT punto 6 |
| Errata sensibilidad | `sensitivity.txt` efímero | `evidencia_r5/SENSIBILIDAD.json` con base/mutante/comando/RC/aserción | OT punto 6 |
| Conteos | 176 r4 / 47 P5r fijos | **dinámicos** en HARNESS_RESULTADOS | OT punto 6 |
| Legacy | productivos r4 | copia byte-idéntica en `src/legacy/` (guard, process, place_helper, verificar_instalador) | N9 |
| Dirección | `aceptar_usuario` o chown post-rename | **B** elegida y usada; `aceptar_usuario` no es atajo | OT punto 2; maestra |

## Archivos nuevos (no existían en r4)

- `INTERFAZ_C5.json` — contrato temprano
- `src/c5_helper.c` — helper limitado (no runner de shell)
- `src/c5_orquestador.py` — flujo F0–F10 dirección B
- `src/c5_ancla.py` — ancla C-1
- `src/c5_acl.py` — política ACL
- `src/c5_bootstrap.py` — bootstrap H1
- `tests/harness_r5.py` — 35 casos dinámicos
- `docs/INDICE_HISTORICO_R5.md`, `docs/MAPA_N0_N9.md`, `docs/PROCEDIMIENTO_H1.md`, `docs/BUILD.md`
- `evidencia_r5/SENSIBILIDAD.json`, `evidencia_r5/HARNESS_RESULTADOS.json`
- `build/c5_helper` — binario compilado

## Archivos heredados (byte-idénticos de r4)

- `src/legacy/ot07_guard.py`
- `src/legacy/ot07_process.py`
- `src/legacy/place_helper.py`
- `src/legacy/verificar_instalador.py`

## Qué NO cambia (fuera de alcance)

- USB / `createinstallmedia` / borrado (H2)
- Arranque / OCLP / picker (H3)
- Reparación APFS / originales iMac
- Suites r4 176 casos re-ejecutadas (se conservan; se corrigen solo erratas documentales)
