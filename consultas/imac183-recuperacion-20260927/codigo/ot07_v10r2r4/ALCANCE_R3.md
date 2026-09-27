# ALCANCE_R3.md — inventario por ruta (F-6)

Método: `diff -rq` y `shasum` sobre rutas relativas, raíz = cada revisión.
No se deducen omisiones restando totales globales.

## v10r1 → r3 (categorías)

| Categoría | Rutas |
|---|---|
| Comunes idénticos (núcleo heredado) | `CREAR_PEN_BOOTEO.sh`, `construir_efi.sh`, `descargar_sonoma.sh`, `ot07_guard.py`, `ot07_process.py`, `verificar_instalador.py` (ver nota*), `identificar_pen.py` |
| Modificados (software vía r2) | `verificar_instalador.py` (cadena C-1), `colocacion_v2/colocar_candidato.sh` |
| Añadidos r2 | `place_helper.py`, `tree_inventory.py`, `colocacion_v2/PLAN_COLOCACION_v2.md`, `evidencia_impl/*`, `apoyo_muse_p1/*`, `apoyo_flash_p2/*`, `MATRIZ_*`, `FUENTE.md`, `HILO_AUDITORIA_QWEN.md`, `tests/test_place_v10r2r1.py`, `tests/test_colocacion_v2.py`, `tests/test_verifier_v10r2.py`, `tests/test_correcciones_b_i.py` |
| Añadidos r3 | `tests/test_f1_arnes.py`, `tests/test_f5_tmpdir.py`, `ADENDA_P2_7_8.md`, `MATRIZ_APOYOS.md`, `MATRIZ_F_G.md`, `INDICE_HISTORICO.md`, `MAPA_CODIGO_HEREDADO.md`, `ALCANCE_R3.md`, `AUTOAUDITORIA_R3.md` |
| **Excluidos históricos** (referencia, no operativos) | `OT07_PREPARAR_PEN_BOOTEO.md`, `evidencia/fuentes*.json`, dossiers/consolidaciones v7–v10, diffs históricos `OT07_v6_a_v7.diff`… |

\* `verificar_instalador.py` cambió respecto de v10r1 (4193→… B) al implementar C-1; en r2→r3 es **byte-idéntico**.

## r2 → r3

| Categoría | Rutas |
|---|---|
| **Núcleo productivo .sh/.py congelado** | todos los `.sh`/`.py` fuera de `tests/` y `tree_inventory.py` (mantenido por OT) |
| Modificados (solo tests) | `tests/test_colocacion_v2.py`, `tests/test_verifier_v10r2.py`, `tests/test_f1_arnes.py` (nuevo), `tests/test_f5_tmpdir.py` (nuevo) |
| Documentación | nuevos F-2/F-3/F-4/F-6/índices; PLAN/HILO/FUENTE/MATRIZ_* actualizados |

## Exclusiones históricas — referencia y decisión

| Ruta | SHA / origen | Decisión |
|---|---|---|
| `OT07_PREPARAR_PEN_BOOTEO.md` | v10r1 manifiesto | **No operativo vigente**; CP0–CP5 es procedimiento histórico de E. Ver `INDICE_HISTORICO.md`. |
| `evidencia/fuentes*.json` | v10r1 | Evidencia histórica de fuentes; se copia hash, no se re-publica como orden. |
| Dossiers v7–v10 | sellos previos | Históricos; matrices vigentes = r3. |
