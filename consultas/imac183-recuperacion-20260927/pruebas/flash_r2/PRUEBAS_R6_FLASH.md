# PRUEBAS_R6_FLASH — OT07-P7 · GLM Flash R2 · batería contra el orquestador real r6

**Rotulo**: NO_PRODUCTIVO_NO_AUTORIZADO — ensayo no privilegiado sobre copia privada del producto sellado.
**RUN**: RUN.20260927T131419Z.C5IMAC1 · **Entrega**: FLASH_PRUEBAS_C5_R2 · UTC: 2026-09-27T16:55:16.023530+00:00

## 1. Objeto y resultado

Con r6 **CANDIDATO_R6_REVISADO_ACEPTADO** por Max y `INTERFAZ_C5.json` SIN
cambios (sha `c4dcf663…` verificado en la entrega r6), esta revisión R2 ejecuta
la batería FLASH completa contra el orquestador real
(`OT07_REVISION_v10r2r6_MIMO/src/c5_orquestador.py`, modo
`simulated`/`fixture_ensayo`), **solo desde copia privada** (insumo sellado
jamás in-place; SHA del orquestador copiado = `a4471560…` = manifiesto r6).

| Contador | Valor | Semántica |
|---|---|---|
| total_casos | 66 | 51 de R1 (regresión) + 15 nuevos ×r6 |
| ejecutados | 64 | |
| pasa_oraculo | 62 | oráculo previsto cumplido con evidencia medida |
| falla_producto | 2 | ataque/detección ⇒ FALLO del producto |
| skip_nativo_pendiente | 2 | c5-n1-01 (H1) + c5-r6-05 (H1, medición registrada) |
| inconclusivo / error | 0 / 0 | |

## 2. Casos ×r6 (15)

| ID | Crit. | Estado | Tipo |
|---|---|---|---|
| c5-r6-01-gate-y-modos | N0 | PASA | REAL_HOY |
| c5-r6-02-puntos-fault | N4 | PASA | REAL_HOY |
| c5-r6-03-positivo-fixture-ensayo | N1 | PASA | REAL_HOY |
| c5-r6-04-fd-escritura-origen | N2 | PASA | REAL_HOY |
| c5-r6-05-fd-staging-post-frontera | N2 | SKIP | NATIVA_PENDIENTE_H1 |
| c5-r6-06-eexist-y-destino | N6 | PASA | REAL_HOY |
| c5-r6-07-estados-post-publicacion | N6 | PASA | REAL_HOY |
| c5-r6-08-microventana-f9 | N4 | PASA | REAL_HOY |
| c5-r6-09-politica-acl-allow-write | N3 | FALLA_PRODUCTO | REAL_HOY |
| c5-r6-10-r6-1-fail-open | N3 | FALLA_PRODUCTO | REAL_HOY |
| c5-r6-11-limpieza-confinada | N8 | PASA | REAL_HOY |
| c5-r6-12-escaner-subprocess | N0 | PASA | REAL_HOY |
| c5-r6-13-origen-swap-pre-frontera | N4 | PASA | REAL_HOY |
| c5-r6-14-proteccion-insuficiente-f7 | N1 | PASA | REAL_HOY |
| c5-r6-15-cadena-ancla-c1 | N5 | PASA | REAL_HOY |

## 3. Regresión R1 (51 casos, mismos adaptadores que R1)

| ID | Crit. | Estado | Tipo |
|---|---|---|---|
| c5-n0-01-gate-euid0 | N0 | PASA | REAL_HOY |
| c5-n0-02-env-inyectado | N0 | PASA | REAL_HOY |
| c5-n0-03-codigo-sustituido | N0 | PASA | REAL_HOY |
| c5-n0-04-rutas-auxiliares | N0 | PASA | REAL_HOY |
| c5-n0-05-ancla-atacante | N0 | PASA | REAL_HOY |
| c5-n1-01-positivo-proteccion-nativa | N1 | SKIP | NATIVA_PENDIENTE_H1 |
| c5-n1-02-borrado-raiz-por-padre | N1 | PASA | REAL_HOY |
| c5-n1-03-raiz-gw | N1 | PASA | REAL_HOY |
| c5-n1-04-raiz-ow | N1 | PASA | REAL_HOY |
| c5-n1-05-dueño-incorrecto | N1 | PASA | REAL_HOY |
| c5-n1-06-proteccion-parcial | N1 | PASA | REAL_HOY |
| c5-n1-07-metadata-vs-capacidad | N1 | PASA | REAL_HOY |
| c5-n2-01-fd-escritura-origen | N2 | PASA | REAL_HOY |
| c5-n2-02-fd-escritura-staging | N2 | PASA | REAL_HOY |
| c5-n2-03-flujo-frontera-inodos-nuevos | N2 | PASA | REAL_HOY |
| c5-n2-04-mutacion-unica-diseno | N2 | PASA | REAL_HOY |
| c5-n3-01-acl-esperada | N3 | PASA | REAL_HOY |
| c5-n3-02-acl-allow-extra | N3 | PASA | REAL_HOY |
| c5-n3-03-acl-heredada | N3 | PASA | REAL_HOY |
| c5-n3-04-capacidad-borrado | N3 | PASA | REAL_HOY |
| c5-n3-05-bypass-acl-sensibilidad | N3 | PASA | REAL_HOY |
| c5-n4-01-symlink-escape | N4 | PASA | REAL_HOY |
| c5-n4-02-symlink-roto | N4 | PASA | REAL_HOY |
| c5-n4-03-ciclo-symlinks | N4 | PASA | REAL_HOY |
| c5-n4-04-hardlink | N4 | PASA | REAL_HOY |
| c5-n4-05-fifo-durante-proteccion | N4 | PASA | REAL_HOY |
| c5-n4-06-sonda-primitivas | N4 | PASA | REAL_HOY |
| c5-n4-07-swaps-deterministas | N4 | PASA | REAL_HOY |
| c5-n4-08-ruta-reemplazable-antes-de-uso | N4 | PASA | REAL_HOY |
| c5-n5-01-ancla-alterada | N5 | PASA | REAL_HOY |
| c5-n5-02-par-atacante-delegada | N5 | PASA | REAL_HOY |
| c5-n5-03-hash-original-ancla-atacante | N5 | PASA | REAL_HOY |
| c5-n5-04-snapshot-no-fijada | N5 | PASA | REAL_HOY |
| c5-n6-01-destino-preexistente | N6 | PASA | REAL_HOY |
| c5-n6-02-eexist-ganador-intacto | N6 | PASA | REAL_HOY |
| c5-n6-03-excepcion-pre-publicacion | N6 | PASA | REAL_HOY |
| c5-n6-04-excepcion-post-publicacion | N6 | PASA | REAL_HOY |
| c5-n6-05-limpieza-falla | N6 | PASA | REAL_HOY |
| c5-n6-06-interrupcion-reintento | N6 | PASA | REAL_HOY |
| c5-n6-07-indeterminado-no-sin-efectos | N6 | PASA | REAL_HOY |
| c5-n6-08-limpieza-confinada | N6 | PASA | REAL_HOY |
| c5-n7-01-carrera-check-exec | N7 | PASA | REAL_HOY |
| c5-n7-02-rehash-ruta-insuficiente | N7 | PASA | REAL_HOY |
| c5-n7-03-dependencias-inyectadas | N7 | PASA | REAL_HOY |
| c5-n8-01-fuera-de-ambito | N8 | PASA | REAL_HOY |
| c5-n8-02-registro-sin-glob | N8 | PASA | REAL_HOY |
| c5-n8-03-adyacente-intacto | N8 | PASA | REAL_HOY |
| c5-n9-01-regresion-p5r | N9 | PASA | REAL_HOY |
| c5-n9-02-disciplina-mutacion | N9 | PASA | REAL_HOY |
| c5-n9-03-contadores-verdes | N9 | PASA | REAL_HOY |
| c5-c0-01-contrato-interfaz-c5 | C0 | PASA | REAL_HOY |

Regresión **50/51 PASA + 1 SKIP (H1)** — idéntica a R1: sin regresiones por el
cambio de entorno. La suite P5r interna (c5-n9-01) volvió a cerrar **47/47**.

## 4. Hallazgos contra el producto r6 (para MiMo r6b / adjudicación Max)

### F-R6-N3-1 — NUEVO (c5-r6-09, FALLA_PRODUCTO)
`c5_acl.DERECHOS_ESCRITURA` enumera nombres NFSv4 canónicos
(`write_data`, `append_data`, `delete`, …), pero `ls -le` muestra los nombres
de **chmod**. Medido con ACEs reales sobre fixtures propios:

| ACE (chmod +a, válida) | ACE según ls/lector | `validar_acl` del producto |
|---|---|---|
| `OPERADOR allow write` | `['write']` | **ok=True — NO detectada** |
| `OPERADOR allow append` | `['append']` | **ok=True — NO detectada** (sonda directa) |
| `OPERADOR allow write,delete` | `['write','delete']` | ok=False — detectada (por `delete`) |
| `OPERADOR allow delete` | `['delete']` | ok=False — detectada |
| `root allow write` | `['write']` | ok=True — correcto por política (principal root) |

**Corrección sugerida (una línea + pruebas)**: añadir los nombres que `ls -le`
imprime (`write`, `append`, `writeattr`, `writeextattr`, `writesecurity`) a
`DERECHOS_ESCRITURA`, o comparar por contención (`'write' in perm`). Impacto
hoy: acotado en simulated (la copia por bytes no traslada ACEs al staging —
medido), pero la política N3 declarada queda incompleta y es la barrera que
debe ser fail-closed cuando el recorrido/origen traiga ACLs.

### R6-1 reproducida y medida end-to-end (c5-r6-10, FALLA_PRODUCTO)
- (a) Con detección funcionando (`validar_acl` ⇒ problemas) el flujo aborta:
  `ABORTADO_STAGING_RETENIDO rc=2` — fail-closed correcto.
- (b) Con `validar_acl` lanzando `AclPolicyError` (ls inparseable), el
  `except acl_mod.AclPolicyError: pass` de F6 (líneas 648-649) engulle la
  excepción y el flujo **PUBLICA** (`PUBLICADO_VERIFICADO rc=0`).
Coincide con el hallazgo R6-1 de Max (obligatoria antes de H1): cambiar a
abort con `ABORTADO_STAGING_RETENIDO`.

## 5. Referencias de Max incorporadas (medidas aquí como controles independientes)

- **fd del dueño sobre staging en simulated** (c5-r6-05, SKIP→H1): con
  instrumentación determinista de copia privada (callback justo tras
  `create_staging_and_copy`, sin alterar la lógica del producto), el fd O_RDWR
  del dueño **abre** (modo 0o644) y la escritura post-publicación **muta el
  objeto publicado** (`publicado_mutado: true`). Coincide con la referencia de
  Max; el oráculo conclusivo (fd ⇒ EACCES/EPERM) es H1-N2 con la frontera
  nativa del helper.
- **Micro-ventana de swap** (c5-r6-08, PASA): reproducida independientemente
  con mutante único MUT-R6-D (swap tras el último re-pin): el sustituto se
  publica y **F9 lo captura** — `PUBLICADO_INCONSISTENTE_NO_BORRADO rc=4`,
  objeto NO borrado. Coincide con Max; la micro-ventana queda declarada y se
  cierra en native.

## 6. Verificaciones positivas contra r6 (extracto)

- Gates F0: euid==0 ⇒ `NO_AUTORIZADO rc=5` sin efectos; modos no decididos y
  root+simulated ⇒ `RECHAZADO_GATE rc=1` (c5-r6-01).
- Matriz de faults booleanos: 8 puntos de fase con veredicto correcto
  (pre-staging SIN_EFECTOS; post-staging STAGING_RETENIDO rc=2 unificado;
  `swap_hoja` aborta sin publicar) (c5-r6-02).
- Positivo `fixture_ensayo`: `PUBLICADO_VERIFICADO rc=0`, publicado = inodo de
  la hoja (rename), legible, sin residuos (c5-r6-03).
- N2 origen: fd preabierto al origen NO alcanza el publicado (c5-r6-04);
  frontera de referencia FLASH vs r6 cubierta en el mapa delta.
- EEXIST/destino: aborto en F1 con ganador intacto (c5-r6-06); estados
  post-publicación honestos (rc=8 sin borrado; limpieza fallida rc=3 con
  residuo declarado) (c5-r6-07); cleanup confinado + list-stale (c5-r6-11);
  escáner: `subprocess` confinado a NativePriv (c5-r6-12); re-pin de origen
  pre-frontera detecta el swap (c5-r6-13); F7 detecta g+w residual y nodo sin
  lchown (c5-r6-14); cadena C-1: DELEGADA/C-1/rechazo de par atacante
  (c5-r6-15).

## 7. Host, herramientas y reproducibilidad

- HOST_PREPARACION.local · macOS 26.6.2 · arm64 · uid 501/euid 501 · umask 0o77
- /usr/bin/python3 3.9.6 con `-B`; producto r6 SOLO desde `copias_privadas/r6/`
  (hashes en `copias_privadas/r6/SHA256SUMS_COPIA.txt`; producto sellado intacto, verificado post-copia).
- Reproducir: `umask 077; PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B harness/runner_r6.py`
  (`--list`, `--ids …`, `--solo-r6`, `--solo-r1`).
- Evidencia: `resultados/resultados_harness_r6.json` (esquema v1 de
  CONTRATO_SALIDAS_HARNESS.md en R1), `resumen_r6.md`, `ejecucion_r6.log`.
