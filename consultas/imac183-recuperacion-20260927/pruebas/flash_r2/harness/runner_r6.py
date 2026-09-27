#!/usr/bin/env python3
# =====================================================================
# NO_PRODUCTIVO_NO_AUTORIZADO — OT07-P7 GLM Flash R2 (RUN.20260927T131419Z.C5IMAC1)
# runner_r6 — batería FLASH completa contra el ORQUESTADOR REAL r6:
#   (1) regresión: los 51 casos de R1 (adaptadores P5r/ref) re-ejecutados
#   (2) 15 casos específicos r6 (sut_r6, modo simulated/fixture_ensayo)
# DEFAULT NO PRIVILEGIADO: rechaza euid==0; sin dispositivos; el caso que
# exige H1 queda SKIP. El producto r6 corre SOLO desde copia privada.
# Uso: /usr/bin/python3 -B harness/runner_r6.py [--list] [--ids id1,id2]
#      [--solo-r6] [--solo-r1]
# =====================================================================
"""Runner R2: batería FLASH×r6."""
from __future__ import annotations

import argparse
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, 'fixtures'))

from harness_common import utcnow  # noqa: E402
import casos_c5  # noqa: E402
import casos_r6  # noqa: E402
from casos_r6 import CtxR6  # noqa: E402
from runner import (BASE as _B, contadores, entorno_harness,  # noqa: E402
                    guardarriales)

SRC_R6 = os.path.join(BASE, 'copias_privadas', 'r6')


def main():
    ap = argparse.ArgumentParser(description='Runner FLASH×r6 (R2)')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--ids', default=None)
    ap.add_argument('--solo-r6', action='store_true')
    ap.add_argument('--solo-r1', action='store_true')
    args = ap.parse_args()

    if args.list:
        for c in casos_c5.CASOS:
            print('R1 %s | %s | %s' % (c['id'], c['criterio'], c['tipo']))
        for c in casos_r6.CASOS_R6:
            print('R6 %s | %s | %s' % (c['id'], c['criterio'], c['tipo']))
        return 0

    env = entorno_harness()
    if env['euid'] == 0:
        print(json.dumps({'error': 'el runner corre SOLO como uid operador'}))
        return 5

    work_base = os.path.join(BASE, 'resultados', 'work')
    os.makedirs(work_base, exist_ok=True)
    fixtures = guardarriales(os.path.join(work_base, 'fixture_base'),
                             skip_probes=False)
    C = casos_c5.CtxCasos(work_base, fixtures)
    X = CtxR6(C, SRC_R6)

    ids = [x.strip() for x in args.ids.split(',')] if args.ids else None
    resultados = []
    if not args.solo_r6:
        resultados += casos_c5.ejecutar_todos(C, solo_ids=ids)
    if not args.solo_r1:
        resultados += casos_r6.ejecutar_r6(X, solo_ids=ids)

    salida = {
        'esquema': 'FLASH_PRUEBAS_C5/resultados/v1',
        'revision_harness': 'FLASH_PRUEBAS_C5_R2',
        'run_id': 'RUN.20260927T131419Z.C5IMAC1',
        'utc': utcnow(),
        'host': env,
        'modo_harness': 'NO_PRIVILEGIADO (default; sin root, sin dispositivos)',
        'sut': {
            'producto': 'OT07_REVISION_v10r2r6_MIMO (src/c5_orquestador.py)',
            'ejecucion': 'SOLO desde copia privada (insumo sellado nunca '
                         'in-place)',
            'sha_orquestador_copia': X.ad.sha_orquestador,
            'modo': 'simulated / fixture_ensayo',
            'contrato': 'INTERFAZ_C5.json R5-CONTRATO-1 SIN cambios '
                        '(c4dcf6631f4f52a3c9885c4e4da00700670344ec0b8610b43316aff497b1ffbc)',
            'revision_max': 'CANDIDATO_R6_REVISADO_ACEPTADO '
                            '(REVISION_MAX_R6.md); R6-1 reproducida aquí',
        },
        'referencias_max_incorporadas': [
            'en simulated el fd del dueño sobre staging sigue abriendo '
            '(limitación sin root; frontera nativa en helper) → medido aquí '
            'con instrumentación determinista (c5-r6-05, SKIP H1)',
            'micro-ventana de swap publicó el sustituto y F9 lo captura con '
            'rc=4 → reproducida independientemente (c5-r6-08, MUT-R6-D)',
        ],
        'fixtures': {
            'app': fixtures['app'], 'bytes': fixtures['bytes'],
            'anchor_sha256_r6_formato': 'por caso (inventory_tree del propio '
                                        'producto)',
            'marker_sha256': fixtures['marker_sha256'],
            'sustituto_sha256': fixtures['sustituto_sha256'],
        },
        'casos': resultados,
        'contadores': contadores(resultados),
    }
    out_json = os.path.join(BASE, 'resultados', 'resultados_harness_r6.json')
    with open(out_json, 'w') as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    lineas = ['# Resumen FLASH×r6 — %s' % salida['utc'], '',
              '| Caso | Criterio | Estado | Tipo |', '|---|---|---|---|']
    for r in resultados:
        lineas.append('| %s | %s | %s | %s |' % (r['id'], r['criterio'],
                                                 r['estado'], r['tipo']))
    lineas += ['', 'Contadores: `%s`' % json.dumps(salida['contadores'],
                                                   ensure_ascii=False)]
    with open(os.path.join(BASE, 'resultados', 'resumen_r6.md'), 'w') as f:
        f.write('\n'.join(lineas) + '\n')

    informes = []
    for d in sorted(os.listdir(work_base)):
        if d.startswith('c5_') or d.startswith('r6_'):
            informes += C.limpiar_work(os.path.join(work_base, d))
    with open(os.path.join(BASE, 'resultados', 'limpieza.txt'), 'w') as f:
        for i in informes:
            f.write(json.dumps(i, ensure_ascii=False) + '\n')

    print(json.dumps(salida['contadores'], ensure_ascii=False))
    print('JSON: %s' % out_json)
    return 0 if salida['contadores']['error_harness'] == 0 else 1


if __name__ == '__main__':
    os.umask(0o077)
    sys.exit(main())
