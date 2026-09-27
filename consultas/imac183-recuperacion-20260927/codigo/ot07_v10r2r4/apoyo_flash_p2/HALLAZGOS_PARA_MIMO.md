# HALLAZGOS_PARA_MIMO — OT07-P2 (GLM Flash → MiMo v2.6 Pro)

Insumos para la implementación v10r2 y la colocación. Nada de esto es una auditoría
independiente final: es colaboración del autor del artefacto original. Los tests sobre esta
propuesta no acreditan la versión que MiMo termine integrando.

## 1. `mv -n` NO es suficiente para el traslado (demostrado en el host, fixtures sin privilegios)

`pruebas/harness_traslado.sh`: en macOS 26/27 (BSD mv), `mv -n` con un **directorio** que aparece
en el destino **anida** la app dentro (`RC=0`), y con un **symlink** destino **atraviesa** el
enlace y escribe dentro del árbol ajeno (`RC=0`). Además, con destino archivo preexistente sale
**RC=0 sin mover** (RC=0 no significa éxito). La verificación de estado post-traslado es
obligatoria pase lo que pase, y preferentemente debe evitarse la escritura errónea, no solo
detectarla.

## 2. Primitiva correcta: `renamex_np(RENAME_EXCL|RENAME_NOFOLLOW_ANY)`

- Documentación primaria: `man 2 renamex_np` y `sys/stdio.h` del SDK local
  (`RENAME_EXCL=0x4`, `RENAME_NOFOLLOW_ANY=0x10`). `RENAME_EXCL` devuelve **EEXIST si el destino
  existe** (sea archivo, directorio o symlink) en filesystems con `VOL_CAP_INT_RENAME_EXCL`
  (APFS local lo soporta — verificado empíricamente en fixtures de /private/var/tmp).
- Con `RENAME_EXCL`: la carrera check→mv deja de poder escribir dentro de destino ajeno; los dos
  contendientes dan un ganador (rc=0) y un perdedor (EEXIST) determinista; **nunca anida**.
- `RENAME_NOFOLLOW_ANY` devuelve ELOOP si la ruta contiene enlaces intermedios: usar rutas físicas
  (`/private/var/…`) y asumir el límite de que un `realpath` previo ya habría seguido el enlace del
  padre (documentado en MATRIZ_P2).
- Entregado: `mv_excl.c` (fuente) y `mv_excl` (compilado con
  `-isysroot …/MacOSX26.5.sdk`; el clang del host **falla** con el SDK 27 por defecto:
  `tapi error: malformed file … arm64e.x1-macos` — fijar SDK o redistribuir el binario).
  Verificación independiente vía `ctypes` incluida (`renamex_resultados.txt`).

## 3. Defecto de mi propio parche v2 que el harness destapó (método, para no repetir)

La función de inventario con `( cd X && find … ) | xargs shasum` **no funciona**: el `cd` del
subshell no afecta al lado derecho del pipeline, así que shasum buscaba las rutas relativas en el
cwd equivocado ("No such file or directory"). Reemplazado por un helper python que genera el
inventario con rutas relativas al padre. Segundo defecto (mismo origen): la sección de espacio
usaba `DEST_PADRE` antes de definirla (unbound con `set -u`) — corregido reordenando. Ambos fueron
detectados POR LAS PRUEBAS y corregidos antes del sello; el harness quedó conservado con sus
etapas intermedias en el historial de la sesión, y la versión final 21/21.

## 4. Comprobaciones que el v1 no hacía y el v2 hace (C-2/C-3/C-4/C-6/C-7/C-8/C-9)

- Existencia, bytes, SHA pineado y firma (`signed Apple Software` + `Apple Root CA`) del PKG con
  RC comprobado, `LC_ALL=C`, sin pipelines que enmascaren RC — **antes** de cualquier efecto.
- El hash/firma esperados son constantes del script (sellado), nunca datos del candidato.
- `dirname` del destino derivado y verificado; mismo filesystem con `stat -f %d`; staging
  exclusivo por `mktemp -d`; inventario **EXACTO** (extras/faltantes, no solo `shasum -c`) en
  origen, staging y final; symlinks salientes rechazados con resolución transitiva.

## 5. C-5 (propiedad del bundle colocado) — preparado, requiere decisión de OPERADOR

`MODO_PROTECCION` con tres valores: `REQUIERE_DECISION_C5` (por defecto: RC=3 y sin
COLOCADO_VERIFICADO), `root` (`chown -R -h root:wheel` + `chmod -R go-w`, una sola operación
privilegiada extra sobre el árbol ya verificado sin enlaces salientes) o `aceptar_usuario`
(aceptación explícita registrada). Límites declarados: ventana entre traslado y protección;
`chown -R -h` no sigue enlaces (que ya están excluidos); **no hay protección contra un
administrador con sudo ya autorizado** (no se exige). Recordatorio de Qwen: el bundle con dueño
`OPERADOR:wheel` lo ejecutaría root (`CREAR_PEN_BOOTEO.sh:113` en v10r1) vía createinstallmedia.

## 6. Espacio por fases (C-9)

Pico real ≈ **38.2 GiB** (PKG 12.72 + app extraída 12.7 + staging 12.7 + redondeos), no los
~30 GiB que declaró mi FUENTE.json. El script v2 mide espacio vivo (du+df+reserva 2 GiB) y falla
cerrado; MiMo debe mantener esa medición viva y NO fijar "38 GiB" como constante de suficiencia.

## 7. Errata de adquisición (C-10 / desviación documental)

Ver `ERRATA_ADQUISICION.md`. Resumen: la metadata primaria de catálogo NO se obtuvo (403/404
documentados); el estado que usé (`CANDIDATO_PREPARADO_PENDIENTE_AUDITORIA`) no fue el literal
`FUENTE_NO_ACREDITADA` que mi OT pedía para ese caso; autenticidad criptográfica (acreditada por
firma y dominio Apple) queda separada de la versión/build (14.8.9/23J631 sigue INFERIDA de la
pista y pendiente de `Assets[0]` en E-R2). No se ratifica el desvío ni se atribuye aceptación a
OPERADOR: esa decisión sigue abierta.

## 8. Evidencia de forma a rectificar en documentos NUEVOS (C-10, de Qwen)

- `02_zip_vs_carpeta.log` (Flash, 95 B): conclusión sin comando/salida → en esta entrega el
  equivalente (`pruebas/harness_v2_resultados.txt`, `renamex_*`) conserva comando/salida; el ZIP
  de esta entrega (si se genera) se comparará byte a byte.
- `09_expansion_inspeccion.log`: lista de TODOS los symlinks bajo un rótulo "que escapen" →
  aquí el chequeo de confinamiento es un chequeo real (python) con salida vacía = ninguno.
- `10_replica_postinstall.log`: sin RC de la réplica → NO_CAPTURADO se mantiene como histórico;
  esta entrega no fabrica el RC (las nuevas métricas registran comando y RC desde el origen).

## 9. Recordatorio de alcance

MiMo es el único escritor de v10r2. Esta carpeta es insumo: adoptar el parche requiere revisión
de Qwen vinculada a los hashes de `SHA256SUMS.txt` de esta entrega y re-ejecución de los casos
pertinentes sobre el texto final integrado. E sigue NO_EJECUTADO; sin medio creado; arranque
NO_PROBADO; F/G no autorizados.
