# HILO_AUDITORIA_QWEN.md — v10r2r2 (corrección tras NO-GO)

Auditoría independiente del candidato **v10r2r2**. Solo lectura.
No ejecutar E/F/G, colocación, OCLP, señales, USB, erase, CIM, attach/detach ni boot.

## Modalidad

Carpeta local: `/Users/OPERADOR/Documents/Codex/2026-09-25/hi/outputs/OT07_REVISION_v10r2r2`.
SHA del manifiesto y recibo externo: ver `ENTREGA_CERRADA_v10r2r2_MIMO.json`.

## Qué verificar (reproducir; no aceptar autorreporte)

1. **Integridad:** manifiesto del candidato, ZIP↔carpeta por archivo, v10r2r1 y
   sellos anteriores intactos.
2. **B-1:** con `OT07_MODO_PROTECCION=root` el script **no** crea destino ni
   `COLOCADO_VERIFICADO`; gate `C5_NO_IMPLEMENTADA`. Igual para vacío/desconocido.
3. **B-2:** `du`/`df` con RC≠0 o salida no numérica abortan; `NEED` no puede
   colapsar a 2 GiB por salida vacía.
4. **I-1:** `inventory_tree` rechaza raíz symlink **antes** de resolve (ambas APIs).
5. **I-2/I-4:** espacio antes de expand-full; error de limpieza reportado.
6. **I-5:** PKG/app ausentes abortan antes de efectos.
7. **C-1 cadena:** se conserva GO de Qwen; re-ejecutar `verify_offline_provenance`
   solo si cambió inventario/preflight/cleanup (justificado en esta revisión:
   I-1/I-2/I-4). Positivo offline sobre PKG real, sin `main()` ni attach.
8. **Pruebas:** contar y re-ejecutar (`python3 -B -m unittest discover -s tests`).
   Negativos = RC + ausencia de destino/efectos, no greps de texto.
9. **Documentación:** PLAN/HILO/FUENTE/MATRIZ coherentes con el código final.

## Fuera de alcance

Aprobar colocación, C-5 operacional, E, F, G, USB, boot. Promover versión/build.
