# MATRIZ_M1_M10.md — disposición de hallazgos Qwen (v10r2r2)

| ID | Hallazgo | Disposición | Evidencia / cambio |
|---|---|---|---|
| **B-1** | `root` publicaba antes de bloquear | **CORREGIDO** | `check_c5_policy`: `C5_IMPLEMENTED=('aceptar_usuario',)`; `root` → `C5_NO_IMPLEMENTADA` en el gate. Test `test_root_fails_at_gate_not_after_move` + `test_script_root_mode_leaves_no_destination` (sin destino, sin COLOCADO). Protección sigue **NO implementada** (limitación expresa). |
| **B-2** | `du` fallo → GO | **CORREGIDO** | `measure_space_need/avail` con RC, `parse_positive_int` (vacío/no-numérico/0/negativo/overflow), `space-check` en el script. Tests `B2_SpaceGate` (5). Sin `NEED_KIB=0`. |
| **B-3** | Plan ≠ código | **CORREGIDO** | `PLAN_COLOCACION_v2.md` reescrito desde el código final: inventario, helper, rename_excl, 0 sudo activos, espacio vivo, C-5 gate. Sin `APP_MANIFIESTO` ni `mv -n`. |
| **I-1** | `resolve()` antes de `is_symlink()` | **CORREGIDO** | `inventory_tree` (helper y verificador): rechaza symlink **antes** de resolve. Tests `I1_InventoryRoot` (3). |
| **I-2** | Sin presupuesto antes de expand-full | **CORREGIDO** | `verify_offline_provenance`: `statvfs` vs `pkg_size+1GiB` antes de expandir. |
| **I-3** | Tests assertIn / `NEED_KIB=0` / aserción vacua | **CORREGIDO** | `test_correcciones_b_i.py` conductual; `test_colocacion_v2` reescrito; se retira aserción vacua. |
| **I-4** | `ignore_errors=True` en cleanup | **CORREGIDO** | `shutil.rmtree` sin `ignore_errors`; fallo → `I4_LIMPIEZA_FALLIDA` (no éxito silencioso). |
| **I-5** | PKG/app en `/var/tmp` sin comprobación | **CORREGIDO** | Script §0b e `verify_offline_provenance`: `I5_PKG_AUSENTE`/`I5_APP_AUSENTE` antes de efectos. |
| **M-1** | errno colapsado a 1 | **CORREGIDO** | `rename_excl` devuelve el errno real (17, 62, …). |
| **M-2** | `tree_inventory.py` / `apoyo_muse` código muerto | **NO APLICABLE a corrección funcional** | Se conservan como referencia en `apoyo_*`; productivo es `place_helper.inventory_tree`. |
| **M-3** | `FUENTE.md` inexistente | **CORREGIDO** | Se publica `FUENTE.md` en esta revisión. |
| **M-4** | Integración P2 §7/§8 sin adjudicar | **CORREGIDO** | Ver `MATRIZ_INTEGRACION.md` (adenda). |
| **M-5** | HILO apunta a v10r2 / 131 tests | **CORREGIDO** | `HILO_AUDITORIA_QWEN.md` actualizado a v10r2r2 y conteo real. |
| **M-6** | Matrices contradictorias en C-9/conteos | **CORREGIDO** | Esta matriz + PLAN son la fuente vigente; las anteriores quedan como histórico de v10r2r1. |
| **M-7** | Diff sin exclusiones explícitas | **CORREGIDO** | `OT07_v10r2r1_a_v10r2r2.diff` + lista de exclusiones en el recibo. |
| **M-8** | Sondeo constructor ajustable por entorno | **RESIDUAL** | Fuera del alcance de esta corrección (núcleo heredado sin cambio demostrado); se registra para E. |
| **M-9** | `test_flow` frágil ante TMPDIR | **CORREGIDO** | Sustitución acotada a `/var/tmp/ot07_`. |
| **M-10** | `"identical": false` sin explicar transform | **CORREGIDO** | `CHAIN_REPORT` y `FUENTE.md` declaran `identical_except_postinstall` y las 2 adiciones. |

## Pendientes nativos (NO acreditados, se conservan)

C-5 operacional (decisión OPERADOR + implementación), `Assets[0]`, `hdiutil verify`,
colocación real, OCLP, ensayo EOF del supervisor, picker/arranque.
