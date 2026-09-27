# MAPA_CODIGO_HEREDADO.md — origen de versiones (F-8, G-1)

Núcleo productivo **byte-idéntico a r2** en esta revisión. Los headers antiguos
no se reescriben (OT lo prohíbe). Este mapa explica la versión de origen.

| Archivo | Header literal | Origen real | Estado |
|---|---|---|---|
| `CREAR_PEN_BOOTEO.sh` | «OT07 v9» / comentarios v7–v9 | Heredado de v10r1; sin cambios r2/r3 | Congelado |
| `construir_efi.sh` | «construir_efi.sh» sin versión | v10r1 | Congelado |
| `descargar_sonoma.sh` | «OT07 v7» | v10r1 | Congelado |
| `ot07_guard.py` | «OT07 v8» | v10r1 | Congelado |
| `ot07_process.py` | «ledger v9» | v10r1 | Congelado |
| `verificar_instalador.py` | «v10r2» (C-1) | r2 | Congelado |
| `place_helper.py` | «v10r2r1» | r2 | Congelado |
| `colocacion_v2/colocar_candidato.sh` | «v3 — OT07 v10r2r1» | r2 | Congelado |
| `tree_inventory.py` | «v10r2» | r2 (referencia, no activo) | Congelado |

## G-1 — limpieza y retención

| Comportamiento | Real | Límite |
|---|---|---|
| `INV_*` en éxito | `rm -f` al final del script | — |
| `INV_*` en fallo | **pueden retenerse** en `/private/var/tmp` | No se garantiza limpieza; I-4 reporta error de rmtree |
| Temporales ajenos | **no se borran** | Política explícita |
| `expand` del verificador | `shutil.rmtree` sin `ignore_errors`; fallo → `I4_LIMPIEZA_FALLIDA` | Puede dejar el árbol si el FS falla |

No se afirma limpieza garantizada en todos los caminos.
