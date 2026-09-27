# ADENDA_P2_7_8.md — F-2/M-4 (la adenda que faltaba)

No se afirma «CORREGIDO, ver adenda» sin este documento. Cada fila identifica
hallazgo original, evidencia, adopción/rechazo, documento corregido y límite.

## §7 — Errata de adquisición (desviación documental)

| Campo | Contenido |
|---|---|
| Hallazgo original | Flash E2-R1: sin metadata primaria de catálogo (403/404) no usó la etiqueta obligatoria `FUENTE_NO_ACREDITADA`; usó `CANDIDATO_PREPARADO_PENDIENTE_AUDITORIA`. |
| Evidencia | `apoyo_flash_p2/ERRATA_ADQUISICION.md`; logs de 403/404 en evidencia sellada O5HIqi. |
| Adopción | **Aceptada la errata como interpretación** de tres estados separados: (1) autenticidad criptográfica PKG = ACREDITADA; (2) versión/build del SO = PENDIENTE (`Assets[0]`); (3) cumplimiento documental de la orden = **DESVIADO** (etiqueta incorrecta). |
| Rechazo | No se ratifica retroactivamente la etiqueta de Flash ni se atribuye aceptación a OPERADOR. |
| Documento corregido | `FUENTE.md` (r3) con la tabla de tres estados; `MATRIZ_APOYOS.md` §errata. |
| Límite pendiente | Decisión de OPERADOR sobre si la desviación invalida la adquisición o se acepta con constancia. **No** cambia el PKG ni la cadena C-1. |

## §8 — Evidencia de forma (C-10)

| Hallazgo original | Evidencia | Adopción | Documento | Límite |
|---|---|---|---|---|
| `02_zip_vs_carpeta.log` (95 B) conclusión sin comando/salida | Qwen r2; Flash P2 §8 | **Aceptado**: los logs nuevos (ZIP↔carpeta de r3) llevan comando, conteos y resultado por archivo. | `evidencia_r3/zip_vs_carpeta.log` | El log histórico **no se edita**; queda como `NO_CAPTURADO` su detalle. |
| `09_expansion_inspeccion.log` rótulo «que escapen» sobre lista completa de symlinks | idem | **Aceptado**: la conclusión 0 absolutos/0 `..` es correcta (verificado por Qwen/GLM); el rótulo era erróneo. | `FUENTE.md` §transform; inventarios r3 | No se reescribe el log sellado. |
| `10_replica_postinstall.log` sin RC de la réplica | idem | **Aceptado**: RC histórico = **NO_CAPTURADO**. No se fabrica. | `MATRIZ_APOYOS.md` | Cualquier RC futuro sale de una ejecución nueva, no de este log. |

## Separación obligatoria (recordatorio)

| Estado | ¿Afecta a C-1? | ¿Afecta a colocación/E? |
|---|---|---|
| Autenticidad criptográfica PKG | No (ya GO) | No |
| Metadata de catálogo | No | No |
| Versión/build SO | No | Sí (pendiente `Assets[0]` en E) |
| Cumplimiento documental OT adquisición | No | Decisión de OPERADOR |
