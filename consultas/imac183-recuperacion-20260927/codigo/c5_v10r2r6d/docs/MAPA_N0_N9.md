# MAPA_N0_N9.md — cobertura archivo/función por criterio

Cada celda: propiedad → implementación → prueba. Conteos dinámicos en
`evidencia_r6/HARNESS_RESULTADOS.json` (48/48 en r6). Tras H1 se completan
las columnas «nativo» con evidencia real.

| ID | Propiedad | Implementación (archivo:función) | Prueba no privilegiada | Nativo (tras H1) |
|---|---|---|---|---|
| N0 | Bootstrap sin runner mutable del uid | `c5_bootstrap.py:inventario_bootstrap, condiciones_H1`; `c5_helper.c:cmd_selfcheck`; `c5_orquestador.py:_exigir_euid_no_cero` | N0-01..03 | hash/identidad efectivos + pruebas confinadas |
| N1 | Raíz e hijos protegidos; write/chmod no autorizado falla | `c5_helper.c:protect_one,walk_protect,cmd_verify,verify_one` (incluye **raíz**); `c5_orquestador.py:_protect_tree,check_expected_metadata` | N1-01..03 (HB-1 mutante SENS-HB1-RAIZ-GW) | UID operador; RC/errno y bytes |
| N2 | **Ningún fd previo altera el inodo consumido** (H-R5-1) | Frontera: `SimulatedPriv/NativePriv.create_staging_and_copy` — en native `c5_helper.c:cmd_mkdir_staging,cmd_copy_tree` (root:0 0700); sin ventana crear→copiar del operador | **N2-04** (fd-sobre-staging), **N2-05** (sin ventana), **N2-06** (PoC Max), N2-02/03 (E1/E2) | open O_WRONLY tras frontera → EACCES; comparación destino/origen |
| N3 | ACL allow/herencia/padre/eliminación explícitas | `c5_acl.py:leer_acl_extendida,validar_acl,normalizar_acl_privilegiada`; cableado en F6 (`acl_mod.validar_acl`); `c5_helper.c:protect_one` (acl_set_file) | N3-01..02, H-R5-4b | ± ACL reales; rename/unlink separados |
| N4 | Recorrido confinado; AT_UNIQUE; fail-closed | `c5_orquestador.py:inventory_tree,_copy_tree`; `c5_helper.c:cmd_probe_at` (AT_UNIQUE); rechazo hardlink/FIFO/symlink-escape | N4-01..05 | sonda syscall real + negativos |
| N5 | Ancla C-1 / snapshot único (H-R5-4) | `c5_ancla.py:verificar_ancla,acreditar_origen_desde_manifiesto,construir_evidencia_c1,adaptar_ancla_c1`; `c5_orquestador.py:fijar_ancla` | N5-01..04, H-R5-4a, H-R5-6.8 | verificación dentro de frontera antes de consumir |
| N6 | F8 exclusivo; estados verdaderos; retry sin huérfanos (H-R5-2/3) | `c5_orquestador.py:rename_excl,_verdict_por_estado,list_stale,place F7–F10` con `hoja_pin`/`padre_pin`/modo 0700; `c5_helper.c:cmd_publish` re-pin | N6-01..06, H-R5-3a/3b (SENS-LIMPIEZA-RC3, SENS-EEXIST-GANADOR, SENS-HR5-2-SWAP-HOJA) | efectos nativos, identidades, limpieza |
| N7 | Verificar→ejecutar vincula objeto real | `c5_orquestador.py:pin,pin_equal`; `c5_helper.c` (fstat del fd en H1); docs H1 §oráculos | N7-01..02 (SENS-PIN-SUSTITUTO) | fixture ejecutable + mutador sincronizado |
| N8 | Operación confinada al fixture/bundle (H-R5-5) | `SimulatedPriv._confine,registrar_ambito`; `c5_helper.c:path_confinada,exigir_confinada` (prefijo `ot07_c5_staging.` / `C5_AUTH_BASE`) | N8-01..02, H-R5-5a/5b | journal/relectura, cero efecto externo |
| N9 | Regresión r4/P5r, guards, espacio, limpieza | `src/legacy/` byte-idéntico r4; espacio F2; sin diskutil en C5 | N9-01..03 + suite legacy | logs nativos sin promover USB/arranque |

## Erratas r4 (exigidas por OT punto 6)

| Errata | Dónde se corrige | Prueba |
|---|---|---|
| puntero `codesign_cim` vacío | `docs/INDICE_HISTORICO_R5.md` (puntúa vacío = no acreditado) | ERRATA-01 |
| evidencia sensibilidad base/mutante/comando/RC/aserción | `evidencia_r5/SENSIBILIDAD.json` (**12 casos**, `conteo_casos`) | ERRATA-02, H-R5-6.7 |

## Hallazgos Max r5 → cobertura r6

| Hallazgo | Oráculos r6 |
|---|---|
| H-R5-1 frontera N2 | N2-04, N2-05, N2-06 + H1-N2 fd-sobre-staging |
| H-R5-2 re-pin hoja | N6-05, N6-06 |
| H-R5-3 veredictos | H-R5-3a, H-R5-3b |
| H-R5-4 ancla+ACL | H-R5-4a, H-R5-4b |
| H-R5-5 confinamiento | H-R5-5a, H-R5-5b |
| H-R5-6.1 rc6→rc2 | documentado en DIFF y SENSIBILIDAD |
| H-R5-6.7 conteo sensibilidad | H-R5-6.7 |
| H-R5-6.8 adaptador C-1 | H-R5-6.8 |

## Fuera de alcance hasta hito

| Tema | Hasta |
|---|---|
| USB / createinstallmedia / borrado | H2 |
| Arranque / picker / OCLP | H3 |
| Instalador real en /Applications | H1 (sección separada) + N0–N8 GO |
| Reparación APFS / originales iMac | fuera de esta OT |
