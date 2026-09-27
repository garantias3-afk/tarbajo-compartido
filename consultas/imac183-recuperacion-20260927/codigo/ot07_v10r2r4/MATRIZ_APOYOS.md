# MATRIZ_APOYOS.md — F-3: disposición de P2/P3/P4 por hallazgo

Reglas: cada fila identifica revisión+sello del apoyo, resultado **en esa revisión**,
estado en r2/r3 y prueba/lectura. No se fuerza un número de cierre. P3/P4 no
validan r2/r3; sus fallos sobre r1/P2 no se atribuyen a r2.

## Cronología (importante)

| Apoyo | Revisión que ensayó | Sello | Cierre/entrega | Relación con r2/r3 |
|---|---|---|---|---|
| P2 Flash | snapshot P2 (`colocar_candidato_v2.sh`) | 22/22 `3751360c…` | antes de r2 | Insumo integrado en r2 con rechazo del binario |
| P3 Flash | snapshot P2 + propuesta v3 propia | 18 entradas `877a0b2b…` | inicio 23:10:56Z; **posterior al cierre r2 (22:54Z)** | No valida r2; se evalúa ahora |
| P4 Flash | **snapshot r1** (`d979460b…`) | sello P4 | posterior al cierre r2 | Reproduce NO-GO Qwen sobre r1; **no** son fallos de r2 |

## Disposición por hallazgo

### P2 §7/§8 → ver `ADENDA_P2_7_8.md` (F-2)

### P3 (MATRIZ_P3) — evaluación sobre r3

| Hallazgo P3 | Resultado en P3 | Estado en r2 (MiMo) | Disposición r3 | Prueba/lectura |
|---|---|---|---|---|
| C-5 tardío (destino antes de RC3) | CONFIRMADO en P2 | B-1 **CORREGIDO** (gate previo) | **CERRADO en r2**; P3 no lo vio | `tests/test_correcciones_b_i.py` B1 |
| MODO inválido deja destino | CONFIRMADO P2 | B-1 **CORREGIDO** | **CERRADO** | idem |
| Link interno invisible al inventario | P3 P2 | Inventarios r2 comparan sha256 por ruta | **RESIDUAL** (link interno sin referencia PKG) | `FUENTE.md` / límites |
| Dir extra vacío llega al destino | P3 P2 | `compare-inv` exige igualdad exacta de `entries` | **CORREGIDO en r2** (dir extra ⇒ `only_in_b` no vacío ⇒ fail) | `test_inventory_detects_extra_dir` |
| Manifiesto+app alterados juntos | P3 P2 | r2 usa inventario anclado a PKG, no `APP_MANIFIESTO` | **CERRADO en r2** | `compare-inv` vs `inv_extracted_app.json` |
| FIFO bloquearía inventario | inspección P3 | `inventory_tree` rechaza tipos especiales | **CORREGIDO** (fail-closed) | `verificar_instalador`/`place_helper` |
| Escape transitivo / ciclo / link roto | P3 P2 pasaba | r2: `resolve(strict=True)` + relative_to(root) | **CERRADO en r2** | `test_absolute/dotdot_symlink_rejected` |
| `/usr/bin/rmdir`/`chmod` ausentes | P3 runtime | Script usa `/bin/mkdir`, `rmdir` del shell | **NO APLICABLE a r2** (diferente implementación) | lectura `colocar_candidato.sh` |
| Alias /var ELOOP | P3 ctypes | r2 `physical_path()` mapea alias | **CERRADO en r2** | `test_rename_excl_preserves_eexist_and_eloop` |
| realpath legitima padre hostil | P3 límite | r2 exige padre no-symlink + alias enumerados | **RESIDUAL declarado** | `PLAN_COLOCACION_v2.md` |
| Inventario `f.read()` completo | P3 | r2 usa bloques de 1 MiB | **CERRADO en r2** | `sha256_file` |
| RSS 17.4 MB / límite stat | P3 recomendación | parcial (bloques) | **RESIDUAL** (sin límite duro stat) | lectura |
| sudo post-traslado / aceptar_usuario 0 sudo | informativo | r2: 0 sudo activos; root NO_ACTIVO | **COHERENTE** | script §8 |
| Fuzz 120 mutaciones | P3 OK sobre P3 v3 | — | **REFERENCIA** (sobre snapshot P2) | `pruebas/` de P3 |

### P4 (MATRIZ_P4) — evaluación sobre r3

| Paquete P4 | Resultado en r1 | Estado en r2/r3 | Disposición |
|---|---|---|---|
| B-1 root publica | CONFIRMADO r1 | **CORREGIDO r2** | **CERRADO**; P4 no ensayó r2 |
| B-2 du/df | CONFIRMADO r1 | **CORREGIDO r2** | **CERRADO** |
| I-1 symlink root | CONFIRMADO r1 | **CORREGIDO r2** | **CERRADO** |
| I-2 expand sin presupuesto | CONFIRMADO r1 | **CORREGIDO r2** | **CERRADO** |
| I-4 INV retenido | CONFIRMADO r1 | Parcial (cleanup reporta error; retención residual) | **RESIDUAL** documentado |
| I-5 disponibilidad ≠ autenticidad | P4 r1 | r2 falla si falta input; autenticidad = PKG pineado | **COHERENTE** con C-1 |
| Aserción vacua / NEED_KIB=0 | CONFIRMADO r1 | **CORREGIDO r3 (F-1)** | **CERRADO en r3** |
| M-9 TMPDIR | parcial P4 | **CORregido r2 + tests r3 (F-5)** | ver `test_f5_tmpdir.py` |
| B-3 PLAN contradicciones | CONFIRMADO r1 | **CORREGIDO r2** | **CERRADO** |

## Incorporación efectiva en r3

| Origen | ¿Se incorpora? | Cómo |
|---|---|---|
| P2 §7/§8 | Sí (documental) | `ADENDA_P2_7_8.md` |
| P3 (bancos fuzz/dir extra) | Parcial | Casos ya cubiertos en r2 se citan; límites residuales se declaran |
| P4 (oráculos B-1/B-2/I-*) | Sí como referencia de regresión | Mismos invariantes; ejecutados sobre r2/r3, **no** se copian fallos de r1 |
| Propuesta v3 de P3 | **No como producto** | El producto es `colocar_candidato.sh` r2/r3 congelado |
