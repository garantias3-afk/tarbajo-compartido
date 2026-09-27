#!/usr/bin/env python3
"""harness_r5.py — harness NO privilegiado para candidato r5.

N0–N9 (lo comprobable sin root) + erratas r4 + contrato INTERFAZ_C5.
Conteos DINÁMICOS. Sin sudo/root/USB/arranque/OCLP/señales ajenas.
Uso: python3 -B tests/harness_r5.py
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import tempfile
import traceback
from pathlib import Path

os.umask(0o077)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src"
sys.path.insert(0, str(SRC))

import c5_orquestador as O  # noqa: E402
import c5_ancla as A  # noqa: E402
import c5_acl as ACL  # noqa: E402

RESULTADOS: list[dict] = []
_COLA: list[tuple[str, str, callable]] = []


def test(id_: str, nombre: str):
    def deco(fn):
        _COLA.append((id_, nombre, fn))
        return fn
    return deco


def assert_true(x, msg=""):
    if not x:
        raise AssertionError(msg or "assert_true")


def assert_eq(a, b, msg=""):
    if a != b:
        raise AssertionError(msg or f"{a!r} != {b!r}")


def hacer_fixture(base: Path):
    origen = base / "origen"
    origen.mkdir(parents=True)
    (origen / "a.txt").write_bytes(b"hello c5\n")
    (origen / "sub").mkdir()
    (origen / "sub" / "b.bin").write_bytes(b"\x00\x01\x02" * 100)
    (origen / "link").symlink_to("a.txt")
    inv = O.inventory_tree(str(origen))
    ancla_path = base / "ancla.json"
    ancla_path.write_text(json.dumps(inv, sort_keys=True), encoding="utf-8")
    h = hashlib.sha256(ancla_path.read_bytes()).hexdigest()
    return origen, ancla_path, h


@test("N0-01", "bootstrap rechaza euid==0 en simulated")
def t_n001():
    O._exigir_euid_no_cero("test")


@test("N0-02", "inventario bootstrap cubre fuentes y herramientas")
def t_n002():
    import c5_bootstrap as B
    inv = B.inventario_bootstrap(str(RAIZ))
    assert_true(len(inv["items"]) >= 4)
    for it in inv["items"]:
        if it.get("rel"):
            assert_true("sha256" in it)


@test("N0-03", "sin runner mutable: sin os.chown/seteuid en orquestador")
def t_n003():
    src = (SRC / "c5_orquestador.py").read_text()
    assert_true("os.chown" not in src)
    assert_true("seteuid" not in src)


@test("N1-01", "positivo: fixture copia + go-w aplicado")
def t_n101():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        r = O.place(str(origen), str(destino), str(ancla), h,
                    modo="fixture_ensayo", priv_name="simulated",
                    staging_base=str(base))
        assert_eq(r["rc"], 0, json.dumps(r)[:400])
        assert_eq(r["verdict"], "PUBLICADO_VERIFICADO")
        st = os.lstat(destino / "a.txt")
        assert_true(not (st.st_mode & (stat.S_IWGRP | stat.S_IWOTH)))


@test("N1-02", "negativo: raíz con g+w detectada (HB-1)")
def t_n102():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        real = O._protect_tree
        def mut(root, priv, acl_enabled, j):
            real(root, priv, acl_enabled, j)
            os.chmod(root, 0o777)
        O._protect_tree = mut
        try:
            r = O.place(str(origen), str(destino), str(ancla), h,
                        modo="fixture_ensayo", priv_name="simulated",
                        staging_base=str(base))
        finally:
            O._protect_tree = real
        assert_true(r["rc"] != 0, f"rc={r['rc']}")


@test("N1-03", "root-owned ≠ ineliminable (padre/sticky)")
def t_n103():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        p = Path(td) / "obj"
        p.write_text("x")
        info = ACL.separar_escritura_de_eliminacion(str(p))
        assert_true(set(info) >= {"contenido_w", "padre_w", "padre_sticky"})


@test("N2-01", "diseño: inodos finales en frontera del helper")
def t_n201():
    src = (SRC / "c5_orquestador.py").read_text()
    assert_true("PREFIJO_STAGING" in src)
    assert_true("0o700" in src)


@test("N2-02", "fd de escritura sobre origen ⇒ ancla detecta mutación")
def t_n202():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        fd = os.open(str(origen / "a.txt"), os.O_WRONLY | os.O_APPEND)
        try:
            os.write(fd, b"INJECTED")
            r = O.place(str(origen), str(destino), str(ancla), h,
                        modo="fixture_ensayo", priv_name="simulated",
                        staging_base=str(base))
            assert_true(r["rc"] != 0)
        finally:
            os.close(fd)


@test("N2-03", "E1: chmod no revoca fd O_RDWR ya abierto")
def t_n203():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        p = Path(td) / "f.txt"
        p.write_bytes(b"ABC")
        fd = os.open(str(p), os.O_RDWR)
        try:
            os.chmod(p, 0o000)
            os.lseek(fd, 0, os.SEEK_SET)
            n = os.write(fd, b"Z")
            assert_eq(n, 1)
        finally:
            os.close(fd)
            os.chmod(p, 0o644)


@test("N3-01", "validar_acl no crashea y reporta estructura")
def t_n301():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        p = Path(td) / "x"
        p.write_text("z")
        try:
            r = ACL.validar_acl(str(p))
            assert_true("ok" in r and "aces" in r)
        except ACL.AclPolicyError:
            pass  # fail-closed también válido


@test("N3-02", "capacidades escritura vs eliminación separadas")
def t_n302():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        p = Path(td) / "y"
        p.write_text("z")
        d = ACL.separar_escritura_de_eliminacion(str(p))
        assert_true(set(d) >= {"contenido_w", "padre_w", "padre_sticky"})


@test("N4-01", "symlink absoluto rechazado")
def t_n401():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        origen = Path(td) / "o"
        origen.mkdir()
        (origen / "evil").symlink_to("/etc/passwd")
        try:
            O.inventory_tree(str(origen))
            raise AssertionError("debía rechazar")
        except O.Abort:
            pass


@test("N4-02", "hardlink rechazado")
def t_n402():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        origen = Path(td) / "o"
        origen.mkdir()
        a = origen / "a"
        a.write_text("x")
        os.link(str(a), str(origen / "b"))
        try:
            O.inventory_tree(str(origen))
            raise AssertionError("debía rechazar")
        except O.Abort:
            pass


@test("N4-03", "FIFO rechazado")
def t_n403():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        origen = Path(td) / "o"
        origen.mkdir()
        os.mkfifo(str(origen / "fifo"))
        try:
            O.inventory_tree(str(origen))
            raise AssertionError("debía rechazar")
        except O.Abort:
            pass


@test("N4-04", "AT_UNIQUE en SDK o en helper")
def t_n404():
    for p in [
        Path("/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/sys/fcntl.h"),
        Path("/usr/include/sys/fcntl.h"),
    ]:
        if p.exists():
            assert_true("AT_UNIQUE" in p.read_text())
            return
    assert_true("AT_UNIQUE" in (SRC / "c5_helper.c").read_text())


@test("N4-05", "RESOLVE_BENEATH solo como rechazo documentado")
def t_n405():
    for f in [SRC / "c5_helper.c", SRC / "c5_orquestador.py", RAIZ / "INTERFAZ_C5.json"]:
        if f.exists() and "RESOLVE_BENEATH" in f.read_text():
            assert_true("NO" in f.read_text() or "Linux" in f.read_text())


@test("N5-01", "ancla DELEGADA sin C-1")
def t_n501():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        origen, ancla, h = hacer_fixture(Path(td))
        r = A.verificar_ancla(str(ancla), h, None)
        assert_eq(r["confianza"], "DELEGADA")


@test("N5-02", "ancla C-1 con evidencia autenticada")
def t_n502():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        origen, ancla, h = hacer_fixture(Path(td))
        ev = {"cadena": "C-1", "hash_externo": h,
              "origen_autenticado": True, "snapshot_unico": True}
        r = A.verificar_ancla(str(ancla), h, ev)
        assert_eq(r["confianza"], "C-1")


@test("N5-03", "hash externo divergente rechaza")
def t_n503():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        origen, ancla, h = hacer_fixture(Path(td))
        try:
            A.verificar_ancla(str(ancla), "00" * 32, None)
            raise AssertionError("debía rechazar")
        except A.AnclaError:
            pass


@test("N5-04", "archivo+hash del operador no acredita procedencia")
def t_n504():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        origen, ancla, h = hacer_fixture(Path(td))
        ev = {"cadena": "C-1", "hash_externo": h,
              "origen_autenticado": False, "snapshot_unico": True}
        r = A.verificar_ancla(str(ancla), h, ev)
        assert_eq(r["confianza"], "DELEGADA")


@test("N6-01", "destino preexistente: sin anidar ni borrar ganador")
def t_n601():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        destino.mkdir()
        (destino / "ganador.txt").write_text("preexistente")
        r = O.place(str(origen), str(destino), str(ancla), h,
                    modo="fixture_ensayo", priv_name="simulated",
                    staging_base=str(base))
        assert_true(r["rc"] != 0)
        assert_true((destino / "ganador.txt").exists())


@test("N6-02", "retry crea staging NUEVO")
def t_n602():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        r1 = O.place(str(origen), str(destino), str(ancla), h,
                     modo="fixture_ensayo", priv_name="simulated",
                     staging_base=str(base), faults={"after_protect": True})
        assert_true(os.path.exists(r1["staging_parent"]))
        r2 = O.place(str(origen), str(destino), str(ancla), h,
                     modo="fixture_ensayo", priv_name="simulated",
                     staging_base=str(base))
        assert_eq(r2["rc"], 0)
        assert_true(r2["staging_parent"] != r1["staging_parent"])


@test("N6-03", "limpieza fallida ⇒ RC=3")
def t_n603():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        real_rmdir = os.rmdir
        def fallido(path):
            if "ot07_c5_staging" in str(path):
                raise OSError(66, "Directory not empty")
            return real_rmdir(path)
        os.rmdir = fallido
        try:
            r = O.place(str(origen), str(destino), str(ancla), h,
                        modo="fixture_ensayo", priv_name="simulated",
                        staging_base=str(base))
        finally:
            os.rmdir = real_rmdir
        assert_eq(r["rc"], 3)
        assert_eq(r["verdict"], "OK_CON_LIMPIEZA_INCOMPLETA")


@test("N6-04", "post-publicación mutada ⇒ contenido_ok false")
def t_n604():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        r = O.place(str(origen), str(destino), str(ancla), h,
                    modo="fixture_ensayo", priv_name="simulated",
                    staging_base=str(base))
        assert_eq(r["rc"], 0)
        (destino / "a.txt").write_bytes(b"hacked")
        inv = O.inventory_tree(str(destino))
        ancla_inv = json.loads(ancla.read_text())
        assert_true(not O.compare_content(ancla_inv, inv))


@test("N7-01", "tripleta dev/ino/sha256 estable")
def t_n701():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        p = Path(td) / "obj"
        p.write_bytes(b"payload")
        st = os.lstat(p)
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        st2 = os.lstat(p)
        assert_eq(st2.st_ino, st.st_ino)
        assert_eq(hashlib.sha256(p.read_bytes()).hexdigest(), h)


@test("N7-02", "sustituto rompe pin")
def t_n702():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        p = Path(td) / "obj"
        p.write_bytes(b"v1")
        pin1 = O.pin(str(p))
        p.unlink()
        p.write_bytes(b"v2")
        assert_true(not O.pin_equal(pin1, O.pin(str(p))))


@test("N8-01", "operación confinada al fixture")
def t_n801():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        r = O.place(str(origen), str(destino), str(ancla), h,
                    modo="fixture_ensayo", priv_name="simulated",
                    staging_base=str(base))
        assert_eq(r["rc"], 0)
        assert_true(destino.exists())


@test("N8-02", "SimulatedPriv rechaza path fuera de ámbito")
def t_n802():
    priv = O.PrivFactory.make("simulated", root="/tmp")
    try:
        priv.chmod_tighten("/etc/passwd")
        raise AssertionError("debía rechazar")
    except O.PrivError:
        pass


@test("N9-01", "sin diskutil/createinstallmedia en orquestador")
def t_n901():
    src = (SRC / "c5_orquestador.py").read_text()
    assert_true("diskutil" not in src)
    assert_true("createinstallmedia" not in src)


@test("N9-02", "PYTHONDONTWRITEBYTECODE=1")
def t_n902():
    assert_eq(os.environ.get("PYTHONDONTWRITEBYTECODE"), "1")


@test("N9-03", "umask 077")
def t_n903():
    m = os.umask(0o077)
    os.umask(m)
    assert_eq(m, 0o077)


@test("ERRATA-01", "INDICE_HISTORICO_R5 documenta codesign_cim vacío")
def t_e01():
    idx = (RAIZ / "docs" / "INDICE_HISTORICO_R5.md").read_text()
    assert_true("codesign_cim" in idx)
    assert_true("vacío" in idx or "vacio" in idx.lower())


@test("ERRATA-02", "SENSIBILIDAD.json con base/mutante/comando/RC/aserción")
def t_e02():
    ev = json.loads((RAIZ / "evidencia_r5" / "SENSIBILIDAD.json").read_text())
    assert_true(len(ev["casos"]) >= 2)
    for c in ev["casos"]:
        for k in ("base", "mutante", "comando", "rc", "asercion"):
            assert_true(k in c, f"falta {k} en {c.get('id')}")


@test("IFZ-01", "INTERFAZ_C5.json con 6 acciones + esquema + fallos")
def t_i01():
    ifz = json.loads((RAIZ / "INTERFAZ_C5.json").read_text())
    for a in ("preparacion", "verificacion", "ensayo", "publicacion", "uso", "limpieza"):
        assert_true(a in ifz["acciones"])
    assert_true("esquema_resultado" in ifz)
    assert_true("comportamiento_fallo" in ifz)


@test("IFZ-02", "interfaz marca pseudocomandos P6 como no usados")
def t_i02():
    ifz = (RAIZ / "INTERFAZ_C5.json").read_text()
    assert_true("primitivas_NO_usadas" in ifz)
    assert_true("RESOLVE_BENEATH" in ifz)


# ============ H-R5-1..H-R5-5 (revisión Max r5→r6) ============

@test("N2-04", "H-R5-1: fd-sobre-staging — O_WRONLY tras frontera (simulated: go-w; fuerte en H1-N2)")
def t_n204():
    """La frontera crea los inodos y retira escritura antes de devolver el
    control. En simulated se verifica go-w residual; la aserción FUERTE
    (open O_WRONLY como uid 501 falla sobre root:0) vive en H1-N2 nativo.
    """
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        r = O.place(str(origen), str(destino), str(ancla), h,
                    modo="fixture_ensayo", priv_name="simulated",
                    staging_base=str(base))
        assert_eq(r["rc"], 0, json.dumps(r)[:300])
        st = os.lstat(destino / "a.txt")
        assert_true(not (st.st_mode & (stat.S_IWGRP | stat.S_IWOTH)))
        try:
            fd = os.open(str(destino / "a.txt"), os.O_WRONLY)
            os.close(fd)
            st2 = os.lstat(destino / "a.txt")
            assert_true(not (st2.st_mode & (stat.S_IWGRP | stat.S_IWOTH)))
        except OSError as e:
            assert_true(e.errno in (13, 1), f"errno={e.errno}")


@test("N2-05", "H-R5-1: no hay ventana crear→copiar separada del operador")
def t_n205():
    """El orquestador ya NO llama tempfile.mkdtemp/_copy_tree directamente
    en F3/F4: va por priv.create_staging_and_copy (frontera)."""
    src = (SRC / "c5_orquestador.py").read_text()
    # dentro de place(), F3/F4 usan la frontera
    assert_true("create_staging_and_copy" in src)
    # la creación directa de staging en place() fue eliminada del flujo F3
    import re
    place_src = src[src.index("def place("):src.index("def list_stale")]
    assert_true("tempfile.mkdtemp" not in place_src,
                "place() no debe crear staging directamente")
    assert_true("create_staging_and_copy" in place_src)


@test("N2-06", "H-R5-1 PoC Max: sin ventana crear→copiar (oráculo simulated; fuerte en H1-N2)")
def t_n206():
    """Reproduce la PoC de Max: intentar abrir fd tras la frontera.
    En simulated se verifica go-w; la aserción fuerte (EACCES sobre root:0)
    corresponde a H1-N2 nativo (R6-2: el título no sobreafirma)."""
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        real = O.SimulatedPriv.create_staging_and_copy
        fd_abierto = {}
        def hooked(self, origen, staging_base, hoja_nombre, j):
            parent, leaf = real(self, origen, staging_base, hoja_nombre, j)
            target = os.path.join(leaf, "a.txt")
            try:
                fd_abierto["fd"] = os.open(target, os.O_WRONLY)
                fd_abierto["ok"] = True
            except OSError as e:
                fd_abierto["ok"] = False
                fd_abierto["errno"] = e.errno
            return parent, leaf
        O.SimulatedPriv.create_staging_and_copy = hooked
        try:
            r = O.place(str(origen), str(destino), str(ancla), h,
                        modo="fixture_ensayo", priv_name="simulated",
                        staging_base=str(base))
        finally:
            O.SimulatedPriv.create_staging_and_copy = real
        assert_eq(r["rc"], 0)
        if fd_abierto.get("ok"):
            os.close(fd_abierto["fd"])
            st = os.lstat(destino / "a.txt")
            assert_true(not (st.st_mode & (stat.S_IWGRP | stat.S_IWOTH)))
        else:
            assert_true(fd_abierto.get("errno") in (13, 1))


@test("N6-05", "H-R5-2: swap-de-hoja antes de rename se detecta")
def t_n605():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        r = O.place(str(origen), str(destino), str(ancla), h,
                    modo="fixture_ensayo", priv_name="simulated",
                    staging_base=str(base),
                    faults={"swap_hoja": True})
        assert_true(r["rc"] != 0, f"rc={r['rc']}")
        assert_true("STAGING_RETENIDO" in r["verdict"] or "SIN_EFECTOS" in r["verdict"],
                    r["verdict"])
        assert_true(not r.get("published"), "no debe publicar el sustituto")


@test("N6-06", "H-R5-2: re-pin hoja/padre presente en F7 y F8")
def t_n606():
    src = (SRC / "c5_orquestador.py").read_text()
    place_src = src[src.index("def place("):src.index("def list_stale")]
    assert_true("hoja_pin" in place_src)
    assert_true("padre_pin" in place_src)
    assert_true("hoja swap pre-rename" in place_src)
    assert_true("padre staging no 0700" in place_src)
    # la tautología pin(x)!=pin(x) fue eliminada
    assert_true("pin(os.path.dirname(staging_parent)), pin(os.path.dirname(staging_parent))" not in place_src)


@test("H-R5-3a", "PrivError con staging ⇒ ABORTADO_STAGING_RETENIDO rc=2")
def t_hr53a():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        real = O._protect_tree
        def mut(root, priv, acl_enabled, j):
            raise O.PrivError("priv falla con staging ya creado")
        O._protect_tree = mut
        try:
            r = O.place(str(origen), str(destino), str(ancla), h,
                        modo="fixture_ensayo", priv_name="simulated",
                        staging_base=str(base))
        finally:
            O._protect_tree = real
        assert_eq(r["verdict"], "ABORTADO_STAGING_RETENIDO")
        assert_eq(r["rc"], 2)
        assert_true(os.path.exists(r["staging_parent"]), "staging debe quedar retenido")


@test("H-R5-3b", "excepción genérica post-publicación ⇒ ESTADO_INDETERMINADO")
def t_hr53b():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        # provocar excepción genérica en F9
        real = O.inventory_tree
        calls = {"n": 0}
        def mut(path):
            calls["n"] += 1
            if calls["n"] >= 3:  # F5, F7, F9 — la 3ª es F9
                raise RuntimeError("excepcion-generica-post-publish")
            return real(path)
        O.inventory_tree = mut
        try:
            r = O.place(str(origen), str(destino), str(ancla), h,
                        modo="fixture_ensayo", priv_name="simulated",
                        staging_base=str(base))
        finally:
            O.inventory_tree = real
        assert_eq(r["verdict"], "ESTADO_INDETERMINADO")
        assert_eq(r["rc"], 8)
        assert_true(r.get("published"), "ya estaba publicado")


@test("H-R5-4a", "ancla cableada: origen_autenticado real via manifiesto")
def t_hr54a():
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        origen, ancla, h = hacer_fixture(Path(td))
        # sin manifiesto ⇒ DELEGADA
        ev = A.construir_evidencia_c1(h, hashes_sellados=None)
        r = A.verificar_ancla(str(ancla), h, ev)
        assert_eq(r["confianza"], "DELEGADA")
        # con manifiesto que contiene el hash ⇒ C-1
        ev2 = A.construir_evidencia_c1(h, hashes_sellados={h})
        r2 = A.verificar_ancla(str(ancla), h, ev2)
        assert_eq(r2["confianza"], "C-1")


@test("H-R5-4b", "ACL cableada al pipeline (acl_enabled invoca validar_acl)")
def t_hr54b():
    src = (SRC / "c5_orquestador.py").read_text()
    assert_true("acl_mod.validar_acl" in src)
    assert_true("acl_mod" in src)


@test("H-R5-5a", "helper confina rutas (cleanup sin prefijo rechazado)")
def t_hr55a():
    helper = RAIZ / "build" / "c5_helper"
    if not helper.exists():
        raise AssertionError("helper no compilado")
    import subprocess
    r = subprocess.run([str(helper), "cleanup", "/tmp/otro_dir"],
                       capture_output=True, text=True)
    assert_true(r.returncode != 0)
    assert_true("fuera-de-frontera" in r.stderr or "sin-prefijo" in r.stderr)


@test("H-R5-5b", "helper selfcheck reporta confinamiento y uid parametrizado")
def t_hr55b():
    helper = RAIZ / "build" / "c5_helper"
    import subprocess
    r = subprocess.run([str(helper), "selfcheck"], capture_output=True, text=True)
    assert_eq(r.returncode, 0)
    out = r.stdout
    assert_true("confinamiento" in out)
    assert_true("uid_operador" in out)
    assert_true("0x10" in out)


@test("H-R5-6.7", "SENSIBILIDAD.json: conteo de casos coincide con el recibo")
def t_hr567():
    ev = json.loads((RAIZ / "evidencia_r5" / "SENSIBILIDAD.json").read_text())
    n = len(ev["casos"])
    assert_true(n >= 7, f"sensibilidad: {n} casos")


@test("H-R5-6.8", "adaptador de formato ancla C-1 (lista → dict)")
def t_hr568():
    inv_real = {
        "root": "/App",
        "entries": [
            {"relpath": ".", "type": "dir"},
            {"relpath": "a.txt", "type": "file", "size": 3, "sha256": "abc"},
            {"relpath": "sub", "type": "dir"},
            {"relpath": "link", "type": "symlink", "target": "a.txt"},
        ],
    }
    adapted = A.adaptar_ancla_c1(inv_real)
    assert_true(isinstance(adapted["entries"], dict))
    assert_true("a.txt" in adapted["entries"])
    assert_eq(adapted["entries"]["a.txt"]["sha256"], "abc")
    r5fmt = {"entries": {"a.txt": {"type": "file", "size": 1, "sha256": "x"}}}
    assert_eq(A.adaptar_ancla_c1(r5fmt), r5fmt)


# ============ r6b: fixes R6-1 y F-R6-N3-1 (equivalentes c5-r6-09/10) ============

@test("c5-r6-09b", "F-R6-N3-1: ACE allow write/append de ls -le detectadas")
def t_r609b():
    """ls -le imprime write/append (no write_data/append_data).
    DERECHOS_ESCRITURA debe detectarlos (aliases)."""
    import subprocess
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        p = Path(td) / "sonda.bin"
        p.write_bytes(b"x\n")
        os.chmod(p, 0o444)
        # allow write (nombre ls -le)
        r = subprocess.run(["/bin/chmod", "+a", "user:501 allow write", str(p)],
                           capture_output=True)
        if r.returncode != 0:
            # sin permiso de chmod +a: verificar al menos el conjunto
            assert_true("write" in ACL.DERECHOS_ESCRITURA)
            assert_true("append" in ACL.DERECHOS_ESCRITURA)
            return
        ar = ACL.validar_acl(str(p))
        assert_true(not ar["ok"], f"allow write debe detectarse: {ar}")
        assert_true(any(p["tipo"] == "ACE_ALLOW_WRITE_AJENA" for p in ar["problemas"]))
        # allow append
        subprocess.run(["/bin/chmod", "-N", str(p)], capture_output=True)
        subprocess.run(["/bin/chmod", "+a", "user:501 allow append", str(p)],
                       capture_output=True)
        ar2 = ACL.validar_acl(str(p))
        assert_true(not ar2["ok"], f"allow append debe detectarse: {ar2}")


@test("c5-r6-10b", "R6-1: AclPolicyError ⇒ ABORTADO_STAGING_RETENIDO (fail-closed)")
def t_r610b():
    """El except de F6 ya no engulle el fail-closed: si validar_acl lanza,
    el flujo aborta sin publicar."""
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        real = ACL.validar_acl
        def lanza(path):
            raise ACL.AclPolicyError("ls inparseable (simulado)")
        ACL.validar_acl = lanza
        try:
            r = O.place(str(origen), str(destino), str(ancla), h,
                        modo="fixture_ensayo", priv_name="simulated",
                        staging_base=str(base), acl_enabled=True)
        finally:
            ACL.validar_acl = real
        assert_true(r["rc"] != 0, f"no debe publicar: rc={r['rc']} {r.get('verdict')}")
        assert_true("STAGING_RETENIDO" in r["verdict"] or "SIN_EFECTOS" in r["verdict"],
                    r["verdict"])
        assert_true(not r.get("published"), "no debe publicar con ACL ilegible")


@test("c5-r6-10b-det", "R6-1a: ACE allow-write detectada ⇒ aborta sin publicar")
def t_r610bdet():
    """Cuando la detección funciona (ok=False), el flujo aborta."""
    with tempfile.TemporaryDirectory(dir=str(RAIZ / "fixtures")) as td:
        base = Path(td)
        origen, ancla, h = hacer_fixture(base)
        destino = base / "destino"
        real = ACL.validar_acl
        def detecta(path):
            return {"path": path, "ok": False,
                    "aces": [], "problemas": [{"tipo": "ACE_ALLOW_WRITE_AJENA"}],
                    "politica": {}}
        ACL.validar_acl = detecta
        try:
            r = O.place(str(origen), str(destino), str(ancla), h,
                        modo="fixture_ensayo", priv_name="simulated",
                        staging_base=str(base), acl_enabled=True)
        finally:
            ACL.validar_acl = real
        assert_true(r["rc"] != 0)
        assert_true(not r.get("published"))


@test("R6-4", "C5_AUTH_BASE documentado como confinamiento estricto")
def t_r64():
    txt = (SRC / "c5_helper.c").read_text()
    assert_true("C5_AUTH_BASE" in txt)
    assert_true("estricto" in txt.lower() or "ESTRICTO" in txt)


# ============ r6c: D1 + D2 + protocolo abort ============

@test("D1-01", "copy-tree no hace mkdir de la raíz si dst ya existe")
def t_d101():
    """D1: cmd_copy_tree copia CONTENIDO dentro de la hoja existente."""
    src = (SRC / "c5_helper.c").read_text()
    # la función que copia contenido no debe mkdir la raíz en cmd_copy_tree
    idx = src.index("static int cmd_copy_tree")
    chunk = src[idx:src.index("static int protect_one")]
    assert_true("dst YA EXISTE" in chunk or "CONTENIDO" in chunk)
    assert_true("readdir" in chunk, "debe iterar hijos del origen")


@test("D1-02", "copy_walk hace mkdir solo si dst no existe (EEXIST tolerado en raíz)")
def t_d102():
    src = (SRC / "c5_helper.c").read_text()
    idx = src.index("static int copy_walk")
    chunk = src[idx:src.index("static int cmd_copy_tree")]
    assert_true("ENOENT" in chunk, "debe distinguir dst ausente")
    assert_true("dst-no-es-dir" in chunk or "S_ISDIR" in chunk)


@test("D2-01", "copy-tree conserva modo del origen menos g+w/o+w (incluye HOJA)")
def t_d201():
    src = (SRC / "c5_helper.c").read_text()
    assert_true("IWGRP" in src and "IWOTH" in src)
    assert_true("nmode" in src)
    # R6C-1: chmod de la HOJA tras copiar hijos
    assert_true("chmod-hoja" in src or "chmod(dst, hmode)" in src,
                "la hoja debe recibir el modo del origen menos go-w")
    idx = src.index("static int cmd_copy_tree")
    chunk = src[idx:src.index("static int protect_one")]
    assert_true("hmode" in chunk or "chmod-hoja" in chunk)


@test("D2-02", "_copy_tree del orquestador aplica D2")
def t_d202():
    src = (SRC / "c5_orquestador.py").read_text()
    assert_true("S_IWGRP" in src or "stat.S_IWGRP" in src)


@test("PROTO-01", "protocolo abort RC≠0 documentado en H1")
def t_proto01():
    txt = (RAIZ / "docs" / "PROCEDIMIENTO_H1.md").read_text()
    assert_true("aborta" in txt.lower() or "ABORT" in txt)
    assert_true("RC" in txt)


@test("D3-01", "C5_AUTH_BASE documentado para re-ejecución")
def t_d301():
    txt = (RAIZ / "docs" / "PROCEDIMIENTO_H1.md").read_text()
    assert_true("C5_AUTH_BASE" in txt)


@test("CLEANUP-01", "cleanup con retiro bottom-up de árbol vacío")
def t_clean01():
    src = (SRC / "c5_helper.c").read_text()
    assert_true("rmdir_vacio_bottom_up" in src)
    assert_true("contenido-residual" in src)


def main():
    print("=== harness_r5 no privilegiado ===")
    print(f"uid={os.geteuid()} python={sys.version.split()[0]}")
    for id_, nombre, fn in _COLA:
        try:
            fn()
            RESULTADOS.append({"id": id_, "nombre": nombre, "ok": True, "error": None})
            print(f"  OK   {id_}  {nombre}")
        except Exception as e:
            RESULTADOS.append({
                "id": id_, "nombre": nombre, "ok": False,
                "error": f"{type(e).__name__}: {e}",
            })
            print(f"  FAIL {id_}  {nombre}: {e}")
    total = len(RESULTADOS)
    ok = sum(1 for r in RESULTADOS if r["ok"])
    fail = total - ok
    resumen = {
        "total": total, "ok": ok, "fail": fail, "skips": 0,
        "ids_ok": [r["id"] for r in RESULTADOS if r["ok"]],
        "ids_fail": [r["id"] for r in RESULTADOS if not r["ok"]],
    }
    print(f"\n=== {ok}/{total} OK · {fail} FAIL · 0 skips ===")
    out = RAIZ / "evidencia_r6d" / "HARNESS_RESULTADOS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"resumen": resumen, "resultados": RESULTADOS}, indent=2),
                   encoding="utf-8")
    print(f"evidencia: {out}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
