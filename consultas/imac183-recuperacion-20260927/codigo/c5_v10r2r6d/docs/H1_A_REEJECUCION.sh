#!/bin/bash
# H1 sección A — RE-EJECUCIÓN (plantilla r6c). Operador único: MIMO.
# Protocolo: abortar al PRIMER RC≠0. Nada se publica tras un fallo.
# C5_AUTH_BASE exportado para lecturas del destino publicado (D3).
set -u
umask 077
export PYTHONDONTWRITEBYTECODE=1

R6C="${R6C:-/Users/OPERADOR/Documents/Codex/2026-09-27/pe/outputs/OT07_REVISION_v10r2r6c_MIMO}"
H1="${H1:-/Users/OPERADOR/Documents/Codex/2026-09-27/pe/outputs/RUN.20260927T131419Z.C5IMAC1/h1_mimo_re}"
HELPER="$R6C/build/c5_helper"
# HASH se fija al sellar H1-bis; si difiere, abortar
HASH_ESPERADO="${HASH_ESPERADO:-3bb1b3b5c38f57d25050b104f02d4494b11131b8bdd05986f78c0d091077a66d}"
LOG="$H1/evidencia/H1_A_RE.log"
export C5_AUTH_BASE="$H1"

mkdir -p "$H1/ot07_c5_staging.h1base" "$H1/evidencia"
chmod 700 "$H1" "$H1/ot07_c5_staging.h1base" "$H1/evidencia"

abortar() {
  echo "ABORT: $*" | tee -a "$LOG"
  echo "=== H1_A_RE ABORTADO $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"
  exit 1
}

msudo() {
  local H
  H=$(shasum -a 256 "$HELPER" | awk '{print $1}')
  echo "[hash-pre-sudo] $H" | tee -a "$LOG"
  [ "$H" = "$HASH_ESPERADO" ] || abortar "hash binario $H != $HASH_ESPERADO"
  sudo -A "$HELPER" "$@" >>"$LOG" 2>&1
  local rc=$?
  echo "[sudo] $HELPER $* => RC=$rc" | tee -a "$LOG"
  [ $rc -eq 0 ] || abortar "RC=$rc en: $HELPER $*"
  return 0
}

echo "=== H1_A_RE $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"
echo "C5_AUTH_BASE=$C5_AUTH_BASE" | tee -a "$LOG"

# --- fixture con modos D2: dirs 0755 / archivos 0644 ---
echo "--- fixture (umask 022 solo aquí) ---" | tee -a "$LOG"
FIX="$H1/fixture"
rm -rf "$FIX"
( umask 022
  mkdir -p "$FIX/sub"
  printf 'hello c5 h1 re\n' > "$FIX/a.txt"
  printf 'world\n' > "$FIX/sub/b.bin"
  ln -s a.txt "$FIX/link"
  chmod 755 "$FIX" "$FIX/sub"
  chmod 644 "$FIX/a.txt" "$FIX/sub/b.bin"
)
ls -la "$FIX" "$FIX/sub" | tee -a "$LOG"

python3 -B - <<PY | tee -a "$LOG"
import sys, json, hashlib
from pathlib import Path
sys.path.insert(0, "$R6C/src")
import c5_orquestador as O
inv = O.inventory_tree("$FIX")
Path("$H1/ancla.json").write_text(json.dumps(inv, sort_keys=True))
print("ancla_sha256=", hashlib.sha256(Path("$H1/ancla.json").read_bytes()).hexdigest())
import os
st = os.lstat("$FIX/a.txt"); print(f"pin a.txt dev={st.st_dev} ino={st.st_ino} mode={oct(st.st_mode)}")
# fd del origen conservado (se reabre en paso 9, pero se documenta)
fd = os.open("$FIX/a.txt", os.O_WRONLY | os.O_APPEND)
print(f"fd_origen_abierto fd={fd}")
os.close(fd)
PY

# --- paso 3: mkdir-staging ---
echo "--- paso 3 mkdir-staging ---" | tee -a "$LOG"
msudo mkdir-staging "$H1/ot07_c5_staging.h1base"
PARENT=$(ls -d "$H1/ot07_c5_staging.h1base"/ot07_c5_staging.* 2>/dev/null | tail -1)
HOJA="$PARENT/leaf"
echo "staging_parent=$PARENT" | tee -a "$LOG"
echo "staging_leaf=$HOJA" | tee -a "$LOG"

# --- paso 4: copy-tree (D1: dentro de la hoja) ---
echo "--- paso 4 copy-tree ---" | tee -a "$LOG"
msudo copy-tree "$FIX" "$HOJA"
ls -laR "$HOJA" 2>&1 | tee -a "$LOG"

# --- paso 5: N2 como uid 501 ---
echo "--- paso 5 N2 ---" | tee -a "$LOG"
python3 -B - <<PY 2>&1 | tee -a "$LOG"
import os
hoja = "$HOJA"
def probe(label, fn):
    try:
        fn(); print(f"{label}=INESPERADO_OK")
    except OSError as e:
        print(f"{label}=FALLA_OK errno={e.errno} ({e.strerror})")
probe("N2_OPEN_WRONLY", lambda: os.close(os.open(os.path.join(hoja,"a.txt"), os.O_WRONLY)))
probe("N2_OPEN_RDWR", lambda: os.close(os.open(os.path.join(hoja,"a.txt"), os.O_RDWR)))
probe("N2_RENAME_HOJA", lambda: os.rename(hoja, hoja+".x"))
probe("N2_UNLINK_HOJA", lambda: os.unlink(hoja))
probe("N2_RMDIR_HOJA", lambda: os.rmdir(hoja))
# N2 a nivel ARCHIVO (D1 ya copió contenido)
probe("N2_OPEN_WRONLY_A", lambda: os.close(os.open(os.path.join(hoja,"a.txt"), os.O_WRONLY)))
st = os.lstat(hoja); print(f"hoja_pin dev={st.st_dev} ino={st.st_ino} mode={oct(st.st_mode)} uid={st.st_uid}")
for p in ["a.txt","sub","sub/b.bin","link"]:
    st = os.lstat(os.path.join(hoja,p))
    print(f"pin {p} dev={st.st_dev} ino={st.st_ino} mode={oct(st.st_mode)} uid={st.st_uid} gid={st.st_gid}")
PY

# --- paso 6: protect ---
echo "--- paso 6 protect ---" | tee -a "$LOG"
msudo protect "$HOJA"

# --- paso 7: verify + ls -le ---
# R6C-1: la hoja ya lleva el modo del origen menos go-w. El PADRE staging
# sigue 0700 root:0 ⇒ verify del staging como uid 501 puede fallar por
# denegación de recorrido. La verificación uid 501 del ÁRBOL PUBLICADO se
# hace en el paso 8b con C5_AUTH_BASE. Aquí se registra verify root-side.
echo "--- paso 7 verify staging (root-side por padre 0700) + ls -le ---" | tee -a "$LOG"
set +e
sudo -A "$HELPER" verify "$HOJA" 2>&1 | tee -a "$LOG"
echo "verify_staging_root_RC=$?" | tee -a "$LOG"
"$HELPER" verify "$HOJA" 2>&1 | tee -a "$LOG"
echo "verify_staging_uid501_RC=$? (puede ser 13 por padre 0700)" | tee -a "$LOG"
ls -la "$HOJA" "$HOJA/sub" 2>&1 | tee -a "$LOG"
set -e

# --- paso 8: publish ---
echo "--- paso 8 publish ---" | tee -a "$LOG"
msudo publish "$HOJA" "$H1/h1_destino"
python3 -B - <<PY 2>&1 | tee -a "$LOG"
import os
for p in ["h1_destino","h1_destino/a.txt","h1_destino/sub/b.bin","h1_destino/link"]:
    st = os.lstat(os.path.join("$H1", p))
    print(f"pin {p} dev={st.st_dev} ino={st.st_ino} mode={oct(st.st_mode)} uid={st.st_uid} gid={st.st_gid}")
PY

# --- paso 8b: verify + ls -le del PUBLICADO como uid 501 (D2 + R6C-1) ---
echo "--- paso 8b verify/ls publicado uid 501 (C5_AUTH_BASE) ---" | tee -a "$LOG"
export C5_AUTH_BASE="$H1"
"$HELPER" verify "$H1/h1_destino" 2>&1 | tee -a "$LOG"
echo "verify_publicado_uid501_RC=$?" | tee -a "$LOG"
ls -le "$H1/h1_destino" 2>&1 | tee -a "$LOG"
ls -le "$H1/h1_destino/a.txt" 2>&1 | tee -a "$LOG"
ls -la "$H1/h1_destino" "$H1/h1_destino/sub" 2>&1 | tee -a "$LOG"

# --- paso 9: fd origen + N7 + EEXIST ---
echo "--- paso 9 fd origen + open publicado ---" | tee -a "$LOG"
python3 -B - <<PY 2>&1 | tee -a "$LOG"
import os, hashlib
fd = os.open("$FIX/a.txt", os.O_WRONLY | os.O_APPEND)
n = os.write(fd, b"ATACANTE-FD-ORIGEN\n")
os.close(fd)
print(f"fd_origen_write_bytes={n}")
h_pub = hashlib.sha256(open("$H1/h1_destino/a.txt","rb").read()).hexdigest()
h_orig = hashlib.sha256(open("$FIX/a.txt","rb").read()).hexdigest()
print(f"publicado_sha256={h_pub}")
print(f"origen_sha256={h_orig}")
print(f"publicado_inalterado_por_fd_origen={h_pub != h_orig}")
for flags, name in [(os.O_WRONLY,"O_WRONLY"), (os.O_RDWR,"O_RDWR")]:
    try:
        os.close(os.open("$H1/h1_destino/a.txt", flags)); print(f"PUB_OPEN_{name}=INESPERADO_OK")
    except OSError as e:
        print(f"PUB_OPEN_{name}=FALLA_OK errno={e.errno}")
PY

echo "--- paso 9b EEXIST ---" | tee -a "$LOG"
mkdir -p "$H1/h1_destino_eexist"
echo "ganador" > "$H1/h1_destino_eexist/ganador.txt"
# EEXIST: el publish DEBE fallar con RC≠0 → abort según protocolo, pero el
# oráculo N6 lo espera. Se ejecuta FUERA del flujo principal y se registra.
set +e
msudo_publish() {
  local H
  H=$(shasum -a 256 "$HELPER" | awk '{print $1}')
  echo "[hash-pre-sudo] $H" | tee -a "$LOG"
  [ "$H" = "$HASH_ESPERADO" ] || abortar "hash"
  sudo -A "$HELPER" "$@" >>"$LOG" 2>&1
  echo "[sudo] $HELPER $* => RC=$?" | tee -a "$LOG"
}
msudo mkdir-staging "$H1/ot07_c5_staging.h1base_eexist"
PARENT2=$(ls -d "$H1/ot07_c5_staging.h1base_eexist"/ot07_c5_staging.* 2>/dev/null | tail -1)
HOJA2="$PARENT2/leaf"
msudo copy-tree "$FIX" "$HOJA2"
msudo protect "$HOJA2"
msudo_publish publish "$HOJA2" "$H1/h1_destino_eexist"
test -f "$H1/h1_destino_eexist/ganador.txt" && echo "GANADOR_CONSERVADO=SI" | tee -a "$LOG"
set -e

# --- paso 10: cleanup ---
echo "--- paso 10 cleanup ---" | tee -a "$LOG"
"$HELPER" cleanup "$PARENT" 2>&1 | tee -a "$LOG"
echo "cleanup_RC=$?" | tee -a "$LOG"
python3 -B - <<PY 2>&1 | tee -a "$LOG"
import sys
sys.path.insert(0, "$R6C/src")
import c5_orquestador as O
print("list-stale:", O.list_stale("$H1/ot07_c5_staging.h1base"))
print("list-stale_eexist:", O.list_stale("$H1/ot07_c5_staging.h1base_eexist"))
PY

echo "=== FIN H1_A_RE $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"
