# INDICE_HISTORICO.md — F-4 (matrices y evidencia histórica)

## Matrices: cuál es vigente

| Documento | ¿Vigente? | Nota |
|---|---|---|
| **`MATRIZ_F_G.md`** (r3) | **SÍ** | Disposición F/G |
| **`MATRIZ_APOYOS.md`** (r3) | **SÍ** | P2/P3/P4 |
| **`MATRIZ_M1_M10.md`** | Sí (cierre r2) | M-1…M-10 |
| `MATRIZ_C1_C10.md` | Histórico r2 | C-1…C-10 |
| `MATRIZ_INTEGRACION.md` | Histórico r2 | Muse/Flash P2 |
| `MATRIZ_P2` / `P3` / `P4` | Apoyos Flash | **No** son estado del producto |
| Dossiers v7–v10 | Histórico | — |

## Política de espacio (C-9) — vigente

**`du` del origen + 2 GiB reserva** vs `df` del padre destino, con RC y entero
positivo validados (`place_helper.space-check`). **No** 38+20 GiB ni 131/146 tests.

## Conteos vigentes (r3)

| Batería | Cantidad |
|---|---|
| Suite completa | **174** (contar al sellar) |
| F-1 arnés | 9 |
| F-5 TMPDIR | 4 |
| Productivos .sh/.py | byte-idénticos a r2 |

## Evidencia histórica sellada

Se **copian bytes intactos** a `referencias/` cuando se cite; se identifican como
históricas en este índice. **No** se editan logs ni se fabrican RC pretéritos.

## CP0–CP5

`OT07_PREPARAR_PEN_BOOTEO.md` describe el procedimiento histórico de E.
**No es orden operativa vigente** de r3. Su hash se conserva en `ALCANCE_R3.md`.
