# Dictamen provisional: conservar las dos vías, rescate y arranque

## Conclusión

La objeción del usuario es correcta en su punto central: **volver a leer o montar el volumen no demuestra que el iMac pueda arrancar**. El estado de EFI/OpenCore, la selección del sistema mediante Preboot, el sistema instalado y sus parches deben evaluarse por separado del acceso a APFS/Fusion/FileVault.

La conclusión «el pen es imprescindible» necesita acotarse. **Una ruta externa OpenCore conocida y compatible es una preparación razonable para aislar una EFI interna sospechosa**, sin repararla primero. No es una condición universal para recuperar archivos desde otro equipo; tampoco arregla por sí sola un Fusion que el controlador no consigue ensamblar. USB no es el único tipo de medio externo posible. Esto es una recomendación de preparación, no una autorización para borrar un medio ni iniciar un arranque sobre los originales.

## 1. Cómo comenzó, según el usuario

1. iMac18,3 funcionando con macOS Sonoma y OCLP «2.4».
2. Actualización de la aplicación OCLP a una versión más nueva, recordada como «2.5…».
3. Intento de instalar Sequoia con OCLP; el usuario sospecha haber cometido un error en la EFI.

Estado: **DECLARADO_POR_USUARIO**. No se verificaron aquí la versión exacta de cada aplicación, el OpenCore realmente instalado, el contenido de la EFI seleccionada, los builds de macOS ni el momento preciso de la primera falla. La cronología hace plausible un problema de arranque, pero no permite concluir «OCLP corrompió el Fusion» ni «todo se arregla reconstruyendo EFI».

La documentación de OCLP distingue la aplicación del cargador instalado y de los root patches. Actualizar la aplicación no acredita que el cargador o los parches aplicados tengan esa misma versión. Véanse las fuentes oficiales en FUENTES.md.

## 2. Compatibilidad

Apple identifica iMac18,3 como iMac Retina 5K de 27 pulgadas de 2017 y señala Ventura como su sistema más reciente oficialmente compatible. Las listas de Sonoma y Sequoia excluyen ese iMac; no debe confundirse con iMac Pro 2017. OCLP sí contempla iMac18,3, pero su soporte requiere una configuración y una combinación de versiones apropiadas. Esto justifica investigar OpenCore además del filesystem, sin probar que sea la causa actual. Fuentes S1–S4.

## 3. Problemas que no deben confundirse

| Capa | Qué debe acreditarse | Qué NO acredita |
|---|---|---|
| Componentes de almacenamiento/Fusion | Identidad de los dos miembros, lectura estable y ensamblado correcto | Una entrada con nombre APFS no demuestra que estén reunidos todos los datos |
| APFS y FileVault | Metadatos coherentes, clave disponible de forma privada y archivos legibles | Descifrar o listar carpetas no demuestra contenido íntegro ni arranque |
| Firmware, EFI y OpenCore | Cadena correcta para el modelo, versiones y medio seleccionados | Una app OCLP actualizada no prueba el contenido de la EFI |
| Preboot, volumen System y snapshot de arranque | Relación válida entre el sistema, los metadatos de arranque y el estado elegido | Un checkpoint anterior del contenedor no equivale a un Sonoma arrancable |
| Parches posteriores de OCLP | Necesidad y compatibilidad con el modelo y build realmente instalados | Aplicarlos no repara automáticamente Fusion ni sustituye una copia de los datos |

La tabla separa comprobaciones; no presenta una secuencia de comandos ni afirma que todas esas capas estén dañadas.

## 4. Qué significa «volver a un snapshot anterior»

Un snapshot APFS de un volumen, un checkpoint del contenedor y una EFI no son el mismo objeto. Recuperar un snapshot del sistema no restaura automáticamente la partición EFI, las variables de arranque o los datos de otro volumen. Tampoco puede suponerse que exista un snapshot utilizable de Sonoma, que esté completo o que baste para revertir un intento de actualización a Sequoia. Fuente S9 y análisis de alcance.

La auditoría local histórica desaconsejó tratar el reemplazo de un bloque del contenedor como un rollback probado: seguía presente un checkpoint posterior y el inmediatamente anterior ya registraba cambios de APFS de la etapa investigada. **No hay demostración de que editar un bit o escoger un checkpoint restaure un estado preactualización.** Los identificadores documentados sirven para revisión; no son instrucciones para escribirlos en un disco.

## 5. Qué medio externo sirve para cada objetivo

| Medio | Función | Límite |
|---|---|---|
| USB u otro medio con OpenCore configurado para el iMac | Ofrecer una cadena de arranque alternativa a la EFI interna | Necesita un sistema seleccionable y legible; no contiene necesariamente un instalador |
| Instalador de macOS más OpenCore cuando corresponda | Ofrecer herramientas de instalación/recuperación para el sistema objetivo | Crear, iniciar o usar el instalador son pasos distintos; reinstalar puede escribir sobre el origen |
| Sistema completo compatible en disco externo | Proporcionar un entorno de trabajo independiente | Su arranque no garantiza que los volúmenes internos permanezcan sin escrituras |
| UFS u otro lector en una segunda computadora | Evaluar y extraer datos sin arrancar el macOS instalado en el iMac | Requiere acceso suficiente a los componentes correctos; no certifica arranque futuro |

Fuentes S5–S8 y S10. La documentación se utiliza para distinguir funciones, no para ejecutar aquí su procedimiento general de instalación.

## 6. Lo que muestra la evidencia disponible

- UFS reconoce dos entradas candidatas correspondientes a unos 113 GB y unos 2 TB; al abrir una entrada APFS de unos 112,71 GB advierte que es parte de un volumen distribuido. Eso apoya investigar el ensamblado; no acredita que ya se haya realizado.
- Las capturas muestran tamaños de sector distintos y valores de interfaz cuyo alcance no se ha comprobado. No se calcularán offsets operativos a partir de una etiqueta aislada ni se asumirán equivalencias entre disco completo, partición y dispositivo expuesto adicionalmente.
- Informes históricos documentan lectura/descifrado e inventarios, pero también fallos de lectura y rescate parcial. Los EIO no identifican por sí solos daño físico ni una causa EFI.
- La hipótesis B2 relativa a metadatos Fusion sigue sin una prueba nativa de ensamblado en las fuentes auditadas. Un ensayo sintético no la transforma en reparación validada.
- La línea OT07/C5 prepara y valida mecanismos locales de copia/protección/publicación de un instalador. Incluso un futuro C5_NATIVO_VALIDADO tendría ese alcance; no demostraría que el iMac arrancó ni que todos los datos están recuperados.

El detalle y estado de cada afirmación figuran en EVIDENCIA.md.

## 7. Recomendación para avanzar

**Mantener la preparación de una ruta externa OpenCore y, en paralelo, continuar la evaluación documental del rescate.** No abandonar la primera porque UFS liste archivos, ni abandonar la segunda porque se consiga un menú de arranque.

Antes de una nueva operación sobre medios, faltan la identificación actual de fuentes/destinos, el estado del operador activo y la definición exacta del objetivo: extraer datos, probar una EFI externa, comprobar un sistema existente o reinstalar. Son pruebas distintas y sus permisos no se transfieren entre sí.

Orden propuesto:

1. Completar inventario de datos aún valiosos y evidencia de copias, usando registros existentes. No dar por salvado el conjunto por un subconjunto verificado.
2. Diseñar la preservación con capacidad suficiente y registro de errores. Una imagen parcial de un miembro no es una copia completa del Fusion.
3. Preparar documentalmente el medio externo y su configuración para el modelo; verificar integridad del paquete y completar los controles de su alcance.
4. Resolver en una autorización específica la identidad y el borrado del único medio de destino, si se decide crearlo. H1/C5 no sustituye esa autorización.
5. Diseñar una prueba de arranque separada con criterios observables y riesgo de escrituras considerado. No confundir la aparición del selector con éxito del sistema o recuperación de datos.

No se aconseja iniciar ahora reparaciones APFS, restablecer Fusion, instalar sobre el sistema existente, cambiar la EFI interna ni aplicar parches de raíz como ensayo diagnóstico sobre los originales.

## 8. Preguntas que debe resolver la segunda opinión

- ¿Qué observación diferencia un fallo EFI/OpenCore de un fallo APFS/Fusion, y cuál diferencia ambos de una instalación incompleta?
- ¿Qué parte de la cadena puede probarse en copias o medios externos sin escribir sobre los originales?
- ¿En qué sentido sería necesario el medio externo y en cuál es solo una opción práctica?
- ¿Qué evidencia demostraría la existencia y utilidad de un snapshot anterior, sin confundirlo con un checkpoint?
- ¿Qué defectos concretos tiene este análisis y qué evidencia los contradice?

No se asignan probabilidades numéricas de recuperación: la información disponible no las sustenta.
