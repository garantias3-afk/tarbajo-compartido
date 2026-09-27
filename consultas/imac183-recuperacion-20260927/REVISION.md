# Verificación de la entrega

Fecha: 27/09/2026. Revisión realizada por el mismo agente que preparó el expediente; **no se presenta como auditoría independiente**. Los dictámenes históricos de otros modelos se incluyen como fuentes a contrastar. La revisión independiente y corrección se solicitan a Claude Code.

## Comprobado en esta entrega

- Integridad de los paquetes fuente: OT07 r4 **72/72** entradas del manifiesto; C5 r6d **45/45**. Hash de manifiestos: r4 `17dafa9390342cc857f5721be8e1604f6c5df7434267b0c5d3f611a1f7cc2b41`; r6d `ea55af7231a765d5201b09e1ad13c5956fb52b64db182a3aa1bd99aa23caa3db`.
- Procedencia: **156 archivos** copiados/desidentificados tienen hash de origen y de publicación comprobados. El contenido generado del expediente se cubre además con el manifiesto final.
- Sintaxis, sin ejecutar scripts operativos: **45 fuentes Python** con AST, **5 scripts** con `bash -n`, **32 JSON** parseados en esta pasada. Véase `evidencia/verificacion_entrega/CHECKS.json` para el inventario exacto; no confundir estas cuentas con pruebas conductuales ni con los JSON añadidos después.
- Harness C5 sobre copia aislada: primera corrida **57/59**, dos fallos por helper no compilado. Se conservan log y resultados; no se ocultó esa dependencia de la exportación de fuentes.
- Compilación aislada del helper con SDK 26.5: RC=0, sin mensajes de warnings. Hash resultante `11b37e79be847e3d280bed36b844d1e19e35481a800a35dc633f5167fdc9bfcc`, igual al binario histórico observado. El binario permanece solo en el área local de trabajo y no se publica.
- Repetición del mismo harness con helper compilado: **59/59, RC=0**. Solo usuario normal, fixtures propios, operaciones simuladas, ciertas primitivas Darwin sin privilegios, selfcheck y rechazo de cleanup fuera de frontera. No se ejecutaron copy-tree/protect/publish como root. La suite informa cero skips, pero incluye ramas fallback; no demuestra cobertura nativa completa.
- Se verificaron metadatos actuales del host/apps, tamaños/uchg de dos imágenes, ausencia del instalador en Applications, espacio disponible y una consulta acotada de PIDs. No se leyó contenido de imágenes ni dispositivos.

`git diff --check` devuelve RC=2 por espacios heredados en fuentes, diffs y logs archivados; se conservaron para mantener procedencia. El detalle está en `evidencia/verificacion_entrega/GIT_DIFF_CHECK.json`. La documentación nueva no tiene esos avisos.

## Observaciones que impiden presentar el código como operativo

El ensayo nativo histórico r6b publicó un árbol vacío tras fallar la copia. No se encontró prueba de reejecución nativa exitosa de r6d en los registros consultados. La integración r4+C5, la creación de medio y el arranque no se certifican.

Se dejaron observaciones estáticas nuevas en `MAPA_VERSIONES.md`, entre ellas doble `closedir` y tests que inspeccionan texto. **No se corrigió el código aquí**: la entrega conserva las revisiones que el usuario pidió enviar a Claude para corrección.

## Privacidad y alcance

La publicación contiene fuentes, informes técnicos desidentificados y metadatos mínimos. Se excluyeron datos recuperados, claves FileVault, tokens, licencias, seriales/UUID reales de caso, imágenes, instalador y binario. Rutas de usuario y host se sustituyeron; los UUID de protocolo GPT permanecen. Los manifiestos originales son evidencia histórica y los nuevos describen esta copia.

La comprobación local final de patrones privados/secretos y links principales consta en `evidencia/verificacion_entrega/PRIVACIDAD_Y_ENLACES.json`. Los manifiestos y el ZIP se verifican al sellar. La recepción de los blobs remotos se registra por separado, después de publicar. Integridad documental no implica seguridad de ejecución ni reparación del iMac.
