# MATRIZ_INTEGRACION.md — OT07 v10r2r1 (integración Flash P2 + correcciones)

Sello Flash P2: `SHA256SUMS.txt` = `3751360c8f0409027d0f95150d92057c1164314bc9e7182ace26e9bde2c56c50`
(22/22 OK, verificado por mí). Sus 21/21 son autorreporte; **no** acreditan mi código.
Muse P1: 9/9, integrado en la revisión anterior (se conserva `apoyo_muse_p1/`).

## Decisión por hallazgo del encargo 01_ENCARGO_MIMO_INTEGRAR_P2

### 1. Prevenir escritura indebida en traslado — **INTEGRADO (con corrección propia)**

| Flash propone | Mi integración | Motivo |
|---|---|---|
| Binario `mv_excl` compilado | **No se usa el binario** de Flash | Problema de confianza de binario de usuario como root |
| `renamex_np(RENAME_EXCL\|RENAME_NOFOLLOW_ANY)` | **Sí**, vía **ctypes** en `place_helper.py` | Misma semántica, sin binario externo |
| Rutas `/var/tmp` | **Rutas físicas** `physical_path()` | Comprobado: `RENAME_NOFOLLOW_ANY` da **ELOOP (62)** con prefijo `/var` (symlink). Flash lo documenta como límite; yo lo resuelvo |

Pruebas propias (`test_place_v10r2r1.RenameExclTests`, 5):
- destino ausente → RC=0, **no anida**
- destino directorio → RC=17 EEXIST, conserva `OTHER`, no anida
- destino archivo → RC=17
- destino symlink → RC=17/1, **no escribe** dentro del árbol ajeno
- dos contendientes → un ganador (0) y un perdedor (17)

`mv -n` **eliminado** del script. La detección post-movimiento queda como
postcondición, no como mecanismo de prevención.

### 2. C-5 debe bloquear ANTES de colocar — **INTEGRADO**

- `ph c5-gate "$MODO_PROTECCION"` es la **primera** acción del script, antes de
  PKG, staging, ditto o rename.
- Default `REQUIERE_DECISION_C5` → `C5_NO_DECIDIDA`, sin destino ni efectos.
- `root` pasa el gate pero el script **falla** con `NO_ACTIVO` (chown/chmod
  comentado, a re-auditar). No imprime `COLOCADO_VERIFICADO` con protección
  pendiente.
- `aceptar_usuario` permite completar para pruebas; queda registrado en `C5_MODO`.
- Tests: `test_c5_default_blocks_before_any_destination`, `test_c5_unknown_blocks`,
  `test_script_requires_gate_before_ditto_or_move`.

### 3. Integridad/procedencia antes de publicación — **INTEGRADO**

- Reemplaza `APP_MANIFIESTO.txt` + `shasum -c` por `inventory_tree` propio
  (dirs + regular size/sha256 + symlink targets) contra
  `evidencia_impl/inv_extracted_app.json` (de la cadena PKG).
- Detecta tamper de igual tamaño, extras y faltantes (`test_inventory_detects_*`).
- Enlaces: absolutos, `..`, resolución fuera de raíz, tipos especiales.
- Lectura por bloques de 1 MiB (no `f.read()` del DMG entero).
- Flash: se conserva su `mv_excl.c` como referencia en `apoyo_flash_p2/`; no es
  la primitiva en producción.

### 4. Staging/espacio — **INTEGRADO**

- `mktemp -d` en `/private/var/tmp` (exclusivo, no reutilizable).
- `same-fs` via `st_dev` (no comparar salidas vacías de `stat`).
- Espacio vivo: `du -sk` origen + 2 GiB reserva vs `df` del padre destino.
  Sin constante universal 38 GiB.

### 5. Pruebas contra código integrado — **INTEGRADO**

| Batería | Cantidad | Resultado |
|---|---|---|
| `test_place_v10r2r1.py` (nuevo) | 16 | OK |
| `test_colocacion_v2.py` (reescrito a v3) | 8 | OK |
| Regresión (guards/process/flow/verifier/…) | 122 | OK |
| **Total discover** | **146** | **OK** |

Incluye: destino aparecido antes del rename (EEXIST), C-5 sin efectos,
inventario alterado, padre symlink, PKG ausente. Negativos miden
«sin `COLOCADO_VERIFICADO` **y** sin destino creado».

Muse: sus 24/24 son sobre su comparador. Mis invariantes equivalentes se prueban
en `test_verifier_v10r2` + `test_place_v10r2r1` sobre **mi** código.

## Rechazos técnicos justificados

| Item | Decisión |
|---|---|
| Binario `mv_excl` de Flash | **Rechazado** como primitiva de producción (confianza de binario); se reimplementa por ctypes |
| `colocar_candidato_v2.sh` de Flash completo | **No copiado**; se integran semántica y lecciones (C-5, rename_excl, inventario, espacio vivo) en mi script v3 |
| `MODO=root` ejecutando chown/chmod | **Preparado, NO_ACTIVO**; requiere decisión + re-auditoría |
| Normalizar padre hostil con realpath y decir «rechazado» | **No**; se exige padre real no-symlink y alias solo `/var`↔`/private/var`, `/tmp`↔`/private/tmp` |

## Diferencias de alcance (84 archivos base vs entregas)

- v10r1 = 83 entradas manifiesto / 84 archivos (incluye manifiesto).
- v10r2 = 42 entradas (software + docs + evidencia_impl + apoyo_muse).
- v10r2r1 = software v10r2 + `place_helper.py` + tests nuevos + script v3 +
  esta matriz. Los ZIP/recibo de v10r2 **no se modifican**.
