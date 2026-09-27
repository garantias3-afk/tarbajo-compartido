#!/bin/bash
# OT07 v10 (entrega R1) — creation is destructive ONLY after the explicit confirmation below.
set -uo pipefail
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PYTHONDONTWRITEBYTECODE=1
umask 077
fail(){ echo "### FALLO: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail "Ejecutar manualmente con sudo cuando se autorice CP3."
DIR="$(cd "$(dirname "$0")" && pwd -P)" || fail "directorio del paquete"
(cd "$DIR" && shasum -a 256 -c SHA256SUMS.txt) || fail "integridad del paquete"
DEV="${1:?uso: CREAR_PEN_BOOTEO.sh /dev/diskN UUID}"
WANT_UUID="${2:?falta UUID}"
[ "$WANT_UUID" = 11111111-2222-4333-8444-555555555555 ] || fail "UUID no autorizado"
[[ "$DEV" =~ ^/dev/disk[0-9]+$ ]] || fail "exigir disco completo /dev/diskN"
PY=/usr/bin/python3
GUARD="$DIR/ot07_guard.py"
guard(){ "$PY" "$GUARD" "$@"; }
INSTALLER="/Applications/Install macOS Sonoma.app"
LOCK=/var/run/ot07-kingston.lock
mkdir "$LOCK" || fail "otro ejecutor o bloqueo pendiente: $LOCK; no borrar automaticamente"
CHILD=""
RUN=""
KEEP_LOCK=0
cleanup(){
  local rc=$?
  trap - EXIT
  trap '' INT TERM HUP
  local keep_lock=$KEEP_LOCK
  if [ -n "$CHILD" ]; then
    echo "Esperando al hijo propio $CHILD antes de cerrar; no liberar el turno."
    wait "$CHILD"; local child_rc=$?
    [ "$child_rc" != 127 ] || keep_lock=1
  fi
  [ -z "$RUN" ] || printf '%s\n' "$rc" > "$RUN/exit_code"
  if [ -n "$RUN" ] && [ -f "$RUN/build/process-ledger.json" ]; then
    "$PY" "$DIR/ot07_process.py" check "$RUN/build/process-ledger.json" || keep_lock=1
  fi
  if [ "$keep_lock" = 0 ]; then
    rmdir "$LOCK" || echo "No se pudo liberar $LOCK; inspeccionar antes de otra ejecucion." >&2
  else
    echo "BLOQUEO_CONSERVADO: hijo o ledger sin cierre confirmado; inspeccionar $RUN." >&2
  fi
  echo "OT07_TERMINADO rc=$rc evidencia=$RUN"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
run_child(){
  "$@" & CHILD=$!
  wait "$CHILD"; local rc=$?
  CHILD=""
  return "$rc"
}
RUN=$(mktemp -d /var/tmp/ot07_v10.XXXXXX) || fail "mktemp evidencia"
printf '%s\n' "$$" > "$RUN/executor.pid"
echo "== OT07 v10 R1 | PID=$$ | EVIDENCIA=$RUN =="
guard identity "$DEV" "$WANT_UUID" > "$RUN/identity.before.json" || fail "identidad inicial"
SNAP="$RUN/identity.before.json"
cat "$SNAP"

# Verify installer before any erase. Full source/version/signature checks are shared with CP1.
run_child /bin/bash "$DIR/descargar_sonoma.sh" --verify-only || fail "instalador no verificado"
BUILD_OUT="$RUN/build"
mkdir "$BUILD_OUT" || fail "directorio build"
OCLP_VERSION=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' /Applications/OpenCore-Patcher.app/Contents/Info.plist) || fail "version OCLP"
[ "$OCLP_VERSION" = 2.4.1 ] || fail "esta revision solo audita OCLP 2.4.1; no actualizar implicitamente"
run_child /bin/bash "$DIR/construir_efi.sh" "$BUILD_OUT" || fail "build fallo; pen intacto"
"$PY" "$DIR/ot07_process.py" check-build "$BUILD_OUT/process-ledger.json" || {
  KEEP_LOCK=1
  fail "constructor sin captura verificable; conservar bloqueo"
}
EFISRC="$BUILD_OUT/OpenCore-Build"
guard prepare "$EFISRC" "$RUN/config.oclp.original.plist" > "$RUN/config-policy.json" || fail "payload/config no validos; pen intacto"
guard manifest "$EFISRC" > "$RUN/payload.sha256.json" || fail "manifiesto payload; pen intacto"
NEED=$(guard need "$EFISRC") || fail "C3 preflight; pen intacto"
echo "C3 estimacion conservadora=$NEED bytes (incluye reserva). ESP futura aun no medida."
echo "BORRA SOLO $DEV: KINGSTON UUID=$WANT_UUID. No desconectar ni cambiar dispositivos."
printf 'Escribi CREAR-BOOTEO para continuar: '
read -r R || fail "sin confirmacion"
[ "$R" = CREAR-BOOTEO ] || fail "cancelado"

# Recheck all physical fields + UUID/name, after the potentially long build and confirmation.
guard verify "$EFISRC" "$RUN/payload.sha256.json" || fail "payload cambio antes del borrado"
guard identity "$DEV" "$WANT_UUID" > "$RUN/identity.final.json" || fail "identidad final"
cmp -s "$SNAP" "$RUN/identity.final.json" || fail "identidad cambio"
run_child /usr/sbin/diskutil eraseDisk JHFS+ InstallSonoma GPT "$DEV" || fail "eraseDisk"

# Derive identifiers and GPT UUIDs from this disk; never select volumes by name.
PAIR=$(guard partition "$SNAP" hfs) || fail "particion de datos"
read -r DATAPART DATA_UUID <<< "$PAIR"
PAIR=$(guard partition "$SNAP" efi) || fail "particion EFI"
read -r EFIPART EFI_UUID <<< "$PAIR"
guard bindings "$SNAP" "$DATAPART" "$DATA_UUID" "$EFIPART" "$EFI_UUID" > "$RUN/partitions.after_erase.tmp" &&
  mv "$RUN/partitions.after_erase.tmp" "$RUN/partitions.after_erase.json" || fail "registro GPT posterior al borrado"
MP=$(mktemp -d /var/tmp/ot07_efi.XXXXXX) || fail "mount point privado"
MP=$(cd "$MP" && pwd -P) || fail "mount point canonico"
guard bound "$SNAP" "$EFIPART" "$EFI_UUID" || fail "identidad EFI"
run_child /usr/sbin/diskutil mount -mountPoint "$MP" "/dev/$EFIPART" || fail "montar EFI"
ACTUAL=$(guard mountpoint "$SNAP" "$EFIPART" "$EFI_UUID") || fail "binding EFI"
[ "$ACTUAL" = "$MP" ] || fail "EFI no montada en el punto solicitado; no copiar"
guard capacity "$SNAP" "$EFIPART" "$EFI_UUID" "$NEED" || fail "C3 espacio real; pen ya borrado"
run_child /usr/sbin/diskutil unmount "/dev/$EFIPART" || fail "desmontaje EFI previo al instalador"

# C1: mount data only after validating parent disk and GPT UUID.
TARGET_VOL=$(guard mountpoint "$SNAP" "$DATAPART" "$DATA_UUID") || fail "binding datos"
if [ -z "$TARGET_VOL" ]; then
  guard bound "$SNAP" "$DATAPART" "$DATA_UUID" || fail "identidad datos"
  run_child /usr/sbin/diskutil mount "/dev/$DATAPART" || fail "montar datos"
fi
TARGET_VOL=$(guard mountpoint "$SNAP" "$DATAPART" "$DATA_UUID") || fail "montaje datos"
[ -n "$TARGET_VOL" ] || fail "sin volumen de datos"
run_child "$INSTALLER/Contents/Resources/createinstallmedia" --volume "$TARGET_VOL" --nointeraction || fail "createinstallmedia"

# C2: re-read after rename; each retry checks the same GPT partition on the same USB.
VOL=""
for t in $(seq 1 30); do
  VOL=$(guard mountpoint "$SNAP" "$DATAPART" "$DATA_UUID") || fail "identidad datos tras createinstallmedia"
  [ -z "$VOL" ] || break
  guard bound "$SNAP" "$DATAPART" "$DATA_UUID" || fail "datos cambiaron"
  run_child /usr/sbin/diskutil mount "/dev/$DATAPART" || true
  sleep 2
done
[ -n "$VOL" ] || fail "sin volumen instalador tras 30 intentos; pen ya borrado"

guard bound "$SNAP" "$EFIPART" "$EFI_UUID" || fail "EFI cambio"
run_child /usr/sbin/diskutil mount -mountPoint "$MP" "/dev/$EFIPART" || fail "montar EFI para copia"
ACTUAL=$(guard mountpoint "$SNAP" "$EFIPART" "$EFI_UUID") || fail "binding EFI para copia"
[ "$ACTUAL" = "$MP" ] || fail "punto EFI distinto; no copiar"
guard capacity "$SNAP" "$EFIPART" "$EFI_UUID" "$NEED" || fail "ESP sin espacio real suficiente"
guard verify "$EFISRC" "$RUN/payload.sha256.json" || fail "payload fuente cambio"
[ -n "$MP" ] && [ -d "$MP" ] || fail "mount point invalido antes de limpiar"
[ "$(guard mountpoint "$SNAP" "$EFIPART" "$EFI_UUID")" = "$MP" ] || fail "binding EFI cambio antes de limpiar"
# Remove stale fallback only inside the positively bound ESP, including v6 remnants.
rm -rf "$MP/EFI/BOOT" "$MP/EFI/OC" "$MP/System" "$MP/boot.efi" || fail "limpieza EFI"
mkdir -p "$MP/EFI" || fail "mkdir EFI"
run_child ditto --norsrc --noextattr --noacl "$EFISRC/EFI/OC" "$MP/EFI/OC" || fail "copia EFI/OC"
run_child ditto --norsrc --noextattr --noacl "$EFISRC/System" "$MP/System" || fail "copia System"
run_child cp "$EFISRC/boot.efi" "$MP/boot.efi" || fail "copia boot.efi"
# Native OCLP dual-DP layout. No direct OpenCore or bootstrap added at EFI/BOOT/CoreServices.
guard verify "$MP" "$RUN/payload.sha256.json" || fail "hashes de copia"
sync
guard bound "$SNAP" "$EFIPART" "$EFI_UUID" || fail "EFI cambio antes de desmontar"
run_child /usr/sbin/diskutil unmount "/dev/$EFIPART" || fail "desmontaje EFI; no declarar exito"
run_child /usr/sbin/diskutil mount readOnly -mountPoint "$MP" "/dev/$EFIPART" || fail "remontaje readonly"
ACTUAL=$(guard mountpoint "$SNAP" "$EFIPART" "$EFI_UUID") || fail "binding readback"
[ "$ACTUAL" = "$MP" ] || fail "punto readback distinto"
guard readonly "$SNAP" "$EFIPART" "$EFI_UUID" || fail "readback no es readonly"
guard verify "$MP" "$RUN/payload.sha256.json" || fail "hashes tras remontaje"
run_child /usr/sbin/diskutil unmount "/dev/$EFIPART" || fail "desmontaje final"
rmdir "$MP" || echo "AVISO: mount point desmontado no retirado: $MP" >&2
VOL=$(guard mountpoint "$SNAP" "$DATAPART" "$DATA_UUID") || fail "binding instalador final"
[ -n "$VOL" ] || fail "instalador desmontado"
guard installed "$VOL" || {
  guard diagnostic "$SNAP" "$DATAPART" "$DATA_UUID" > "$RUN/installed-diagnostico.json" || echo "Diagnostico no disponible; identidad incierta o error de lectura." >&2
  fail "instalador ausente/incompleto; revisar $RUN/installed-diagnostico.json"
}
echo "MEDIO_CREADO_INTEGRIDAD_VERIFICADA: $DEV"
echo "ARRANQUE_FISICO: NO_PROBADO. No iniciar el iMac de rescate como parte de esta OT."
echo "Conservar $RUN. La prueba fisica requiere su propio procedimiento de recuperacion."
