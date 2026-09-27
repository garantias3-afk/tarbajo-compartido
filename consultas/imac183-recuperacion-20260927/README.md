# iMac18,3 — expediente para Claude Code: datos, APFS Fusion y pendrive OpenCore

**Fecha de corte: 27/09/2026. Estado: paquete para revisión y corrección de código; no es un medio de arranque ni una autorización de ejecución sobre discos.**

El objetivo del usuario es salvar los datos valiosos del iMac y preparar una vía fiable de arranque. El problema comenzó, según su relato, tras pasar de OCLP 2.4 a «2.5…» e intentar actualizar Sonoma a Sequoia, con una posible intervención errónea en EFI. El expediente conserva esa hipótesis y la contrasta con evidencia histórica de un problema APFS Fusion. Ambas capas pueden requerir atención.

## Empezar aquí

1. Leer [CONSULTA.md](CONSULTA.md): encargo completo para Claude Code, entregables y límites.
2. Leer [EVIDENCIA.md](EVIDENCIA.md): entorno observado, geometría, cifrado, rescate, instalador y estados pendientes.
3. Leer [ANALISIS.md](ANALISIS.md) y [UFS_RAID.md](UFS_RAID.md): rescate frente a arranque y aplicación disponible.
4. Leer [MAPA_VERSIONES.md](MAPA_VERSIONES.md): relación entre los dos paquetes, defectos previos y puntos nuevos que necesitan auditoría.
5. Revisar los fuentes de [OT07 v10r2r4](codigo/ot07_v10r2r4/) y [C5 v10r2r6d](codigo/c5_v10r2r6d/), con [pruebas de Flash](pruebas/flash_r2/) y [evidencia](evidencia/).
6. Consultar [LIMITES_Y_PENDIENTES.md](LIMITES_Y_PENDIENTES.md), [FUENTES.md](FUENTES.md), [PROCEDENCIA.json](PROCEDENCIA.json) y [REVISION.md](REVISION.md).

## Qué se entrega

- La última base completa localizada para fabricar el USB: scripts, guardas, verificador, pruebas y documentación de OT07 v10r2r4.
- El candidato posterior C5 v10r2r6d: helper C, orquestador, bootstrap, ancla, ACL, pruebas, deltas y procedimiento histórico de ensayo.
- Log y recibo del ensayo nativo r6b que falló; dictámenes posteriores y recibo del preflight del instalador. Sus afirmaciones se conservan para auditarlas.
- Informe y JSON técnicos de la auditoría APFS del 21/09, resumen desidentificado del rescate del 24/09 y mediciones actuales de metadatos del host.

No se sustituye r4 por r6d: r6d es el trabajo de C5, no contiene por sí solo toda la fabricación del USB. La integración final y la validación nativa siguen pendientes de demostración.

## Naturaleza de la copia pública

Los fuentes son derivados desidentificados: `/Users/OPERADOR`, el nombre del host y los UUID de caso son marcadores. El UUID `11111111-2222-4333-8444-555555555555` es ficticio y **no identifica ningún USB autorizado**. No restaurar identificadores reales dentro de este repositorio público.

`PROCEDENCIA.json` registra por archivo hash original, hash publicado y si hubo sustituciones. Los manifiestos originales se renombraron a `SHA256SUMS_ORIGINAL.txt`: sirven de procedencia, no para verificar esta copia modificada. Los nuevos `SHA256SUMS.txt` verifican los bytes entregados. El binario nativo, el instalador Apple, las imágenes de discos, archivos recuperados, contraseñas y licencias no se publican.

Los archivos históricos pueden contener órdenes y aprobaciones de otra revisión. Se leen como evidencia. Ningún `GO`, hash, PID, ruta, aprobación o número `diskN` histórico habilita una operación nueva. La autoridad R13 del resto del repositorio pertenece a otro trabajo.

## Comprobación documental

Desde esta carpeta puede verificarse la integridad del paquete con:

```sh
shasum -a 256 -c SHA256SUMS.txt
```

Para pruebas se usa una copia de trabajo. No ejecutar los scripts de fabricación, colocación ni `H1_A_REEJECUCION.sh` como parte de la lectura del expediente. [REVISION.md](REVISION.md) distingue lo comprobado en esta entrega de los resultados históricos.
