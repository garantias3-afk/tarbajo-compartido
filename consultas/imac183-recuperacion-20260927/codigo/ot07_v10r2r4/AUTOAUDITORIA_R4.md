# AUTOAUDITORIA_R4.md — puertas A0–A9 (medidas, no asumidas)

| ID | Expectativa | Comando/inspección | Resultado real | Veredicto |
|---|---|---|---|---|
| **A0** | Base r3 íntegra; 10 productivos idénticos | `shasum -c` r3 = 62/62; `cmp` ×10 vs r3 y r2 | **62/62 OK**; **same=10/10** vs r3 y r2 | **VERDE** |
| **A1** | Sensibilidad espacio + fallback | `tests/test_f1_arnes.py`, `test_f5_tmpdir.py` | Mutación `ok=True` rompe test; mutación `valid=True` rompe test | **VERDE** |
| **A2** | Negativos sin publicación; positivo publica | F1 + B-1 | B-1: rc=1 sin destino; positivo `COLOCADO_VERIFICADO` | **VERDE** |
| **A3** | Suite completa 3 TMPDIR | `unittest discover` ×3 procesos | **D: 176/176 OK 70.8s** · **A: 176/176 OK 71.2s** · **B: 176/176 OK 70.7s** | **VERDE** |
| **A3b** | Rutas efectivas = variante pedida | `tempfile.gettempdir()` en cada corrida | D=`/tmp`; A=`/var/tmp/ot07_r4_A2_*`; B=`/var/tmp/mimo_r4_B2_*` | **VERDE** |
| **A4** | Matrices con evidencia real | `MATRIZ_CIERRE_R4.md` | IDs H-1..H-8/H-2a..g/H-3 con archivo | **VERDE** |
| **A5** | Apoyos con cronología | `MATRIZ_CIERRE_R4.md` H-3 | Fechas de recibos sellados | **VERDE** |
| **A6** | Alcance por ruta | `ALCANCE_R4.md` + `cmp` | 10 productivos idénticos; exclusiones con hash | **VERDE** |
| **A7** | Coherencia de conteos | módulos | flow=6 probe=5 f5=7 total=**176** | **VERDE** |
| **A8** | Entrega sellada | manifiesto/ZIP/recibo | (posterior a este doc) | **ÁMBAR→A8b** |
| **A9** | Preservación r2/r3 | `shasum` | r3 62/62; r2 53/53; ZIPs/recibos intactos | **VERDE** |

## Adversarial de tests

| Pregunta | Resultado |
|---|---|
| ¿Pasan sin la rama? | No: inyección `du` contada; placeholder cardinalidad |
| ¿Mock da el RC esperado? | Positivo exige archivo + `COLOCADO` |
| ¿Interceptan la dependencia real? | `du`/`df` en helper real; PATH stubs |
| ¿Doble sustitución posible? | Token **antes** de insertar; assert `sin /private/private/` |
