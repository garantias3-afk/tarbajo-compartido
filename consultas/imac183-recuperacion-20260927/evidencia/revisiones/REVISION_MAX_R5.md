# REVISION_MAX_R5.md — revisión del delta r5 (CP2) + adjudicaciones CP1

- **Revisor:** GLM Max (ZCode/Z.ai, `account:zai-individual-coding-plan/GLM-5.3` — VERIFICADO por metadatos de sesión). Rol: coordinador/revisor; no escribí código de r5.
- **Objeto:** `OT07_REVISION_v10r2r5_MIMO` — manifiesto 19/19 OK, SHA-256 `2afb2c93fc85d34027630d50f1a867f925ac55c190a47051657ecccf471a7840`; recibo canal `ccbadcb3…e6216` ✓. Base r4 (`17dafa93…`) revalidada íntegra.
- **Entradas también autenticadas:** FLASH `OT07_FLASH_PRUEBAS_C5_R1` 35/35 (`de3a6b17…53701`) y su derivación del contrato (C0 PASA, SHA `c4dcf663…` verificado por Flash y leído por Max); MUSE P8 15/15 (`2dc6d3d9…`). Recibos con `operaciones=false` en las tres.
- **Evidencia propia:** carpeta `OT07_AVANCE_C5_MAX_REV` (workspace de Max): `copias/r5` (copia de trabajo, base = manifiesto sellado), `harness_r5_propio.log` (reproducción), `poc_n2_frontera.log` (PoC del hallazgo principal). Todo EJECUTADO sin privilegios.

## Veredicto

**NO_CANDIDATO_REVISADO.** La transición PREPARACION → CANDIDATO_REVISADO queda denegada por dos defectos bloqueantes (H-R5-1, H-R5-2). **No se presenta H1** (el procedimiento existe y es sustanciablemente correcto, pero el objeto que autorizaría aún no merece autorización). r5 conserva méritos reales (§ Positivo); la corrección es acotada y no reabre lo andado.

## Positivo (verificado por Max)

| Ítem | Verificación |
|---|---|
| `INTERFAZ_C5.json` publicado temprano, sin pseudocomandos P6 | LEÍDO; derivación de Flash compatible (C0 PASA); **sin incompatibilidades de contrato** (CP1 resuelto) |
| Helper C: primitivas reales `lchown(2)`→`fchmodat` (orden nativo), `renamex_np(0x4\|0x10)`, `fstatat+AT_UNIQUE`; sin RESOLVE_BENEATH ni lchown binario | LEÍDO línea a línea; constantes correctas (04_AJUSTES §1/§2) |
| HB-1 en helper (`verify` incluye raíz; `walk_protect` protege raíz primero) | LEÍDO |
| Legacy `ot07_guard/ot07_process/place_helper/verificar_instalador` | **byte-idénticos a r4** (4/4 hashes) — sin cambios laterales |
| Harness 35/35, 0 skips | **EJECUTADO por Max sobre copia propia: 35/35 RC=0** |
| Erratas r4 | VERIFICADO: `INDICE_HISTORICO_R5.md` puntúa `codesign_cim` vacío = **no acreditado**; `SENSIBILIDAD.json` con esquema base/mutante/comando/RC/aserción (ojo: 7 entradas vs «8 casos» del recibo — menor) |
| Batería Flash 50/51 + 1 SKIP (regresión P5r 47/47 incluida) | LEÍDO; hallazgos nativos 1–5 **respaldados por Max** (AT_UNIQUE errno 107 desde uid 501 — también medido por Max en ronda anterior; `execve(/dev/fd)` EACCES; `renamex_np` exige W sobre fuente; padre gobierna borrado) |
| Sin sudo/root/USB/arranque ejecutados; H1 no autoaprobada | Recibos ✓ |

## Hallazgos (orden de gravedad)

### H-R5-1 — BLOQUEANTE (N2): la frontera no está implementada en el flujo; el objeto publicado es alterable por un fd preabierto
- **Requisito:** OT01 §3 (dirección preferida: inodos finales creados en área controlada por el helper privilegiado, inaccesible O_WRONLY/O_RDWR para el uid operador); 05 N2; maestra («las referencias abiertas deben resolverse técnicamente; no pedir al usuario que acepte vulnerabilidades»).
- **Archivos/líneas:** `src/c5_orquestador.py:541-563` (F3 `mkdtemp` **del operador**; F4 `_copy_tree` **como operador**) — el helper no tiene acción de creación/copia; `src/c5_helper.c` (solo protect/verify/publish/cleanup).
- **Disparador y consecuencia (EJECUTADO, PoC propio `poc_n2_frontera.log`):** un fd `O_WRONLY` abierto sobre un inodo de staging entre F4 y F6 (atacante mismo uid, pre-protección) **sobrevive** a `chmod go-w`+ledger-chown y al rename; tras `PUBLICADO_VERIFICADO rc=0` (con `metadata_ok=True`), el fd reescribió el contenido publicado (`ATACANTE-ESCRIBIO-TRAS-PUBLICAR`, modo publicado 0600 limpio). El objeto «verificado» queda controlado por el atacante — exactamente lo que N2 prohíbe. El propio harness de r5 midió que chmod no revoca fd (N2-03), pero su oráculo N2-01 es **textual** (buscar strings en el fuente) y N2-02/H1-N2 solo ensayan fd sobre el **origen** (caso trivial: la copia crea inodos nuevos). El caso real no está cubierto en ningún lado.
- **Corrección mínima:** mover la creación de directors + copia del árbol final **dentro del helper privilegiado** (root crea staging root:0 0700 en área propia, copia desde el origen no confiable leyendo como root, y el uid operador jamás puede abrir O_WRONLY/O_RDWR esos inodos), o equivalente con la propiedad demostrada; añadir el caso fd-sobre-staging (hoy falla) al harness y al oráculo N2 de H1.

### H-R5-2 — GRAVE (N6 / REQUISITO_R5-4 de Flash): ventana pre-rename sin re-pin del staging
- **Archivos/líneas:** `src/c5_orquestador.py:595-596` — comparación **tautológica** (`pin(x) != pin(x)` → `pass`) donde P5r revalidaba pin del padre de staging y modo 0700; F8 (`:603-610`) revalida `pin(origen)` pero **nunca** `pin(hoja)` contra el pin de F3/F7.
- **Consecuencia:** un swap de la hoja de staging entre F7 y F8 publica el sustituto (RENAME_NOFOLLOW_ANY protege symlinks en el camino, no sustitución del directorio fuente). Es el defecto que Flash marcó como REQUISITO_R5 («cerrar la ventana») y no está atendido.
- **Corrección mínima:** re-pin de hoja + padre de staging (y modo 0700) inmediatamente antes de `renamex_np`; caso swap-de-hoja (análogo T22) en el harness.

### H-R5-3 — MODERADA (HB-3/contrato): veredictos de excepción ignoran el estado del disco
- **Archivos/líneas:** `src/c5_orquestador.py:442-445` (`PrivError` → incondicional `NO_AUTORIZADO` rc=5, aunque quede staging propio o publicación propia) y `:652` (el `except` no captura excepciones genéricas: una no-OSError post-F8 escapa **sin veredicto**, violando el `comportamiento_fallo` del propio contrato).
- **Corrección mínima:** decidir por estado primero (como P5r `_verdict_por_estado`); añadir `except Exception` final → ESTADO_INDETERMINADO/rc apropiado; caso PrivError-con-staging y excepción-genérica-post-publicación al harness.

### H-R5-4 — MODERADA (N5/N3): los módulos correctos existen pero no están cableados al flujo
- `src/c5_ancla.verificar_ancla` exige `origen_autenticado` + coincidencia de hash; **pero** `place()` usa su propio `fijar_ancla` (`c5_orquestador.py:294-314`) que marca confianza «C-1» con solo `--c1-hash` auto-declarado del operador — la marca que desbloquea el modo root es vacua en el código actual. `src/c5_acl.validar_acl/normalizar` (política RECHAZAR allow-write ajena) **no se invoca jamás** en F6/F7/F9; el helper añade deny-501 sin validar ACEs allow preexistentes.
- **Corrección mínima:** cablear `verificar_ancla` (con `origen_autenticado` real: p. ej. hash del ancla == hash registrado en el manifiesto sellado r4/C-1) y la política ACL al pipeline; eliminar o endurecer `fijar_ancla`.

### H-R5-5 — MODERADA (N8/N0, endurecimiento pre-H1): helper sin confinamiento de rutas
- `src/c5_helper.c`: `cleanup` sin chequeo de euid ni prefijo (`rmdir` de cualquier directorio vacío que le pasen); `protect/publish` aceptan cualquier ruta (solo euid); `NativePriv` ignora ámbitos. Para que el helper sea un «helper limitado» creíble bajo H1: validar prefijo `ot07_c5_staging.`/rutas autorizadas, dueño del padre, o confinar por fd.

### H-R5-6 — MENORES (incorporar sin reabrir historial)
1. rc6→rc2 unificado: contrato actualizado y válido — documentarlo en `DIFF_r4_a_r5.md` (Flash pidió unificar criterio; su adaptador mapea por veredicto).
2. `uid_t op = 501` y `UID_OPERADOR = 501` hardcodeados (helper e INTERFAZ) — parametrizar.
3. Código muerto en `protect_one` (`uuid_t uu`, `pe`, `tag`).
4. `aceptar_usuario` perdió veredicto diferenciado y ahora protege siempre (más estricto, coherente con B, pero documentar).
5. `check_expected_metadata` devuelve bool sin causas (degradación informativa vs P5r).
6. EXDEV (staging y destino en volúmenes distintos) sin manejo explícito.
7. `SENSIBILIDAD.json`: 7 entradas vs «8 casos» del recibo.
8. Compatibilidad de formato entre el ancla C-1 real (`inv_extracted_app.json` de r4, esquema `tree_inventory.py`) y `inventory_tree` de r5 no demostrada — sin adaptador, `compare_content` divergiría siempre con el ancla real del instalador.

## Adjudicaciones CP1 (contrato) y MUSE

- **INTERFAZ_C5 ↔ adaptador Flash: COMPATIBLES** (C0 PASA por ejecución de Flash; verificado por lectura de Max). La observación rc=6 quedó resuelta por el contrato (unificación en rc=2 con veredictos por string); mantener la nota en DIFF.
- **MUSE/P8:** ancla C-1 verificada 1009/1009 contra inventario propio; PKG `pkgutil` cadena a Apple Root CA RC=0; DMG `hdiutil verify` VALID RC=0 con attach/detach propios; **Assets[0] 14.8.9 / 23J631 MEDIDO ahora**; catálogo RC=0 sin 14.x. **Adjudicación de Max:** la procedencia histórica de la descarga es NO_RECONSTRUCTIBLE y se registra como trazabilidad histórica (no inventada); **no bloquea** la autenticidad medible hoy (firma PKG + ancla sellada + DMG verificado) ni la futura transición INSTALADOR_VALIDADO, que igualmente exigirá re-medición en su momento. `codesign` app RC=1 envelope-obsoleto: coherente con C-1 histórico (LEÍDO), sin cambio. Rescate: 3494 vivo / RESCATE_A intacto / KINGSTON sin cambios (medido por Muse sin tocar) — vigencia de tier2 queda NO_VERIFICADO salvo nueva evidencia.

## Transición y siguiente paso

- **PREPARACION → CANDIDATO_REVISADO: DENEGADA** (H-R5-1, H-R5-2). El resto del pipeline continúa: MiMo corrige el delta mínimo (H-R5-1…H-R5-5 obligatorios; H-R5-6 con al menos 1, 7 y 8), sella r6, y Flash corre su batería (adaptador listo) contra el orquestador corregido; Max reaudita **solo el delta y las regresiones afectadas**. La regresión D/A/B completa del candidato integrado se mantiene para cuando C-5 se integre al árbol del candidato (N9), no para esta corrección puntual.
- **H1 NO se presenta** en esta ronda. Cuando r6 pase la revisión del delta y la batería de Flash contra el orquestador corja, Max emitirá el pedido H1 único (fixture <1 MiB + sección separada del instalador real) con los hashes de r6.
