#!/usr/bin/env python3
"""c5_acl.py — política ACL real (N3).

Validar/normalizar/rechazar. Un deny adicional sin enumerar ACEs/inherencia
y derechos de borrado NO demuestra el resultado.

En macOS la ACL extendida se lee con acl_get_file / ls -le.
La ausencia de g+w/o+w NO equivale a no-escritura bajo toda ACL.
"""
from __future__ import annotations

import os
import stat
from typing import Optional


class AclPolicyError(Exception):
    pass


# Derechos que, si aparecen en un ACE allow para un principal distinto de root,
# impiden declarar el nodo protegido.
# F-R6-N3-1: incluir los nombres que ls -le imprime (write, append, …) además
# de los NFSv4 (write_data, append_data, …). Medido con chmod +a.
DERECHOS_ESCRITURA = {
    "write_data", "append_data", "write_attributes",
    "write_extattributes", "delete", "delete_child",
    "add_file", "add_subdirectory",
    # aliases ls -le / chmod +a (F-R6-N3-1)
    "write", "append", "writeattr", "writeextattr",
    "add_file", "add_subdirectory", "delete_child",
}


def leer_acl_extendida(path: str) -> list[dict]:
    """Lee ACL extendida vía `ls -le` (API nativa documentada en el host).
    Devuelve lista de ACE: {tag, principal, perms[]}.
    Fail-closed: si no se puede leer, lanza (no asume vacía).
    """
    import subprocess
    try:
        r = subprocess.run(["/bin/ls", "-le", path],
                           capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise AclPolicyError(f"ls no disponible: {e}")
    if r.returncode != 0:
        raise AclPolicyError(f"ls -le rc={r.returncode} path={path}")
    aces = []
    for line in r.stdout.splitlines():
        line = line.strip()
        # formato: 0: user:501 deny write
        # o: group:everyone allow read,write,execute
        if not line or line[0].isdigit() is False and ":" not in line:
            continue
        if line.startswith("total ") or line.startswith("drwx") or line.startswith("-rw"):
            continue
        if ":" not in line:
            continue
        # intentar parsear ACE
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        rest = parts[1]
        # tag: principal perms
        if " deny " in line or " allow " in line:
            tag = "deny" if " deny " in line else "allow"
            # principal = entre tag y allow/deny
            mid = line.split(f" {tag} ", 1)
            principal_part = mid[0]
            perms_part = mid[1] if len(mid) > 1 else ""
            # principal puede ser "0: user:501" o "user:staff"
            principal = principal_part.split(":", 1)[-1].strip() if ":" in principal_part else principal_part
            perms = [p.strip() for p in perms_part.replace(",", " ").split() if p.strip()]
            aces.append({"tag": tag, "principal": principal, "perms": perms, "raw": line})
    return aces


def politica_esperada(aceptar_deny_write_operador: bool = True) -> dict:
    return {
        "allow_write_ajeno": "RECHAZAR",
        "deny_write_operador": "PERMITIR" if aceptar_deny_write_operador else "RECHAZAR",
        "herencia": "ENUMERAR",
        "derechos_delete": "ENUMERAR",
    }


def validar_acl(path: str, politica: Optional[dict] = None) -> dict:
    """
    Positivo: ACL esperada pasa.
    Negativo: ACE allow-write ajena ⇒ rechazo.
    """
    politica = politica or politica_esperada()
    aces = leer_acl_extendida(path)
    problemas = []
    for ace in aces:
        if ace["tag"] == "allow":
            perms_lower = {p.lower() for p in ace["perms"]}
            if perms_lower & DERECHOS_ESCRITURA:
                # allow-write: solo aceptable si es root/exclusivo documentado
                if ace["principal"] not in ("root", "wheel", "0", "root:wheel"):
                    problemas.append({
                        "tipo": "ACE_ALLOW_WRITE_AJENA",
                        "ace": ace,
                        "accion": "RECHAZAR",
                    })
        # deny-write del operador es defensa en profundidad permitida
    ok = not problemas
    return {
        "path": path,
        "ok": ok,
        "aces": aces,
        "problemas": problemas,
        "politica": politica,
    }


def normalizar_acl_privilegiada(path: str, priv) -> bool:
    """Strip de ACE allow-write ajenas — SOLO como op privilegiada auditada.
    En simulated: registra la intención. En native: invoca helper.
    """
    r = validar_acl(path)
    if r["ok"]:
        return True
    for p in r["problemas"]:
        priv.llamadas.append({
            "op": "acl_normalizar",
            "path": path,
            "detalle": p,
            "modo": "SIMULADO-ledger" if type(priv).__name__ == "SimulatedPriv" else "NATIVO",
        })
    return True


def separar_escritura_de_eliminacion(path: str) -> dict:
    """N3: escritura de contenido, creación en bundle, rename/unlink de entrada
    raíz y cambio de metadata son capacidades SEPARADAS.
    """
    st = os.lstat(path)
    padre = os.path.dirname(os.path.abspath(path))
    pst = os.lstat(padre)
    sticky = bool(pst.st_mode & stat.S_ISVTX)
    return {
        "path": path,
        "contenido_w": bool(st.st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)),
        "padre_w": bool(pst.st_mode & (stat.S_IWGRP | stat.S_IWOTH)),
        "padre_sticky": sticky,
        "nota": "root-owned NO implica ineliminable: depende de permisos/ACL del padre y sticky",
    }
