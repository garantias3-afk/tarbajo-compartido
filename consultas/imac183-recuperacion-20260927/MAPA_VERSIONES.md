# Qué código revisar y qué falta integrar

## Paquetes complementarios

| Directorio | Función | Revisión local de origen |
|---|---|---|
| `codigo/ot07_v10r2r4/` | Fabricación del USB, EFI, instalador, identidad, procesos y colocación anterior | OT07_REVISION_v10r2r4 |
| `codigo/c5_v10r2r6d/` | Protección del árbol antes de publicarlo: helper C, orquestador, bootstrap, ancla y ACL | OT07_REVISION_v10r2r6d_MIMO |
| `pruebas/flash_r2/` | Harness independiente de C5, fixtures y adaptadores | OT07_FLASH_PRUEBAS_C5_R2, exportación de fuentes/documentación |
| `evidencia/revisiones/` | Auditorías de r5 a r6d y adjudicación nativa A | Registros históricos MAX |
| `evidencia/h1_r6b/` | Log y recibo del único ensayo nativo A incluido | MIMO r6b, fallido |

Se incluyeron las dos versiones actuales útiles, sus deltas heredados y la evidencia necesaria para comparar. Las carpetas r5/r6/r6b/r6c completas no se duplicaron; los deltas y recibos conservados permiten seguir su evolución, pero no se afirma que equivalgan a cada árbol histórico completo. El binario nativo se excluyó deliberadamente. Los resultados generados y copias privadas de Flash no se duplicaron; su manifiesto original parcial no es un check de integridad de esta exportación.

## Entrada del flujo USB

En r4, empezar por `CREAR_PEN_BOOTEO.sh`, `construir_efi.sh`, `descargar_sonoma.sh`, `identificar_pen.py`, `ot07_guard.py`, `ot07_process.py`, `verificar_instalador.py`, `tree_inventory.py`, `place_helper.py` y `colocacion_v2/colocar_candidato.sh`. `ALCANCE_R4.md` declara los diez productivos idénticos a r3/r2; los cambios r4 fueron de pruebas y documentación.

El flujo fija OCLP 2.4.1 y objetivo iMac18,3. Construir desde un Mac arm64 no cambia el modelo destino. Hay que conservar la cadena requerida por el payload OCLP (`EFI/OC`, `System`, `boot.efi`, `Product.efi`) y comprobarla contra la versión concreta; copiar `OpenCore.efi` a `EFI/BOOT/BOOTx64.efi` no constituye demostración de equivalencia. Verificar binding de particiones y mountpoints al disco elegido antes y después del borrado.

El UUID fijo de la copia pública es ficticio. Corregir parametrización no puede eliminar la identidad física ni la revalidación inmediata. No hacer el script “más fácil” admitiendo cualquier UUID/medio.

## C5 no es todavía la integración final

`src/legacy/` conserva módulos anteriores. El orquestador de C5 modela protección antes de publicación; hay que verificar qué implementación llama realmente cada punto de entrada de r4. Un GO aislado del helper no acredita que la creación del USB consuma el mismo instalador, dependencia y configuración previamente verificados.

La interfaz distingue modo simulado de nativo. `chmod` sobre fixtures propios puede ser real mientras ownership/ACL se modelan con un ledger; esos resultados no son root nativo. La frontera debe cubrir el árbol, sus padres, ancestros, dependencias y la ventana verificar→usar. Un descriptor de escritura ya abierto no queda revocado por chown/chmod.

## Fallos históricos que deben tener regresión conductual

1. **D1 r6b:** `mkdir-staging` creaba la hoja y `copy-tree` intentaba crearla otra vez; fallaba con EEXIST. El procedimiento continuó y publicó una hoja vacía. Requiere caso positivo con contenido real y aborto inmediato al primer fallo inesperado.
2. **D2:** los modos 0700/0600 impedían verificar/leer como operador; separar frontera privada del staging y accesibilidad de la publicación protegida.
3. **D3:** el destino publicado caía fuera de la base usada para verificar; la nueva base debe ser explícita, sin ampliar privilegios indiscriminadamente.
4. **R6C-1:** faltaba ajustar el modo de la hoja después de copiar hijos; r6d añade el chmod y cambia el binario. La validación de archivo, raíz y ACL sigue requiriendo ejecución nativa controlada.
5. **Protocolo:** RC y stderr discrepantes, pipelines y capturas deben verificarse. El log nativo incluye una secuencia descartada y otra utilizada; no sumar ambas como resultados válidos.

## Observaciones nuevas de la preparación: requieren auditoría, no son fixes entregados

- **Doble closedir en fuente:** `src/c5_helper.c`, `cmd_copy_tree`, línea 261 cierra `d` ante fallo retornado por `copy_walk`, hace `break`, y línea 263 vuelve a cerrar `d`. La ruta se observa estáticamente; no se ejecutó el helper privilegiado para reproducirla. Pedir un test conductual que fuerce ese retorno y una corrección acotada.
- **Informe versus código:** `REVISION_MAX_R6D.md` describe máscara `~0222`; el código r6d usa `~(S_IWGRP | S_IWOTH)` (equivale a quitar 0022). No son la misma política para el permiso de escritura del dueño. El recibo y la intención r6d hablan de quitar g+w/o+w. Adjudicar qué contrato corresponde y corregir la documentación si procede.
- **Pruebas textuales:** D1-01, D1-02 y D2-01 en `tests/harness_r5.py` buscan palabras/fragmentos en C. Pueden pasar sin ejecutar `copy-tree`. Un conteo 59/59 no prueba por sí mismo ni D1 resuelto nativamente ni N0–N9 cerrados.
- **ACL:** revisar `protect_one` y el tratamiento de fallo de `acl_set_file`: hay una rama que imprime error y sigue. Determinar si el verificador posterior excluye cualquier falso éxito y exigir un negativo que lo pruebe.

Estas observaciones amplían la lista de trabajo para Claude; no constituyen una auditoría exhaustiva ni acreditan explotación. No modificar los fuentes históricos para ocultarlas. Las correcciones deben ir a una revisión nueva con diff y pruebas.
