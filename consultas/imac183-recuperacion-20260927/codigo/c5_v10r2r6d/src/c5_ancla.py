#!/usr/bin/env python3
"""c5_ancla.py — ancla desde cadena C-1 (N5).

Regla: archivo+hash suministrados por operador NO acreditan procedencia.
Se exige evidencia autenticada de cadena C-1 + hash externo fijo + snapshot único.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Optional


class AnclaError(Exception):
    pass


def leer_snapshot_unico(path: str) -> bytes:
    """Lee los bytes UNA vez. El caller debe hashear y parsear ESTA instantánea."""
    with open(path, "rb") as f:
        return f.read()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def verificar_ancla(
    anchor_path: str,
    hash_externo_fijo: str,
    evidencia_c1: Optional[dict] = None,
) -> dict:
    """
    Devuelve:
      {inv, sha256, confianza: C-1|DELEGADA, snapshot_bytes, motivos}

    confianza C-1 solo si evidencia_c1 trae:
      cadena == 'C-1'
      hash_externo == hash_externo_fijo (y coincide con el snapshot)
      origen_autenticado (bool)  — evidencia autenticada, no archivo+hash del operador
      snapshot_unico (bool)
    """
    snapshot = leer_snapshot_unico(anchor_path)
    h = sha256_bytes(snapshot)
    motivos = []

    if h != hash_externo_fijo:
        raise AnclaError(f"hash snapshot {h} != externo fijo {hash_externo_fijo}")

    try:
        inv = json.loads(snapshot.decode("utf-8"))
    except Exception as e:
        raise AnclaError(f"ancla no parseable: {e}")

    confianza = "DELEGADA"
    if evidencia_c1:
        if evidencia_c1.get("cadena") != "C-1":
            motivos.append("cadena no es C-1")
        if evidencia_c1.get("hash_externo") != hash_externo_fijo:
            motivos.append("hash_externo de evidencia no coincide")
        if not evidencia_c1.get("origen_autenticado"):
            motivos.append("origen no autenticado (archivo+hash del operador no basta)")
        if not evidencia_c1.get("snapshot_unico", True):
            motivos.append("snapshot no es único")
        if not motivos:
            confianza = "C-1"
    else:
        motivos.append("sin evidencia C-1: confianza DELEGADA")

    return {
        "inv": inv,
        "sha256": h,
        "confianza": confianza,
        "snapshot_bytes": len(snapshot),
        "motivos": motivos,
    }


def exigir_c1_para_root(ancla: dict, modo: str) -> None:
    """En modo root, la ancla DELEGADA no basta (N5)."""
    if modo == "root" and ancla.get("confianza") != "C-1":
        raise AnclaError("modo root exige ancla C-1 autenticada; DELEGADA rechazada")


# ---------- H-R5-4: origen autenticado real ----------

def acreditar_origen_desde_manifiesto(
    hash_ancla: str,
    hashes_sellados: Optional[set] = None,
) -> bool:
    """origen_autenticado = el hash del ancla está registrado en un manifiesto
    sellado (r4/C-1). Archivo+hash del operador NO alcanza.
    """
    if not hashes_sellados:
        return False
    return hash_ancla.lower() in {h.lower() for h in hashes_sellados}


def construir_evidencia_c1(
    hash_externo: str,
    hashes_sellados: Optional[set] = None,
    cadena: str = "C-1",
) -> dict:
    origen_ok = acreditar_origen_desde_manifiesto(hash_externo, hashes_sellados)
    return {
        "cadena": cadena,
        "hash_externo": hash_externo,
        "origen_autenticado": origen_ok,
        "snapshot_unico": True,
        "requiere_c1": True,
    }


# ---------- H-R5-6.8: adaptador de formato del ancla C-1 real ----------

def adaptar_ancla_c1(inv_real: dict) -> dict:
    """Adapta el inventario del ancla C-1 real (`inv_extracted_app.json` /
    `tree_inventory.py`) al formato de `inventory_tree` de r5.

    Formato C-1 típico (tree_inventory):
      { "entries": [ {"relpath", "type", "size", "sha256", "target", ...} ],
        "root": ... }
    Formato r5 (inventory_tree):
      { "entries": { rel: {"type","size","sha256","target"} , rel+"/": {"type":"dir"} } }

    Fail-closed: formatos desconocidos lanzan.
    """
    if "entries" in inv_real and isinstance(inv_real["entries"], dict):
        return inv_real  # ya está en formato r5
    if "entries" in inv_real and isinstance(inv_real["entries"], list):
        out: dict = {"root": inv_real.get("root"), "entries": {}}
        for e in inv_real["entries"]:
            rel = e.get("relpath") or e.get("rel") or e.get("path")
            if not rel:
                raise AnclaError(f"entrada sin relpath: {e}")
            tipo = e.get("type") or e.get("kind") or ""
            if tipo in ("dir", "directory"):
                key = rel if rel.endswith("/") else rel + "/"
                out["entries"][key] = {"type": "dir"}
            elif tipo in ("symlink", "link"):
                out["entries"][rel] = {"type": "symlink", "target": e.get("target", "")}
            elif tipo in ("file", "reg", "regular"):
                out["entries"][rel] = {
                    "type": "file",
                    "size": e.get("size", 0),
                    "sha256": e.get("sha256") or e.get("hash", ""),
                }
            else:
                raise AnclaError(f"tipo desconocido en ancla C-1: {tipo!r} ({rel})")
        return out
    raise AnclaError("formato de ancla C-1 no reconocido")
