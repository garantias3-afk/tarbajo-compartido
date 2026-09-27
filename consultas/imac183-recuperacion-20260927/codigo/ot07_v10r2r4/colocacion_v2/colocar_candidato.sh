#!/bin/bash
# colocar_candidato.sh v3 — OT07 v10r2r1 (NO ejecutar en esta OT)
# Integra P2 Flash: rename_excl (RENAME_EXCL|RENAME_NOFOLLOW_ANY) + C-5 gate ANTES
# de cualquier efecto + inventario exacto propio (no APP_MANIFIESTO.shasum -c).
# Invocación futura: registrar.sh + sudo -n solo para mv/chown si MODO=root.
set -uo pipefail
umask 077
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
export LC_ALL=C
export PYTHONDONTWRITEBYTECODE=1

DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
HELPER="$DIR/place_helper.py"
PY=/usr/bin/python3

# ==== ANCLAS ====
PKG="/var/tmp/ot07_E2R1_candidato.gMdKSX/InstallAssistant.pkg"
PKG_BYTES=13654790295
PKG_SHA256="ecc36bf172105f8c3325ceeb4e5ab8cc297260be806eac10b21b784ff40d8173"
PKG_STATUS="signed Apple Software"
PKG_ROOT_CA="Apple Root CA"
ORIGEN="/var/tmp/ot07_E2R1_candidato.gMdKSX/extraida/Install macOS Sonoma.app"
DESTINO="/Applications/Install macOS Sonoma.app"
# Inventario de referencia generado por la cadena PKG (no manifiesto shasum del candidato)
INVENTARIO_REF="$DIR/evidencia_impl/inv_extracted_app.json"

# C-5: REQUIERE_DECISION_C5 | root | aceptar_usuario  (variable de entorno del operador)
MODO_PROTECCION="${OT07_MODO_PROTECCION:-REQUIERE_DECISION_C5}"

fail(){ printf '### FALLO: %s\n' "$*" >&2; exit 1; }
ph(){ "$PY" -B "$HELPER" "$@"; }

# ==== 0. C-5 GATE — ANTES de staging, ditto, rename o cualquier escritura a destino ====
# B-1: root es CONOCIDA pero NO implementada -> falla aqui, nunca tras publicar.
ph c5-gate "$MODO_PROTECCION" > /dev/null || fail "C5_GATE: no iniciar colocacion (ver C5_* en stderr)"
printf 'C5_GATE_OK modo=%s (solo politicas implementadas pasan)\n' "$MODO_PROTECCION"

# ==== 0b. I-5: inputs en /var/tmp deben existir antes de cualquier efecto ====
[ -f "$PKG" ] && [ ! -L "$PKG" ] || fail "I5_PKG_AUSENTE: $PKG (dependencia /var/tmp)"
[ -d "$ORIGEN" ] && [ ! -L "$ORIGEN" ] || fail "I5_APP_AUSENTE: $ORIGEN"

# ==== 1. PKG precondiciones (C-2/C-3/C-4) ====
[ -f "$PKG" ] && [ ! -L "$PKG" ] || fail "PKG ausente o symlink"
PKG_SIZE=$( /usr/bin/stat -f %z "$PKG" ) || fail "stat PKG"
[ "$PKG_SIZE" -eq "$PKG_BYTES" ] || fail "PKG bytes $PKG_SIZE != $PKG_BYTES"
PKG_GOT=$( /usr/bin/shasum -a 256 "$PKG" | /usr/bin/awk '{print $1}' ) || fail "sha256 PKG"
[ "$PKG_GOT" = "$PKG_SHA256" ] || fail "PKG sha256 mismatch"
SIG=$(/usr/sbin/pkgutil --check-signature "$PKG" 2>&1) || fail "pkgutil RC=$?"
printf '%s\n' "$SIG" | /usr/bin/grep -q "Status: $PKG_STATUS" || fail "status incorrecto"
printf '%s\n' "$SIG" | /usr/bin/grep -q "$PKG_ROOT_CA" || fail "sin Apple Root CA"
printf 'PKG_PRECONDICIONES_OK\n'

# ==== 2. Origen + inventario EXACTO propio ====
[ -d "$ORIGEN" ] && [ ! -L "$ORIGEN" ] || fail "origen invalido"
[ "$(basename "$ORIGEN")" = "Install macOS Sonoma.app" ] || fail "nombre origen"
[ -f "$ORIGEN/Contents/SharedSupport/SharedSupport.dmg" ] || fail "origen sin DMG"
[ -f "$INVENTARIO_REF" ] || fail "inventario de referencia ausente (cadena PKG)"
INV_ORIG=$(mktemp /private/var/tmp/ot07_inv_orig.XXXXXX) || fail "mktemp inv"
ph inventory "$ORIGEN" "$INV_ORIG" > /dev/null || fail "inventario origen (enlaces/tipos)"
ph compare-inv "$INVENTARIO_REF" "$INV_ORIG" > /dev/null || fail "inventario origen != referencia PKG"
printf 'INVENTARIO_ORIGEN_OK\n'

# ==== 3. Espacio vivo (C-9 / B-2: RC y formato validados, nunca salida vacía) ====
DEST_PADRE=$( dirname "$DESTINO" )
[ -d "$DEST_PADRE" ] && [ ! -L "$DEST_PADRE" ] || fail "padre destino invalido"
ph space-check "$ORIGEN" "$DEST_PADRE" > /dev/null || fail "espacio insuficiente o herramienta de medida fallo"
printf 'ESPACIO_OK\n'

# ==== 4. Destino inexistente + mismo FS ====
if [ -e "$DESTINO" ] || [ -L "$DESTINO" ]; then
  fail "DESTINO ya existe: APP_EXISTENTE_PENDIENTE_VERIFY_ONLY"
fi
ST_PARENT=$(mktemp -d /private/var/tmp/ot07_staging.XXXXXX) || fail "mktemp staging"
ph same-fs "$ST_PARENT" "$DEST_PADRE" > /dev/null || { rmdir "$ST_PARENT" 2>/dev/null; fail "staging y destino en FS distintos"; }
STAGING="$ST_PARENT/Install macOS Sonoma.app"
/bin/mkdir "$STAGING" || fail "mkdir staging"
/usr/bin/ditto "$ORIGEN" "$STAGING" || fail "ditto a staging"
INV_ST=$(mktemp /private/var/tmp/ot07_inv_st.XXXXXX) || fail "mktemp inv st"
ph inventory "$STAGING" "$INV_ST" > /dev/null || fail "inventario staging"
ph compare-inv "$INV_ORIG" "$INV_ST" > /dev/null || fail "staging != origen"
printf 'STAGING_OK %s\n' "$STAGING"

# ==== 5. Re-check destino y padre (alias /var <-> /private/var documentados) ====
if [ -e "$DESTINO" ] || [ -L "$DESTINO" ]; then
  fail "DESTINO aparecio antes del rename; conservar staging"
fi
[ -d "$DEST_PADRE" ] && [ ! -L "$DEST_PADRE" ] || fail "padre destino cambio"

# ==== 6. Traslado atómico EXCLUSIVO (sin anidado posible) ====
# renamex_np(RENAME_EXCL|RENAME_NOFOLLOW_ANY): EEXIST si destino existe; ELOOP si symlink.
RC_MOVE=$( ph rename-excl "$STAGING" "$DESTINO" | /usr/bin/awk -F= '/^RC=/{print $2}' )
case "$RC_MOVE" in
  0) : ;;
  17) fail "DESTINO aparecio en la ventana (EEXIST): sin escritura dentro de ajeno; staging conservado" ;;
  *) fail "rename_excl RC=$RC_MOVE: estado desconocido; staging conservado" ;;
esac
[ -e "$DESTINO" ] && [ ! -e "$STAGING" ] && [ ! -L "$STAGING" ] || fail "post-rename inconsistente"

# ==== 7. Inventario final ====
INV_FIN=$(mktemp /private/var/tmp/ot07_inv_fin.XXXXXX) || fail "mktemp inv fin"
ph inventory "$DESTINO" "$INV_FIN" > /dev/null || fail "inventario final"
ph compare-inv "$INV_ORIG" "$INV_FIN" > /dev/null || fail "destino != origen"
rm -f "$INV_ORIG" "$INV_ST" "$INV_FIN"
rmdir "$ST_PARENT" 2>/dev/null || true

# ==== 8. Protección C-5 (solo si modo=root; aquí NO se ejecuta en esta OT) ====
if [ "$MODO_PROTECCION" = root ]; then
  # PROPUESTA: acotada al árbol ya verificado. Requiere re-auditoría antes de activar.
  # sudo -n /usr/sbin/chown -R -h root:wheel "$DESTINO" || fail "chown"
  # sudo -n /bin/chmod -R go-w "$DESTINO" || fail "chmod"
  fail "MODO=root preparado pero NO_ACTIVO en v10r2r1; decidir y re-auditar antes"
fi

printf 'COLOCADO_VERIFICADO: %s\n' "$DESTINO"
printf 'C5_MODO: %s\n' "$MODO_PROTECCION"
printf 'PKG_SHA256_VERIFICADO: %s\n' "$PKG_SHA256"
exit 0
