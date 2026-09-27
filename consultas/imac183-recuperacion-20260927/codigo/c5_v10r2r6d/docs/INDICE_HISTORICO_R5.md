# INDICE_HISTORICO_R5.md — erratas r4 corregidas en r5

Revisión r5 · MIMO · 2026-09-27. **No se reescriben sellados históricos.**
Las erratas se corrigen aquí con evidencia fresca; los archivos de r4 permanecen intactos.

## Errata 1 — puntero codesign_cim vacío

| Campo | Valor |
|---|---|
| Hallazgo r4 | `evidencia_impl/codesign_cim.txt` vacío (SHA-256 `e3b0c442…b855`); `INDICE_HISTORICO.md` de r4 no lo puntúa con claridad |
| Estado r4 | `MATRIZ_CIERRE_R4.md` H-5 decía «DISPUESTO: se conserva vacío; no se inventa salida» |
| Corrección r5 | Este índice **sí** lo puntúa: el puntero es **vacío a propósito** (no hubo salida de `codesign` para CIM en la cadena C-1). No se fabrica salida. La huella del vacío se conserva como evidencia de ausencia, no de éxito |
| Hash del vacío | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (SHA-256 de 0 bytes) |
| Acción | Cualquier consumidor que espere `codesign_cim` debe tratar **vacío = no acreditado**, jamás «sin hallazgos» |
| Fuente sellada (no editar) | `OT07_REVISION_v10r2r4/evidencia_impl/codesign_cim.txt`, `OT07_REVISION_v10r2r4/INDICE_HISTORICO.md` |

## Errata 2 — evidencia durable de sensibilidad

| Campo | Valor |
|---|---|
| Hallazgo r4 | `sensitivity.txt` efímero / incompleto (base, mutante, comando, RC, aserción no siempre presentes juntos) |
| Corrección r5 | `evidencia_r5/SENSIBILIDAD.json` con esquema obligatorio por caso: `base`, `mutante`, `comando`, `rc`, `asercion` (y `id`, `criterio`) |
| Conteos | **Dinámicos**. No se fuerza 176 (r4) ni 47 (P5r). El harness reporta total real al sellar |
| Verificación | El harness caso `ERRATA-02` exige el esquema; si falta un campo, falla |

## Matrices vigentes en r5

| Documento | Vigencia | Nota |
|---|---|---|
| `INTERFAZ_C5.json` | **SÍ — contrato** | acciones, estados, errno, límites, fallos |
| `docs/MAPA_N0_N9.md` | **SÍ** | cobertura por criterio |
| `docs/PROCEDIMIENTO_H1.md` | **SÍ — no activado** | hashes/rutas/fixture/limpieza |
| `MATRIZ_F_G.md` (r4) | Histórico | conservado en r4 |
| `MATRIZ_C1_C10.md` (r2) | Histórico | C-1 ancla |
| Dossiers v7–v10 | Histórico | — |

## Política de espacio (C-9) — vigente

`du` del origen + **2 GiB reserva** vs `statvfs` del padre staging (entero positivo). Implementado en `c5_orquestador.space_need_bytes/space_avail_bytes`.

## CP0–CP5

`OT07_PREPARAR_PEN_BOOTEO.md` (histórico E) **no** es orden operativa vigente de r5. USB/arranque/OCLP quedan fuera de alcance hasta H2/H3.
