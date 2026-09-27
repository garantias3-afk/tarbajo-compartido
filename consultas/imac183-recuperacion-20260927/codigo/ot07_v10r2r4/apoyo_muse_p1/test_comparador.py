"""P1 — pruebas independientes del comparador/inventario de referencia.

Fixtures chicos construidos aquí; expectativas literales fijadas en cada
test (no se usa la implementación como oráculo: se afirma el código de
resultado exacto). Solo temporales propios; ninguna herramienta nativa
peligrosa, ningún disco real, ninguna red.

 Residual declarado: la sustitución ENTRE observación y uso solo se simula
 (test_sustitucion_entre_observacion_y_uso); en operación se exige
 re-inventariar inmediatamente antes del efecto persistente. Carreras con el
 candidato real: NO probadas aquí (ver MATRIZ_P1.md P1-R1…R3).
"""
import hashlib
import json
import os
import stat
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import comparador as C
import inventario as INV


def sha(b):
    return hashlib.sha256(b).hexdigest()


def escribir(root, rel, data=b"x"):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    return p


def arbol_base(root):
    """Árbol canónico de fixture con enlace interno legítimo."""
    escribir(root, "Contents/Info.plist", b"plist-v1")
    escribir(root, "Contents/Resources/createinstallmedia", b"cim-v1")
    escribir(root, "Contents/SharedSupport/SharedSupport.dmg", b"D" * 4096)
    os.symlink("Info.plist", os.path.join(root, "Contents", "enlace-hermano"))
    os.makedirs(os.path.join(root, "Contents", "vacio"), exist_ok=True)
    return INV.inventario(root)


class Comparador(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="p1_")
        self.a = os.path.join(self.tmp.name, "a")
        self.b = os.path.join(self.tmp.name, "b")
        os.makedirs(self.a)
        self.ref = arbol_base(self.a)

    def tearDown(self):
        self.tmp.cleanup()

    def clonar(self):
        import shutil
        if os.path.lexists(self.b):
            shutil.rmtree(self.b, ignore_errors=False) if not os.path.islink(self.b) \
                else os.unlink(self.b)
        shutil.copytree(self.a, self.b, symlinks=True)
        return INV.inventario(self.b)

    def test_arbol_identico_con_enlace_interno_ok(self):
        r = C.comparar(self.ref, self.clonar())
        self.assertTrue(r.ok)
        self.assertEqual(r.codigo, "OK")

    def test_archivo_alterado_mismo_tamano(self):
        self.clonar()
        escribir(self.b, "Contents/Info.plist", b"plist-v2")  # mismo tamaño
        r = C.comparar(self.ref, INV.inventario(self.b))
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo, "CONTENIDO_ALTERADO")

    def test_archivo_vacio_registrado_y_alterado(self):
        self.clonar()
        escribir(self.b, "Contents/nuevo-vacio", b"")
        inv = INV.inventario(self.b)
        self.assertEqual(inv["Contents/nuevo-vacio"]["sha256"], sha(b""))
        r = C.comparar(self.ref, inv)
        self.assertEqual(r.codigo, "EXTRA")

    def test_extra_y_faltante(self):
        self.clonar()
        escribir(self.b, "Contents/extra.py", b"e")
        os.unlink(os.path.join(self.b, "Contents/Resources/createinstallmedia"))
        r = C.comparar(self.ref, INV.inventario(self.b))
        self.assertFalse(r.ok)
        codigos = [c for c, _ in r.detalles]
        self.assertIn("EXTRA", codigos)
        self.assertIn("FALTANTE", codigos)

    def test_cambio_de_tipo(self):
        import shutil
        self.clonar()
        p = os.path.join(self.b, "Contents/Info.plist")
        os.unlink(p)
        os.mkdir(p)  # archivo -> directorio
        r = C.comparar(self.ref, INV.inventario(self.b))
        self.assertEqual(r.codigo, "TIPO_CAMBIADO")
        self.clonar()
        p2 = os.path.join(self.b, "Contents/Resources/createinstallmedia")
        os.unlink(p2)
        os.symlink("../Info.plist", p2)  # archivo -> enlace válido
        r = C.comparar(self.ref, INV.inventario(self.b))
        self.assertEqual(r.codigo, "TIPO_CAMBIADO")

    def test_enlace_absoluto_rechazado(self):
        self.clonar()
        os.symlink("/etc/passwd", os.path.join(self.b, "Contents/abs"))
        r = C.comparar(self.ref, INV.inventario(self.b))
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo, "ENLACE_SALIENTE")

    def test_enlace_saliente_por_puntos(self):
        self.clonar()
        os.symlink("../../escape", os.path.join(self.b, "Contents/evil"))
        r = C.comparar(self.ref, INV.inventario(self.b))
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo, "ENLACE_SALIENTE")

    def test_enlace_transitivo_que_escapa(self):
        # Solo los .. que superan la profundidad del enlace escapan.
        # "Contents/a2" -> "x/../../../escape" sube 3 desde profundidad 2.
        self.clonar()
        os.symlink("x/../../../escape", os.path.join(self.b, "Contents/a2"))
        man = INV.inventario(self.b)
        estado, _ = C.resolver_enlace(man, "Contents/a2")
        self.assertEqual(estado, "saliente")
        # Dos .. desde profundidad 2 aterrizan en la raíz: colgante, no fuga.
        os.unlink(os.path.join(self.b, "Contents/a2"))
        os.symlink("x/../../escape", os.path.join(self.b, "Contents/a2"))
        man = INV.inventario(self.b)
        self.assertEqual(C.resolver_enlace(man, "Contents/a2")[0], "roto")
        # Cadena por directorio: d/l2 -> ../../../escape supera la
        # profundidad 2 de Contents/d y sale del árbol.
        os.unlink(os.path.join(self.b, "Contents/a2"))
        os.makedirs(os.path.join(self.b, "Contents/d"), exist_ok=True)
        os.symlink("../../../escape", os.path.join(self.b, "Contents/d/l2"))
        r = C.comparar(self.ref, INV.inventario(self.b))
        self.assertEqual(r.codigo, "ENLACE_SALIENTE")

    def test_enlace_transitivo_interno_valido(self):
        self.clonar()
        os.symlink("hermano", os.path.join(self.b, "Contents/cadena"))
        os.symlink("enlace-hermano", os.path.join(self.b, "Contents/hermano"))
        man = INV.inventario(self.b)
        estado, final = C.resolver_enlace(man, "Contents/cadena")
        self.assertEqual(estado, "ok")
        self.assertEqual(final, "Contents/Info.plist")

    def test_enlace_con_puntos_intermedios_validos(self):
        # sub/l -> ../x : los .. intermedios válidos NO son escape.
        self.clonar()
        escribir(self.b, "Contents/x", b"x")
        os.makedirs(os.path.join(self.b, "Contents/sub"), exist_ok=True)
        os.symlink("../x", os.path.join(self.b, "Contents/sub/l"))
        man = INV.inventario(self.b)
        estado, final = C.resolver_enlace(man, "Contents/sub/l")
        self.assertEqual((estado, final), ("ok", "Contents/x"))

    def test_enlace_ciclico(self):
        self.clonar()
        os.symlink("c2", os.path.join(self.b, "Contents/c1"))
        os.symlink("c1", os.path.join(self.b, "Contents/c2"))
        man = INV.inventario(self.b)
        self.assertEqual(C.resolver_enlace(man, "Contents/c1")[0], "ciclico")

    def test_enlace_roto(self):
        self.clonar()
        os.symlink("no-existe", os.path.join(self.b, "Contents/roto"))
        man = INV.inventario(self.b)
        self.assertEqual(C.resolver_enlace(man, "Contents/roto")[0], "roto")

    def test_enlace_a_directorio_no_se_sigue(self):
        # Un enlace a directorio se registra como enlace; su contenido NO se
        # duplica en el inventario (evita ciclos y escapes por recorrido).
        self.clonar()
        os.symlink("Resources", os.path.join(self.b, "Contents/alias-dir"))
        man = INV.inventario(self.b)
        self.assertEqual(man["Contents/alias-dir"]["tipo"], "enlace")
        self.assertNotIn("Contents/alias-dir/createinstallmedia", man)

    def test_sustitucion_dmg_mismo_tamano(self):
        self.clonar()
        escribir(self.b, "Contents/SharedSupport/SharedSupport.dmg", b"E" * 4096)
        r = C.comparar(self.ref, INV.inventario(self.b))
        self.assertEqual(r.codigo, "CONTENIDO_ALTERADO")

    def test_sustitucion_cim(self):
        self.clonar()
        escribir(self.b, "Contents/Resources/createinstallmedia", b"cim-evil!")
        r = C.comparar(self.ref, INV.inventario(self.b))
        self.assertEqual(r.codigo, "CONTENIDO_ALTERADO")

    def test_manifiesto_derivado_de_alterado_no_pasa(self):
        # El manifiesto de un candidato alterado, comparado contra la
        # referencia, debe fallar: el manifiesto no es raíz de confianza.
        self.clonar()
        escribir(self.b, "Contents/Info.plist", b"plist-v2")
        derivado = INV.inventario(self.b)
        r = C.comparar(self.ref, derivado)
        self.assertFalse(r.ok)

    def test_hash_abreviado_no_es_sha256(self):
        # Los valores de 32 hex del log 03 NO deben aceptarse como SHA-256.
        man = dict(self.ref)
        man["Contents/Info.plist"] = dict(man["Contents/Info.plist"], sha256="a" * 32)
        with self.assertRaises(C.ComparadorError) as ctx:
            C.comparar(self.ref, man)
        self.assertEqual(ctx.exception.codigo, "MANIFIESTO_INVALIDO")

    def test_manifiesto_truncado_invalido(self):
        with self.assertRaises(C.ComparadorError) as ctx:
            C.comparar(self.ref, {"solo": {"tipo": "archivo"}})
        self.assertEqual(ctx.exception.codigo, "MANIFIESTO_INVALIDO")
        with self.assertRaises(C.ComparadorError):
            C.comparar(self.ref, "no-es-dict")

    def test_archivo_especial_rechazado(self):
        self.clonar()
        os.mkfifo(os.path.join(self.b, "Contents/tubo"))
        with self.assertRaises(INV.ErrorInventario) as ctx:
            INV.inventario(self.b)
        self.assertEqual(ctx.exception.codigo, "ESPECIAL_NO_PREVISTO")

    def test_fallo_herramienta_lectura(self):
        self.clonar()
        p = os.path.join(self.b, "Contents/Info.plist")
        os.chmod(p, 0)
        try:
            with self.assertRaises(INV.ErrorInventario) as ctx:
                INV.inventario(self.b)
            self.assertEqual(ctx.exception.codigo, "HERRAMIENTA_FALLO")
        finally:
            os.chmod(p, 0o644)

    def test_pin_pkg_ok_y_erroneos(self):
        p = os.path.join(self.tmp.name, "paquete.bin")
        with open(p, "wb") as f:
            f.write(b"P" * 1000)
        bueno = C.verificar_anclaje(p, 1000, sha(b"P" * 1000))
        self.assertEqual(bueno["tamano"], 1000)
        with self.assertRaises(C.ComparadorError):
            C.verificar_anclaje(p, 999, sha(b"P" * 1000))  # bytes
        with self.assertRaises(C.ComparadorError):
            C.verificar_anclaje(p, 1000, sha(b"Q" * 1000))  # hash
        with self.assertRaises(C.ComparadorError):
            C.verificar_anclaje(p, 1000, "a" * 32)  # abreviado
        with self.assertRaises(C.ComparadorError):
            C.verificar_anclaje(os.path.join(self.tmp.name, "ausente"), 0, sha(b""))

    def test_sustitucion_entre_observacion_y_uso(self):
        # Simula la ventana TOCTOU: inventariar, mutar, re-inventariar y
        # comparar contra el manifiesto original debe FALLAR. En operación se
        # exige re-verificar inmediatamente antes del efecto; la ventana
        # residual (lectura→uso) permanece y se documenta, no se elimina.
        self.clonar()
        manifiesto_previo = INV.inventario(self.b)
        escribir(self.b, "Contents/Info.plist", b"plist-v3")
        r = C.comparar(manifiesto_previo, INV.inventario(self.b))
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo, "CONTENIDO_ALTERADO")

    def test_transformacion_sharedsupport_explicita(self):
        payload = {"SharedSupport.dmg": {"tipo": "archivo", "tamano": 4,
                                         "sha256": sha(b"PAYL"), "destino": None}}
        reglas = {"SharedSupport.dmg": "Contents/SharedSupport/SharedSupport.dmg"}
        movido = C.aplicar_transformacion(payload, reglas)
        app = {"Contents/SharedSupport/SharedSupport.dmg": payload["SharedSupport.dmg"]}
        r = C.comparar(movido, app)
        self.assertTrue(r.ok)
        # Sin la regla declarada, el mismo par debe fallar (nada se infiere).
        with self.assertRaises(C.ComparadorError):
            C.aplicar_transformacion(payload, "no-dict")
        r2 = C.comparar(payload, app)
        self.assertFalse(r2.ok)

    def test_transformacion_rechaza_colision_y_ausencia(self):
        with self.assertRaises(C.ComparadorError):
            C.aplicar_transformacion({}, {"a": "b"})
        man = {"a": {"tipo": "archivo", "tamano": 1, "sha256": sha(b"1"), "destino": None},
               "b": {"tipo": "archivo", "tamano": 1, "sha256": sha(b"1"), "destino": None}}
        with self.assertRaises(C.ComparadorError):
            C.aplicar_transformacion(man, {"a": "b"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
