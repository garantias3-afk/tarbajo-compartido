# Aplicación de recuperación disponible

**VERIFICADO_ACTUAL:** UFS Explorer RAID Recovery 10.22 está instalada en el host de preparación. El plist confirma producto y versión. Las capturas previas muestran interfaz Apple Silicon. No se verificó licencia/activación, límite de exportación, configuración actual, escaneo activo ni un ensamblado exitoso.

La guía oficial del fabricante para APFS Fusion contempla UFS Explorer RAID Recovery y describe ensamblado automático; si falla, reconstrucción virtual desde las partes de datos, con el miembro tier1 primero y la opción Span of storages. No describe sumar arbitrariamente discos físicos completos ni RAID 0. La guía fue actualizada en 2022 y no certifica este caso con metadatos anómalos o FileVault. [Fuente oficial](https://www.ufsexplorer.com/articles/how-to/recover-data-apple-fusion-drive/).

En el hilo se vio el miembro pequeño (~113 GB, sector 4096), el CT2000MX500SSD1 (~1,82 TB, sector 512) y un aviso de volumen distribuido al abrir Data. El último paso propuesto fue inspeccionar el menú RAID; no quedó prueba de la selección ni de la construcción. Ver [EVIDENCIA.md](EVIDENCIA.md) para las rutas históricas y sus límites.

## Encargo al revisor

Proponer un procedimiento verificable para esta versión: identificación de componentes y rangos; reconocimiento de particiones frente a discos completos/dispositivos sintetizados; tratamiento de sectores distintos; orden correcto; soporte de APFS cifrado; y validación de lecturas en archivos de varios rangos. Comprobar manual oficial/ayuda antes de inventar nombres de botones o offsets.

La falta de espejo/paridad y de un miembro completo impide suponer integridad por previsualizar algunos archivos. Separar descubrimiento de metadatos, desbloqueo, lectura, copia y validación. El resultado se guarda en otro medio. La verificación de archivos debe incluir tamaño, lectura completa, hashes y validación de formatos seleccionados, con errores y omisiones contados.

Este expediente no instruye desactivar SIP, instalar extensiones, iniciar escaneos, modificar RAID físico, reparar APFS ni escribir en los miembros. La receta general del fabricante no autoriza aplicar esos pasos al equipo. Claude debe devolver el plan y los datos que necesita del operador; no puede afirmar que controló UFS desde la nube.
