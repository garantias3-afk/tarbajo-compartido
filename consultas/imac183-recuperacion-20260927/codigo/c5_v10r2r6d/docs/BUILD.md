# BUILD.md — compilación reproducible del candidato r5

## Entorno medido (no asumir)

| Campo | Valor |
|---|---|
| host | HOST_PREPARACION.local |
| macOS | 26.6.2 (25G83) |
| arch | arm64 |
| uid | 501 (OPERADOR) |
| clang | Apple clang version 21.0.0 (clang-2100.1.1.101) |
| python | 3.9.6 |
| SDK usado | `MacOSX26.5.sdk` (el `MacOSX27.0.sdk` del CLT falla el linker: `libSystem.B.tbd` malformado / `arm64e.x1` desconocido) |

## Comando exacto

```bash
umask 077
export PYTHONDONTWRITEBYTECODE=1
clang -O2 -Wall -Wextra -std=c11 -mmacosx-version-min=14.0 \
  -isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk \
  -o build/c5_helper src/c5_helper.c
```

Flags: `-O2 -Wall -Wextra -std=c11 -mmacosx-version-min=14.0`. Sin LTO, sin bitcode.

## Verificación post-build

```bash
./build/c5_helper selfcheck
./build/c5_helper probe-at src/c5_helper.c
```

## Constantes SDK verificadas (no inventadas)

| Constante | Valor | Fuente |
|---|---|---|
| `AT_UNIQUE` | `0x8000` | `sys/fcntl.h:187` |
| `RENAME_EXCL` | `0x00000004` | `sys/stdio.h:37` |
| `RENAME_NOFOLLOW_ANY` | `0x00000010` | `sys/stdio.h:39` (**no** 0x80) |
| `lchown` | syscall `lchown(2)` | no hay binario `lchown` en el host |
| `RESOLVE_BENEATH` | **no existe en macOS** | no se porta |

## Regresión del fix de constantes

La primera corrida del harness falló 5 casos (N1-01, N6-02/03/04, N8-01) con
`errno=22 EINVAL` en `renamex_np`. Causa: `RENAME_NOFOLLOW_ANY` tomado como
`0x80` (valor incorrecto). Corregido a `0x10` según `sys/stdio.h`. Ver
`evidencia_r5/HARNESS_RESULTADOS.json` (versión final) y `evidencia_r5/SENSIBILIDAD.json`.

## Uso del Python

```bash
python3 -B src/c5_orquestador.py run --priv simulated ...
python3 -B src/c5_bootstrap.py .
python3 -B tests/harness_r5.py
```

Nunca `sudo python3`. El helper C es el único binario destinado a H1.
