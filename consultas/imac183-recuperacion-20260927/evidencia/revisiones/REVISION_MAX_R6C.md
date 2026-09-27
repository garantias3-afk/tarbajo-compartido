# REVISION_MAX_R6C.md — reauditoría del delta r6b→r6c (helper) — un bloqueante menor antes de H1-bis

- **Objeto:** `OT07_REVISION_v10r2r6c_MIMO` — manifiesto 40/40 OK `b307200dc6eaac496fa32657ae87713bf016f128a6fa252352997d92006d0375` (= pin AVISO); recibo `712aac31…4e51` ✓; r6b intacto. Binario nuevo `3bb1b3b5c38f57d25050b104f02d4494b11131b8bdd05986f78c0d091077a66d` — **procedencia verificada por Max** (recompila limpio, selfcheck idéntico; bytes difieren solo por firma del linker). Harness **59/59 reproducido por Max** (RC=0, 0 skips).

## Disposición

| Corrección | Veredicto |
|---|---|
| D1: `copy-tree` copia CONTENIDO dentro de la hoja existente (mkdir solo si falta dst; archivos O_EXCL; origen no-dir → dst/basename) | **CORRECTA** (leída línea a línea; colisión en hoja usada ⇒ EEXIST fail-closed) |
| D2: modos del origen menos g+w/o+w en archivos y subdirectorios (helper) y en `_copy_tree` (orquestador) | **CORRECTA para hijos; INCOMPLETA para la RAÍZ** — ver bloqueante |
| Protocolo: plantilla `H1_A_REEJECUCION.sh` con aborto al primer RC≠0, hash-pre-sudo en cada sudo, `C5_AUTH_BASE` | **CORRECTA** (con un ajuste de orden de verificación — ver bloqueante) |
| Opcional cleanup: `rmdir_vacio_bottom_up` (solo rmdir de árboles vacíos confinados; contenido residual ⇒ abort) | **CORRECTA** (sin rm genérico; permite retirar jCwt99 sin nuevos tipos de sudo) |

## Bloqueante menor (una línea + plantilla) — r6d antes de H1-bis

**R6C-1: el modo de la HOJA nunca se ajusta.** `mkdir-staging` la crea 0700 root:0 y `cmd_copy_tree` copia los hijos sin aplicar el modo del origen a la hoja. Consecuencias medibles en la propia plantilla: el paso 8 (pines de `h1_destino/a.txt`, `sub/b.bin`, `link` como uid 501) y el paso 9 (`sha256` del publicado, oráculo N7 del fd del origen) **fallarán con EACCES** — la raíz publicada queda 0700 e intransitable; el paso 7 (`verify`/`ls -le` como uid 501 del STAGING) además choca estructuralmente contra el padre root 0700. Con esto, la re-ejecución volvería a quedarse sin N1/N3/N7 legibles y el lector independiente de ACL de Flash (uid 501) no podría leer el árbol. Correcciones:
1. `cmd_copy_tree`: cuando src es dir, aplicar al dst (hoja) `chmod(dst, modo_origen & ~0222)` tras copiar (dst ya es root:0). El orquestador simulated ya hace el equivalente (`chmod(hoja, modo_origen)`) — paridad.
2. Plantilla: la verificación como uid 501 apunta al **árbol publicado** (tras publish, con `C5_AUTH_BASE=$H1` para el `verify` del helper); el `verify` del staging pre-publish pasa a ser root-side (`sudo`) o se elimina del paso 7.
3. (Nits no bloqueantes: los oráculos D1-01/D2-01/CLEANUP-01 del harness son textuales — válidos como chequeo de contrato, la validación real sigue siendo la re-ejecución nativa; añadir a D2-01 la aserción del chmod de hoja.)

**Sin r6d no se pide H1-bis**: quemar una ejecución privilegiada que provablemente no puede recolectar la mitad de sus oráculos contradice el protocolo. r6d = la línea del helper + ajuste de plantilla + rebuild/resello (hash nuevo) + harness. Max reaudita el delta (spot-check), y entonces presenta H1-bis con el hash definitivo.
