# DIFF r5 → r6 — corrección del delta (revisión Max)

Base r5 sellada: `OT07_REVISION_v10r2r5_MIMO` manifiesto
`2afb2c93fc85d34027630d50f1a867f925ac55c190a47051657ecccf471a7840`
**no se edita**. Este paquete es r6.

## Bloqueantes corregidos

### H-R5-1 (N2) — frontera en el flujo

| Archivo | Cambio |
|---|---|
| `src/c5_helper.c` | Nuevas acciones `mkdir-staging` y `copy-tree`: root crea `ot07_c5_staging.*` root:0 0700 y copia el árbol leyendo como root. El uid operador jamás abre O_WRONLY/O_RDWR sobre esos inodos |
| `src/c5_orquestador.py` | `SimulatedPriv.create_staging_and_copy` y `NativePriv.create_staging_and_copy`. F3+F4 son **una** operación de frontera (sin `tempfile.mkdtemp`/`_copy_tree` directos en `place()`) |
| `tests/harness_r5.py` | N2-04 (fd-sobre-staging), N2-05 (sin ventana crear→copiar del operador), N2-06 (PoC Max reproducida) |
| `docs/PROCEDIMIENTO_H1.md` | Oráculo N2 real: open O_WRONLY tras frontera debe fallar |

### H-R5-2 (N6) — re-pin de hoja antes de renamex_np

| Archivo | Cambio |
|---|---|
| `src/c5_orquestador.py` | Eliminada la tautología `pin(x)!=pin(x)`. F7 y F8 re-pinan `hoja_pin`, `padre_pin` y modo `0700` del padre. Fault `swap_hoja` para oráculo |
| `src/c5_helper.c` | `cmd_publish` re-pin de la hoja + valida padre 0700 confinado antes de `renamex_np` |
| `tests/harness_r5.py` | N6-05 (swap-de-hoja), N6-06 (presencia del re-pin) |

## Obligatorios H-R5-3/4/5

| Hallazgo | Cambio |
|---|---|
| **H-R5-3** veredictos por estado | `_verdict_por_estado` decide por disco **antes** que por tipo de excepción. PrivError con staging ⇒ `ABORTADO_STAGING_RETENIDO` rc=2. `except Exception` final ⇒ `ESTADO_INDETERMINADO` si ya publicó. Tests H-R5-3a/3b |
| **H-R5-4** cableado ancla+ACL | `fijar_ancla` delega en `c5_ancla.verificar_ancla`; `origen_autenticado` real vía `acreditar_origen_desde_manifiesto` (hash en manifiesto sellado). `c5_acl.validar_acl` invocado en F6 cuando `acl_enabled`. Tests H-R5-4a/4b |
| **H-R5-5** confinamiento helper | `path_confinada` (prefijo `ot07_c5_staging.` o `C5_AUTH_BASE`); `cleanup` exige prefijo; `protect/publish/verify` confinados. Tests H-R5-5a/5b |

## Menores H-R5-6 (1, 7, 8)

| # | Cambio |
|---|---|
| 1 | **rc6→rc2 unificado**: los abortos van a `rc=2`; `rc=6` no se usa. Flash mapea por veredicto (string), no por rc numérico. Documentado aquí y en `SENSIBILIDAD.json` |
| 2 | `C5_UID_OPERADOR` / `UID_OPERADOR` parametrizables (env) — helper C `#define` y Python `os.environ` |
| 3 | Código muerto eliminado en `protect_one` (`uuid_t`, `pe`, `tag`) |
| 4 | `aceptar_usuario` sigue protegiendo con dirección B (más estricto; coherente con OT: no es atajo) |
| 5 | `check_expected_metadata` conserva bool (se mantiene); las causas van en `phases`/`error` |
| 6 | EXDEV: `rename_excl` propagaría errno; el veredicto sería `ABORTADO_STAGING_RETENIDO` rc=2 (fail-closed) |
| 7 | `SENSIBILIDAD.json`: **12 casos** reales (`conteo_casos`); se retiró la inconsistencia 7 vs 8 del recibo r5 |
| 8 | `c5_ancla.adaptar_ancla_c1`: adaptador `inv_extracted_app.json` / `tree_inventory.py` (lista) → formato `inventory_tree` (dict). Test H-R5-6.8 |

## Harness

- r5: 35/35 · r6: **48/48** (13 casos nuevos: N2-04/05/06, N6-05/06, H-R5-3a/3b, H-R5-4a/4b, H-R5-5a/5b, H-R5-6.7/6.8)
- Conteos dinámicos; evidencia en `evidencia_r6/HARNESS_RESULTADOS.json`

## Qué NO cambia

- Dirección B (protección antes de publicar)
- Primitivas reales (sin RESOLVE_BENEATH, sin lchown binario)
- Legacy byte-idéntico de r4
- Sin root/USB/arranque; H1 no presentada
- `INTERFAZ_C5.json` (contrato compatible; Flash C0 PASA)
