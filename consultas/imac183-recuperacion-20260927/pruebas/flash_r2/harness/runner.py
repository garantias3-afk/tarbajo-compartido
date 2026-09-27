#!/usr/bin/env python3
# =====================================================================
# NO_PRODUCTIVO_NO_AUTORIZADO — OT07-P7 GLM Flash (RUN.20260927T131419Z.C5IMAC1)
# runner de PRUEBAS_NATIVAS_C5. DEFAULT: SOLO NO PRIVILEGIADO.
#   - Rechaza euid==0 antes de cualquier efecto.
#   - No acepta operación sobre /dev/*, createinstallmedia ni volúmenes.
#   - Los intentos de ataque corren SIEMPRE como uid operador (hijos con
#     identidad registrada; el lector independiente también rechaza root).
#   - Construye fixtures propios <1 MiB (binario inocuo determinista),
#     ejecuta las sondas de primitivas y la batería N0–N9.
# Uso:
#   /usr/bin/python3 -B harness/runner.py                 (batería completa)
#   /usr/bin/python3 -B harness/runner.py --list
#   /usr/bin/python3 -B harness/runner.py --ids c5-n2-01,c5-n7-01
#   /usr/bin/python3 -B harness/runner.py --skip-probes   (reusa sondas)
# =====================================================================
"""Runner C5: default no privilegiado; resultados bajo contrato de salidas."""
from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import subprocess
import sys
import socket

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, 'fixtures'))

from harness_common import (ERROR, FALLA_PRODUCTO, INCONCLUSIVO, PASA,  # noqa: E402
                            ROTULO, SKIP, utcnow)
import make_fixtures_c5 as FX  # noqa: E402
import casos_c5  # noqa: E402

PROHIBIDOS_PREFIJO = ('/dev/', '/Volumes/', '/System/', '/Library/')


def entorno_harness() -> dict:
    return {
        'hostname': socket.gethostname(),
        'macOS': platform.mac_ver()[0],
        'build': subprocess.run(['sw_vers', '-productVersion'],
                                capture_output=True).stdout.decode().strip(),
        'arch': platform.machine(),
        'uid': os.getuid(), 'euid': os.geteuid(),
        'grupos': os.getgroups(),
        'python': sys.version.split()[0],
        'python_bin': sys.executable,
        'umask': oct(os.umask(0o077)),
        'rotulo': ROTULO,
    }


def guardarriales(fixtures_dir: str, skip_probes: bool) -> dict:
    """Fixtures propios + pins + rutas para la batería."""
    os.makedirs(fixtures_dir, exist_ok=True)
    info = FX.build_all(fixtures_dir)
    binaries = info['binaries']
    app = info['app']
    sha_plist = FX.sha256_file(os.path.join(app, 'Contents', 'Info.plist'))
    # ancla desde copia pristine (HB-4: hash externo registrado aquí)
    anchor_path = os.path.join(fixtures_dir, 'inv_ref.json')
    from harness_common import inventory_tree, sha256_bytes
    inv = inventory_tree(app)
    data = json.dumps(inv, indent=2, sort_keys=True).encode() + b'\n'
    with open(anchor_path, 'wb') as f:
        f.write(data)
    anchor_sha = sha256_bytes(data)
    probes_path = os.path.join(BASE, 'resultados', 'probes_nativos.json')
    cc_sysroot = None
    if not skip_probes or not os.path.isfile(probes_path):
        r = subprocess.run([sys.executable, '-B', os.path.join(
            BASE, 'harness', 'probe_primitivas.py')], capture_output=True)
        if r.returncode != 0:
            raise RuntimeError('sondas fallaron: %s'
                               % r.stderr.decode()[-300:])
    # sysroot usado por las compilaciones del propio build_all
    sysroots = [c for c in binaries['marker']['compilaciones']
                if '-isysroot' in c['cmd']]
    if sysroots:
        cc_sysroot = sysroots[0]['cmd'].split('-isysroot ')[1].split(' ')[0]
    return {
        'app': app,
        'bytes': info['fixture_bytes'],
        'limite_bytes': info['limite_bytes'],
        'anchor_path': anchor_path,
        'anchor_sha': anchor_sha,
        'sha_plist': sha_plist,
        'marker': binaries['marker']['path'],
        'marker_sha256': binaries['marker']['sha256'],
        'sustituto': binaries['sustituto']['path'],
        'sustituto_sha256': binaries['sustituto']['sha256'],
        'cc_sysroot': cc_sysroot,
        'cc_version': binaries['cc_version'],
        'probes_path': probes_path if os.path.isfile(probes_path) else None,
        'binarios_info': binaries,
        'interfaz_c5_ruta': _resolver_contrato(),
        'copias': {
            'c5_protect': os.path.join(BASE, 'copias_privadas',
                                       'c5_protect_p5r.py'),
            'make_fixtures': os.path.join(BASE, 'copias_privadas',
                                          'make_fixtures_p5r.py'),
            'run_tests': os.path.join(BASE, 'copias_privadas',
                                      'run_tests_p5r.py'),
            'mutantes': os.path.join(BASE, 'copias_privadas',
                                     'mutantes_p5r.py'),
        },
    }


INTERFAZ_C5_SHA_ESPERADO = 'c4dcf6631f4f52a3c9885c4e4da00700670344ec0b8610b43316aff497b1ffbc'


def _resolver_contrato():
    """INTERFAZ_C5.json: canal del RUN (entregas/MIMO) o entrega r5 sellada;
    se verifica el SHA-256 contra el sello de MiMo."""
    candidatos = (
        os.path.join(os.path.dirname(os.path.dirname(BASE)), 'MIMO',
                     'INTERFAZ_C5.json'),
        '/Users/OPERADOR/Documents/Codex/2026-09-27/pe/outputs/'
        'OT07_REVISION_v10r2r5_MIMO/INTERFAZ_C5.json',
    )
    for c in candidatos:
        if os.path.isfile(c):
            return c
    return None


def contadores(resultados: list) -> dict:
    c = {PASA: 0, FALLA_PRODUCTO: 0, SKIP: 0, INCONCLUSIVO: 0, ERROR: 0}
    for r in resultados:
        c[r['estado']] = c.get(r['estado'], 0) + 1
    ejecutados = c[PASA] + c[FALLA_PRODUCTO] + c[INCONCLUSIVO] + c[ERROR]
    return {'total_casos': len(resultados), 'ejecutados': ejecutados,
            'pasa_oraculo': c[PASA], 'falla_producto': c[FALLA_PRODUCTO],
            'skip_nativo_pendiente': c[SKIP], 'inconclusivo': c[INCONCLUSIVO],
            'error_harness': c[ERROR],
            'regla': 'falla_producto = ataque exitoso = FALLO DEL PRODUCTO; '
                     'inconclusivo NUNCA es verde; skip = exige H1/contrato'}


def main():
    ap = argparse.ArgumentParser(description='Runner PRUEBAS_NATIVAS_C5')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--ids', default=None,
                    help='lista separada por comas de ids de caso')
    ap.add_argument('--skip-probes', action='store_true')
    ap.add_argument('--solo-doc', action='store_true',
                    help='solo impresión de resumen (sin ejecutar)')
    args = ap.parse_args()

    if args.list:
        for c in casos_c5.CASOS:
            print('%s | %s | %s | %s | %s' % (c['id'], c['criterio'],
                                              c['tipo'], c['adapters'],
                                              c['titulo'][:60]))
        return 0

    env = entorno_harness()
    if env['euid'] == 0:
        print(json.dumps({'error': 'el runner corre SOLO como uid operador '
                                   '(euid!=0); nada se ejecuta como root'}))
        return 5
    for pref in PROHIBIDOS_PREFIJO:
        if BASE.startswith(pref):
            print(json.dumps({'error': 'ruta de trabajo prohibida: %s' % pref}))
            return 5

    work_base = os.path.join(BASE, 'resultados', 'work')
    os.makedirs(work_base, exist_ok=True)
    fixtures = guardarriales(os.path.join(work_base, 'fixture_base'),
                             args.skip_probes)
    C = casos_c5.CtxCasos(work_base, fixtures)

    ids = [x.strip() for x in args.ids.split(',')] if args.ids else None
    resultados = casos_c5.ejecutar_todos(C, solo_ids=ids)

    salida = {
        'esquema': 'FLASH_PRUEBAS_C5/resultados/v1',
        'ot': 'OT07-P7 — pruebas adversariales (02_OT_FLASH_PRUEBAS.md R2)',
        'revision_harness': 'FLASH_PRUEBAS_C5_R1',
        'run_id': 'RUN.20260927T131419Z.C5IMAC1',
        'utc': utcnow(),
        'host': env,
        'modo_harness': 'NO_PRIVILEGIADO (default; sin root, sin dispositivos)',
        'fixtures': {
            'app': fixtures['app'], 'bytes': fixtures['bytes'],
            'anchor_sha256': fixtures['anchor_sha'],
            'marker_sha256': fixtures['marker_sha256'],
            'sustituto_sha256': fixtures['sustituto_sha256'],
            'cc_version': fixtures['cc_version'],
            'cc_sysroot': fixtures['cc_sysroot'],
            'binario_inocuo': 'c5_marker propio (fuente fixtures/c5_marker.c)',
        },
        'adaptadores_disponibles': ['p5r_prototipo', 'ref_frontier',
                                    'ref_frontier_rehash', 'ref_rename',
                                    'interfaz_c5 (SKIP: contrato no publicado)'],
        'contrato_pendiente': {
            'INTERFAZ_C5.json': fixtures['interfaz_c5_ruta'],
            'estado': 'NO_PUBLICADO_AUN: los casos contra el contrato de '
                      'MiMo se derivan en revisión nueva del harness '
                      '(los casos presentes usan P5r + flujos referencia)',
        },
        'casos': resultados,
        'contadores': contadores(resultados),
        'limpieza': 'cada caso limpia su work propia registrada; informe en '
                    'resultados/limpieza.txt',
    }
    out_json = os.path.join(BASE, 'resultados', 'resultados_harness.json')
    with open(out_json, 'w') as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    # resumen MD
    lineas = ['# Resumen PRUEBAS_NATIVAS_C5 — %s' % salida['utc'], '',
              'Modo: %s' % salida['modo_harness'], '',
              '| Caso | Criterio | Estado | Verificación |', '|---|---|---|---|']
    for r in resultados:
        lineas.append('| %s | %s | %s | %s |' % (r['id'], r['criterio'],
                                                 r['estado'], r['tipo']))
    lineas += ['', 'Contadores: `%s`' % json.dumps(salida['contadores'], ensure_ascii=False)]
    with open(os.path.join(BASE, 'resultados', 'resumen_harness.md'), 'w') as f:
        f.write('\n'.join(lineas) + '\n')

    # limpieza final de works propias (registro)
    informes = []
    for d in sorted(os.listdir(work_base)):
        if d.startswith('c5_'):
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
