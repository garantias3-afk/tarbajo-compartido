# Fuentes primarias y alcance

Consulta documental del 27/09/2026. S1, S3, S5, S6 (Updating), S7, S8, S9, S10 y S13 se abrieron nuevamente durante esta entrega. Las restantes ya estaban documentadas en la investigación del hilo anterior del mismo día; se conservan como referencias a contrastar, no como verificación de versiones instaladas. Ninguna página sustituye la evidencia local.

| ID | Fuente | Uso y límite |
|---|---|---|
| S1 | [Apple: identificar el iMac](https://support.apple.com/en-gb/108054) | iMac18,3 corresponde al 27 pulgadas 2017; Ventura es el máximo oficial indicado. No es iMac Pro 2017. |
| S2 | [Sonoma](https://support.apple.com/en-us/105113), [Sequoia](https://support.apple.com/en-us/120282) | Listas Apple de compatibilidad; no prueban estado del equipo. |
| S3 | [OCLP: modelos](https://dortania.github.io/OpenCore-Legacy-Patcher/MODELS.html) | Modelo admitido; no garantiza cualquier instalación/hardware. |
| S4 | [OCLP Sonoma](https://dortania.github.io/OpenCore-Legacy-Patcher/SONOMA-DROP.html), [OCLP Sequoia](https://dortania.github.io/OpenCore-Legacy-Patcher/SEQUOIA-DROP.html) | Contexto de soporte y límites. |
| S5 | [OCLP: construir OpenCore](https://dortania.github.io/OpenCore-Legacy-Patcher/BUILD.html) | Configuración específica del modelo de destino. |
| S6 | [OCLP: actualizar](https://dortania.github.io/OpenCore-Legacy-Patcher/UPDATE.html), [postinstalación](https://dortania.github.io/OpenCore-Legacy-Patcher/POST-INSTALL.html) | Distinguir aplicación, cargador y root patches. |
| S7 | [OCLP: instaladores](https://dortania.github.io/OpenCore-Legacy-Patcher/INSTALLER.html) | Crear instalador y preparar OpenCore son pasos separados. |
| S8 | [OCLP: arrancar](https://dortania.github.io/OpenCore-Legacy-Patcher/BOOT.html) | Selector EFI/OpenCore y selector del sistema son etapas diferentes. |
| S9 | [Apple File System Reference](https://developer.apple.com/support/downloads/Apple-File-System-Reference.pdf) | Referencia 2020: checkpoints (pp. 8, 26–27), roles (64–65), snapshot metadata (117). No certifica compatibilidad completa de un parser con versiones futuras. |
| S10 | [UFS: recuperación Fusion](https://www.ufsexplorer.com/articles/how-to/recover-data-apple-fusion-drive/) | Sección APFS desde Mojave; reconstrucción virtual y comprobación de datos. Guía 2022, no prueba del caso. |
| S11 | [OCLP 2.4.0](https://github.com/dortania/OpenCore-Legacy-Patcher/releases/tag/2.4.0), [2.4.1](https://github.com/dortania/OpenCore-Legacy-Patcher/releases/tag/2.4.1), [2.5.0](https://github.com/dortania/OpenCore-Legacy-Patcher/releases/tag/2.5.0) | Referencias fijadas por versión para que el revisor contraste código/payload; no inferir que fueron instaladas en el iMac. |
| S12 | [Problemas de arranque](https://dortania.github.io/OpenCore-Legacy-Patcher/TROUBLESHOOT-MISC.html), [problemas de la app](https://dortania.github.io/OpenCore-Legacy-Patcher/TROUBLESHOOT-APP.html) | Hipótesis de root patches/transición de versiones, pendientes de evidencia. |
| S13 | [Apple: modo disco de destino](https://support.apple.com/guide/mac-help/transfer-files-mac-computers-target-disk-mode-mchlp1443/mac) | Acceso externo sin arrancar el sistema instalado; no impone por sí mismo solo lectura ni repara Fusion. |

La auditoría APFS incluida cita además implementaciones públicas `apfsprogs` y `apfs-fuse`, con las URLs y hashes consultados en `evidencia/apfs/fuentes_codigo.json`. Son evidencia sobre esas implementaciones, no especificación completa del driver propietario de Apple. Las fuentes y conclusiones históricas deben evaluarse críticamente.

Inferencia central: una EFI externa compatible puede aislar un problema de arranque, pero no repara necesariamente el contenedor ni constituye requisito universal para extraer datos desde otra computadora. Esta inferencia combina las funciones documentadas con los límites del caso; no es un diagnóstico confirmado.
