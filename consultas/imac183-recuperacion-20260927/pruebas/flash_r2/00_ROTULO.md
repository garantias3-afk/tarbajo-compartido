# 00_ROTULO — FLASH_PRUEBAS_C5_R2 (OT07-P7 · GLM Flash · batería × r6)

**NO_PRODUCTIVO_NO_AUTORIZADO** · RUN.20260927T131419Z.C5IMAC1 · canal entregas/FLASH/
Revisión de: FLASH_PRUEBAS_C5_R1 (sellada; sin cambios). Objeto: ejecutar la
batería FLASH contra el ORQUESTADOR REAL r6 tras el
CANDIDATO_R6_REVISADO_ACEPTADO de Max.

## Contenido

| Ruta | Contenido |
|---|---|
| `PRUEBAS_R6_FLASH.md` | resultados 66 casos (62 PASA / 2 FALLA_PRODUCTO / 2 SKIP / 0 error), hallazgos F-R6-N3-1 y R6-1 medida, referencias Max incorporadas |
| `MAPA_DELTA_R2.md` | delta R1→R2, correlación oráculos×r6, pendientes |
| `harness/` | R1 + `sut_r6.py` (adaptador r6 con instrumentación y mutantes) + `casos_r6.py` (15) + `runner_r6.py` |
| `copias_privadas/r6/` | c5_orquestador.py, c5_ancla.py, c5_acl.py, c5_bootstrap.py (hashes registrados; el sellado jamás se ejecutó in-place) |
| `resultados/` | resultados_harness_r6.json, resumen_r6.md, ejecucion_r6.log, probes_nativos.json, limpieza.txt (0 residuos) |
| `SHA256SUMS.txt` | manifiesto sellado al cierre |

## Resultado en una línea

Batería FLASH completa contra r6: **62 PASA · 2 FALLA_PRODUCTO (hallazgos
reales: F-R6-N3-1 'allow write/append' no detectada por c5_acl; R6-1
fail-open reproducida end-to-end) · 2 SKIP (H1: c5-n1-01 y c5-r6-05 con
medición determinista registrada) · 0 inconclusivos · 0 errores**; sin
regresiones R1 (50/51 + suite P5r 47/47).

## Límites respetados

- Sin root/sudo/dispositivos/arranque/OCLP; sin señales a procesos ajenos.
- Producto r6 ejecutado SOLO desde copia privada verificada por hash
  (`a4471560…` = manifiesto r6); mutaciones solo en copias privadas con
  anclaje único (MUT-R6-A/B/C/D/E/F + SCAN).
- Ataques como uid operador con identidad registrada por hijo; contrato
  INTERFAZ_C5 sin cambios (adaptador R1 sigue válido, verificado por hash).
- Una entrega sellada no se edita: esta es revisión nueva con el delta
  revalidado.
