#!/usr/bin/env python3
# =====================================================================
# NO_PRODUCTIVO_NO_AUTORIZADO — OT07-P7 GLM Flash (RUN.20260927T131419Z.C5IMAC1)
# mutadores — sensibilidad del harness: UNA mutación por copia privada,
# anclaje único exigido (count==1), aserción prevista registrada. La base
# positiva debe PASAR y el mutante debe ser detectado POR LA ASERCIÓN
# PREVISTA; un helper que falla antes del punto ensayado produce
# INCONCLUSIVO, jamás verde.
#   MUT-A2  sut_adapters.py: instantánea del ancla → relectura en F5
#           (detecta c5-n5-04-snapshot-no-fijada)
#   MUT-C1  comparador.py: ignora ACE allow al comparar
#           (detecta c5-n3-05-bypass-acl-sensibilidad)
#   REF-RENAME: variante de diseño (publicar staging por rename en vez de
#           frontera con inodos nuevos) — detecta c5-n2-01/02/04
#   FAKE-OK: SUT falso que devuelve rc=0 sin efectos — el harness NO puede
#           dar verde sin efectos medidos (c5-n9-03)
# =====================================================================
"""Mutadores controlados del harness C5."""
from __future__ import annotations

import hashlib
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_common import sha256_file  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def mutar_copia(src_path: str, tag: str, old: str, new: str, work: str):
    """Copia privada con UNA mutación; exige anclaje único del fragmento."""
    with open(src_path, 'r', encoding='utf-8') as f:
        src = f.read()
    n = src.count(old)
    if n != 1:
        raise RuntimeError('mutante %s: anclaje no único (%d) en %s'
                           % (tag, n, src_path))
    mut = src.replace(old, new)
    path = os.path.join(work, 'mut_%s.py' % tag)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(mut)
    return {'tag': tag, 'path': path,
            'sha_base': sha256_file(src_path), 'sha_mutante': sha256_file(path)}


def cargar_modulo(path: str, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


def mutante_sut_adapters(work: str, tag: str = 'A2'):
    """MUT-A2: F5 relee el ancla en vez de usar la instantánea de F1."""
    info = mutar_copia(
        os.path.join(HERE, 'sut_adapters.py'), tag,
        old="            inv_st = inventory_tree(leaf)\n",
        new="            inv_st = inventory_tree(leaf)\n"
            "            inv_ref = json.loads(open(ctx['anchor_path'], 'rb')"
            ".read().decode())  # MUT-A2: relectura del ancla\n",
        work=work)
    mod = cargar_modulo(info['path'], 'sut_adapters_mut_%s' % tag)
    return info, mod


def mutante_comparador(work: str, tag: str = 'C1'):
    """MUT-C1: el comparador ignora la ACE allow medida."""
    info = mutar_copia(
        os.path.join(HERE, 'comparador.py'), tag,
        old="    if verificar_acl and medicion.get('ace_allow_encontrada') and \\\n            not afirmacion.get('acl_allow_afirmada', False):",
        new="    if False and medicion.get('ace_allow_encontrada') and \\\n            not afirmacion.get('acl_allow_afirmada', False):  # MUT-C1",
        work=work)
    mod = cargar_modulo(info['path'], 'comparador_mut_%s' % tag)
    return info, mod


class FakeSutSiempreOk:
    """SUT falso: verdict verde sin efectos ni medición. Sirve SOLO para
    probar que el harness no otorga verde sin evidencia (c5-n9-03)."""
    name = 'fake_siempre_ok'
    hooks_disponibles = []

    def place(self, ctx, faults=None):
        return {'adapter': self.name, 'verdict': 'COLOCADO_PROTEGIDO_VERIFICADO',
                'rc': 0, 'published': True, 'staging': None,
                'staging_parent': None, 'destino': ctx['destino'],
                'cleanup_ok': True, 'ino_map': {}, 'events': [], 'uso': None,
                'owner_ledger': {}}

    def use_published(self, result, ctx, faults=None):
        return {'resultado': 'EJECUTADO', 'stdout': 'C5_FIXTURE_VERIFICADO',
                'binding': 'fake'}


def registrar_mutantes_regresion_p5r(suite_dir: str) -> list:
    """MUT-M1..M3 de P5r: se ejecutan dentro de la suite de regresión
    (run_tests_p5r.py) en su disposición sellada; aquí solo se declaran."""
    return [
        {'id': 'MUT-M1', 'origen': 'P5r', 'criterio': 'N1',
         'descripcion': 'omisión de revalidación de la RAÍZ (HB-1)',
         'detectado_por': 'R01/R02/R03 (suite P5r) · equivalente c5-n1-03/04'},
        {'id': 'MUT-M2', 'origen': 'P5r', 'criterio': 'N3',
         'descripcion': 'ledger de ACL por ruta mutable (HB-2)',
         'detectado_por': 'R04 (suite P5r) · equivalente c5-n3-01'},
        {'id': 'MUT-M3', 'origen': 'P5r', 'criterio': 'N6',
         'descripcion': 'etiqueta incondicional SIN_EFECTOS (HB-3)',
         'detectado_por': 'R10 (suite P5r) · equivalente c5-n6-03/07'},
    ]
