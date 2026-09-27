# MATRIZ_F_G.md — disposición F-1…F-12 y G-1…G-4

## Cerrados en esta revisión (r3)

| ID | Asunto | Disposición | Evidencia |
|---|---|---|---|
| **F-1** | Sustituciones huérfanas + aserción vacua + inyección real de `du` | **CORREGIDO** | `tests/test_f1_arnes.py` (9): inyección única de `du`/`df`, RC/entero, frontera espacio, positivo publicación, sensibilidad con mutación |
| **F-2** | Adenda P2 §7/§8 inexistente | **CORREGIDO** | `ADENDA_P2_7_8.md` con hallazgo/evidencia/adopción/documento/límite |
| **F-3** | Disposición P3/P4 | **CORREGIDO** | `MATRIZ_APOYOS.md` (cronología + filas por hallazgo) |
| **F-4** | Matrices históricas como vigentes | **CORREGIDO** | `INDICE_HISTORICO.md`; C-9 = `du + 2 GiB`; conteos vigentes 159+ |
| **F-5/G-4** | Fixtures TMPDIR | **CORREGIDO** | `tests/test_f5_tmpdir.py` (4): default, `/var/tmp/ot07_*`, `/var/tmp` sin prefijo, inexistente no valida |
| **F-6** | Inventario de alcance | **CORREGIDO** | `ALCANCE_R3.md` (comunes/modificados/añadidos/excluidos) |

## Disposición individual F-7…F-12 / G-1…G-3

| ID | Asunto | Disposición | Fundamento / límite |
|---|---|---|---|
| **F-7** | `tree_inventory.py` código muerto | **NO APLICABLE (referencia)** | Se conserva como referencia de Muse; las implementaciones activas son `place_helper.inventory_tree` y `verificar_instalador.inventory_tree`. **Sin unificación** en esta OT (núcleo congelado). |
| **F-8** | Headers viejos («v4»/«v2») | **RESIDUAL** | Núcleo productivo byte-idéntico; no se reescriben headers. Ver `MAPA_CODIGO_HEREDADO.md`. |
| **F-9** | Rama `root` inalcanzable tras B-1 | **RESIDUAL / defensa adicional** | Es correcto que `root` falle en el gate; **no** es C-5 implementada. Protección sigue pendiente. |
| **F-10** | Unicode en rutas | **RESIDUAL declarado** | Sin normalización Unicode; se acepta como límite de esta familia. |
| **F-11** | Diagnóstico de error original en cleanup | **RESIDUAL** | `I4_LIMPIEZA_FALLIDA` incluye la excepción; no se restaura la excepción original si cleanup falla en `finally` (se encadena). |
| **F-12** | Symlink PKG check temprano | **CORREGIDO en r2** (`[ ! -L "$PKG" ]` §1 + I-5 §0b) | Se mantiene; sin cambio adicional. |
| **G-1** | Limpieza silenciada / retención INV_ORIG | **RESIDUAL** | r2/r3 limpia `INV_*` en el camino de éxito; en fallos puede retener (I-4 reporta). **No** se garantiza limpieza total ni se borran temporales ajenos. Ver `MAPA_CODIGO_HEREDADO.md`. |
| **G-2** | Diferenciar entrega cerrada / software aprobado / autorización | **CORREGIDO (documental)** | Recibo: `ENTREGA_CERRADA` = integridad. Veredicto: `CANDIDATO_AUTOAUDITADO_PENDIENTE_AUDITORIA_EXTERNA`. Operación: todo NO_EJECUTADO. |
| **G-3** | Insumos P3/P4 sin recepción acreditada | **CORREGIDO** | `MATRIZ_APOYOS.md` distingue inicio/cierre/sello/recepción; P3 posterior a cierre r2; P4 ensayó r1. |
