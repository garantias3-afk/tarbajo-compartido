#!/usr/bin/env python3
"""c5_bootstrap.py — bootstrap sin sudo de código mutable del uid (N0).

Identifica binario/intérprete/dependencias/hash y verifica TODO dentro de la
frontera ANTES de cualquier uso privilegiado. Prepara procedimiento H1;
NO lo ejecuta. Root queda cerrado hasta H1 explícita.

Prohibido:
  - sudo de python3/bash que importen código desde carpeta del uid
  - helper persistente, setuid instalado, sudoers
  - guardar contraseña
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

os.umask(0o077)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

# Identidades fijadas al candidato r5 (se recalculan al sellar)
PIN_HELPER_SRC = "src/c5_helper.c"
PIN_ORQUESTADOR = "src/c5_orquestador.py"
PIN_ANCLA = "src/c5_ancla.py"
PIN_ACL = "src/c5_acl.py"
PIN_INTERFAZ = "INTERFAZ_C5.json"

INTERPRETE = "/usr/bin/python3"
CLANG = "/usr/bin/clang"
SHELL_OK = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


def verificar_identidad(path: str) -> dict:
    st = os.lstat(path)
    return {
        "path": os.path.abspath(path),
        "sha256": sha256_file(path) if stat.S_ISREG(st.st_mode) else None,
        "mode": oct(st.st_mode),
        "uid": st.st_uid,
        "gid": st.st_gid,
        "dev": st.st_dev,
        "ino": st.st_ino,
        "nlink": st.st_nlink,
        "es_symlink": stat.S_ISLNK(st.st_mode),
    }


def inventario_bootstrap(raiz: str) -> dict:
    """Inventario de TODO lo que se ejecutaría privilegiado + dependencias."""
    raiz = os.path.abspath(raiz)
    criticos = [
        PIN_HELPER_SRC, PIN_ORQUESTADOR, PIN_ANCLA, PIN_ACL, PIN_INTERFAZ,
    ]
    items = []
    for rel in criticos:
        p = os.path.join(raiz, rel)
        if not os.path.exists(p):
            items.append({"rel": rel, "error": "AUSENTE"})
        else:
            d = verificar_identidad(p)
            d["rel"] = rel
            items.append(d)
    # intérprete y compilador (del sistema, no del uid)
    for p in (INTERPRETE, CLANG, "/usr/sbin/chown"):
        if os.path.exists(p):
            items.append(verificar_identidad(p))
    return {
        "raiz": raiz,
        "items": items,
        "python": sys.version,
        "euid": os.geteuid(),
        "nota": "ningún item del uid se ejecuta como root sin verificar dentro de frontera",
    }


def condiciones_H1(raiz: str) -> dict:
    """Checklist de precondiciones para pedir H1. NO ejecuta nada privilegiado."""
    inv = inventario_bootstrap(raiz)
    faltantes = [i for i in inv["items"] if i.get("error")]
    interprete_ok = os.path.isfile(INTERPRETE) and not os.path.islink(INTERPRETE)
    # el intérprete NO debe importar desde carpeta del uid
    return {
        "inventario": inv,
        "faltantes": faltantes,
        "interprete_sistema": interprete_ok,
        "sin_sudo_de_mutable": True,
        "fixture_H1": {
            "ruta_propuesta": os.path.join(raiz, "fixtures", "h1_fixture"),
            "max_bytes": 1024 * 1024,
            "operaciones": [
                "mkdir staging 0700",
                "copiar fixture <1MiB",
                "lchown(2) 0:0 via c5_helper protect",
                "chmod go-w via c5_helper",
                "ACL deny-write uid 501",
                "renamex_np RENAME_EXCL a destino propio",
                "verificar metadata",
                "rmdir staging",
            ],
            "uid_esperado": "0:0 tras protect",
            "acl_esperada": "deny write para uid 501",
            "limpieza": "rmdir staging; list-stale si falla; sin glob",
        },
        "residuos_posibles": [
            "staging ot07_c5_staging.* retenido si publicación aborta",
            "destino publicado NO se borra jamás en fallo",
        ],
        "listo_para_pedir_H1": len(faltantes) == 0 and interprete_ok,
    }


def main():
    raiz = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__)) + "/.."
    r = condiciones_H1(raiz)
    print(json.dumps(r, indent=2))
    return 0 if r["listo_para_pedir_H1"] else 2


if __name__ == "__main__":
    sys.exit(main())
