# MATRIZ C-1 … C-10 — cierre en v10r2

| ID | Defecto (v10r1 / artefactos Flash) | Estado en v10r2 | Dónde | Evidencia |
|---|---|---|---|---|
| **C-1** | `codesign --strict -R=anchor apple` sobre APP → RC=1 envelope obsolete ⇒ E2 imposible | **CORREGIDO (implementación)** | `verificar_instalador.py`: cadena PKG pineada + `expand-full` + árbol + DMG 64-hex + CIM estricto; APP codesign queda diagnóstico | `evidencia_impl/CHAIN_REPORT.json`, `offline_positive.json`, tests 13 |
| **C-2** | `PENDING_PKG_SHA256` en el plan | **CORREGIDO** | `colocacion_v2/PLAN_COLOCACION_v2.md` y `colocar_candidato.sh` §0 con hash real | test `test_no_pending_placeholder` |
| **C-3** | `PKG_SHA256_ESPERADO` solo se imprimía | **CORREGIDO** | §0 compara existencia, bytes, SHA-256 y firma **antes** de mover | tests `test_pkg_missing/hash/bytes` |
| **C-4** | Literal `"successful"` insatisfacible | **CORREGIDO** | `Status: signed Apple Software` + `Apple Root CA` | test `test_c2_pkg_hash…` |
| **C-5** | Dueño `OPERADOR:wheel` + CIM como root | **PROPUESTA_NO_EJECUTADA** | §8 del script (comentado) + decisión en PLAN v2 | requiere OPERADOR + re-auditoría |
| **C-6** | Literal `/Applications` | **CORREGIDO** | `DEST_PARENT=$(dirname "$DESTINO")` | `test_c6_c7_c8_c9_present` |
| **C-7** | `mkdir -p` en staging | **CORREGIDO** | `mkdir "$STAGING"` sin `-p`; padre debe existir | idem |
| **C-8** | Sin chequeo mismo filesystem | **CORREGIDO** | `stat -f %d` staging == destino | idem |
| **C-9** | Presupuesto sin staging | **CORREGIDO** | `NEED_KIB` ≈38 GiB + margen 20 GiB en `df` | idem |
| **C-10** | Evidencia mal rotulada / RC ausente | **CORREGIDO documentalmente** | esta matriz + FUENTE.md; RC históricos = `NO_CAPTURADO` | no se edita evidencia sellada |

## Controles adicionales (de la especificación GLM §4 y Muse H1–H7)

- Ancla PKG fuera del candidato (nunca `APP_MANIFIESTO` como raíz de confianza).
- Transform postinstall explícito (`POSTINSTALL_ADDITIONS`).
- Enlaces: absolutos, `..`, resolución, escapes, ciclos, tipos especiales.
- DMG SHA-256 completo 64 hex.
- Fail-closed ante herramienta ausente / lectura parcial / firma fallida.
- Re-hash del PKG tras derivación.
- `spctl`/`codesign -d` solo diagnóstico.

## Pruebas

| Batería | Cantidad | Resultado |
|---|---|---|
| Suite completa `discover -s tests` | **131** | **OK** (reproducido) |
| `test_verifier_v10r2.py` | 13 | OK |
| `test_colocacion_v2.py` | 9 | OK |
| Muse `test_comparador.py` (referencia) | 24 | OK (su comparador) |
| Positivo offline cadena real | 1 | OK (`ok=true`, 43 s) |

Pendientes nativos (NO ejecutados en esta OT): `hdiutil verify` + `Assets[0]`,
colocación, OCLP, erase/CIM, picker/boot.
