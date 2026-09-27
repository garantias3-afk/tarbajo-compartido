# Reproducción acotada de la suite C5

Esta es la reproducción sin privilegios realizada durante la preparación. **No es ensayo nativo H1**. Leer primero el harness y usar una copia descartable: escribe su propio archivo `evidencia_r6d/HARNESS_RESULTADOS.json`, reemplazando el resultado histórico de esa copia.

Entorno utilizado: macOS 26.6.2, arm64, usuario normal, Python 3.9.6, Apple clang 21.0.0, SDK 26.5. Los originales públicos no incluyen `build/c5_helper` ni directorios vacíos. Sin ese binario, los casos H-R5-5a/H-R5-5b fallaron; los otros 57 pasaron.

Desde la raíz de esta consulta, preparar la copia en un directorio temporal NUEVO:

```sh
ensayo_c5=$(mktemp -d "${TMPDIR:-/tmp}/c5-cloud-review.XXXXXX")
cp -R codigo/c5_v10r2r6d "$ensayo_c5/candidato"
mkdir -p "$ensayo_c5/candidato/fixtures" "$ensayo_c5/candidato/build"
clang -O2 -Wall -Wextra -std=c11 -mmacosx-version-min=14.0 \
  -isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk \
  -o "$ensayo_c5/candidato/build/c5_helper" \
  "$ensayo_c5/candidato/src/c5_helper.c"
```

Solo si la compilación terminó con RC=0, ejecutar sin sudo:

```sh
python3 -B "$ensayo_c5/candidato/tests/harness_r5.py"
```

En esta entrega devolvió 59/59 y RC=0. El hash del helper recompilado coincidió con el histórico de r6d. Las llamadas al helper de esa suite se limitan a selfcheck y rechazo de cleanup fuera de frontera; la copia/protección/publicación privilegiadas no se ejecutan. Parte de las pruebas usa operaciones reales sin privilegios sobre fixtures y parte mocks/ledger o inspecciones textuales. Hay fallback condicional en algunas pruebas, aunque el contador de skips impreso sea cero.

En Linux o sin ese SDK, registrar lo no ejecutable y mantener pendientes las pruebas Darwin; no sustituir la implementación macOS por un stub y declarar equivalencia. No ejecutar `docs/H1_A_REEJECUCION.sh` para compensar. La suite de r4 y la de Flash se entregan para auditoría, pero no fueron ejecutadas durante esta publicación.
