# CONTRATO_CADENA.md — OT07-P1 (Muse 1.3, apoyo a MiMo)

Contrato preciso para la cadena PKG→payload→app. No reemplaza el verificador
productivo de MiMo: es la especificación + referencia + pruebas que MiMo puede
adoptar o adaptar. Modelo/host/UTC/encargo al pie.

## 1. Tabla del flujo de confianza

| # | Eslabón (input) | Quién lo controla | Comprobación | Resultado que lo acredita | Momento del efecto persistente |
|---|---|---|---|---|---|
| T1 | PKG `InstallAssistant.pkg` | Apple (firma) + revisión (pin) | Existencia + bytes exactos 13654790295 + SHA-256 completo `ecc36bf1…08173` medido independiente (nunca leído del candidato) | `verificar_anclaje()` OK | Ninguno (lectura) |
| T2 | Firma del PKG | Apple | `pkgutil --check-signature` con `LC_ALL=C`, RC capturado sin pipe que lo oculte; exigir `Status: signed Apple Software` + cadena hasta `Apple Root CA` (literal, no `successful`) | RC=0 + literales | Ninguno |
| T3 | Expansión controlada | Operador (MiMo) | `pkgutil --expand-full` a mktemp privado NUEVO, sin privilegios, sin ejecutar scripts; registrar comando/RC/rutas; presupuesto Pico≈PKG+extraída+staging+app | Árbol derivado + log | Temporal propio (limpieza confinada) |
| T4 | Transformación SharedSupport | Revisión (tabla explícita) | Mapeo declarado origen→destino (p. ej. `SharedSupport.dmg` de nivel PKG → `Contents/SharedSupport/` de la app, según postinstall oficial LEÍDO, jamás ejecutado) vía `aplicar_transformacion()`; nada inferido por similitud de nombres | Manifiesto reubicado | Ninguno (puro) |
| T5 | Comparación árbol↔payload | Comparador | `inventario()` sin seguir enlaces + `comparar()` contenido SHA-256 de 64 hex, enlaces por destino+resolución transitiva, cobertura exacta, rechazo de especiales | `Resultado(ok=True, codigo=OK)` | Ninguno |
| T6 | DMG origen↔app | Comparador | SHA-256 completo + tamaño en sus rutas (mismo mecanismo T5, sin caso especial) | Igualdad de 64 hex | Ninguno |
| T7 | CIM | Apple + revisión | `codesign --verify --strict -R=anchor apple` RC=0 (se conserva); Identifier/Platform/spctl solo diagnóstico | RC=0 | Ninguno |
| T8 | Verificación DMG/Assets[0] posterior | `verificar_instalador.py` (E autorizada) | `hdiutil verify` + MobileAsset Mac/SFR + `Assets[0]` 14.x/build 23… con attach/detach normal | `INSTALADOR_LISTO` | Montaje lectura temporal (cierre verificado) |

Lo que **no** sustituye eslabones: `codesign -d` (muestra metadatos sin validar
bytes), `spctl` RC genérico (diagnóstico), hash abreviado de 32 hex (no es
SHA-256 completo: rechazarlo, ver test `test_hash_abreviado_no_es_sha256`),
manifiesto generado post-extracción y tomado con confianza ciega.

## 2. Datos faltantes de la evidencia (cómo generarlos, sin inventarlos)

El log 03 reporta 745 elementos y dos hex de 32 caracteres para el DMG sin
algoritmo/programa/rutas. Para reproducir con valor probatorio, ejecutar (solo
lectura) y conservar programa+salida+RC:

```bash
cd <dir-payload> && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256 > MANIFIESTO.txt
wc -l < MANIFIESTO.txt                              # conteo de regulares
find . -type l | LC_ALL=C sort | tee ENLACES.txt | wc -l
find . -type l -exec sh -c 'case $(readlink "$1") in /*|*../*) echo "$1";; esac' _ {} \;
shasum -a 256 <DMG-payload> <DMG-app>               # 64 hex cada uno
```

Separar cantidades por tipo: jamás llamar "745 archivos regulares" a una suma
que pueda incluir enlaces. `inventario.py` de esta entrega produce ese formato
(JSON con tipo por entrada) más destinos de enlace.

## 3. Inventario sin seguir enlaces (`inventario.py`)

Recorrido con `scandir` + `lstat` (`follow_symlinks=False`) en cada entrada;
los symlinks a directorios se registran y NO se descienden (evita ciclos y
fugas por recorrido). Registro por ruta relativa: `tipo` (archivo/directorio/
enlace), `tamano`+`sha256` streaming para regulares (el vacío se registra con
`e3b0…`, nunca se omite), `destino` para enlaces. FIFOs/sockets/dispositivos
→ `ESPECIAL_NO_PREVISTO`. Cobertura exacta por construcción (todo lo listado
queda registrado; `comparar` exige igualdad de conjuntos).

Qué es criptográfico (contenido de regulares, destinos literales) vs política
de permisos (legibilidad/ejecutabilidad se controlan por separado; NO se exige
que propietario/modo sean idénticos tras una transformación autorizada como
ditto+mv: la igualdad es de contenido + destinos, no de metadatos de dueño).

## 4. Comparador (`comparador.py`) y adaptador

API pura: `comparar(esperado, obtenido) -> Resultado(ok, codigo, detalles)`;
`aplicar_transformacion(manifest, reglas)`; `resolver_enlace(manifest, ruta)`;
`verificar_anclaje(ruta, tamano, sha256)`. El desajuste es resultado, la entrada
inválida o herramienta rota es excepción `ComparadorError`. Jerarquía de código:
política de enlaces ante todo, luego FALTANTE/EXTRA/TIPO/CONTENIDO.

`adaptador_mimo.py` aplica ESTA suite a la implementación real de MiMo sin
reescribir expectativas: solo `envolver_mimo()` puede editarse para su firma;
códigos no mapeados se informan como INADAPTADO. Pendiente: ejecutarlo cuando
MiMo publique su comparador.

## 5. Coste y estrategia (sin caché confiada)

Medido en fixtures; extrapolación declarada, no medida sobre el PKG real
(prohibido en paralelo a MiMo): inventario = 1 pasada streaming O(n) + hashes;
comparar = O(n) en memoria. Costes por `verify-only`: expansión (~13 GiB) +
app + staging + pico documentado ≈38 GiB; limpieza confinada (rm solo bajo el
temporal propio verificado como dir real, nunca siguiendo enlaces).
Estrategia: UN inventario por árbol reutilizado en origen/staging/final
(hash una vez, comparar tres veces); prohibido caché por mtime/nombre o
manifiesto mutable sin anclaje al pin T1 (sería raíz de confianza
auto-otorgada). Sin tercera medición de ESP: exit status + hashes la cubren.

## 6. TOCTOU residual y prevención exigida

Ventana observación→uso no eliminable: re-inventariar inmediatamente antes de
cada efecto persistente (colocación, erase, copia), single-thread, sin
escritores concurrentes; documentar la ventana. Sustitución entre observación
y uso queda DEMOSTRADA como detectable (`test_sustitucion_entre_observacion_y_uso`).
Carreras con el candidato real: NO probadas aquí (filas P1-R1…R3 de MATRIZ).

---
Modelo: Muse Spark 1.3 · Host: MacBook-Pro-de-OPERADOR (macOS 26.6.2, arm64) ·
UTC: 2026-09-26 · Encargo: OT07-P1 (apoyo a MiMo, sin operación).
Base leída: v10r1 (83/84) + ZIP 729c561c…; PKG medido solo en tamaño
(13654790295). Sin expansión/hash del PKG/DMG real (producción de MiMo).
