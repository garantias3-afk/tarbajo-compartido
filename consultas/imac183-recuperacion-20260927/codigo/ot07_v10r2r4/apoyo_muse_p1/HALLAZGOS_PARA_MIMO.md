# HALLAZGOS_PARA_MIMO.md — priorizado (Muse 1.3 → MiMo v2.6 Pro)

Sin observaciones hipotéticas como defectos demostrados. Por hallazgo:
evidencia, impacto, corrección propuesta, limitación.

## H1 — Manifiesto esperado debe anclarse fuera del candidato (bloqueante de diseño)
- **Evidencia**: `APP_MANIFIESTO.txt` se genera post-extracción; el log 03 no publica programa/rutas/hashes completos; `test_manifiesto_derivado_de_alterado_no_pasa` demuestra que un manifiesto derivado no prueba nada.
- **Impacto**: manifiesto bajo control del mismo flujo que coloca = raíz de confianza auto-otorgada; un árbol alterado con su propio manifiesto pasa.
- **Corrección**: el manifiesto esperado de v10r2 debe venir de medición independiente pineada (tu expansión del PKG verificado T1–T3) y quedar sellado con la entrega; jamás aceptar un manifiesto aportado junto al candidato. Usar `inventario.py` como formato (JSON tipo+tamaño+hash+destino).
- **Limitación**: exige tu positivo nativo de procedencia (no lo produzco yo en paralelo).

## H2 — Transformación SharedSupport explícita (bloqueante de diseño)
- **Evidencia**: el postinstall ubica el DMG de nivel PKG en `Contents/SharedSupport/`; comparar por igualdad de nombres sin regla lo omite o lo confunde con extra/faltante.
- **Impacto**: falso negativo o cobertura incompleta del DMG (el archivo de 13 GB más crítico).
- **Corrección**: tabla `origen→destino` declarada + `aplicar_transformacion()` (referencia incluida) aplicada antes de `comparar()`; test `test_transformacion_sharedsupport_explicita`.
- **Limitación**: el mapeo exacto debe leerse del postinstall oficial (tu trabajo §1.4 OT principal), no de mi fixture.

## H3 — Política de enlaces completa, no solo conteo (importante)
- **Evidencia**: "0 absolutos, 0 .." es parcial; GLM-05 demuestra que metadatos solos pasan symlinks salientes. Mi suite demuestra saliente/transitivo/cíclico/roto y `..` intermedios válidos.
- **Impacto**: enlace saliente o ciclo aceptado por conteo ingenuo → escape del árbol o cuelgue del recorrido.
- **Corrección**: adoptar `resolver_enlace()` (profundidad-real, sin disco) y jerarquía de códigos; nunca seguir enlaces en el recorrido (`inventario.py` no desciende a dirs-enlace).
- **Limitación**: resolución sobre manifiesto, no sobre FS vivo (correcto por diseño; la ventana viva la cubre P1-14).

## H4 — Hashes completos de 64 hex en DMG↔DMG (importante)
- **Evidencia**: log 03 publica dos hex de 32 caracteres sin algoritmo; `test_hash_abreviado_no_es_sha256` rechaza esa forma.
- **Impacto**: asumir abreviado=SHA-256 degrada la comparación del payload mayor a 128 bits efectivos desconocidos.
- **Corrección**: publicar programa+Ruta+RC+64 hex (comandos en CONTRATO §2); `verificar_anclaje()` rechaza longitudes ≠64.
- **Limitación**: los hashes reales los medís vos (prohibido duplicarlos yo en paralelo).

## H5 — Contenido, no metadatos (importante, ya demostrado por GLM-05)
- **Evidencia**: GLM-05: chequeo de solo-metadatos pasa en todos los adversos; mi P1-04/P1-12 lo replican contra la referencia.
- **Impacto**: `codesign -d`/Identifier/spctl como criterio sustituto = colocación de árbol alterado.
- **Corrección**: mantener §4.1 GLM (cadena PKG + comparación de contenido + CIM estricto); metadatos solo diagnóstico.
- **Limitación**: ninguna; es diseño.

## H6 — Coste y limpieza (menor, operativo)
- **Evidencia**: pico ≈38 GiB (PKG+extraída+staging); expansión repetida por cada verify-only.
- **Impacto**: `ENOSPC` a mitad de staging o temporales huérfanos de 13 GB.
- **Corrección**: un inventario por árbol reutilizado en las tres comparaciones; presupuesto por fases (C-9); limpieza confinada (rm solo bajo temporal propio verificado, sin seguir enlaces); prohibir caché por mtime/nombre.
- **Limitación**: cifras de pico reales las medís vos.

## H7 — TOCTOU observación→uso (menor, residual declarado)
- **Evidencia**: `test_sustitucion_entre_observacion_y_uso` (detectable al re-verificar).
- **Impacto**: sustitución en la ventana entre última verificación y efecto persistente.
- **Corrección**: re-verificar inmediatamente antes de cada efecto (colocación, mv, erase futuro); documentar la ventana; sin escritores concurrentes.
- **Limitación**: carreras reales con el candidato (P1-R1…R3) no probadas aquí; exigen ensayo fuera de rescate.

## Qué debe ejecutar MiMo una vez integrado
1. `verificar_anclaje()` sobre el PKG real (T1) + `pkgutil --check-signature` con cadena (T2), con comando/RC/log.
2. Expansión controlada + `inventario.py` (o equivalente) sobre payload y app + `comparar()` con la tabla T4 (T3–T6), publicando programa/rutas/hashes completos.
3. `adaptador_mimo.py` + `tests/test_comparador.py` contra su comparador real; declarar equivalencias o desvíos.
4. Pruebas de carrera P1-R1…R3 con fixtures de escritura (nunca el candidato real) y medición de pico P1-C1.
5. Entrega v10r2 con manifiesto de cobertura exacta + ZIP comparado; sin tocar v10r1 ni sellos ajenos.
