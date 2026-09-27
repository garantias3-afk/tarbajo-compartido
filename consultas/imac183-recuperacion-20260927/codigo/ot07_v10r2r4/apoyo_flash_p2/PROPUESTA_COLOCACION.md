# PROPUESTA_COLOCACION v2 — OT07-P2 (GLM Flash)

**Estado: PROPUESTA para revisión (Qwen 3.8) e integración (MiMo v2.6 Pro). No se ejecutó contra
/Applications, sin sudo real, sin tocar el PKG real ni la app extraída (solo fixtures).**
Esta propuesta corrige C-2…C-9 y C-10 (evidencia nueva) sobre los artefactos originales de Flash,
que permanecen intactos en `/var/tmp/ot07_E2R1_evidencia.O5HIqi` (hashes verificados en
`insumos/HASHES_ORIGEN.txt`).

## 1. Identidad pineada (referencia externa, nunca del candidato a verificar)

| Campo | Valor | Procedencia |
|---|---|---|
| PKG_RUTA | `/var/tmp/ot07_E2R1_candidato.gMdKSX/InstallAssistant.pkg` | evidencia adquisición O5HIqi |
| PKG_BYTES | 13654790295 | anunciado por servidor y medido por Flash/Qwen/GLM53 |
| PKG_SHA256 | `ecc36bf172105f8c3325ceeb4e5ab8cc297260be806eac10b21b784ff40d8173` | tres mediciones independientes |
| Firma esperada | `Status: signed Apple Software` + cadena con `Apple Root CA` | `pkgutil --check-signature` |
| Manifiesto app | `APP_MANIFIESTO.txt` (721 archivos, E2-R1) + equivalencia payload verificada por GLM53 (03) | evidencia sellada |

El hash esperado está **escrito como constante** en `colocar_candidato_v2.sh` (que a su vez queda
sellado por hash en esta entrega). El script no lo lee del candidato ni de su manifiesto.

## 2. Secuencia del script v2 (colocar_candidato_v2.sh)

1. **Precondiciones del PKG (C-2/C-3/C-4)**: existencia; bytes exactos; SHA-256 pineado (RC de
   shasum comprobado); `pkgutil --check-signature` con RC capturado a archivo, literal
   `signed Apple Software` y presencia de `Apple Root CA`. Todo con `LC_ALL=C` y sin pipelines
   que enmascaren RC.
2. **Origen**: directorio real, no symlink, con `SharedSupport.dmg`; chequeo de enlaces absolutos;
   `symlinks_salientes` (transitivo, anti-ciclo, python del sistema); **inventario EXACTO**
   (suma completa de archivos regulares, rutas relativas) contra el manifiesto de referencia:
   detecta extras, faltantes y cambios de igual tamaño.
3. **Espacio (C-9)**: `du` del origen, `df` del volumen destino, requerido = origen + 2 GiB de
   reserva; falla si insuficiente. El pico real estimado de la operación completa (PKG + app
   extraída + staging + reserva) es ≈ 41 GiB; el número vinculante lo mide el script en vivo.
4. **Destino y padres (C-6)**: `DEST_PADRE=$(dirname "$DESTINO")` derivado y verificado (dir
   real, no symlink), definido ANTES de su primer uso (defecto detectado y corregido por el
   propio harness: ver HALLAZGOS §3).
5. **Staging EXCLUSIVO (C-7)**: `mktemp -d` dentro del directorio del candidato — no puede
   preexistir ni colisionar; copia con `ditto` y RC comprobado.
6. **Mismo filesystem (C-8)**: `stat -f %d` de staging-padre vs destino-padre; cross-device
   falla (un `mv` cross-device no sería renombrado atómico).
7. **Inventario EXACTO de staging** + confinamiento de enlaces; **re-comprobación inmediata**
   del destino y del padre.
8. **Traslado con `mv_excl`** (renamex_np `RENAME_EXCL|RENAME_NOFOLLOW_ANY`): RC 0 = movido;
   RC 17 (EEXIST) = destino apareció en la ventana → fail con staging conservado y SIN escribir
   dentro de destino ajeno; otro RC → fail estado-desconocido. **Sin fallback a `mv -n`**:
   la batería de primitivas (pruebas/harness_traslado.sh) demuestra que `mv -n` anida en un
   directorio aparecido (RC=0) y atraviesa un symlink destino (RC=0).
9. **Inventario EXACTO final** en el destino + rmdir del staging.
10. **Protección C-5 (preparada, decisión explícita)**: `MODO_PROTECCION`:
    - `REQUIERE_DECISION_C5` (por defecto): sale RC=3 con `COLOCADO_SIN_PROTEGER` y exige decisión.
    - `root`: `sudo -n /usr/sbin/chown -R -h root:wheel` + `sudo -n /usr/sbin/chmod -R go-w`
      sobre el árbol YA VERIFICADO sin enlaces salientes; RC comprobado; fallo →
      `PROTECCION_FALLIDA` (sin COLOCADO_VERIFICADO).
    - `aceptar_usuario`: registra la aceptación explícita y continúa.
    No se presenta chown/chmod como protección completa: existe ventana entre traslado y
    protección, `-h` evita seguir el (ya excluido) enlace, y no hay protección contra un
    administrador con sudo ya autorizado.

## 3. Pruebas (resultados en `pruebas/`)

- `harness_traslado.sh` — primitiva `mv`/`mv -n` REAL del host sobre fixtures (8 casos).
- `renamex_resultados.txt` + `renamex_binario_resultados.txt` — semántica de
  `renamex_np(RENAME_EXCL)` vía ctypes y binario compilado (9 casos + humo).
- `harness_v2.py` → `harness_v2_resultados.txt` — **21 casos sobre copias sustituidas del v2,
  21/21 OK** (éxito + 20 negativos). Ningún negativo produce `COLOCADO_VERIFICADO` ni toca
  destino real. Stubs declarados: pkgutil (positivo/negativo), ditto, stat, df, chown.
- Diff de referencia: `colocar_v1_a_v2.diff` (250 líneas).

## 4. Qué queda sin validar (declaración explícita)

- Operación real sobre `/Applications` con sudo y PKG real de 13.65 GB (prohibida en esta OT).
- `ditto`/`renamex_np` reales sobre árboles de 13 GB (fixtures pequeños).
- El positivo de firma usa stub de pkgutil (el positivo REAL del PKG está acreditado por tres
  mediciones independientes en evidencias selladas).
- `chown/chmod` reales sobre el bundle colocado (sustitutos con fallos inyectados).
- Enlace simbólico sustituyendo a un PADRE intermedio en la ventana del syscall: mitigado por
  `RENAME_NOFOLLOW_ANY` + verificación del padre inmediato; la sustitución de un padre por un
  DIRECTORIO real en la ventana es residual (documentada, no elimnable en user-space).
- Compilador del host: clang falla con el SDK 27 por defecto (`tapi error: malformed file`,
  `arm64e.x1-macos`); el binario se compiló con `-isysroot MacOSX26.5.sdk` (disponible).
  MiMo debe fijar el SDK o redistribuir el binario ya compilado.

## 5. Cambio mínimo sobre MiMo

MiMo puede adoptar directamente `colocar_candidato_v2.sh` + `mv_excl(.c)` con las constantes
pineadas, o integrar la primitiva en su v10r2. En ambos casos: re-ejecutar los casos pertinentes
sobre SU texto final y re-auditar (esta colaboración no acredita la versión integrada).
