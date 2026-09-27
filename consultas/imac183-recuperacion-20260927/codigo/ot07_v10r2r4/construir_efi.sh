#!/bin/bash
# =====================================================================
# construir_efi.sh — construye la EFI de OpenCore para iMac18,3 y la CAPTURA
# antes de que OCLP la borre. Escribe solo salida/temporales; no borra discos.
#
# Hallazgo empirico (24/09): OCLP 2.4.1 empaquetado construye en un temporal
# aleatorio (/tmp/tmpXXXX/Build-Folder/OpenCore-Build) y lo BORRA al terminar.
# Por eso: esperar la linea "has been built at", PAUSAR OCLP (SIGSTOP), copiar,
# verificar, y recien entonces reanudarlo (SIGCONT).
#   bash construir_efi.sh <DIR_SALIDA>
# Deja <DIR_SALIDA>/OpenCore-Build (EFI + System) + manifiesto + veredicto.
# =====================================================================
set -uo pipefail
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PYTHONDONTWRITEBYTECODE=1
umask 077
DIR="$(cd "$(dirname "$0")" && pwd -P)" || exit 1
OUT="${1:?falta directorio de salida}"
OCLP="/Applications/OpenCore-Patcher.app/Contents/MacOS/OpenCore-Patcher"
IMAC="iMac18,3"
fail(){ echo "### FALLO: $*"; echo "VEREDICTO_EFI: FALLO"; exit 1; }
[ -x "$OCLP" ] || fail "no existe OCLP en $OCLP"
[ -e "$OUT/OpenCore-Build" ] && fail "$OUT/OpenCore-Build ya existe: usar un directorio nuevo"
mkdir -p "$OUT" || fail "no pude crear $OUT"
LOG="$OUT/oclp_build.log"; : > "$LOG"
echo "== CONSTRUIR EFI $IMAC — $(date) =="
echo "OCLP: $(defaults read /Applications/OpenCore-Patcher.app/Contents/Info.plist CFBundleShortVersionString 2>/dev/null)"

VERSION=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' /Applications/OpenCore-Patcher.app/Contents/Info.plist) || fail "version OCLP"
[ "$VERSION" = 2.4.1 ] || fail "solo OCLP 2.4.1 auditado"
export PYTHONUNBUFFERED=1
LEDGER="$OUT/process-ledger.json"
[ ! -e "$LEDGER" ] || fail "ledger previo: usar salida nueva"
"$OCLP" --build --model "$IMAC" >> "$LOG" 2>&1 &
PID=$!
echo "OCLP pid=$PID"
process(){ /usr/bin/python3 "$DIR/ot07_process.py" "$@"; }
thaw(){ [ ! -f "$LEDGER" ] || process thaw "$LEDGER"; }
cleanup(){
  local rc=$?
  trap - EXIT
  trap '' INT TERM HUP
  if ! thaw; then
    echo "REANUDACION_PENDIENTE: conservar $LEDGER y el bloqueo; requiere inspeccion." >&2
    exit 1
  fi
  echo "Esperando fin del hijo OCLP propio; una demora no libera el turno." >&2
  wait "$PID" 2>/dev/null || true
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
process init "$LEDGER" "$PID" "$$" || fail "identidad inicial de OCLP"
freeze(){ process freeze "$LEDGER"; }

# PROBE_LOOP_START
# Presupuesto de vueltas, no un plazo de reloj de 20 min. 24000*0.05s es solo el piso
# de sleep si cada vuelta no hace otro trabajo. alive no corre en cada vuelta.
# Agotar el sondeo no mata al hijo ni libera el lock del supervisor.
PROBE_ITERS=${OT07_PROBE_ITERS:-24000}
PROBE_ALIVE_EVERY=${OT07_PROBE_ALIVE_EVERY:-20}
PROBE_SLEEP=${OT07_PROBE_SLEEP:-0.05}
SRC=""
for i in $(seq 1 "$PROBE_ITERS"); do
  if [ -z "$SRC" ]; then
    SRC=$(awk '/has been built at:/{
      if (match($0,/\/[^[:space:]]+Build/)) { print substr($0,RSTART,RLENGTH); exit }
      getline; gsub(/^[ \t]+|[ \t]+$/,""); if ($0 ~ /^\//) { print; exit } }' "$LOG")
  fi
  # aceptar solo cuando el build esta realmente en disco (evita capturar el marcador)
  PRODUCT="System/Library/CoreServices/.diagnostics/Drivers/HardwareDrivers/Product.efi"
  if [ -n "$SRC" ] && [ -f "$SRC/EFI/OC/OpenCore.efi" ] && [ -f "$SRC/boot.efi" ] && [ -f "$SRC/$PRODUCT" ]; then break; fi
  SRC=""   # si el texto aparecio pero el dir aun no, seguir esperando
  if [ "$i" -eq 1 ] || [ $((i % PROBE_ALIVE_EVERY)) -eq 0 ]; then
    process alive "$LEDGER" || break
  fi
  sleep "$PROBE_SLEEP"
done
if [ -z "$SRC" ]; then
  echo "SONDEO_AGOTADO: no matar al hijo ni liberar el lock" >&2
  wait "$PID" || true
  fail "sondeo agotado; captura no aceptada"
fi
# la ruta debe ser un temporal seguro y contener OpenCore-Build
case "$SRC" in
  /tmp/*OpenCore-Build|/private/tmp/*OpenCore-Build|/var/folders/*OpenCore-Build|/private/var/folders/*OpenCore-Build) : ;;
  *) wait "$PID"; fail "ruta de build no valida o no capturable: '$SRC' (ver $LOG)";;
esac
[[ "$SRC" == *".."* ]] && fail "ruta con .. rechazada"
# La identidad estable registrada se revalida en freeze; exec puede cambiar comm.
process alive "$LEDGER" || fail "identidad OCLP perdida antes de capturar"
# PROBE_LOOP_END
freeze || fail "no se confirmo OCLP detenido; pen intacto"
echo "OCLP pausado. Build en: $SRC"
reanudar(){ thaw || fail "reanudar procesos registrados; conservar ledger"; }
if [ ! -d "$SRC/EFI/OC" ]; then reanudar; wait "$PID"; fail "el build desaparecio antes de copiar: $SRC"; fi

ditto "$SRC" "$OUT/OpenCore-Build" || { reanudar; wait "$PID"; fail "ditto fallo"; }
( cd "$SRC" && find . -type f -print0 | xargs -0 shasum -a 256 ) | sort > "$OUT/manif_origen.sha256" \
  || { reanudar; wait "$PID"; fail "manifiesto origen fallo"; }
( cd "$OUT/OpenCore-Build" && find . -type f -print0 | xargs -0 shasum -a 256 ) | sort > "$OUT/manif_copia.sha256" \
  || { reanudar; wait "$PID"; fail "manifiesto copia fallo"; }
reanudar
wait "$PID"; RC=$?
trap - EXIT INT TERM HUP
echo "OCLP exit=$RC"
[ "$RC" = 0 ] || fail "OCLP salio con $RC"
diff -u "$OUT/manif_origen.sha256" "$OUT/manif_copia.sha256" > "$OUT/manif.diff" || fail "la copia difiere del build (ver manif.diff)"
N=$(wc -l < "$OUT/manif_copia.sha256" | xargs)
[ "$N" -ge 100 ] || fail "manifiesto sospechosamente chico ($N archivos, se esperan ~150)"

# verificacion estructural
B="$OUT/OpenCore-Build"
for f in "EFI/OC/OpenCore.efi" "EFI/OC/config.plist"; do
  [ -f "$B/$f" ] || fail "falta $f en el build"
done
# OCLP 2.4.1 firmware.py dual-DP: diags.efi -> boot.efi raiz;
# bootstrap previo -> Product.efi -> EFI/OC/OpenCore.efi.
# Se conserva el layout fuente: sin EFI/BOOT ni CoreServices/boot.efi.
# La captura y sus hashes NO prueban el picker ni un arranque fisico.
[ -f "$B/boot.efi" ] || fail "falta boot.efi en la raiz (loader iMac18,3)"
PRODUCT="System/Library/CoreServices/.diagnostics/Drivers/HardwareDrivers/Product.efi"
[ -f "$B/$PRODUCT" ] || fail "falta $PRODUCT (cadena dual-DP de iMac18,3)"
LOADER="boot.efi + $PRODUCT"
python3 - "$B/EFI/OC/config.plist" "$IMAC" <<'PY' || fail "config.plist no corresponde a iMac18,3"
import plistlib, sys
d = plistlib.load(open(sys.argv[1], 'rb')); want = sys.argv[2]
rev = d.get('#Revision', {})
model = str(rev.get('Original-Model','')) if isinstance(rev, dict) else ''
lp = d.get('Misc', {}).get('Boot', {}).get('LauncherPath', '')
print(f"  Original-Model={model!r} LauncherPath={lp!r}")
# igualdad ESTRICTA del modelo (no substring) y LauncherPath al boot.efi raiz
sys.exit(0 if (model == want and lp == '\\boot.efi') else 1)
PY
echo "  estructura del build:"; ls "$B" | sed 's/^/    /'
echo "  loader: $LOADER"
echo "  archivos: $N (manifiesto origen == copia)"
echo "VEREDICTO_EFI: OK  ->  $B"
