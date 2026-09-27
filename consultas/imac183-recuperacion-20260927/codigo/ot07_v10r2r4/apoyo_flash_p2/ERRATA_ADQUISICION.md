# ERRATA_ADQUISICION — OT07-P2 (punto 8) — GLM Flash

Rectificación documental sobre mi propia entrega E2-R1 (`/var/tmp/ot07_E2R1_evidencia.O5HIqi`,
sello `MANIFIESTO_EVID.txt` 27 entradas). La evidencia sellada NO se edita: esta errata vive en
esta carpeta nueva y queda enlazada por hashes.

## Lo que la orden pedía

`01_OT_GLM_FLASH.md`, paso 4: la pista de terceros servía solo como pista; había que «enlazar y
conservar la metadata primaria que relaciona URL final, producto, versión/build y tamaño»; y si no
se encontraba vínculo primario, marcar **`FUENTE_NO_ACREDITADA`**.

## Lo que ocurrió

- La metadata primaria de catálogo **no se obtuvo**: 404 en los patrones históricos de
  `swscan.apple.com`, 403 de `mesu.apple.com` para `MacSoftwareUpdate` (con diagnóstico: mesu
  responde 200 a otros assets públicos) y 404 en GDMF. Todo documentado en `FUENTE.json`.
- No apliqué la etiqueta `FUENTE_NO_ACREDITADA`: usé el estado `CANDIDATO_PREPARADO_PENDIENTE_AUDITORIA`
  con la inaccesibilidad documentada. **Esa fue una desviación documental de mi encargo** —
  confirmada por GLM 5.3 Max (DICTAMEN_BLOQUEO_Y_SOLUCION.md §5) y con antecedente en el propio
  dictamen de Qwen (2.1, «GO condicionado»).

## Estados separados (no consolidar)

1. **Autenticidad criptográfica del PKG**: ACREDITADA de forma independiente de la metadata de
   catálogo — dominio final `swcdn.apple.com` con certificado EV de Apple Inc. verificado, sin
   redirecciones, y `pkgutil --check-signature` = `signed Apple Software` con cadena completa
   hasta `Apple Root CA`, reproducido por Qwen y GLM 5.3 Max.
2. **Versión/build del sistema (14.8.9 / 23J631)**: PENDIENTES/INFERIDOS. Lo único medido dentro
   del PKG es `com.apple.pkg.InstallAssistant.macOSSonoma`, `version=23.9.631`,
   `CFBundleShortVersionString=19.8.62` (la coherencia `23.9.631 ↔ 23J631` es una inferencia de
   sufijo, no una medición del SO). Solo se acreditará leyendo `Assets[0]` (`OSVersion`/`Build`)
   del MobileAsset dentro de `SharedSupport.dmg`, lo que corresponde a E-R2.
3. **Cumplimiento documental del encargo de adquisición**: DESVIADO (etiqueta/estado no
   aplicados). Esta errata no ratifica el desvío ni simula cumplimiento retroactivo; la decisión
   de aceptarlo o exigir otra vía es de OPERADOR y debe quedar registrada en evidencia propia.

## Efecto práctico

La cadena de confianza de colocación propuesta (PKG anclado por bytes/SHA/firma Apple + árbol
derivado del payload del propio PKG) no depende de la metadata de catálogo ni de la versión
inferida: sigue válida pase lo que pase con esta errata. La etiqueta de estado correcta para la
adquisición, a efectos del registro de la cadena, es: **adquisición con fuente de pista de
terceros y metadata primaria NO ACREDITADA**, y esa condición acompaña al candidato hasta que
E-R2 lea `Assets[0]` o OPERADOR disponga otra vía (App Store / host compatible) con metadata
primaria completa.
