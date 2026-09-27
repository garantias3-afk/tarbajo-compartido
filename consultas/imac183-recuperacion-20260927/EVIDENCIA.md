# Evidencia técnica y estado real de las afirmaciones

## 1. Etiquetas

- **VERIFICADO_ACTUAL**: lectura de archivos, metadatos o comandos inocuos ejecutada al preparar esta entrega; alcance exacto indicado.
- **HISTORICO_DOCUMENTAL**: se leyó el informe/log, pero no se repitió la medición del medio ni se verificaron todos sus resultados.
- **DECLARADO_POR_USUARIO**: antecedente aportado por el usuario.
- **INFERENCIA**: conclusión técnica razonada, separada de una observación.
- **NO_VERIFICADO**: falta evidencia suficiente; no significa resultado negativo.

Un hash de informe confirma qué informe se leyó; no convierte su contenido en una nueva medición del disco. Los hashes publicados de bloques históricos no equivalen a hashes de imágenes completas.

## 2. Incidente y equipos diferentes

**DECLARADO_POR_USUARIO:** el iMac18,3 funcionaba con Sonoma y OCLP «2.4»; se actualizó la app a «2.5…»; luego se intentó instalar Sequoia y el usuario sospecha un error en EFI. No constan versión exacta de la app histórica, build de cada macOS, último OpenCore realmente arrancado, firmware, GPU precisa, contenido EFI antes/después ni momento exacto de la falla. La secuencia temporal no establece causalidad.

**VERIFICADO_ACTUAL, host que prepara el expediente:** Mac17,9, arm64, macOS 26.6.2 build 25G83, Python 3.9.6. Es otro Mac, no el iMac averiado. La medición íntegra está en [ENTORNO_LOCAL_20260927.json](evidencia/ENTORNO_LOCAL_20260927.json), con hora UTC y hashes de los plist consultados.

| Objeto local | Observación actual | Límite |
|---|---|---|
| `/Applications/OpenCore-Patcher.app` | CFBundleShortVersionString y CFBundleVersion 2.4.1 | App en host de preparación; no prueba OCLP/EFI instalados en el iMac |
| UFS Explorer RAID Recovery | Versión 10.22, bundle `com.sdl.exe.UFS-Explorer-RAID-Recovery` | Instalación comprobada; licencia/activación y capacidad efectiva de guardar archivos no comprobadas |
| `/Applications/Install macOS Sonoma.app` | No existe en el corte actual | Puede existir un candidato extraído en otra ruta; no se ha colocado en Applications |
| Proceso histórico 3494 | `ps` lo muestra como apfs-fuse, activo | No se revalidaron flags de montaje ni identidad suficiente para enviar señales |
| PIDs históricos 3512 y 9811 | No aparecen en la consulta acotada | No prueba finalización exitosa del rescate; no se enviaron señales |

La documentación histórica de compilación especifica Apple clang 21.0.0 y SDK MacOSX26.5.sdk, mínimo macOS 14.0. Reporta problema de linker con SDK 27.0. Es un dato histórico a reproducir si se recompila; no trasladar ABI/APIs de macOS a Linux ni generar un helper arm64 para ejecutar en el iMac Intel.

## 3. Almacenamiento y tamaños: no confundir unidades ni objetos

Capturas del hilo del 27/09, **HISTORICO_DOCUMENTAL**:

| Entrada UFS | Capacidad mostrada | Sector mostrado | Ruta de aquella captura |
|---|---:|---:|---|
| Apple Thunderbolt UTDM | 113,00 GB | 4096 bytes | `/dev/rdisk7` |
| ATA CT2000MX500SSD1 | 1,82 TB | 512 bytes | `/dev/rdisk8` |
| Entrada adicional UTDM/volumen | 112,71 GB | No adjudicado aquí | `/dev/rdisk9` |

UFS mostró el volumen Data y advirtió que pertenecía a un volumen distribuido. No se acreditó que hubiera reconstruido el conjunto completo. Los `diskN` son transitorios; la entrada adicional no se convierte por inferencia en un tercer miembro. El CT2000MX500SSD1 es el modelo observado: no cambiarlo a un HDD solo porque la guía general de Fusion use ese ejemplo. Las etiquetas de capacidad de UI no sustituyen la geometría en bytes de las imágenes.

**HISTORICO_DOCUMENTAL, auditoría binaria del 21/09**, detalle en [AUDITORIA_APFS.md](evidencia/apfs/AUDITORIA_APFS.md) y [evidencia_apfs.json](evidencia/apfs/evidencia_apfs.json):

| Magnitud de tier1 | Valor registrado |
|---|---:|
| Disco completo/imagen | 121332826112 bytes |
| Sector GPT del disco | 4096 bytes (4Kn) |
| Inicio EFI | 24576 bytes, LBA 6 |
| Tamaño EFI | 314572800 bytes (300 MiB) |
| Inicio Apple_APFS | 314597376 bytes, LBA 76806 |
| Tamaño Apple_APFS | 121018208256 bytes |
| Bloques APFS tier1 | 29545461 de 4096 bytes |
| Bloques APFS tier2, según metadatos | 488327436 de 4096 bytes |
| Suma nx_block_count | 517872897 |
| GPT secundaria | LBA 29622271 |

Estos valores son diagnósticos históricos; no son una receta de escritura. Se conservaron los offsets completos del informe para permitir auditar sus cálculos. El plan viejo confundía tamaño de disco y partición: no reutilizarlo.

**VERIFICADO_ACTUAL, solo stat de dos archivos existentes:** `disk121_completo.img` tiene 121332826112 bytes; `meta2TB_16G.img` tiene 17179869184 bytes (16 GiB). Ambos mantienen flag `uchg`. No se leyeron sus contenidos ni se calcularon sus hashes completos. La primera tiene tamaño de imagen completa de tier1, pero tamaño+uchg no prueba adquisición íntegra ni identidad total con el original. La segunda es parcial y no respalda el store tier2 completo. No se buscó exhaustivamente si existe otro clon en otro destino.

**VERIFICADO_ACTUAL:** el JSON de entorno contiene espacio disponible en el host (~139,4 GB decimales) y destino de rescate (~46,2 GB decimales), con hora del corte. Es espacio observado, no reservado. Ninguno de esos valores demuestra capacidad suficiente para una imagen completa independiente de un miembro de ~2 TB. No confiar en una cifra antigua de “~122 GB faltantes” sin explicar formato, compresión, asignación, soporte y peor caso; no sumar destinos como si fueran automáticamente un único archivo utilizable.

## 4. APFS, cifrado, checkpoint y rollback

**HISTORICO_DOCUMENTAL:** los antecedentes describen Data cifrado con FileVault, oid 1033, y acceso previo mediante lector `apfs-fuse` con tratamiento de errores. No se publica ni solicita la contraseña. Enumerar no acredita lectura íntegra; un lector anterior podía devolver ceros al ignorar fallos. Tampoco debe suponerse que el defecto siga presente en el binario actual sin comparar código/binario/evidencia.

La auditoría del 21/09 registra 55 NXSB, 54 con rol tier1 y uno con rol tier2; todos con checksum válido en aquella medición. El NXSB más reciente del tier1 (xid 60773513) y su block0 tenían el mismo rol que tier2. Los UUID públicos son sustitutos consistentes: conservan igualdad y el bit de rol bajo, no la identidad física.

**B1 no acredita rollback a Sonoma:** cambiar block0 por xid 60773512 no elimina el NXSB posterior válido del descriptor, localizado en paddr 29385430. El estado 60773512 ya refiere registros `apfs_kext/fsck_apfs 2332.140.13.703.4`. Data, System, Recovery y Update apuntan al mismo APSB en ambos estados; Preboot cambia de 2108273 a 2108305. Esto no identifica qué archivos se modificaron ni quién cambió el bit.

**B2 es hipótesis experimental:** conservar xid 60773513 y corregir el rol de tier1 en dos estructuras. Pruebas sintéticas de bytes/checksum no prueban ensamblado macOS, coherencia completa, recuperación ni arranque. No se incluyen binarios de parche ni ejecutor B2 como vía operativa. El informe conserva sus resultados para revisión adversarial.

El informe encontró Data flags `0x38` (incluye `0x20`) y objeto de write-back cache oid 1026 con 47 bloques de listas; no recorrió todas las listas ni cuantificó escrituras pendientes. El riesgo de iniciar el sistema no se limita a ese mecanismo. `-nomount` o FileVault no convierten el medio en no escribible.

La GPT fue coherente en las estructuras examinadas de la imagen; eso no prueba contenido EFI correcto. No hay inventario acreditado de snapshots de arranque utilizables ni validación de todo System/Data/Preboot. Un checkpoint NXSB, un snapshot APFS y una copia externa son objetos distintos.

## 5. Rescate y cobertura

[OT06_RESUMEN_DESIDENTIFICADO.json](evidencia/OT06_RESUMEN_DESIDENTIFICADO.json) conserva conteos del cierre del 24/09 y hash del informe fuente. **HISTORICO_DOCUMENTAL**: 32 archivos prioritarios (11636226 bytes); 31298 archivos del subconjunto manifestado de Documents (616721143 bytes), frente a 400624 enumerados. Registra 8618 fallos: 8610 EIO, seis fallos de SCANDIR y dos de STAT; además 1283 podas y 222 symlinks omitidos.

El subconjunto verificado no equivale al rescate completo. Los contenidos no enumerados no están cuantificados por el número de eventos. La verificación local de copias no certifica identidad frente a todos los originales. EIO no prueba por sí solo daño físico. Los nombres de documentos/carpetas personales se excluyeron del paquete público.

## 6. Instalador disponible en registros

El [recibo de Muse](evidencia/instalador/RECIBO_MUSE_PREFLIGHT.json) y [CHAIN_REPORT](codigo/ot07_v10r2r4/evidencia_impl/CHAIN_REPORT.json) son evidencia histórica legible, no mediciones repetidas ahora:

- `InstallAssistant.pkg`: 13654790295 bytes; SHA-256 `ecc36bf172105f8c3325ceeb4e5ab8cc297260be806eac10b21b784ff40d8173`; firma Apple reportada válida.
- `SharedSupport.dmg`: 13643079050 bytes; SHA-256 `3e8c07f8d0e93fecdb3dcdc7f80b9de5b9ab93861991cc711ec3ff6b756c7b8d`.
- Assets[0] reportado: Sonoma 14.8.9 / 23J631; verificación DMG y firma de createinstallmedia reportadas exitosas.
- Inventario de app extraída: 1009 entradas; relación con payload y transformación `link_shared_support.bash` modelada. No se ejecutó el postinstall como prueba de procedencia.
- Firma global de app: RC=1, `resource envelope is obsolete (custom omit rules)`; el expediente propone cadena alternativa C-1. Debe auditarse su suficiencia; no transformar RC=1 en éxito de codesign ni omitir el error.
- Procedencia de descarga original del PKG no reconstruida. Firma, hashes, inventario y descarga son afirmaciones distintas.

Las rutas temporales históricas no garantizan disponibilidad actual. No se publica el instalador de ~13,6 GB. El código debe fallar cerrado si faltan esos objetos, firmas, ancla confiable o vinculación al objeto efectivamente consumido.

## 7. C5 y USB: estado por fase

| Fase | Evidencia disponible | Estado adjudicado de esta entrega |
|---|---|---|
| Integridad de base OT07 r4 | Manifiesto original recalculado 72/72 | VERIFICADO_ACTUAL, bytes del paquete |
| Integridad de candidato C5 r6d | Manifiesto original recalculado 45/45 | VERIFICADO_ACTUAL, bytes del paquete |
| Pruebas 59/59 r6d | Recibo MiMo y log Max incluidos | HISTORICO_DOCUMENTAL; ver REVISION para pruebas repetidas aquí |
| Ensayo nativo A r6b | Log+recibo+adjudicación | Falló copia; publicó árbol vacío; C5_NATIVO_VALIDADO no otorgado |
| Delta r6c/r6d | Fuentes+deltas+revisiones | Correcciones candidatas; revisar afirmaciones contra código |
| Reejecución nativa A con r6d | No se localizó resultado en las entregas consultadas | NO_VERIFICADO |
| Colocación real del instalador, sección B | Condicionada a A | No acreditada; app ausente en Applications al corte |
| Borrado/creación del USB H2 | No se incluye resultado | NO_VERIFICADO; exige identidad actual del único destino |
| Arranque físico H3 | No se incluye resultado | NO_VERIFICADO |
| Ensamblado o reparación APFS B2 | Fuera de OT07 | NO_VERIFICADO nativamente |

Binario original C5 r6d observado por hash: `11b37e79be847e3d280bed36b844d1e19e35481a800a35dc633f5167fdc9bfcc`. Se excluye de la publicación. Ese hash no aprueba un binario recompilado ni una versión corregida. Las autorizaciones históricas no se transfieren al revisor cloud.
