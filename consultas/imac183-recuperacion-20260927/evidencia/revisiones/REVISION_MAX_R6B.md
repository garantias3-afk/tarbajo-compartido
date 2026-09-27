# REVISION_MAX_R6B.md — spot-check del delta r6→r6b

- **Objeto:** `OT07_REVISION_v10r2r6b_MIMO` — manifiesto 34/34 OK `7e69177e9bb68706632e56dcd8e7c4fcbb21d39ffacea338e273209f5b114141` (= pin AVISO); recibo canal `cc348e76…75a8` ✓; r6 intacto (`4fa65e4f…`); INTERFAZ sin cambios (`c4dcf663…`).
- **Delta:** solo `c5_acl.py` (aliases F-R6-N3-1), `c5_helper.c` (**solo comentarios**: R6-3/R6-4/build-doc), `c5_orquestador.py` (R6-1 fail-closed), harness (+4) y evidencia. Sin cambios laterales.

## Verificaciones (EJECUTADO por Max sobre copia propia)

| Ítem | Resultado |
|---|---|
| R6-1 end-to-end (inyección AclPolicyError, `acl_enabled=True`) | `ABORTADO_STAGING_RETENIDO rc=2 published=False` ✓ (antes publicaba rc=0) |
| F-R6-N3-1 (ACEs reales `chmod +a`) | `allow write`/`append`/`delete` **detectadas**; `allow read` no (correcto) ✓ |
| Harness r6b | **52/52 OK, RC=0, 0 skips** (reproducido por Max) |
| Regresión micro-ventana swap | sustituto publicado pero F9 ⇒ `PUBLICADO_INCONSISTENTE_NO_BORRADO rc=4` ✓ backstop intacto |
| Procedencia binario | recompilado desde `src/c5_helper.c` (SDK 26.5, comando de BUILD.md): build OK, `selfcheck` idéntico; bytes difieren solo por firma ad-hoc del linker (documentado). Binario enviado pineado por hash |
| Reproducción MiMo (`evidencia_r6b/REPRODUCCION_R6B.json`) | 5/5 coherente con lo medido por Max y Flash |

**Veredicto: CANDIDATO_R6B_ACEPTADO. Transición IMPLEMENTACION_PROBADA OTORGADA** (código + revisión independiente de delta + batería Flash R2 con hallazgos corregidos y verificados por ambas partes + harness 52/52 + comandos exactos + manifestación). H1 se presenta junto con este sello. Nota documental (post-H1): `PROCEDIMIENTO_H1.md` paso 4 debe registrar la secuencia con las acciones de frontera (`mkdir-staging`+`copy-tree`) — la secuencia autoritativa va en la solicitud H1 de Max.
