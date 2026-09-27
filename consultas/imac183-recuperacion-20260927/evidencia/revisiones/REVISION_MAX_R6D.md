# REVISION_MAX_R6D.md — spot-check del delta r6c→r6d: ACEPTADO

- **Objeto:** `OT07_REVISION_v10r2r6d_MIMO` — manifiesto 45/45 OK `ea55af7231a765d5201b09e1ad13c5956fb52b64db182a3aa1bd99aa23caa3db` (= pin AVISO); recibo `4af85b4d…d5b8` ✓; r6c intacto. Binario `11b37e79be847e3d280bed36b844d1e19e35481a800a35dc633f5167fdc9bfcc` — procedencia verificada (recompila limpio, selfcheck idéntico). Harness **59/59 reproducido por Max** (RC=0, 0 skips).
- **R6C-1 CORREGIDO:** `cmd_copy_tree` aplica `chmod(dst, modo_origen & ~0222)` a la hoja tras copiar los hijos (líneas 265-269; paridad con simulated). Plantilla: paso 7 registra verify root-side del staging (y el RC esperado 13 como uid 501); paso 8b verifica el ÁRBOL PUBLICADO como uid 501 con `C5_AUTH_BASE=$H1`. D2-01 del harness endurecido.
- Delta acotado a lo pedido, sin cambios laterales. **H1-bis se presenta junto con este sello** (mismo alcance A+B-condicionada, objeto = binario nuevo).
