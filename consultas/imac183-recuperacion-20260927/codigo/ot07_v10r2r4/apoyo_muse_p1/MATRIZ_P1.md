# MATRIZ_P1.md — aceptación para MiMo y auditores

ID estable | Requisito | Fixture / test | Expectativa | Falla antes de privilegios | Evidencia real pendiente
---|---|---|---|---|---
P1-01 | Pin PKG (existencia+bytes+SHA-256 completo) | `test_pin_pkg_ok_y_erroneos` | OK solo con 13654790295-equivalente y 64 hex; abreviado rechazado | Sí (pre-colocación) | Medición MiMo sobre el PKG real (la mía: solo tamaño)
P1-02 | Firma PKG con cadena hasta Root CA | (MiMo; patrón C-4) | `signed Apple Software` + `Apple Root CA`, RC capturado | Sí | Ejecución MiMo con log
P1-03 | Inventario sin seguir enlaces, cobertura exacta | `test_enlace_a_directorio_no_se_sigue` + suite | Dir-enlace registrado, contenido no duplicado; conjuntos iguales | Sí | Positivo nativo MiMo (él expande)
P1-04 | Alterado mismo tamaño detectado | `test_archivo_alterado_mismo_tamano`, `test_sustitucion_dmg_mismo_tamano`, `test_sustitucion_cim` | `CONTENIDO_ALTERADO` | Sí | — (sintético suficiente)
P1-05 | Extra/faltante | `test_extra_y_faltante`, `test_archivo_vacio_registrado_y_alterado` | `EXTRA`/`FALTANTE`; vacío con `e3b0…` | Sí | — |
P1-06 | Cambio de tipo | `test_cambio_de_tipo` (3 variantes) | `TIPO_CAMBIADO` | Sí | — |
P1-07 | Enlace absoluto/saliente | `test_enlace_absoluto_rechazado`, `test_enlace_saliente_por_puntos` | `ENLACE_SALIENTE` | Sí | — |
P1-08 | Transitivo/cíclico/roto | `test_enlace_transitivo_*`, `test_enlace_ciclico`, `test_enlace_roto` | saliente/cíclico/roto; `..` válidos intermedios OK | Sí | — |
P1-09 | Interno legítimo + árbol idéntico aceptados (anti-rechazo-total) | `test_arbol_identico_con_enlace_interno_ok`, `test_enlace_transitivo_interno_valido` | `OK` | N/A (positivos) | — |
P1-10 | Transformación SharedSupport explícita | `test_transformacion_sharedsupport_explicita` (+rechazos) | OK solo con regla declarada; sin regla falla | Sí | Mapeo postinstall oficial leído por MiMo |
P1-11 | Manifiesto derivado de alterado no pasa | `test_manifiesto_derivado_de_alterado_no_pasa` | `ok=False` (manifiesto no es raíz de confianza) | Sí | — |
P1-12 | Hash abreviado/manifiesto truncado inválidos | `test_hash_abreviado_no_es_sha256`, `test_manifiesto_truncado_invalido` | `MANIFIESTO_INVALIDO` | Sí | — |
P1-13 | Especiales y fallos de herramienta | `test_archivo_especial_rechazado`, `test_fallo_herramienta_lectura` | `ESPECIAL_NO_PREVISTO` / `HERRAMIENTA_FALLO`, sin éxito | Sí | — |
P1-14 | Sustitución observación→uso detectable | `test_sustitucion_entre_observacion_y_uso` | `CONTENIDO_ALTERADO` al re-verificar | Sí (si se re-verifica) | Ventana residual documentada |
P1-15 | DMG↔DMG 64 hex + tamaño | Patrón P1-04 sobre rutas SharedSupport | Igualdad exacta | Sí | Hashes completos MiMo (log 03 los debe; 32 hex no valen) |
P1-16 | CIM con firma estricta conservada | (MiMo; GLM §4.1) | `codesign --verify --strict -R=anchor apple` RC=0 | Sí | Ejecución MiMo |
P1-17 | Adaptador sobre implementación real | `adaptador_mimo.py` + esta suite | Códigos P1 o INADAPTADO declarado | Sí | Comparador publicado por MiMo |
P1-R1 | Carrera lector↔colocador concurrente | Simulada (P1-14); real NO probada | Re-verificación inmediata pre-efecto; ventana documentada | Parcial | Ensayo con escritores reales fuera de rescate |
P1-R2 | Cambio de input durante lectura larga (13 GB) | Simulada; real NO probada | Hash streaming + tamaño antes/después; abortar ante cambio | Parcial | Medición MiMo con re-lectura |
P1-R3 | Destino aparece entre chequeo y `mv` | Lógica en script v2 (re-chequeo + `mv -n` + verificación); fixture pendiente MiMo | Sin sobreescritura ni éxito falso | Sí (diseño) | Prueba de colocación con fixture de carrera |
P1-C1 | Coste: pico ≈38 GiB, limpieza confinada | Declarado; fixtures chicos | Presupuesto por fases + rm solo temporal propio | N/A | Medición MiMo en expansión real |
