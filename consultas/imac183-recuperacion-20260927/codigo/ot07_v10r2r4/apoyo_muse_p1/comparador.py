#!/usr/bin/python3
"""P1 — comparador de referencia: API pura y contrato de errores.

Compara un manifiesto ESPERADO (p. ej. derivado del PKG pineado por medición
independiente) contra un manifiesto OBTENIDO (inventario fresco del candidato
o colocado). Todo es datos ya leídos: esta unidad no toca disco.

Contrato:
- El desajuste de contenido es un RESULTADO (ok=False + código), no excepción.
- La entrada inválida o la herramienta rota es EXCEPCIÓN ComparadorError.
- DMG/CIM sustituidos se detectan como CONTENIDO_ALTERADO en su ruta: el
  mismo mecanismo hash, sin caso especial que oculte.
- Los enlaces se juzgan por destino literal MÁS resolución transitiva acotada
  dentro del propio manifiesto (sin tocar disco): absoluto, escape por ..,
  ciclo y roto se rechazan; interno válido se acepta.
- La transformación autorizada (p. ej. SharedSupport.dmg de nivel PKG a
  Contents/SharedSupport/ de la app) es una tabla explícita origen→destino
  aplicada por `aplicar_transformacion`; nada se infiere por similitud.

Códigos de resultado: OK, FALTANTE, EXTRA, TIPO_CAMBIADO,
CONTENIDO_ALTERADO, ENLACE_SALIENTE, ENLACE_CICLICO, ENLACE_ROTO,
ESPECIAL_NO_PREVISTO.
Códigos de excepción: MANIFIESTO_INVALIDO, HERRAMIENTA_FALLO (reservado),
TRANSFORMACION_INVALIDA.
"""
import sys

CODIGOS_RESULTADO = ("OK", "FALTANTE", "EXTRA", "TIPO_CAMBIADO",
                     "CONTENIDO_ALTERADO", "ENLACE_SALIENTE",
                     "ENLACE_CICLICO", "ENLACE_ROTO",
                     "ESPECIAL_NO_PREVISTO")


class ComparadorError(Exception):
    def __init__(self, codigo, detalle=""):
        super().__init__(codigo + (": " + detalle if detalle else ""))
        self.codigo = codigo
        self.detalle = detalle


class Resultado:
    def __init__(self, ok, codigo, detalles):
        self.ok = ok
        self.codigo = codigo
        self.detalles = list(detalles)

    def __repr__(self):
        return "Resultado(ok=%r, codigo=%r, detalles=%r)" % (
            self.ok, self.codigo, self.detalles)


def _validar_manifiesto(manifest, quien):
    if not isinstance(manifest, dict):
        raise ComparadorError("MANIFIESTO_INVALIDO", quien + " no es dict")
    for ruta, reg in manifest.items():
        if not isinstance(ruta, str) or not ruta or ruta.startswith("/"):
            raise ComparadorError("MANIFIESTO_INVALIDO", quien + " ruta: %r" % (ruta,))
        if not isinstance(reg, dict) or reg.get("tipo") not in ("archivo", "directorio", "enlace"):
            raise ComparadorError("MANIFIESTO_INVALIDO", quien + " registro: %s" % ruta)
        if reg["tipo"] == "archivo" and (
                not isinstance(reg.get("tamano"), int) or not isinstance(reg.get("sha256"), str)
                or len(reg["sha256"]) != 64):
            raise ComparadorError("MANIFIESTO_INVALIDO", quien + " hash: %s" % ruta)
        if reg["tipo"] == "enlace" and not isinstance(reg.get("destino"), str):
            raise ComparadorError("MANIFIESTO_INVALIDO", quien + " destino: %s" % ruta)
    return manifest


def _unir(base_dir, destino):
    """Une destino al directorio del enlace y normaliza. Devuelve
    (escapo: bool, ruta_normalizada). Solo el escaping real desde la raíz
    cuenta como saliente; los .. intermedios válidos se permiten."""
    if destino.startswith("/"):
        return True, destino
    partes = []
    escapo = False
    for parte in (base_dir + "/" + destino).split("/"):
        if parte in ("", "."):
            continue
        if parte == "..":
            if partes:
                partes.pop()
            else:
                escapo = True
        else:
            partes.append(parte)
    return escapo, "/".join(partes)


def resolver_enlace(manifest, ruta, max_saltos=40):
    """Sigue la cadena dentro del manifiesto. Devuelve ('ok', ruta_final),
    ('roto', donde), ('ciclico', donde) o ('saliente', donde). Sin disco."""
    vistos = set()
    actual = ruta
    for _ in range(max_saltos + 1):
        if actual in vistos:
            return ("ciclico", actual)
        vistos.add(actual)
        reg = manifest.get(actual)
        if reg is None:
            return ("roto", actual)
        if reg["tipo"] != "enlace":
            return ("ok", actual)
        base = actual.rsplit("/", 1)[0] if "/" in actual else ""
        escapo, actual = _unir(base, reg["destino"])
        if escapo:
            return ("saliente", actual)
    return ("ciclico", actual)


def aplicar_transformacion(manifest, reglas):
    """Reubica entradas según tabla explícita {origen: destino}. Pura."""
    _validar_manifiesto(manifest, "manifiesto")
    if not isinstance(reglas, dict):
        raise ComparadorError("TRANSFORMACION_INVALIDA", "reglas no es dict")
    for origen, destino in reglas.items():
        if not isinstance(origen, str) or not isinstance(destino, str) \
                or not origen or not destino or destino.startswith("/"):
            raise ComparadorError("TRANSFORMACION_INVALIDA", "%r -> %r" % (origen, destino))
        if origen not in manifest:
            raise ComparadorError("TRANSFORMACION_INVALIDA", "origen ausente: " + origen)
        if destino in manifest and destino not in reglas:
            raise ComparadorError("TRANSFORMACION_INVALIDA", "destino colisiona: " + destino)
    nuevo = dict(manifest)
    for origen, destino in reglas.items():
        nuevo[destino] = nuevo.pop(origen)
    return nuevo


def comparar(esperado, obtenido):
    """Compara dos manifiestos ya validados. Nunca toca disco."""
    _validar_manifiesto(esperado, "esperado")
    _validar_manifiesto(obtenido, "obtenido")
    detalles = []
    for ruta in sorted(set(esperado) - set(obtenido)):
        detalles.append(("FALTANTE", ruta))
    for ruta in sorted(set(obtenido) - set(esperado)):
        detalles.append(("EXTRA", ruta))
    for ruta in sorted(set(esperado) & set(obtenido)):
        exp, got = esperado[ruta], obtenido[ruta]
        if exp["tipo"] != got["tipo"]:
            detalles.append(("TIPO_CAMBIADO", "%s: %s -> %s" % (ruta, exp["tipo"], got["tipo"])))
            continue
        if exp["tipo"] == "archivo":
            if exp["tamano"] != got["tamano"] or exp["sha256"] != got["sha256"]:
                detalles.append(("CONTENIDO_ALTERADO",
                                 "%s: tamano %r->%r" % (ruta, exp["tamano"], got["tamano"])))
        elif exp["tipo"] == "enlace":
            if exp["destino"] != got["destino"]:
                detalles.append(("CONTENIDO_ALTERADO", "%s: destino %r->%r"
                                 % (ruta, exp["destino"], got["destino"])))
    # Política de enlaces sobre el árbol obtenido (aunque coincida con esperado,
    # un esperado con salientes también debe fallar: se juzgan ambos).
    for nombre, manifest in (("esperado", esperado), ("obtenido", obtenido)):
        for ruta in sorted(manifest):
            if manifest[ruta]["tipo"] != "enlace":
                continue
            estado, donde = resolver_enlace(manifest, ruta)
            if estado != "ok":
                detalles.append(({"saliente": "ENLACE_SALIENTE",
                                  "ciclico": "ENLACE_CICLICO",
                                  "roto": "ENLACE_ROTO"}[estado],
                                 "%s:%s sigue a %s" % (nombre, ruta, donde)))
    # Tipos especiales no previstos en manifiestos construidos a mano.
    for nombre, manifest in (("esperado", esperado), ("obtenido", obtenido)):
        for ruta in sorted(manifest):
            if manifest[ruta]["tipo"] not in ("archivo", "directorio", "enlace"):
                detalles.append(("ESPECIAL_NO_PREVISTO", "%s:%s" % (nombre, ruta)))
    if not detalles:
        return Resultado(True, "OK", [])
    # La política de enlaces y tipos especiales precede a la diferencia de
    # conjuntos: un extra saliente es ante todo saliente.
    jerarquia = {"ENLACE_SALIENTE": 0, "ENLACE_CICLICO": 1, "ENLACE_ROTO": 2,
                 "ESPECIAL_NO_PREVISTO": 3, "FALTANTE": 4, "EXTRA": 5,
                 "TIPO_CAMBIADO": 6, "CONTENIDO_ALTERADO": 7}
    codigo = sorted((c for c, _ in detalles), key=lambda c: jerarquia.get(c, 99))[0]
    return Resultado(False, codigo, detalles)


def verificar_anclaje(ruta, tamano_esperado, sha_esperado):
    """Pin de un archivo (p. ej. PKG): existencia + tamaño exacto + SHA-256
    completo. Excepción si algo difiere o la lectura falla. Nunca acepta
    hashes abreviados: sha_esperado debe tener 64 hex."""
    import os
    if not isinstance(sha_esperado, str) or len(sha_esperado) != 64:
        raise ComparadorError("ANCLAJE_INVALIDO", "se exige SHA-256 completo de 64 hex")
    try:
        st = os.stat(ruta)
    except OSError as e:
        raise ComparadorError("HERRAMIENTA_FALLO", "%s: %s" % (ruta, e))
    import stat as _stat
    if not _stat.S_ISREG(st.st_mode):
        raise ComparadorError("ANCLAJE_FALLIDO", "%s no es archivo regular" % ruta)
    if st.st_size != tamano_esperado:
        raise ComparadorError("ANCLAJE_FALLIDO",
                              "%s bytes %d != %d" % (ruta, st.st_size, tamano_esperado))
    import hashlib
    h = hashlib.sha256()
    try:
        with open(ruta, "rb") as f:
            for bloque in iter(lambda: f.read(1024 * 1024), b""):
                h.update(bloque)
    except OSError as e:
        raise ComparadorError("HERRAMIENTA_FALLO", "%s: %s" % (ruta, e))
    if h.hexdigest() != sha_esperado.lower():
        raise ComparadorError("ANCLAJE_FALLIDO", "%s SHA no coincide" % ruta)
    return {"ruta": ruta, "tamano": st.st_size, "sha256": h.hexdigest()}


if __name__ == "__main__":
    print("comparador de referencia P1: importar comparar/aplicar_transformacion/resolver_enlace",
          file=sys.stderr)
