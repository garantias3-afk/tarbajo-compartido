# MATRIZ_P2 — fallos cubiertos por la propuesta de colocación v2

Fuente de resultados: `pruebas/harness_v2_resultados.txt` (21/21 OK, sobre copias sustituidas del
script v2 con fixtures en `/private/var/tmp`, sin sudo, sin /Applications), `pruebas/harness_traslado.sh`
(primitiva real `mv`/`mv -n`) y `pruebas/renamex_resultados.txt` / `renamex_binario_resultados.txt`
(primitiva `renamex_np(RENAME_EXCL)` vía ctypes y binario). "C-#" = hallazgo de DICTAMEN_QWEN.md.

| # | Fallo / escenario | Disparador | Resultado esperado | Resultado observado | Cubre |
|---|---|---|---|---|---|
| 1 | Camino feliz | fixture íntegro, modo aceptar_usuario | COLOCADO_VERIFICADO, app en destino, staging retirado | OK (rc=0, DMG presente en destino) | positivo |
| 2 | PKG ausente | `pkg_mod=ausente` | fail antes de efectos | OK: "PKG ausente" | C-3 |
| 3 | PKG truncado (5 bytes) | `pkg_mod=truncado` | fail por bytes | OK: "bytes del PKG inesperados: 5" | C-3 |
| 4 | PKG cambiado (mismo tamaño) | contenido distinto, SHA pineado | fail por SHA | OK: "SHA-256 del PKG no coincide" | C-3 |
| 5 | Firma no Apple (RC≠0) | stub pkgutil RC=1 | fail por RC comprobado | OK: "pkgutil --check-signature RC=1" | C-3/C-4 |
| 6 | Firma sin literal | salida sin `signed Apple Software` | fail por literal | OK: "firma del PKG no es 'signed Apple Software'" | C-4 |
| 7 | Fuente alterada (igual tamaño) | tamper tras manifiesto | fail por inventario exacto | OK: "inventario ORIGEN difiere" | punto 6 |
| 8 | Archivo extra en origen | archivo añadido | fail (extra detectado) | OK: "inventario ORIGEN difiere" | punto 6 |
| 9 | Manifiesto con entrada omitida | manifiesto recortado | fail (extra respecto a manifiesto) | OK: "inventario ORIGEN difiere" | punto 6 |
| 10 | Enlace absoluto saliente | symlink → /etc | fail | OK: "symlink ABSOLUTO en origen: 1" | punto 6 |
| 11 | Enlace transitivo saliente | link→link→`../../../fuera` | fail | OK: "SALIENTE … sale de la raíz" | punto 6 |
| 12 | Error de ditto | stub ditto RC=1 | fail con RC visible | OK: "ditto RC=1" | punto 6 |
| 13 | Cross-device | stubs stat con dev distintos | fail antes del traslado | OK: "cross-device" | C-8 |
| 14 | Falta de espacio | stub df 1000 KiB | fail antes de copiar | OK: "espacio insuficiente" | C-9/punto 7 |
| 15 | Destino preexistente (dir) | fixture con dir destino | fail sin tocar nada | OK: "DESTINO ya existe" | v1 ya lo tenía |
| 16 | Destino aparece en la ventana | wrapper crea dir antes del mv | EEXIST, sin anidar, staging conservado | OK: "(EEXIST): staging conservado" | punto 3-4 |
| 17 | Abuelo del destino es symlink | Applications→apps_real | fail (padre symlink o ELOOP) | OK: "padre de destino es symlink: rechazado" | C-6 |
| 18 | Protección fallida (C-5) | stub chown RC=1, modo root | PROTECCION_FALLIDA, sin COLOCADO_VERIFICADO | OK | C-5 |
| 19 | Decisión C-5 no tomada | modo por defecto | RC=3 COLOCADO_SIN_PROTEGER (sin COLOCADO) | OK | C-5 |
| 20 | Interrupción simulada post-copia | `exit 77` tras ditto | staging conservado, destino intacto | OK: rc=77, staging.QcjAty presente | punto 6 |
| 21 | Reintento tras interrupción | nueva corrida completa | éxito sin chocar con staging huérfano | OK: rc=0 | punto 6 |

## Primitiva de traslado — comportamiento REAL del host (fixtures, sin privilegios)

`mv -n` (BSD mv, macOS 26/27):

| Escenario | RC | Efecto observado |
|---|---|---|
| Destino inexistente | 0 | mueve limpio |
| Destino archivo preexistente | **0** | NO mueve, sin mensaje (RC=0 ≠ éxito) |
| Destino directorio preexistente | **0** | **ANIDA**: destino/Install macOS Sonoma.app/… |
| Destino symlink (a dir ajeno) | **0** | **ATRAVIESA** el symlink y mueve dentro del árbol ajeno |
| Dir aparecido entre check y mv | **0** | anida |
| Dos contendientes, destino inexistente | 0 y 1 | uno gana; el otro falla ENOTEMPTY sin anidar |
| Control `mv` sin -n, dir→archivo | 1 | ENOTDIR, no destruye |

`renamex_np(RENAME_EXCL)` (vía ctypes y binario compilado):

| Escenario | RC | Efecto |
|---|---|---|
| Destino inexistente | 0 | renombrado atómico |
| Destino archivo/dir/symlink existente | 17 EEXIST | sin tocar destino, staging conservado, **sin anidar ni atravesar** |
| Dos contendientes | 0 y 17 | determinista; perdedor conserva su staging |
| Ruta con symlink en padres (con RENAME_NOFOLLOW_ANY y ruta física) | 0 o ELOOP | el flag rechaza resolución con enlaces; con `realpath` previo el symlink del padre ya fue seguido por el llamador (límite documentado) |

Nota sobre `RENAME_NOFOLLOW_ANY`: devuelve ELOOP si la ruta contiene symlinks intermedios (en este
host `/var → private/var`), por lo que la llamada productiva debe usar rutas físicas resueltas
(`realpath`) y asumir que la resolución previa tiene su propia ventana residual; el binario
`mv_excl` fija EXCL|NOFOLLOW_ANY.

## Espacio por fases (punto 7) — a partir de tamaños de entrada

| Fase | Consumo incremental | Acumulado (aprox.) |
|---|---|---|
| PKG en disco (ya existe) | 12.72 GiB | 12.72 GiB |
| Extracción del payload a app base | ~0.04 GiB | ~12.76 GiB |
| Réplica del SharedSupport.dmg en la app | ~12.71 GiB | ~25.5 GiB |
| Staging (ditto completo) | ~12.71 GiB | **~38.2 GiB (pico)** |
| Traslado (mismo volumen: renombrado) | 0 | ~25.5 GiB tras liberar staging |
| Reserva exigida por el script | 2 GiB sobre el libre | verificación viva |

Datos que MiMo debe medir en vivo (no asumir): `du -sk` de la app extraída, `df -k` del volumen
destino antes de copiar y antes del traslado, y el pico con staging. El script v2 ya verifica
espacio con la medición real y falla si no alcanza.

## Rollback y limpieza

- Fallo antes del traslado: staging queda en el candidato (etiquetado por mktemp), destino
  intacto; el reintento crea staging NUEVO (prueba 21) y el huérfano se diagnostica/borra a mano.
- Fallo en el traslado (EEXIST): staging conservado; nunca se limpia recursivamente una ruta
  del destino ni se borra una app preexistente.
- No hay `rm -rf` sobre rutas no autenticadas: el único borrado es del dir temporal creado por
  `mktemp` en la misma corrida.
