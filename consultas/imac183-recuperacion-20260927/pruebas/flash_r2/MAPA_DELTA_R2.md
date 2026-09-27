# MAPA_DELTA_R2 — batería FLASH × orquestador r6

Entrega FLASH_PRUEBAS_C5_R2 · RUN.20260927T131419Z.C5IMAC1 · NO_PRODUCTIVO_NO_AUTORIZADO.

Delta respecto a R1: (1) 15 casos nuevos contra `c5_orquestador.py` r6 real
(simulated/fixture_ensayo, copia privada); (2) los 51 casos R1 re-ejecutados
como regresión con sus adaptadores; (3) contrato INTERFAZ_C5 sin cambios —
`InterfazC5Adapter`/`MAPA_VEREDICTOS_C5` siguen válidos (verificado por hash
sobre la entrega r6).

## Cobertura del orquestador r6 por criterio (15 casos)

| Criterio | Casos r6 | Estado | Qué cierra |
|---|---|---|---|
| N0 | c5-r6-01 (gate/modos), c5-r6-12 (escáner subprocess confinado a NativePriv) | PASA | gates F0 + superficie de código privilegiado |
| N1 | c5-r6-03 (positivo), c5-r6-14 (F7: g+w residual / nodo sin lchown ⇒ aborto) | PASA | HB-1 revalidación raíz+hijos con ledger |
| N2 | c5-r6-04 (fd origen), c5-r6-05 (fd staging post-frontera — SKIP→H1) | PASA/SKIP | lado origen medido; lado staging: limitación simulated declarada, oráculo conclusivo H1-N2 |
| N3 | c5-r6-09 (**FALLA_PRODUCTO**: F-R6-N3-1), c5-r6-10 (**FALLA_PRODUCTO**: R6-1 reproducida) | FALLA | política ACL con ACEs reales; fail-open medido end-to-end |
| N4 | c5-r6-02 (matriz faults 8 puntos + swap_hoja), c5-r6-08 (micro-ventana F9), c5-r6-13 (swap origen pre-frontera) | PASA | swaps deterministas; backstop F9 medido |
| N5 | c5-r6-15 (DELEGADA / C-1 autenticada / par atacante rechazado) | PASA | cadena C-1 con evidencia autenticada |
| N6 | c5-r6-06 (EEXIST/destino), c5-r6-07 (rc=8 sin borrado; rc=3 con residuo) | PASA | estados por H-R5-3 |
| N8 | c5-r6-11 (cleanup confinado, list-stale, ajenos intactos) | PASA | H-R5-5 |

## Correlación R1 → r6 (qué usa cada oráculo contra el producto real)

| Oráculo R1 (adaptador) | Equivalente ×r6 (adaptador r6) | Resultado |
|---|---|---|
| c5-n0-01 gate euid (P5r) | c5-r6-01 | PASA (rc=5 sin efectos) |
| c5-n0-03 escáner (P5r) | c5-r6-12 (+ disciplina de inyección) | PASA |
| c5-n0-04 rutas auxiliares | (cubierto: mkdtemp fallo ⇒ ABORTADO_SIN_EFECTOS rc=2; symlink base = limitación compartida, REQUISITO ya registrado) | — |
| c5-n0-05 / n5-01..03 ancla | c5-r6-15 (más evidencia C-1 autenticada real) | PASA |
| c5-n1-03/04/05/06 hooks | c5-r6-14 (mutantes únicos A/F) | PASA |
| c5-n1-07 comparador | sin cambios (comparador sobre árbol publicado r6 válido) | PASA (regresión R1) |
| c5-n2-01 fd origen | c5-r6-04 | PASA |
| c5-n2-02 fd staging | c5-r6-05 (instrumentación determinista) | SKIP→H1 (ref. Max incorporada) |
| c5-n2-03/04 frontera ref | c5-r6-03 (positivo) + PoC frontera de Max | PASA |
| c5-n3-01/02/03 ACL lector | c5-r6-09 (sondas de política con ACEs reales) | **FALLA** (F-R6-N3-1) |
| c5-n6-01..06 estados | c5-r6-02/06/07/08 | PASA |
| c5-n6-07 indeterminado | c5-r6-07 (rc=8) | PASA |
| c5-n6-08/8-02/8-03 limpieza | c5-r6-11 | PASA |
| c5-n4-07 swaps | c5-r6-02/08/13 | PASA |
| c5-n4-08 / n7-* ruta reemplazable | sin cambios de diseño: r6 USO sigue NO_ACTIVADO; requisito de contexto raíz ya fijado (execve /dev/fd EACCES medido en R1) | — |

## Hallazgos entregados a MiMo/Max (resumen operativo)

1. **F-R6-N3-1 (nuevo, FALLA_PRODUCTO)**: `validar_acl` no detecta ACE
   `allow write` ni `allow append` (nombres que `ls -le` imprime; sondas con
   ACEs reales medidas). Corrección de una línea en `c5_acl.DERECHOS_ESCRITURA`
   + el par positivo/negativo ya escrito (c5-r6-09).
2. **R6-1 reproducida (FALLA_PRODUCTO)**: `except AclPolicyError: pass` en F6
   publica con validación salteada (c5-r6-10). Corrección obligatoria ya
   dispuesta por Max (abort con ABORTADO_STAGING_RETENIDO).
3. **Referencias Max confirmadas de forma independiente**: fd del dueño abre en
   simulated y la escritura post-publicación muta el objeto (c5-r6-05,
   SKIP→H1); micro-ventana publicada y capturada por F9 rc=4 sin borrado
   (c5-r6-08).
4. **Sin regresiones**: 50/51 casos R1 re-validados (+1 SKIP H1); suite P5r
   interna 47/47.

## Pendientes (NO aprobados aquí)

- **H1** (bloquea C5_NATIVO_VALIDADO): c5-n1-01 completo + c5-r6-05 conclusivo
  (fd ⇒ EACCES sobre inodos root:0) + sonda AT_UNIQUE en sesión privilegiada.
- Correcciones r6b: R6-1 (obligatoria) y F-R6-N3-1 (recomendada antes de H1;
  una línea + re-ejecución de c5-r6-09/10 sobre la copia corregida).
- R6-2/R6-3/R6-4 de Max sin cambios desde esta revisión.
