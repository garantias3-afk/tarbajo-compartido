# Auditoría adversarial del plan FIX_BIT

Fecha: 2026-09-21. **VEREDICTO: NO-GO para el plan actual sobre originales. B1 rechazada como rollback demostrado. B2 es candidata a ensayo aislado, no una reparación validada.**

La anomalía del identificador Fusion es real en las imágenes. Encontré dos refutaciones independientes de la justificación de B1: no elimina el checkpoint más nuevo y el estado 60773512 ya contiene modificaciones del software APFS 2332.140.13.703.4 que la consulta atribuye a Sequoia. No se acredita que invertir el bit sea suficiente para recuperar el montaje o el arranque.

**Alcance y procedencia.** Leí los cinco binarios y el plan de FIX_BIT, la GPT y bloques seleccionados del clon completo de tier1, el primer bloque de la imagen parcial de tier2, el código local del lector, dos implementaciones públicas y los manuales Apple instalados. No modifiqué los originales, las imágenes, FIX_BIT ni los montajes. No ejecuté fsck, First Aid, reparación, desbloqueo, ensamblado ni arranque. Los nuevos archivos están en el directorio de esta auditoría.

El host observado mediante sysctl es Mac17,9, Darwin 25.6.0 arm64; no se trata del iMac18,3 indicado como equipo averiado. Los originales aparecen por Thunderbolt; diskutil informa medios escribibles y dos contenedores stub. Las aperturas de sus dispositivos raw fueron denegadas y sudo no interactivo requirió contraseña. Por ello no certifico sus bloques actuales: la comparación binaria se refiere a las imágenes. No solicité ni utilicé contraseñas.

**Hallazgos y decisión.**

| ID | Gravedad | Estado | Hallazgo |
|---|---|---|---|
| F01 | Alta | CONFIRMED | B1 deja intacto y localizable el NXSB válido 60773513. Cambiar solo el bloque 0 no demuestra selección de 60773512. |
| F02 | Alta | CONFIRMED | 60773512 ya referencia APSB modificados por APFS 2332.140.13.703.4; Data y System son idénticos en los dos estados. |
| F03 | Crítica para preservación | CONFIRMED | Arrancar el propio iMac no impide escrituras. La reversión de uno o dos bloques no revierte posteriores cambios de ambos discos. |
| F04 | Alta | CONFIRMED | PLAN_ESCRITURA.txt identifica la partición con el tamaño del disco entero: 121332826112 en lugar de 121018208256 bytes. |
| F05 | Alta | PARTIAL | La anomalía de roles está demostrada en imágenes; que sea la única causa del fallo de montaje sigue sin demostrar. |
| F06 | Alta | REJECTED | Checksums válidos en estructuras seleccionadas no prueban ausencia de toda corrupción ni un sistema arrancable. |
| F07 | Media | CONFIRMED | ver_bloque.py emite una conclusión de reparabilidad excesiva y retorna exit 0 aun con checksum inválido. |
| F08 | Alta | CONFIRMED | El respaldo aportado de tier2 es parcial, 16 GiB; el clon completo de tier1 no respalda el Fusion completo. |

Las clasificaciones CONFIRMED identifican hechos o defectos verificados; no certifican el comportamiento del driver propietario de Apple. REJECTED se aplica a la inferencia indicada, no significa que haya demostrado corrupción global.

**1. Bit de miembro Fusion y suficiencia del bloque 0.**

La interpretación operativa es consistente: bit 0 del byte 15 de nx_fusion_uuid apagado para tier1, encendido para tier2. apfsprogs lo comprueba explícitamente y advierte la discrepancia de la referencia Apple. Su comprobación del par también compara xid y el resto del superbloque, normalizando rol y checksum; esto orienta la auditoría, pero no documenta todos los requisitos del driver macOS. [Código de apfsprogs, fusion_super_compare](https://github.com/linux-apfs/apfsprogs/blob/master/apfsck/super.c#L147-L198).

La constante FUSION_TIER2_DEVICE_BYTE_ADDR pertenece a las direcciones de bloques; no es el nombre del bit del UUID. La referencia Apple contiene ambas descripciones y una formulación problemática del rol del UUID. [Apple File System Reference, pp. 34 y 173](https://developer.apple.com/support/downloads/Apple-File-System-Reference.pdf).

Medición propia: de 55 NXSB del anillo, 54 terminan en ce70 y uno en ce71. Todos pasan Fletcher-64. Esto demuestra la anomalía histórica, pero no identifica por sí solo al escritor ni permite atribuir los otros 54 checkpoints a Sonoma.

No está probado que baste escribir el bloque 0: el checkpoint 60773513 conserva ce71 bajo B1. B2 hace coincidir ambas copias de tier1 y, frente al bloque 0 de la imagen parcial de tier2, obtiene igualdad salvo rol/checksum. La condición sigue pendiente de comprobar contra el estado actual de ambos originales y de ensayar el ensamblado nativo sobre copias completas.

**2. B1 versus B2 y riesgo de rollback.**

Prefiero **B2 como candidato experimental** porque conserva las referencias y la transacción más reciente. Verifiqué que cada binario B2 cambia únicamente el byte 1295 y cuatro bytes del checksum, frente a su original. Ambos archivos B2 son idénticos y correctos respecto de sus hashes publicados.

B1 mantiene desc_base=29385401 y desc_blocks=300. El NXSB 60773513 sigue dentro de ese intervalo, en el bloque 29385430, con checksum válido. El algoritmo de búsqueda de apfs-fuse vuelve a encontrar ese xid; sus desc_index/desc_len se usan después de seleccionar el NXSB. El código ofrece req_xid para seleccionar expresamente un estado anterior: copiar un NXSB al bloque 0 no equivale a ese parámetro. No ejecuté un montaje nativo para observar la política exacta de macOS. [ApfsContainer::Init](https://github.com/sgan81/apfs-fuse/blob/master/ApfsLib/ApfsContainer.cpp#L54-L146).

Apple describe el bloque 0 como acceso a los checkpoints y la selección del estado válido más reciente. [Apple File System Reference, pp. 8 y 26–27](https://developer.apple.com/support/downloads/Apple-File-System-Reference.pdf).

La segunda refutación procede directamente de los APSB resueltos por el OMAP de 60773512:

| Volumen | Bloque del store en 60773512 | xid del APSB | Registro ya presente |
|---|---:|---:|---|
| Data | 2107525 | 60773510 | apfs_kext y fsck_apfs 2332.140.13.703.4 |
| System | 2108221 | 60773511 | apfs_kext 2332.140.13.703.4 |
| Recovery | 2107446 | 60773508 | apfs_kext 2332.140.13.703.4 |
| Preboot | 2108273 | 60773512 | apfs_kext 2332.140.13.703.4, last_xid 60772920 |
| Update | 7488828 | 60772811 | Registro más reciente 2236.141.1.700.1 |

Al comparar 60773512 con 60773513, Data, System, Recovery y Update apuntan al mismo APSB físico. Solo Preboot cambia de APSB, a 2108305. No he inferido qué archivos concretos cambiaron a partir de esta comparación.

La suma de estas pruebas refuta que B1 sea el último estado previo a la intervención de APFS 2332 o que descarte toda la instalación interrumpida. El registro de fsck tampoco permite fechar o atribuir causalmente el cambio del bit en el NXSB.

Respecto de bloques liberados o reescritos: no encontré evidencia de sobrescritura en las estructuras verificadas de 60773512. Tampoco recorrí todo su grafo, sus extents y la asignación de ambos dispositivos. Copy-on-write y las colas de liberación ayudan a preservar coherencia, pero no certifican que cualquier checkpoint conservado sea un punto de restauración completo. Forzar un estado histórico podría referenciar datos reutilizados o enfrentar información de asignación y estado Fusion incompatible con el tier2 actual. No recomiendo invalidar checkpoints más nuevos para intentar forzarlo sobre originales.

**3. Orden de lectura y bloque 0 de tier2.**

No hay evidencia suficiente para afirmar el orden en que macOS descubre los dos dispositivos. En el lector público examinado, el main device suministrado aporta el NXSB inicial; eso no prueba el orden de enumeración de IOKit.

El valor ce71 es el rol esperado para tier2. **No lo convertiría a ce70.** El bloque 0 de meta2TB_16G.img, leído a offset 0, es idéntico a block0_original.bin: xid 60773513 y SHA-256 9cde39555ea1ea30eb561fa853e59e85c079308ab7afdffac2411ed5f7cc8e7a. No surge de esa evidencia una necesidad de modificar tier2 para ensayar B2.

Si se intentara B1, el bloque 0 de tier1 quedaría en xid 60773512 y la copia aportada de tier2 en 60773513. Es una discrepancia adicional, no una justificación para hacer nuevas escrituras no ensayadas.

**4. Spillover y primera verificación sin escrituras.**

Confirmé en Data flags=0x38, que incluye 0x20. La definición pública pide ejecutar el spillover cleaner, pero no especifica el instante en que corre al montar. No debe confundirse automáticamente con reproducción de un journal. [Apple File System Reference, p. 62](https://developer.apple.com/support/downloads/Apple-File-System-Reference.pdf).

También verifiqué checksum e identidad del objeto de estado de la write-back cache, oid 1026, en ambos checkpoints: registra 47 bloques de listas y offsets de cabeza y cola distintos. No recorrí ni validé el contenido de todas esas listas; no cuantifico escrituras pendientes. El riesgo de escritura no depende exclusivamente del cleaner.

Arrancar el propio Sonoma monta Data para trabajar y puede producir escrituras ordinarias y de mantenimiento. Incluso si System se monta read-only, eso no hace read-only a los dos medios físicos.

Para el primer ensayo recomiendo dos imágenes completas preservadas, dos copias de trabajo y originales desconectados. No presentar a APFS simultáneamente originales e imágenes con los mismos UUID: una imagen de tier1 y un tier2 original conectado no constituyen un laboratorio aislado.

Después de preparar y verificar B2 offline en la copia de tier1, ambos miembros de prueba deben exponerse como dispositivos no escribibles antes del ensamblado. hdiutil documenta -readonly a nivel del dispositivo y -nomount para suprimir el montaje; -nomount solo no significa protección contra escritura. La imagen completa de tier1 usa GPT 4Kn: hay que comprobar que el mecanismo de exposición respete los sectores de 4096 bytes; no he ensayado aquí esa presentación.

Estos son patrones documentados de la fase de inspección, **no comandos ya ejecutados ni una receta de conexión de los originales**. C y V son identificadores simbólicos que deben resolverse sobre el contenedor y volumen de las copias:

```text
diskutil apfs unlockVolume /dev/diskCsV -nomount
fsck_apfs -n -F /dev/rdiskC
diskutil mount readOnly nobrowse /dev/diskCsV
```

Orden: dispositivos protegidos y ensamblados, desbloqueo sin montar si corresponde, verificación del contenedor desmontado, montaje explícito de un volumen en read-only. No incluir contraseña en argumentos o logs. Confirmar ausencia de montajes de escritura, protección del medio y resultado de cada paso. Si macOS no ensambla o no permite comprobarlos en ese contexto, registrar el fallo y detener el ensayo, sin relajar la protección de los originales.

La sintaxis y alcance se contrastaron con /usr/share/man/man8/diskutil.8, /usr/share/man/man8/fsck_apfs.8 y /usr/share/man/man1/hdiutil.1 de este host. Validar disponibilidad en el entorno externo elegido. fsck -n prohíbe reparaciones; -F exige comprobar volúmenes cifrados desbloqueados. Un chequeo que omite estructuras cifradas no acredita su integridad. nobrowse solo afecta visibilidad.

**5. GPT, geometría e identidad del destino.**

Confirmado sobre el clon: cabeceras GPT primaria y secundaria con CRC válidos, CRC válidos de sus tablas y entradas coincidentes. La cabecera secundaria está en el último LBA del archivo. Las particiones ocupan los intervalos esperados:

| Magnitud | Valor |
|---|---:|
| Disco completo / archivo | 121332826112 bytes |
| Sector GPT / dispositivo de tier1 | 4096 bytes |
| EFI, inicio | 24576 bytes, LBA 6 |
| EFI, tamaño | 314572800 bytes = 300 MiB |
| Apple_APFS, inicio | 314597376 bytes, LBA 76806 |
| Apple_APFS, tamaño | 121018208256 bytes = 29545461 bloques APFS |
| Apple_APFS, último LBA | 29622266 |
| GPT secundaria, LBA | 29622271 |
| Checkpoint B2, offset en partición | 120362721280 bytes |
| Checkpoint B2, offset en disco completo | 120677318656 bytes |

Los tamaños y el offset de la partición observada en vivo por diskutil coinciden. La identificación publicada en PLAN_ESCRITURA.txt:8 es incorrecta: usa el tamaño del archivo/disco para la partición.

La GPT actual es coherente. Sin una GPT anterior al incidente no puedo probar que el instalador nunca la modificó. Tampoco certifico contenido EFI/OpenCore o arranque por verificar GPT. No hay evidencia en estas lecturas que justifique repararla.

El nx_uuid es compartido por el par y por sus copias; no identifica por sí solo el destino. Una futura operación necesita identidad física, geometría, UUID de partición, rol y comprobación exacta del contenido original. El UUID de partición tier1 observado es A887F5E2-9B2F-589E-8272-B88E9485386E. Los números diskN son transitorios y no deben conservarse como identidad.

**6. Pasos previos y criterio de aceptación.**

1. Terminar y verificar la extracción necesaria: cobertura, errores, tamaños, hashes y apertura de formatos representativos. No he auditado su finalización en esta revisión. Los informes anteriores del mismo directorio documentan un lector que devolvía ceros al ignorar errores y su posterior corrección; una igualdad de hashes usando el mismo lector defectuoso no prueba recuperación. Confirmar el binario efectivo y sus validaciones, sin asumir que aquel defecto persiste.
2. Obtener un clon completo de tier2 y preservar coherencia temporal de ambos miembros. La imagen parcial de 16 GiB no cubre los aproximadamente 2 TB del store. El tier1 completo permite restaurar tier1; no restaura cambios posteriores en tier2.
3. Registrar el estado actual de ambos bloques 0 y del checkpoint objetivo; compararlo con la evidencia aquí revisada. Si difiere, no aplicar automáticamente estos binarios.
4. Ensayar B2 en un par de copias completas, offline y aislado de los originales. Las dos escrituras no son una transacción atómica conjunta; completar y verificar ambas antes de exponer el par al driver.
5. Hacer comprobación nativa de solo lectura, con soporte de esa versión APFS y cifrado desbloqueado según corresponda. Guardar log, código de salida y advertencias; comprobar cobertura de todos los volúmenes y snapshots. No usar First Aid ni fsck -y en los originales como prueba diagnóstica.
6. Verificar lectura de datos y estado de System/Data, Preboot y snapshot de arranque. Un contenedor ensamblado no demuestra que OCLP, EFI o la instalación interrumpida permitan arrancar. Si hace falta una prueba con escrituras, usar copias descartables de los dos miembros.
7. Solo después de esos resultados se puede evaluar una operación sobre originales. Esta auditoría no aporta esa validación ni recomienda arrancar el original ahora.

La reversión de B2 requiere restaurar **ambos bloques modificados**. Aun así, solo revierte B2 mientras ningún otro actor haya escrito. Tras escrituras adicionales, la restauración exacta requiere respaldos del par en el mismo estado, no solo block0_original.bin.

**Controles adicionales del paquete.**

Verifiqué independientemente los cinco SHA-256 contra SHA256SUMS.txt y todos sus Fletcher-64. Los originales del bloque 0 y del checkpoint coinciden con sus posiciones en el clon. B1 es exactamente la copia del checkpoint 60773512; su checksum ya era válido. B2 conserva xid 60773513 y sus dos archivos coinciden.

En 60773512 verifiqué los tres checkpoint maps, su marca final y los 255 objetos mapeados: checksum, oid, xid, tipo y subtipo. En 60773513 hice lo mismo con dos maps y 200 objetos. Para cada estado también verifiqué el OMAP de contenedor, su raíz de cinco entradas, los APSB resueltos y la raíz del Fusion middle tree. Los recuentos del spaceman son 29545461 + 488327436 = 517872897, iguales a nx_block_count. Esto amplía la evidencia local; no es una verificación completa del contenedor ni del contenido de todos los archivos.

El inspector original imprime una aprobación de reparación basándose en magic, checksum y rol. No puede deducir ensamblado del par a partir de un bloque aislado. En una prueba con copia corrupta creada únicamente en work, imprimió checksum inválido y finalizó con código 0. Debe tratarse como visor informativo, no como gate ejecutable. No lo modifiqué.

El clon tier1 y la imagen parcial tier2 conservaron el flag uchg. No calculé hash de los 121 GB completos ni certifiqué su igualdad total con el dispositivo real. El ensayo B1 descrito en el paquete solo demuestra que la sustitución de un bloque produce bytes y checksum esperados; no acredita cuál checkpoint seleccionaría el driver ni seguridad de montaje.

**Evidencia reproducible adjunta.**

- evidencia_apfs.json: geometría, hashes, 55 NXSB, campos de ambas variantes, mappings y objetos verificados, APSB e historiales.
- evidencia_tier2_parcial.json: procedencia y comparación del bloque 0 del tier2 parcial; limitación de lectura en vivo.
- prueba_inspector.json: salida y código de retorno del caso con checksum inválido.
- auditar_clon_solo_lectura.py: inspector independiente empleado; solo abre el clon y los binarios para lectura y escribe su informe en outputs.
- fuentes_codigo.json: URLs y SHA-256 de las dos fuentes públicas descargadas durante la revisión.
- SHA256SUMS_AUDITORIA.txt: integridad de los entregables.
