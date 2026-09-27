# ALCANCE_R4.md — inventario por ruta r3→r4

Método: `cmp` / `diff -rq` sobre rutas relativas. Raíz = cada revisión.

## Productivos (congelados)

| Archivo | vs r3 | vs r2 |
|---|---|---|
| CREAR_PEN_BOOTEO.sh | idéntico | idéntico |
| construir_efi.sh | idéntico | idéntico |
| descargar_sonoma.sh | idéntico | idéntico |
| ot07_guard.py | idéntico | idéntico |
| ot07_process.py | idéntico | idéntico |
| place_helper.py | idéntico | idéntico |
| tree_inventory.py | idéntico | idéntico |
| verificar_instalador.py | idéntico | idéntico |
| identificar_pen.py | idéntico | idéntico |
| colocacion_v2/colocar_candidato.sh | idéntico | idéntico |

**10/10 `cmp` same.** Apoyos y `evidencia_impl/` heredados **byte-idénticos**.

## Modificados (solo tests)

| Ruta | Cambio |
|---|---|
| `tests/test_flow.py` | Placeholder único + orden token→insertar + aserciones anti doble-sustitución |
| `tests/test_probe.py` | Fixture en `/private/tmp` (allowlist) + negativo allowlist |
| `tests/test_f5_tmpdir.py` | Test fantasma falsable + sensibilidad fallback |

## Añadidos r4

`MATRIZ_CIERRE_R4.md`, `ALCANCE_R4.md`, `AUTOAUDITORIA_R4.md`, `evidencia_r4/*`

## Exclusiones históricas (hash literal v10r1)

| Ruta | SHA-256 (manifiesto v10r1) |
|---|---|
| `OT07_PREPARAR_PEN_BOOTEO.md` | `27d44ec953b71f15ead11f6e12c3bee7ea810628d41325d8c1e92e3068d4360c` |
| `evidencia/fuentes*.json` | en manifiesto v10r1 |

Procedimiento CP0–CP5 = histórico de E; **no** orden operativa vigente.
