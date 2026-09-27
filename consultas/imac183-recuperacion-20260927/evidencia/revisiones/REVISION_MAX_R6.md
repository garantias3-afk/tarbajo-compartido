# REVISION_MAX_R6.md — reauditoría del delta r5→r6 (CP2)

- **Revisor:** GLM Max (ZCode/Z.ai, GLM-5.3 — VERIFICADO). Solo el delta y las regresiones afectadas, según lo pactado.
- **Objeto:** `OT07_REVISION_v10r2r6_MIMO` — manifiesto 27/27 OK `4fa65e4fe69de4e5408b64e31c1ad65f283980e1569839397481deb268736b6d` (= pin del AVISO); recibo canal `a0cb242f…f657` ✓; r5 intacto (declarado por MiMo, manifiesto `2afb2c93…`); `INTERFAZ_C5.json` SIN cambios (adaptador Flash sigue válido).
- **Evidencia propia:** `evidencia_r6/` (harness reproducido, PoC N2, micro-ventana) — EJECUTADO sin privilegios.

## Disposición de los hallazgos de REVISION_MAX_R5

| Hallazgo | Disposición r6 | Verificación Max |
|---|---|---|
| H-R5-1 (N2, bloqueante) | **CORREGIDO estructuralmente**: `mkdir-staging`+`copy-tree` como root en el helper (root:0, 0600/0700, O_NOFOLLOW/O_EXCL, hardlink/especiales rechazados); `place()` ya no crea ni copia (F3+F4 = `priv.create_staging_and_copy`, con re-pin de origen pre-frontera) | LEÍDO código helper+orquestador; **EJECUTADO**: PoC propio contra r6 confirma que en **simulated** el fd del dueño sigue abriendo (limitación física sin root, declarada por MiMo en los propios tests) — la frontera que cierra es la **nativa**, y el oráculo real (fd-sobre-staging como uid 501 debe fallar EACCES/EPERM) quedó añadido a H1-N2, más N2bis swap-de-hoja. Harness: N2-04/05/06 (+N2-05 textual de ausencia de mkdtemp en place) |
| H-R5-2 (N6) | **CORREGIDO**: re-pin de hoja+padre (y modo 0700) en F7 y F8; tautología eliminada; `cmd_publish` del helper re-pina dentro del proceso root inmediatamente antes de `renamex_np` (rechaza hoja-swap con ESTALE) | LEÍDO + **EJECUTADO**: inyecté un swap tras el último re-pin del orquestador (micro-ventana): publicó el sustituto pero **F9 lo reportó `PUBLICADO_INCONSISTENTE_NO_BORRADO` rc=4 sin borrar** — el backstop funciona; la micro-ventana residual queda como carrera declarada, cerrada en native por el re-pin del helper |
| H-R5-3 | **CORREGIDO**: estado primero (PrivError con staging ⇒ STAGING_RETENIDO rc=2; publicadas ⇒ rc=4/7/8; NoAutorizado solo sin efectos; `except Exception` final ya no escapa sin veredicto) | LEÍDO diff + casos H-R5-3a/b en harness |
| H-R5-4 | **CORREGIDO**: `place()` delega en `c5_ancla.verificar_ancla` + `adaptar_ancla_c1` (fail-closed ante formato desconocido); `acreditar_origen_desde_manifiesto` exige hash del ancla en manifiesto sellado; gate DELEGADA⇒no-root persiste (línea 586); `c5_acl.validar_acl` cableada en F6 | LEÍDO; ver R6-1 (fail-open residual en el except) |
| H-R5-5 | **CORREGIDO**: `path_confinada` (prefijo `ot07_c5_staging.`/componente o `C5_AUTH_BASE`) en todas las acciones del helper; `cleanup` además exige directorio+prefijo; `NativePriv.registrar_ambito` fija `C5_AUTH_BASE` | LEÍDO; nota R6-4 sobre la debilidad del strstr |
| H-R5-6.1/7/8 | rc6→rc2 documentado en DIFF; SENSIBILIDAD 8 entradas + `conteo_casos: 12`; adaptador de ancla C-1 real; UID parametrizado; código muerto fuera | VERIFICADO |

**Harness r6 reproducido por Max sobre copia propia: 48/48 OK, RC=0, 0 skips** (35 de r5 + 13 oráculos nuevos).

## Veredicto

**CANDIDATO_R6_REVISADO_ACEPTADO.** La transición PREPARACION → CANDIDATO_REVISADO se otorga. Los dos bloqueantes de r5 quedaron corregidos con el diseño correcto (frontera nativa en el helper + re-pines con backstop F9 medido por Max). H1 **aún no se presenta**: falta la batería independiente de Flash contra el orquestador r6 (adaptador ya válido, contrato sin cambios) y dos condiciones menores pre-H1:

- **R6-1 (obligatoria antes de H1, una línea):** en F6, `except acl_mod.AclPolicyError: pass` es **fail-open** — si `ls -le` no puede leer una ACL, la validación se salta silenciosamente, contradiciendo el fail-closed declarado del módulo. Cambiar a abort (`ABORTADO_STAGING_RETENIDO`).
- **R6-2 (menor, próxima revisión que toque harness):** títulos de N2-04/N2-06 sobreafirman en simulated (la aserción fuerte vive en H1-N2 nativo); N6-05 usa un fault que se auto-aborta (no ejercita la detección — mi micro-ventana sí la ejercitó vía F9).
- **R6-3 (cosmético):** bloque «Primitivas REALES» duplicado en el header de `c5_helper.c`.
- **R6-4 (nota de diseño):** `strstr("/ot07_c5_staging.")` acepta cualquier ruta que contenga el componente — para H1 fijar `C5_AUTH_BASE` al fixture base (ya lo hace `NativePriv`); documentar que el confinamiento estricto viene de esa variable.

## Siguiente paso

1. Flash corre su batería (51 casos + adaptador INTERFAZ_C5 sin cambios) contra el orquestador r6 en modo `simulated`/`fixture_ensayo` — mensaje PARA_PEGAR_FLASH_R6 adjunto.
2. MiMo aplica R6-1 (y R6-2/R6-3 si toca harness) en la misma revisión menor r6b o junto con lo que surja de Flash.
3. Con batería verde + R6-1 aplicada, Max emite el pedido **H1** único (PROCEDIMIENTO_H1 de r6 + sección separada del instalador real).
