#!/usr/bin/python3
"""P1 — inventario de referencia sin seguir enlaces.

Recorre un árbol SIN seguir ningún symlink (ni en el recorrido ni en la
lectura): usa lstat/scandir con follow_symlinks=False en cada entrada.
Registra por ruta relativa: tipo, tamaño/hash para regulares, destino para
enlaces, presencia de directorios. Rechaza archivos especiales.

No ejecuta nada, no monta, no requiere privilegios. Solo lectura del árbol
indicado. La ventana observación→uso (TOCTOU) no queda eliminada por este
módulo: quien lo use debe inventariar de nuevo inmediatamente antes de
cualquier efecto persistente y documentar la ventana residual.
"""
import hashlib
import json
import os
import stat
import sys

CHUNK = 1024 * 1024


class ErrorInventario(Exception):
    """Fallo de herramienta o entrada no prevista. Mensaje = código legible."""

    def __init__(self, codigo, detalle=""):
        super().__init__(codigo + (": " + detalle if detalle else ""))
        self.codigo = codigo
        self.detalle = detalle


def sha256_archivo(path):
    """Hash streaming; distingue E/S fallida (excepción) de archivo vacío."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for bloque in iter(lambda: f.read(CHUNK), b""):
                h.update(bloque)
    except OSError as e:
        raise ErrorInventario("HERRAMIENTA_FALLO", "%s: %s" % (path, e))
    return h.hexdigest()


def _relativa(root, path):
    rel = os.path.relpath(path, root)
    if rel.startswith(".."):
        raise ErrorInventario("RUTA_FUERA_DE_RAIZ", rel)
    return rel


def inventario(root):
    """Devuelve dict {relpath: registro}. Determinista (claves ordenadas)."""
    st = os.lstat(root)
    if not stat.S_ISDIR(st.st_mode):
        raise ErrorInventario("RAIZ_NO_ES_DIRECTORIO", root)
    if os.path.islink(root):
        raise ErrorInventario("RAIZ_ES_ENLACE", root)
    registros = {}

    def visitar(path):
        try:
            with os.scandir(path) as it:
                entradas = sorted(it, key=lambda e: e.name)
        except OSError as e:
            raise ErrorInventario("HERRAMIENTA_FALLO", "%s: %s" % (path, e))
        for entrada in entradas:
            try:
                info = entrada.stat(follow_symlinks=False)
            except OSError as e:
                raise ErrorInventario("HERRAMIENTA_FALLO", "%s: %s" % (entrada.path, e))
            modo = info.st_mode
            rel = _relativa(root, entrada.path)
            if entrada.is_symlink():
                try:
                    destino = os.readlink(entrada.path)
                except OSError as e:
                    raise ErrorInventario("HERRAMIENTA_FALLO", "%s: %s" % (entrada.path, e))
                registros[rel] = {"tipo": "enlace", "tamano": None,
                                  "sha256": None, "destino": destino}
            elif stat.S_ISDIR(modo):
                registros[rel] = {"tipo": "directorio", "tamano": None,
                                  "sha256": None, "destino": None}
                visitar(entrada.path)
            elif stat.S_ISREG(modo):
                registros[rel] = {"tipo": "archivo",
                                  "tamano": info.st_size,
                                  "sha256": sha256_archivo(entrada.path),
                                  "destino": None}
            else:
                raise ErrorInventario("ESPECIAL_NO_PREVISTO",
                                      "%s modo=%o" % (rel, stat.S_IFMT(modo)))

    visitar(root)
    return dict(sorted(registros.items()))


def main(argv):
    if len(argv) != 2 or argv[0] in ("-h", "--help"):
        print("uso: inventario.py <arbol>  -> manifiesto JSON en stdout", file=sys.stderr)
        return 2
    try:
        print(json.dumps(inventario(argv[1]), indent=2, sort_keys=True))
    except ErrorInventario as e:
        print("INVENTARIO_FALLO: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
