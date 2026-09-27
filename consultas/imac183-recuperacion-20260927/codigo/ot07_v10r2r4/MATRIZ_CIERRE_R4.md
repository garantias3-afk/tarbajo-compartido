# MATRIZ_CIERRE_R4.md — H/F/G (Qwen R3 + GLM R3)

## Qwen R3 — H-1 / H-2 / H-3

| ID | Hallazgo | Disposición r4 | Evidencia |
|---|---|---|---|
| **H-1** | Suite falla bajo TMPDIR `/var/tmp/ot07_*` (26 flujo+1) y `/var/tmp` (1) por doble sustitución y allowlist de probe | **CORREGIDO** | `test_flow.py`: tokenización `/var/tmp/ot07_` → `__OT07_TMPROOT__/ot07_` **antes** de insertar rutas; aserción cardinalidad + sin `/private/private/`. `test_probe.py`: fixture positivo en `/private/tmp` (allowlist del producto) + negativo allowlist. Suite **176/176** en D, A (`/var/tmp/ot07_*`) y B (`/var/tmp/mimo_r4_*`) |
| **H-2a** | `f5_tmpdir=4` vs 6 tests reales | **CORREGIDO** | Recibo r4 con conteos observados por módulo |
| **H-2b** | «159+» en MATRIZ_F_G | **CORREGIDO** | Conteos vigentes = suite real 176 |
| **H-2c** | Test fantasma tautológico | **CORREGIDO** | `test_nonexistent_tmpdir_does_not_silently_validate` falsable + `test_sensitivity_mutant_accepting_fallback_fails_the_test` |
| **H-2d** | `evidencia_r3/zip_vs_carpeta.log` inexistente | **CORREGIDO** | Enlace a `outputs/ZIP_VS_CARPETA_v10r2r3.log` (externo, en recibo r3) |
| **H-2e** | Hash de `OT07_PREPARAR_PEN_BOOTEO.md` ausente | **CORREGIDO** | `ALCANCE_R4.md` con hash literal del manifiesto v10r1 |
| **H-2f** | Alcance dice PLAN actualizado r2→r3 (byte-idéntico) | **CORREGIDO** | `ALCANCE_R4.md` por ruta exacta |
| **H-2g** | `sensitivity.txt` efímero | **CORREGIDO** | Evidencia durable en `evidencia_r4/` con hash del mutante |
| **H-3** | Cronología P3 «posterior a cierre r2» | **CORREGIDO** | Ver abajo |

### H-3 cronología (fechas completas, de recibos sellados)

| Evento | UTC |
|---|---|
| cierre **r2r1** | 2026-09-26T22:54:12Z |
| P3 inicio | 2026-09-26T23:10:56Z |
| P3 resultados | 2026-09-26T23:29:31Z |
| P3 sello | 2026-09-26T23:30:50Z |
| cierre **r2r2** | 2026-09-27T00:10:15Z |

P3 **inició y selló después de r2r1 y antes de r2r2**. Ensayó snapshot P2; no valida r2/r3.

## GLM R3 — H-1…H-8 (disposición)

| ID | Asunto | Disposición |
|---|---|---|
| H-1 | Arnes/TMPDIR | **CORREGIDO** (idéntico a Qwen H-1) |
| H-2 | Rótulos/conteos | **CORREGIDO** (H-2a–g) |
| H-3 | Cronología | **CORREGIDO** (H-3) |
| H-4 | Evidencia sensibilidad durable | **CORREGIDO** (`evidencia_r4/`) |
| H-5 | codesign_cim.txt vacío histórico | **DISPUESTO**: se conserva vacío; **no se inventa salida**. Registrado en `INDICE_HISTORICO.md` |
| H-6 | Errata M-9 | **CORREGIDO**: M-9 era fragilidad; r4 la cierra con las 3 corridas |
| H-7 | Excepción ubicación build fixture probe | **DECLARADA**: `/private/tmp` para el fixture; resto hereda TMPDIR |
| H-8 | G-1 limpieza residual | **RESIDUAL mantenido** (no se convierte en corrección productiva) |

## F/G heredados

F-1 se mantiene (inyección+sensibilidad). F-5/G-4/A3b: **CERRADO en r4** con las 3 corridas.  
C-5: **PENDIENTE**. Núcleo productivo: **byte-idéntico a r3/r2**.
