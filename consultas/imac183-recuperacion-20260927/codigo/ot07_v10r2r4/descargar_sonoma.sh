#!/bin/bash
# OT07 v9 — --verify-only never downloads. CP1 downloads only when manually invoked.
set -uo pipefail
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PYTHONDONTWRITEBYTECODE=1
umask 077
fail(){ echo "VEREDICTO: $*" >&2; exit 1; }
DIR="$(cd "$(dirname "$0")" && pwd -P)" || fail DIRECTORIO
(cd "$DIR" && shasum -a 256 -c SHA256SUMS.txt) || fail INTEGRIDAD_PAQUETE
if [ "${1:-}" = --verify-only ]; then
  /usr/bin/python3 "$DIR/verificar_instalador.py" || fail INSTALADOR_NO_VERIFICADO
  echo 'VEREDICTO: INSTALADOR_LISTO'; exit 0
fi
[ "$#" = 0 ] || fail "uso: descargar_sonoma.sh [--verify-only]"
if [ -d "/Applications/Install macOS Sonoma.app" ]; then
  /usr/bin/python3 "$DIR/verificar_instalador.py" || fail "INSTALADOR_EXISTENTE_INVALIDO; revisar manualmente, no sobrescribir"
  echo 'VEREDICTO: INSTALADOR_LISTO'; exit 0
fi
FREE=$(df -k /Applications | tail -1 | awk '{print $4}')
[[ "$FREE" =~ ^[0-9]+$ ]] && [ "$FREE" -ge 20971520 ] || fail SIN_ESPACIO
CATALOG=$(mktemp /var/tmp/ot07_catalog.XXXXXX) || fail MKTEMP
trap 'rm -f "$CATALOG"' EXIT
/usr/sbin/softwareupdate --list-full-installers > "$CATALOG" 2>&1 || fail LISTA_INSTALADORES
cat "$CATALOG"
VER=$(/usr/bin/python3 - "$CATALOG" <<'PY'
import re,sys
versions=[]
for line in open(sys.argv[1]):
    if re.search(r'beta|\bRC\b|seed|developer',line,re.I): continue
    m=re.search(r'Version:\s*(14\.[0-9]+(?:\.[0-9]+)?)(?=\s|,|$)',line)
    if m: versions.append(m[1])
if versions: print(max(versions,key=lambda v:tuple(map(int,v.split('.')))))
PY
) || fail PARSEO_CATALOGO
[ -n "$VER" ] || fail "SONOMA_NO_DISPONIBLE; obtener instalador Apple por via separada; sin fallback Mist sin privilegios"
/usr/sbin/softwareupdate --fetch-full-installer --full-installer-version "$VER" || fail DESCARGA_FALLO
/usr/bin/python3 "$DIR/verificar_instalador.py" || fail INSTALADOR_NO_VERIFICADO
echo 'VEREDICTO: INSTALADOR_LISTO'
