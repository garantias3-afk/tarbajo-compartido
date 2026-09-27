# ADJUDICACION_MAX_H1_A.md — adjudicación N0–N9 del ensayo nativo A (r6b)

- **Evidencia autenticada:** `RECIBO_H1_NATIVO_A.json` (`bb5dd90f…1c52` ✓) y `H1_NATIVO_A.log` (`77512794…262e` ✓), leído íntegro por Max. Binario ejecutado: `92a33c5b…` con `[hash-pre-sudo]` verificado antes de CADA sudo (disciplina N0 cumplida en el log).
- **Registro honesto de la corrida:** el log contiene DOS secuencias. La primera (17:22:13Z) tuvo captura rota (staging vacío, paths literales `/leaf`, oráculos errno=2 contra rutas inexistentes) — se descarta como evidencia. La real es el reintento (17:23:46Z, SUDO_ASKPASS), de la que trata esta adjudicación y el resumen de MiMo.

## Oráculos

| N | Veredicto | Evidencia (log, reintento) |
|---|---|---|
| N0 bootstrap | **GO** | hash del binario verificado ante cada sudo; sellos de entrada verificados; `listo_para_pedir_H1=true`; selfcheck RC=0 |
| N1 metadata raíz/hijos | **PENDIENTE** | árbol vacío por D1: sin archivos que verificar |
| N2 aislamiento frontera | **GO-parcial (contenedor)** | 5/5 errno=13 como uid 501 (open O_WRONLY/O_RDWR, rename/unlink/rmdir) por denegación de recorrido de los contenedores root:0 0700; lectura del publicado denegada (errno 13). **Nivel archivo pendiente**: el árbol estaba vacío (D1) y la copia nativa jamás ejecutó contenido |
| N3 ACL ± | **PENDIENTE** | `ls -le` como uid 501 imposible sobre 0700 root (D2) |
| N4 AT_UNIQUE/esp. | **PENDIENTE** | solo probe-at del fixture (RC=0, sin hardlink de prueba en esta corrida) |
| N5 ancla | **PENDIENTE** | ancla generada y verificada en preparación; mutación no ensayada |
| N6 EEXIST | **GO** | `publish` ⇒ RC=4, errno=17 «destino preexistente»; `ganador.txt` conservado; staging retenido y listable por `list-stale` |
| N7 check→uso | **PENDIENTE** | fd del origen escribió 19 bytes (el origen es del operador); el oráculo «fd del origen no altera lo publicado» NO es concluyente con árbol vacío |
| N8 confinamiento | **GO-parcial** | D3: `verify` del destino publicado rechazado «fuera-de-frontera» (el confinamiento FUNCIONA); cleanup confinado OK; `list-stale` sin glob |
| N9 regresión | n/a esta fase | — |

**Transición C5_NATIVO_VALIDADO: NO otorgada.** Sección B NO habilitada (correctamente no ejecutada).

## Decisiones sobre D1/D2/D3

- **D1 — REQUIERE_CORRECCIÓN (r6c, bloqueante):** confirmado con mecanismo exacto: `copy_walk` hace `mkdir(dst)` de la RAÍZ del origen, pero la hoja ya fue creada por `mkdir-staging` ⇒ errno 17, RC 2, árbol vacío. La acción `copy-tree` jamás había podido ejecutarse antes de H1 (acción solo-root) — es exactamente el tipo de defecto que el ensayo nativo existe para detectar. Registro además que mi revisión de código no lo atrapó: el delta r6 leyó `cmd_copy_tree` sin cruzar la preexistencia de la hoja. Corrección: copiar DENTRO de la hoja existente (el `mkdir` raíz sobra; los archivos ya van con `O_EXCL`), o que `mkdir-staging` no cree la hoja y la cree `copy-tree` — decisión de MiMo, con test no privilegiable pero con verificación de contrato (RC=0 y árbol completo) en la re-ejecución.
- **D2 — decisión de diseño (r6c):** el helper fija 0700/0600 siempre; la INTERFAZ dice «r-x de otros conservado si origen 0755». Corrección coherente: `copy-tree` conserva los modos del origen menos `g+w/o+w` (dueño root + go-w + ACL deny dan la no-escritura; el recorrido/lectura queda para verificación). El fixture de la re-ejecución se crea con dirs 0755/archivos 0644 (umask 022 solo para el fixture) para que `verify`/`ls -le` como uid 501 funcionen. Si MiMo prefiere mantener 0700, entonces la verificación se declara root-side (sudo ls -le/verify) y se documenta como excepción — elegir una de las dos, explícita en el recibo.
- **D3 — procedimiento (sin cambio de código):** el rechazo «fuera-de-frontera» del `verify` sobre `h1_destino` es el confinamiento funcionando. En la re-ejecución: `C5_AUTH_BASE=$H1` exportado para las lecturas del destino publicado (el helper ya lo soporta).
- **Protocolo (nuevo, obligatorio):** la corrida CONTINUÓ (`protect`/`publish`) después de un `copy-tree` RC=2 — prohibido. La re-ejecución aborta al primer RC≠0 y registra; nada se publica tras un fallo. (El `h1_destino` vacío publicado es producto de eso; queda como residuo registrado.)
- **Residuos:** correcto no borrar a ciegas. `ot07_c5_staging.jCwt99` (root) queda retenido; en r6c, `cleanup` puede ganar retiro bottom-up de ÁRBOL VACÍO propio confinado (sin `rm` genérico) — opcional pero recomendado para cerrar el ciclo sin nuevos tipos de sudo. `h1_destino_eexist` contiene el ganador del operador (retirable por el operador).

## Camino a la re-ejecución

1. MiMo sella **r6c** (D1 + D2 + protocolo; opcional cleanup-mejora y D3-doc) — diff por archivo, harness propio re-corrido.
2. Max reaudita el delta del helper (el binario cambia).
3. **H1-bis**: como el hash del helper cambia, la aprobación actual NO cubre el binario nuevo — pediré a OPERADOR una confirmación puntual (mismo alcance A, hash nuevo) antes de re-ejecutar. Sección B sigue condicionada al GO completo de A.
