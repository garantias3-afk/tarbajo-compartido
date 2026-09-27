#!/usr/bin/python3
"""P1 — adaptador para aplicar las pruebas a la implementación real de MiMo
sin reescribir sus expectativas.

MiMo conserva libertad de API. Este adaptador solo exige un punto de entrada
compatible; si su firma difiere, editar ÚNICAMENTE `envolver_mimo()`.

Contrato esperado del comparador real (documentar desvíos, no adaptarlos en
silencio):
  comparar(esperado: dict, obtenido: dict) -> objeto con .ok (bool),
      .codigo (str) y .detalles (lista).
  Debe cubrir los códigos P1 de tests/test_comparador.py; la tabla
  TRADUCCION_CODIGOS registra equivalencias declaradas por MiMo y la
  herramienta informa códigos no mapeados como INADAPTADO (fallo del adaptador,
  no del árbol).

Uso:
  python3 -B adaptador_mimo.py /ruta/a/comparador_mimo.py
"""
import importlib.util
import sys

# Rellenar cuando MiMo publique su API. Clave: código MiMo; valor: código P1.
# Vacío = exigir códigos P1 literales.
TRADUCCION_CODIGOS = {}


def cargar_comparador(ruta):
    spec = importlib.util.spec_from_file_location("comparador_mimo", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    if not hasattr(modulo, "comparar"):
        raise SystemExit("ADAPTADOR: %s no expone comparar(esperado, obtenido)" % ruta)
    return modulo


def envolver_mimo(modulo):
    """Traduce el resultado de MiMo al contrato P1. Editar solo aquí."""
    def comparar(esperado, obtenido):
        resultado = modulo.comparar(esperado, obtenido)
        codigo = TRADUCCION_CODIGOS.get(resultado.codigo, resultado.codigo)
        return resultado.ok, codigo, list(resultado.detalles)
    return comparar


def main(argv):
    if len(argv) != 2:
        print("uso: adaptador_mimo.py <comparador_mimo.py>", file=sys.stderr)
        return 2
    modulo = cargar_comparador(argv[1])
    comparar = envolver_mimo(modulo)
    # Autoprueba mínima del adaptador (no sustituye la suite):
    ok, codigo, _ = comparar({}, {})
    print("ADAPTADOR_OK" if ok and codigo == "OK" else "ADAPTADOR_RECHAZADO: %r" % (codigo,))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
