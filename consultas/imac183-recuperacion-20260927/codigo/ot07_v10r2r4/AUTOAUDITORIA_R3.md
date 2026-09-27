# AUTOAUDITORIA_R3.md — puertas A0–A9 (MiMo, antes de sellar)

Regla: cada fila lleva comando/inspección **real** y resultado medido.
No se completa «OK» por haber editado un archivo.

| ID | Expectativa previa | Comando/inspección | Archivo:línea | Resultado real | Evidencia | Veredicto |
|---|---|---|---|---|---|---|
| **A0 Objeto** | Base r2 íntegra; 0 cambios productivos | `shasum -c` r2 = 53/53; `cmp` de 10 productivos vs r2 | `SHA256SUMS.txt` r2; `cmp` | **OK_r2=53**, **same=10 diff=0** | salida de comandos en esta sesión | **VERDE** |
| **A1 Sensibilidad** | Mutación del rechazo de espacio debe hacer fallar el test | `test_mutating_space_rejection_breaks_test` | `tests/test_f1_arnes.py` | baseline rc≠0; **mutante `ok=True` rc=0** (el test fallaría sobre el mutante); hash del mutante registrado en `sensitivity.txt` | unittest F1 | **VERDE** |
| **A1b Inyección** | `du`/`df` inyectados 1 sola vez, gate alcanzado | `test_du_*`, `test_df_*`, `test_injection_point_unique` | `place_helper.py:229` (punto de mutación `ok = avail >= need`) | 7/7 OK; contador `du` = 1 | unittest | **VERDE** |
| **A2 Efectos** | Negativos sin publicación; positivo sí publica | `test_arnes_puede_llegar_a_publicacion` + B-1 script | `tests/test_f1_arnes.py`, `test_correcciones_b_i.py` | B-1: rc=1 destino=False COLOCADO=False; positivo: rc=0 destino=True | unittest | **VERDE** |
| **A3 Regresión** | bash -n + suite completa | `bash -n` ×2; `unittest discover` | scripts; tests | **bash OK**; **174/174 OK** (70.9 s) | salida | **VERDE** |
| **A3b TMPDIR** | 3 variantes existentes usadas | `test_f5_tmpdir.py` | `tests/test_f5_tmpdir.py` | 4/4 OK; inexistente **no** se valida como variante | unittest | **VERDE** |
| **A4 Matrices** | Filas CORREGIDO con evidencia real | lectura `MATRIZ_*`, `ADENDA_P2_7_8.md` | r3 | Cada fila enlaza archivo de esta revisión o apoyo sellado; sin «ver adenda» vacía | documentos | **VERDE** |
| **A5 Apoyos** | P2 §7/§8 + P3/P4 con cronología | `MATRIZ_APOYOS.md` | r3 | P3 posterior a cierre r2; P4 ensayó r1; disposición por hallazgo | documento | **VERDE** |
| **A6 Alcance** | Listados por ruta, núcleo congelado | `ALCANCE_R3.md` + `cmp` | r3 | 10 productivos byte-idénticos; exclusiones enumeradas | A0 | **VERDE** |
| **A7 Coherencia** | Sin mezclar cifras históricas | `INDICE_HISTORICO.md` | r3 | C-9 = du+2GiB; conteos 174; C-5 pendiente | documento | **VERDE** |
| **A8 Entrega** | Manifiesto/ZIP/recibo verificables | (se sella después de este documento) | — | **PENDIENTE de sellado** (se completa en recibo) | recibo externo | **ÁMBAR** → se cierra con A8b |
| **A9 Preservación** | Bases y recibos intactos | `shasum` r2 zip/recibo | — | ZIP `2383bb85…`, recibo `4369c20e…` **coinciden** con la OT | salida | **VERDE** |

## Revisión adversarial de tests modificados

| Pregunta | Resultado |
|---|---|
| ¿Pasan sin ejecutar la rama? | No: `space-check` invoca `du`/`df` (contador=1); mutación rompe el test. |
| ¿Un error de ruta/mock da el RC esperado? | Positivo exige `COLOCADO_VERIFICADO` + archivo en destino; no solo RC=0. |
| ¿Se intercepta la dependencia real? | Inyección **única** en `measure_space_need/avail`; `test_injection_point_unique` lo exige. |
| ¿El positivo prueba la preparación? | Sí: publica con `aceptar_usuario` + inventario + DMG presente. |

## Puertas rojas

**Ninguna.** A8 se cierra con el recibo externo post-sello (no forma parte del candidato).
