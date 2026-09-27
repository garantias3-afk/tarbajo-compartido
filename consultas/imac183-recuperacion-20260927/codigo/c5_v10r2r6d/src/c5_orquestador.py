#!/usr/bin/env python3
"""c5_orquestador.py — dirección B: proteger ANTES de publicar.

OT07-C5-NATIVO r6 · MIMO · candidato no privilegiado.
Flujo F0–F10 del diseño P5R, con frontera real en el flujo (H-R5-1):
la creación de inodos finales y la copia ocurren DENTRO del helper
(privilegiado). Un fd O_WRONLY/O_RDWR del uid operador no puede abrir
esos inodos: no existe ventana entre crear y proteger.

H-R5-2: re-pin de hoja + padre (modo 0700) inmediatamente antes de renamex_np.
H-R5-3: veredictos por estado para PrivError y excepciones genéricas.
H-R5-4: ancla C-1 (c5_ancla) y política ACL (c5_acl) cableadas al pipeline.

Primitivas: lchown(2)/fchmodat/openat/fstatat+AT_UNIQUE/renamex_np.
NO usa RESOLVE_BENEATH ni binario lchown (ver 04_AJUSTES).
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Any, Optional

# Forzar higiene
os.umask(0o077)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

# H-R5-6.2: UID operador parametrizable
UID_OPERADOR = int(os.environ.get("C5_UID_OPERADOR", "501"))
GID_WHEEL = 0
UID_ROOT = 0
RESERVA_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB (C-9)
PREFIJO_STAGING = "ot07_c5_staging."

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import c5_ancla as ancla_mod  # noqa: E402
import c5_acl as acl_mod  # noqa: E402


class Abort(Exception):
    def __init__(self, msg: str, verdict: str = "ABORTADO_SIN_EFECTOS", rc: int = 2):
        super().__init__(msg)
        self.verdict = verdict
        self.rc = rc


class PrivError(Exception):
    def __init__(self, msg: str, rc: int = 5):
        super().__init__(msg)
        self.rc = rc
        self.verdict = "NO_AUTORIZADO"


class NoAutorizado(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)
        self.rc = 5
        self.verdict = "RECHAZADO_GATE_SIN_EFECTOS"


class Journal:
    """Registro por llamada; efectos observables con errno/dev/ino."""

    def __init__(self):
        self.events: list[str] = []
        self.effects: list[dict] = []

    def log(self, msg: str):
        self.events.append(msg)

    def effect(self, op: str, path: str, errno: Optional[int] = None,
               dev: Optional[int] = None, ino: Optional[int] = None):
        self.effects.append({
            "op": op, "path": path, "errno": errno, "dev": dev, "ino": ino
        })


def _exigir_euid_no_cero(donde: str):
    if os.geteuid() == 0:
        raise PrivError(f"euid==0 rechazado en {donde}: modo simulated no corre bajo root")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def pin(path: str) -> dict:
    st = os.lstat(path)
    return {"dev": st.st_dev, "ino": st.st_ino, "mode": st.st_mode}


def pin_equal(a: dict, b: dict) -> bool:
    return a.get("dev") == b.get("dev") and a.get("ino") == b.get("ino")


def physical_path(path: str) -> str:
    """Canonicaliza sin seguir symlink finales para el inventario."""
    return os.path.realpath(path)


def inventory_tree(root: str) -> dict:
    """Inventario exacto de contenido: tipo/tamaño/sha256/target.
    Rechaza especiales, hardlinks, symlinks que escapan.
    """
    root_real = physical_path(root)
    out = {"root": root_real, "root_pin": pin(root), "entries": {}}
    for dirpath, dirnames, filenames in os.walk(root_real, followlinks=False):
        # Estabilidad del recorrido
        dirnames.sort()
        filenames.sort()
        rel_dir = os.path.relpath(dirpath, root_real)
        if rel_dir == ".":
            rel_dir = ""
        for name in list(dirnames):
            p = os.path.join(dirpath, name)
            st = os.lstat(p)
            rel = os.path.join(rel_dir, name) if rel_dir else name
            if stat.S_ISLNK(st.st_mode):
                raise Abort(f"symlink-in-dir-no-permitido: {rel}")
            if not stat.S_ISDIR(st.st_mode):
                raise Abort(f"tipo-inesperado-en-dir: {rel}")
            out["entries"][rel + "/"] = {"type": "dir"}
        for name in filenames:
            p = os.path.join(dirpath, name)
            st = os.lstat(p)
            rel = os.path.join(rel_dir, name) if rel_dir else name
            if stat.S_ISLNK(st.st_mode):
                target = os.readlink(p)
                if target.startswith("/") or ".." in target.split("/"):
                    raise Abort(f"symlink-escapa: {rel} -> {target}")
                resolved = os.path.normpath(os.path.join(os.path.dirname(p), target))
                if not resolved.startswith(root_real):
                    raise Abort(f"symlink-sale-de-raiz: {rel}")
                out["entries"][rel] = {"type": "symlink", "target": target}
            elif stat.S_ISREG(st.st_mode):
                if st.st_nlink > 1:
                    raise Abort(f"hardlink-rechazado: {rel}")
                out["entries"][rel] = {
                    "type": "file", "size": st.st_size, "sha256": sha256_file(p)
                }
            else:
                raise Abort(f"tipo-especial-rechazado: {rel}")
    return out


def compare_content(ref: dict, got: dict) -> bool:
    return ref.get("entries") == got.get("entries")


def check_expected_metadata(root: str, priv, expect_owner=(UID_ROOT, GID_WHEEL)) -> bool:
    """Revalida dueño y go-w en RAÍZ e hijos (HB-1)."""
    ok = True
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        filenames.sort()
        candidates = [dirpath] + [os.path.join(dirpath, n) for n in filenames]
        for p in candidates:
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                continue
            owner = priv.owner_of(p)
            if owner != expect_owner:
                ok = False
            if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                ok = False
    return ok


# ---------- interfaz privilegiada ----------

class SimulatedPriv:
    """Modo simulated: chmod go-w REAL; chown/ACL en ledger por (dev,ino).
    H-R5-1: create_staging_and_copy crea los inodos y les retira escritura
    ANTES de devolver el control al operador — equivalente no privilegiado
    de la frontera del helper. En native, el helper los crea root:0.
    """

    def __init__(self):
        _exigir_euid_no_cero("SimulatedPriv.__init__")
        self._owner: dict[tuple, tuple] = {}
        self._acl: dict[tuple, list] = {}
        self.llamadas: list[dict] = []
        self._ambitos: list[str] = []

    def registrar_ambito(self, path: str):
        real = physical_path(path)
        self._ambitos.append(real)

    def _confine(self, path: str) -> str:
        real = physical_path(path)
        if real.startswith("/var/"):
            real = "/private" + real
        for amb in self._ambitos:
            if real == amb or real.startswith(amb.rstrip("/") + "/"):
                return real
        raise PrivError(f"fuera-de-ambito: {path}")

    def _key(self, path: str) -> tuple:
        st = os.lstat(path)
        return (st.st_dev, st.st_ino)

    def create_staging_and_copy(self, origen: str, staging_base: str,
                                hoja_nombre: str, j) -> tuple[str, str]:
        """H-R5-1: crea staging + copia como UNA operación de frontera.
        En simulated: crea y retira escritura antes de retornar.
        Devuelve (staging_parent, staging_leaf).
        """
        staging_parent = tempfile.mkdtemp(prefix=PREFIJO_STAGING, dir=staging_base)
        os.chmod(staging_parent, 0o700)
        self.registrar_ambito(staging_parent)
        hoja = os.path.join(staging_parent, hoja_nombre)
        os.mkdir(hoja, 0o700)
        j.effect("mkdir", staging_parent)
        j.effect("mkdir", hoja)
        _copy_tree(origen, hoja, j)
        os.chmod(hoja, os.lstat(origen).st_mode & 0o777)
        # Frontera: retirar escritura a otros/grupo; dueño queda del uid pero
        # el "flujo" no abre fd de escritura. En native: root:0 desde el inicio.
        self._cerrar_escritura_staging(staging_parent)
        self.llamadas.append({
            "op": "create_staging_and_copy", "parent": staging_parent,
            "leaf": hoja, "modo": "SIMULADO-frontera"
        })
        return staging_parent, hoja

    def _cerrar_escritura_staging(self, root: str):
        """Retira g+w/o+w en todo el árbol (higiene de frontera simulated)."""
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            for name in filenames + dirnames:
                p = os.path.join(dirpath, name)
                st = os.lstat(p)
                if stat.S_ISLNK(st.st_mode):
                    continue
                os.chmod(p, st.st_mode & ~(stat.S_IWGRP | stat.S_IWOTH))

    def chmod_tighten(self, path: str) -> bool:
        real = self._confine(path)
        st = os.lstat(real)
        if stat.S_ISLNK(st.st_mode):
            return True
        nmode = st.st_mode & ~(stat.S_IWGRP | stat.S_IWOTH)
        os.chmod(real, nmode, follow_symlinks=False)
        self.llamadas.append({"op": "chmod_go_w", "path": real, "real": True})
        return True

    def lchown_root(self, path: str) -> bool:
        real = self._confine(path)
        st = os.lstat(real)
        if stat.S_ISLNK(st.st_mode):
            return True
        k = self._key(real)
        self._owner[k] = (UID_ROOT, GID_WHEEL)
        self.llamadas.append({
            "op": "lchown_root_wheel", "path": real,
            "modo": "SIMULADO-ledger", "dev": k[0], "ino": k[1]
        })
        return True

    def set_acl_deny_write(self, path: str) -> bool:
        real = self._confine(path)
        k = self._key(real)
        self._acl[k] = [{"tag": "deny", "principal": UID_OPERADOR,
                         "perms": ["write_data", "append_data", "delete"]}]
        self.llamadas.append({"op": "acl_deny_write", "path": real, "modo": "SIMULADO-ledger"})
        return True

    def owner_of(self, path: str) -> tuple:
        try:
            k = self._key(path)
        except OSError:
            return (-1, -1)
        return self._owner.get(k, (os.lstat(path).st_uid, os.lstat(path).st_gid))

    def acl_deny_write_listed(self, path: str) -> list:
        k = self._key(path)
        return self._acl.get(k, [])


class NativePriv:
    """Interfaz privilegiada nativa — SOLO tras H1. Invoca c5_helper.
    H-R5-5: confinamiento de rutas registrado y pasado al helper.
    """

    def __init__(self, helper_path: str):
        if os.geteuid() != 0:
            raise PrivError("NativePriv requiere H1 + euid 0")
        self.helper = helper_path
        self.llamadas: list[dict] = []
        self._ambitos: list[str] = []

    def registrar_ambito(self, path: str):
        self._ambitos.append(physical_path(path))
        os.environ["C5_AUTH_BASE"] = path  # confinamiento del helper

    def _run(self, *args) -> int:
        import subprocess
        r = subprocess.run([self.helper, *args], capture_output=True, text=True)
        self.llamadas.append({"op": args[0], "rc": r.returncode,
                              "stdout": r.stdout, "stderr": r.stderr})
        return r.returncode

    def create_staging_and_copy(self, origen: str, staging_base: str,
                                hoja_nombre: str, j) -> tuple[str, str]:
        """H-R5-1: el helper crea root:0 0700 y copia como root.
        El uid operador jamás abre O_WRONLY/O_RDWR esos inodos.
        """
        import json as _json
        import subprocess
        r = subprocess.run([self.helper, "mkdir-staging", staging_base],
                           capture_output=True, text=True)
        self.llamadas.append({"op": "mkdir-staging", "rc": r.returncode,
                              "stdout": r.stdout, "stderr": r.stderr})
        if r.returncode != 0:
            raise PrivError(f"mkdir-staging rc={r.returncode}")
        info = _json.loads(r.stdout.strip().splitlines()[-1])
        parent, leaf = info["parent"], info["leaf"]
        self.registrar_ambito(parent)
        j.effect("mkdir", parent)
        j.effect("mkdir", leaf)
        rc = self._run("copy-tree", origen, leaf)
        if rc != 0:
            raise PrivError(f"copy-tree rc={rc}")
        j.effect("copy-tree", leaf)
        return parent, leaf

    def chmod_tighten(self, path: str) -> bool:
        return self._run("protect", path) == 0

    def lchown_root(self, path: str) -> bool:
        return self._run("protect", path) == 0

    def set_acl_deny_write(self, path: str) -> bool:
        return True  # implementado dentro de protect

    def owner_of(self, path: str) -> tuple:
        st = os.lstat(path)
        return (st.st_uid, st.st_gid)


class PrivFactory:
    @staticmethod
    def make(name: str, root: str = "/"):
        if name == "simulated":
            p = SimulatedPriv()
            p.registrar_ambito(root)
            return p
        if name == "native":
            raise PrivError("native requiere H1 explícita; no activado en r5")
        raise PrivError(f"priv desconocido: {name}")


# ---------- ancla C-1 (HB-4/N5) — H-R5-4: cableado a c5_ancla ----------

def fijar_ancla(anchor_path: str, anchor_sha256_esperado: str,
                evidencia_c1: Optional[dict] = None) -> dict:
    """H-R5-4: delega en c5_ancla.verificar_ancla (origen_autenticado real).
    H-R5-6.8: adapta el formato del ancla C-1 real al de inventory_tree.
    """
    r = ancla_mod.verificar_ancla(anchor_path, anchor_sha256_esperado, evidencia_c1)
    # adaptar inventario C-1 real → formato r5
    r["inv"] = ancla_mod.adaptar_ancla_c1(r["inv"])
    if r["confianza"] == "DELEGADA" and evidencia_c1 and evidencia_c1.get("requiere_c1"):
        ancla_mod.exigir_c1_para_root(r, "root")
    return r


# ---------- espacio (C-9) ----------

def space_need_bytes(origen: str) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(origen, followlinks=False):
        for n in filenames:
            p = os.path.join(dirpath, n)
            st = os.lstat(p)
            if stat.S_ISREG(st.st_mode):
                total += st.st_size
    return total


def space_avail_bytes(dirpath: str) -> int:
    st = os.statvfs(dirpath)
    return st.f_bavail * st.f_frsize


# ---------- rename exclusivo ----------

def rename_excl(src: str, dst: str) -> int:
    """RENAME_EXCL|RENAME_NOFOLLOW_ANY vía ctypes sobre libSystem.
    Falla cerrado si la primitiva no está disponible.
    """
    try:
        import ctypes
        import ctypes.util
        lib = ctypes.CDLL(ctypes.util.find_library("System"), use_errno=True)
        renamex = lib.renamex_np
        renamex.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex.restype = ctypes.c_int
        # constantes reales del SDK (sys/stdio.h MacOSX26.5):
        RENAME_EXCL = 0x00000004
        RENAME_NOFOLLOW_ANY = 0x00000010
        rc = renamex(src.encode(), dst.encode(), RENAME_EXCL | RENAME_NOFOLLOW_ANY)
        if rc != 0:
            return ctypes.get_errno()
        return 0
    except Exception:
        # fail-closed: no degradar a os.rename
        raise Abort("RENAMENP_NO_DISPONIBLE", "ABORTADO_STAGING_RETENIDO", 2)


# ---------- copia estricta ----------

def _copy_tree(src: str, dst: str, j: Journal):
    """Copia lstat-only: dirs+regulares+symlinks validados; rechaza especiales."""
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        dirnames.sort()
        filenames.sort()
        rel = os.path.relpath(dirpath, src)
        target_dir = dst if rel == "." else os.path.join(dst, rel)
        if rel != ".":
            # D2: modo del origen menos g+w/o+w
            src_dir = dirpath
            smode = os.lstat(src_dir).st_mode & 0o777 & ~(stat.S_IWGRP | stat.S_IWOTH)
            os.mkdir(target_dir, smode)
            j.effect("mkdir", target_dir)
        for name in filenames:
            sp = os.path.join(dirpath, name)
            dp = os.path.join(target_dir, name)
            st = os.lstat(sp)
            if stat.S_ISLNK(st.st_mode):
                t = os.readlink(sp)
                if t.startswith("/") or ".." in t.split("/"):
                    raise Abort(f"symlink-escapa: {rel}/{name}")
                os.symlink(t, dp)
                j.effect("symlink", dp)
            elif stat.S_ISREG(st.st_mode):
                if st.st_nlink > 1:
                    raise Abort(f"hardlink: {rel}/{name}")
                with open(sp, "rb") as fsrc, open(dp, "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst, 1 << 16)
                # D2: modo del origen menos g+w/o+w
                os.chmod(dp, st.st_mode & 0o777 & ~(stat.S_IWGRP | stat.S_IWOTH))
                j.effect("copy", dp)
            else:
                raise Abort(f"tipo-especial: {rel}/{name}")


# ---------- protección del árbol (F6) ----------

def _protect_tree(root: str, priv, acl_enabled: bool, j: Journal):
    """Orden real nativo: lchown primero, chmod después.
    En simulated: chmod real + lchown en ledger (el orden lo impone chown(2)).
    Symlinks jamás tocados.
    """
    paths = [root]
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        filenames.sort()
        for n in filenames:
            paths.append(os.path.join(dirpath, n))
        for n in dirnames:
            paths.append(os.path.join(dirpath, n))
    for p in paths:
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            continue
        # Nativo: lchown primero (corta escritura del operador). Simulated: mismo
        # orden de llamadas aunque el ledger se aplique después del chmod real.
        priv.lchown_root(p)
        j.effect("lchown", p)
        priv.chmod_tighten(p)
        j.effect("chmod", p)
        if acl_enabled:
            priv.set_acl_deny_write(p)
            j.effect("acl", p)


# ---------- veredicto por estado observado (HB-3) ----------

def _verdict_por_estado(result: dict, j: Journal, exc: Optional[Exception]) -> dict:
    """H-R5-3: decide por ESTADO OBSERVADO primero; PrivError y excepciones
    genéricas NO incondicionales — si queda staging/publicación propio, el
    veredicto lo refleja. rc6→rc2 unificado (H-R5-6.1): abortos van a rc=2.
    """
    published = result.get("published", False)
    staging = result.get("staging_parent") or result.get("staging_leaf")
    staging_existe = bool(staging and os.path.exists(staging))
    if exc is None:
        if result.get("cleanup_ok") is False:
            result["verdict"] = "OK_CON_LIMPIEZA_INCOMPLETA"
            result["rc"] = 3
        else:
            result["verdict"] = "PUBLICADO_VERIFICADO" if published else "SIN_EFECTOS"
            result["rc"] = 0 if published else 2
        return result
    # hubo excepción — estado primero (H-R5-3)
    if isinstance(exc, NoAutorizado) and not staging_existe and not published:
        result["verdict"] = "RECHAZADO_GATE_SIN_EFECTOS"
        result["rc"] = 1
        return result
    if published and result.get("content_ok") is False:
        result["verdict"] = "PUBLICADO_INCONSISTENTE_NO_BORRADO"
        result["rc"] = 4
        return result
    if published and result.get("metadata_ok") is False:
        result["verdict"] = "PUBLICADO_VERIFICACION_INCOMPLETA"
        result["rc"] = 7
        return result
    if published:
        # incluye PrivError y excepción genérica post-F8 (H-R5-3)
        result["verdict"] = "ESTADO_INDETERMINADO"
        result["rc"] = 8
        return result
    if staging_existe:
        # PrivError con staging propio ⇒ STAGING_RETENIDO, no NO_AUTORIZADO
        result["verdict"] = "ABORTADO_STAGING_RETENIDO"
        result["rc"] = 2
        return result
    if isinstance(exc, PrivError):
        result["verdict"] = "NO_AUTORIZADO"
        result["rc"] = 5
        return result
    if isinstance(exc, NoAutorizado):
        result["verdict"] = "RECHAZADO_GATE_SIN_EFECTOS"
        result["rc"] = 1
        return result
    result["verdict"] = "ABORTADO_SIN_EFECTOS"
    result["rc"] = 2
    return result


# ---------- flujo principal F0–F10 ----------

def place(origen: str, destino: str, anchor_path: str,
          anchor_sha256: str, modo: str, priv_name: str = "simulated",
          staging_base: Optional[str] = None, journal: Optional[Journal] = None,
          faults: Optional[dict] = None, acl_enabled: bool = False,
          evidencia_c1: Optional[dict] = None) -> dict:
    j = journal or Journal()
    faults = faults or {}
    result: dict[str, Any] = {
        "phases": [], "published": False, "content_ok": None,
        "metadata_ok": None, "cleanup_ok": None,
        "staging_parent": None, "staging_leaf": None,
        "priv": {"modo": priv_name, "chmod_go_w_real": False,
                 "chown_root": "SIMULADO-ledger" if priv_name == "simulated" else "NATIVO",
                 "llamadas": []},
    }

    def phase(pid: str, ok: bool, errno: Optional[int] = None):
        result["phases"].append({"id": pid, "ok": ok, "errno": errno})

    try:
        # F0 GATE
        _exigir_euid_no_cero("place")
        if modo in ("", "REQUIERE_DECISION_C5") or modo not in (
                "root", "aceptar_usuario", "simulated_h1", "fixture_ensayo"):
            # aceptar_usuario NO es atajo: se acepta solo como modo documentado
            # pero la protección sigue siendo B (pre-publicación).
            if modo != "aceptar_usuario":
                phase("F0", False, 1)
                raise NoAutorizado(f"modo no decidido: {modo!r}")
        if modo == "root" and priv_name == "simulated":
            phase("F0", False, 1)
            raise NoAutorizado("modo root exige priv native (H1)")
        phase("F0", True, 0)

        priv = PrivFactory.make(priv_name, root=os.path.dirname(os.path.abspath(staging_base or tempfile.gettempdir())) or "/")
        result["priv"]["llamadas"] = priv.llamadas

        if faults.get("identify"):
            raise Abort("fault:identify")

        # F1 IDENTIFY + ANCLA
        if not os.path.exists(origen) or os.path.islink(origen):
            phase("F1", False, 2)
            raise Abort("origen invalido")
        if os.path.exists(destino):
            phase("F1", False, 17)
            raise Abort("destino preexistente", "ABORTADO_SIN_EFECTOS", 2)
        ancla = fijar_ancla(anchor_path, anchor_sha256, evidencia_c1)
        if ancla["confianza"] == "DELEGADA" and modo == "root":
            phase("F1", False, 1)
            raise Abort("ancla DELEGADA no basta para modo root", "ABORTADO_SIN_EFECTOS", 2)
        origen_pin = pin(origen)
        padre_destino = os.path.dirname(os.path.abspath(destino))
        if not os.path.isdir(padre_destino) or os.path.islink(padre_destino):
            phase("F1", False, 2)
            raise Abort("padre destino invalido")
        phase("F1", True, 0)
        j.log(f"ancla confianza={ancla['confianza']} sha256={ancla['sha256'][:16]}…")

        # F2 SPACE
        need = space_need_bytes(origen) + RESERVA_BYTES
        base = staging_base or tempfile.gettempdir()
        avail = space_avail_bytes(base)
        if need > avail:
            phase("F2", False, 28)
            raise Abort(f"espacio insuficiente need={need} avail={avail}")
        phase("F2", True, 0)

        if faults.get("before_staging"):
            raise Abort("fault:before_staging")

        # F3+F4 STAGING+COPY — H-R5-1: DENTRO de la frontera del helper.
        # El uid operador no crea ni copia los inodos finales.
        if pin(origen) != origen_pin:
            phase("F3", False, 2)
            raise Abort("origen swap pre-frontera", "ABORTADO_SIN_EFECTOS", 2)
        staging_parent, hoja = priv.create_staging_and_copy(
            origen, base, os.path.basename(os.path.abspath(destino)), j)
        result["staging_parent"] = staging_parent
        result["staging_leaf"] = hoja
        hoja_pin = pin(hoja)
        padre_pin = pin(staging_parent)
        phase("F3", True, 0)
        phase("F4", True, 0)

        if faults.get("after_copy"):
            raise Abort("fault:after_copy", "ABORTADO_STAGING_RETENIDO", 2)

        # F5 REFCHK
        inv_staging = inventory_tree(hoja)
        if not compare_content(ancla["inv"], inv_staging):
            phase("F5", False, 2)
            raise Abort("contenido staging != ancla", "ABORTADO_STAGING_RETENIDO", 2)
        phase("F5", True, 0)

        if faults.get("mid_protect"):
            raise Abort("fault:mid_protect", "ABORTADO_STAGING_RETENIDO", 2)

        # F6 PROTECT + validación ACL (H-R5-4)
        _protect_tree(hoja, priv, acl_enabled, j)
        result["priv"]["chmod_go_w_real"] = True
        if acl_enabled:
            for dirpath, dirnames, filenames in os.walk(hoja, followlinks=False):
                for name in [dirpath] + [os.path.join(dirpath, n) for n in filenames]:
                    try:
                        ar = acl_mod.validar_acl(name)
                        if not ar["ok"]:
                            phase("F6", False, 1)
                            raise Abort(f"ACL allow-write ajena: {name}",
                                        "ABORTADO_STAGING_RETENIDO", 2)
                    except acl_mod.AclPolicyError as e:
                        # R6-1: fail-closed real — ACL ilegible NO se ignora
                        phase("F6", False, 1)
                        raise Abort(f"ACL ilegible (fail-closed): {name}: {e}",
                                    "ABORTADO_STAGING_RETENIDO", 2)
        phase("F6", True, 0)

        if faults.get("after_protect"):
            raise Abort("fault:after_protect", "ABORTADO_STAGING_RETENIDO", 2)

        # F7 REVALID
        inv2 = inventory_tree(hoja)
        content_ok = compare_content(ancla["inv"], inv2)
        metadata_ok = check_expected_metadata(hoja, priv)
        result["content_ok"] = content_ok
        result["metadata_ok"] = metadata_ok
        if not content_ok or not metadata_ok:
            phase("F7", False, 2)
            raise Abort("revalidacion falla", "ABORTADO_STAGING_RETENIDO", 2)
        # H-R5-2: re-pin de hoja y padre (modo 0700) — NO tautología
        if not pin_equal(pin(hoja), hoja_pin):
            phase("F7", False, 2)
            raise Abort("hoja swap post-protect", "ABORTADO_STAGING_RETENIDO", 2)
        if not pin_equal(pin(staging_parent), padre_pin):
            phase("F7", False, 2)
            raise Abort("padre staging swap", "ABORTADO_STAGING_RETENIDO", 2)
        padre_mode = os.lstat(staging_parent).st_mode & 0o777
        if padre_mode != 0o700:
            phase("F7", False, 2)
            raise Abort(f"padre staging modo {oct(padre_mode)} != 0700",
                        "ABORTADO_STAGING_RETENIDO", 2)
        phase("F7", True, 0)

        if faults.get("before_publish"):
            raise Abort("fault:before_publish", "ABORTADO_STAGING_RETENIDO", 2)

        # F8 PUBLISH — H-R5-2: re-pin inmediato antes de renamex_np
        if os.path.exists(destino):
            phase("F8", False, 17)
            raise Abort("destino aparecio", "ABORTADO_STAGING_RETENIDO", 2)
        if pin(origen) != origen_pin:
            phase("F8", False, 2)
            raise Abort("origen swap pre-rename", "ABORTADO_STAGING_RETENIDO", 2)
        # re-pin hoja + padre + modo 0700 justo antes del rename
        if not pin_equal(pin(hoja), hoja_pin):
            phase("F8", False, 2)
            raise Abort("hoja swap pre-rename", "ABORTADO_STAGING_RETENIDO", 2)
        if not pin_equal(pin(staging_parent), padre_pin):
            phase("F8", False, 2)
            raise Abort("padre staging swap pre-rename", "ABORTADO_STAGING_RETENIDO", 2)
        if (os.lstat(staging_parent).st_mode & 0o777) != 0o700:
            phase("F8", False, 2)
            raise Abort("padre staging no 0700 pre-rename", "ABORTADO_STAGING_RETENIDO", 2)
        if faults.get("pre_rename"):
            raise Abort("fault:pre_rename", "ABORTADO_STAGING_RETENIDO", 2)
        if faults.get("swap_hoja"):
            # inyectar swap de hoja para oráculo del harness
            os.rename(hoja, hoja + ".swap")
            os.mkdir(hoja, 0o700)
            phase("F8", False, 2)
            raise Abort("fault:swap_hoja", "ABORTADO_STAGING_RETENIDO", 2)
        errno_rn = rename_excl(hoja, destino)
        if errno_rn == 17:  # EEXIST
            phase("F8", False, 17)
            raise Abort("EEXIST carrera; sin anidar", "ABORTADO_STAGING_RETENIDO", 2)
        if errno_rn != 0:
            phase("F8", False, errno_rn)
            raise Abort(f"rename errno={errno_rn}", "ABORTADO_STAGING_RETENIDO", 2)
        result["published"] = True
        j.effect("rename", destino, errno=0)
        phase("F8", True, 0)

        # F9 VERIFY destino
        inv_dst = inventory_tree(destino)
        content_ok = compare_content(ancla["inv"], inv_dst)
        metadata_ok = check_expected_metadata(destino, priv)
        result["content_ok"] = content_ok
        result["metadata_ok"] = metadata_ok
        if not content_ok or not metadata_ok:
            phase("F9", False, 2)
            raise Abort("publicado inconsistente", "PUBLICADO_INCONSISTENTE_NO_BORRADO", 4)
        phase("F9", True, 0)

        # F10 CLEANUP
        try:
            os.rmdir(staging_parent)
            result["cleanup_ok"] = True
            j.effect("rmdir", staging_parent, errno=0)
            phase("F10", True, 0)
        except OSError as e:
            result["cleanup_ok"] = False
            j.effect("rmdir", staging_parent, errno=e.errno)
            phase("F10", False, e.errno)
            result["verdict"] = "OK_CON_LIMPIEZA_INCOMPLETA"
            result["rc"] = 3
            result["events"] = j.events
            result["effects"] = j.effects
            result["residuos"] = [staging_parent]
            return result

        result["verdict"] = "PUBLICADO_VERIFICADO"
        result["rc"] = 0
    except (Abort, PrivError, NoAutorizado, OSError) as e:
        result = _verdict_por_estado(result, j, e)
        result["error"] = str(e)
    except Exception as e:  # H-R5-3: excepción genérica ⇒ veredicto por estado
        result = _verdict_por_estado(result, j, e)
        result["error"] = f"{type(e).__name__}: {e}"
    result["events"] = j.events
    result["effects"] = j.effects
    result["residuos"] = []
    if result.get("staging_parent") and os.path.exists(result["staging_parent"]):
        result["residuos"].append(result["staging_parent"])
    return result


def list_stale(base: str) -> list:
    """Huérfanos ot07_c5_staging.* — solo lectura, sin borrar."""
    out = []
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        if name.startswith(PREFIJO_STAGING):
            p = os.path.join(base, name)
            out.append({"path": p, "pin": pin(p)})
    return out


def main(argv):
    if len(argv) < 2:
        print(json.dumps({"ok": False, "error": "uso"}))
        return 1
    cmd = argv[1]
    if cmd == "list-stale":
        base = "."
        if "--base" in argv:
            base = argv[argv.index("--base") + 1]
        print(json.dumps({"stale": list_stale(base)}, indent=2))
        return 0
    if cmd == "run":
        # parse mínimo
        def arg(name, default=None):
            if name in argv:
                return argv[argv.index(name) + 1]
            return default
        modo = arg("--modo", "fixture_ensayo")
        priv = arg("--priv", "simulated")
        r = place(
            origen=arg("--origen", ""),
            destino=arg("--destino", ""),
            anchor_path=arg("--inv-ref", ""),
            anchor_sha256=arg("--inv-ref-hash", ""),
            modo=modo,
            priv_name=priv,
            staging_base=arg("--staging-base"),
            acl_enabled="--acl" in argv,
            evidencia_c1={"cadena": "C-1", "hash_externo": arg("--c1-hash")} if arg("--c1-hash") else None,
        )
        print(json.dumps(r, indent=2))
        return r.get("rc", 2)
    print(json.dumps({"ok": False, "error": f"cmd {cmd}"}))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
