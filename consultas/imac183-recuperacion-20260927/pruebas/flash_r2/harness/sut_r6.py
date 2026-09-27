#!/usr/bin/env python3
# =====================================================================
# NO_PRODUCTIVO_NO_AUTORIZADO — OT07-P7 GLM Flash R2 (RUN.20260927T131419Z.C5IMAC1)
# sut_r6 — adaptador de la batería FLASH hacia el ORQUESTADOR REAL r6
# (src/c5_orquestador.py de OT07_REVISION_v10r2r6_MIMO, copia privada).
#   - place(): traduce ctx del harness a la firma r6; faults SOLO
#     booleanos (r6 no define hooks de callback); veredictos ya en el
#     vocabulario de INTERFAZ_C5.
#   - anchor_for(): ancla en FORMATO r6 (inventory_tree del propio
#     producto) + hash externo — el formato del ancla es del SUT.
#   - instrumentar(): envuelve create_staging_and_copy en la COPIA
#     PRIVADA para abrir un fd del dueño justo tras la frontera
#     simulated (reproducción determinista del hallazgo de Max; la
#     lógica del producto no se altera).
#   - mutar(): mutación ÚNICA por copia privada con anclaje exigido
#     (MUT-R6-A..F) para los oráculos que r6 no expone como fault.
# =====================================================================
"""Adaptador r6 del harness FLASH (revisión R2)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_common import Journal, sha256_bytes, sha256_file  # noqa: E402

FAULTS_BOOLEANOS_R6 = ('identify', 'before_staging', 'after_copy',
                       'mid_protect', 'after_protect', 'before_publish',
                       'pre_rename', 'swap_hoja')


def cargar_orquestador(src_dir: str, nombre: str):
    """Carga c5_orquestador desde copia privada (sys.path aislado)."""
    ruta = os.path.join(src_dir, 'c5_orquestador.py')
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


class R6OrquestadorAdapter:
    """place() del orquestador r6 en modo simulated/fixture_ensayo."""
    name = 'r6_orquestador'
    hooks_disponibilizados = list(FAULTS_BOOLEANOS_R6)

    def __init__(self, src_dir: str, instancia: str = 'r6'):
        self.src_dir = src_dir
        self.mod = cargar_orquestador(
            src_dir, 'c5_orquestador_r6_%s_%d' % (instancia, os.getpid()))
        self.sha_orquestador = sha256_file(
            os.path.join(src_dir, 'c5_orquestador.py'))

    # -- ancla en formato del producto --------------------------------------
    def anchor_for(self, app_dir: str, out_path: str):
        """Ancla generada con inventory_tree DEL PROPIO r6 (formato 'file'/
        'dir/' — el formato P5r 'regular' NO es comparable por r6)."""
        inv = self.mod.inventory_tree(app_dir)
        data = json.dumps(inv, indent=2, sort_keys=True).encode() + b'\n'
        with open(out_path, 'wb') as f:
            f.write(data)
        return out_path, sha256_bytes(data)

    # -- place ---------------------------------------------------------------
    def place(self, ctx: dict, faults: dict | None = None) -> dict:
        booleanos = {k: True for k, v in (faults or {}).items()
                     if k in FAULTS_BOOLEANOS_R6 and v}
        ignorados = [k for k in (faults or {})
                     if k not in FAULTS_BOOLEANOS_R6]
        j = self.mod.Journal()
        r = self.mod.place(
            origen=ctx['origen'], destino=ctx['destino'],
            anchor_path=ctx['anchor_path'], anchor_sha256=ctx['anchor_sha'],
            modo=ctx.get('modo', 'fixture_ensayo'),
            priv_name='simulated', staging_base=ctx['staging_base'],
            journal=j, faults=booleanos,
            acl_enabled=bool(ctx.get('acl', False)))
        r['adapter'] = self.name
        r['destino'] = ctx['destino']  # r6 no incluye el destino en el resultado
        r['faults_ignorados'] = ignorados  # callbacks sin equivalente en r6
        r['ino_map'] = {}
        if os.path.lexists(ctx['origen']):
            st = os.lstat(ctx['origen'])
            r['ino_map']['origen'] = {'dev': st.st_dev, 'ino': st.st_ino}
        if r.get('staging_leaf'):
            st = os.lstat(r['staging_leaf']) if os.path.lexists(
                r['staging_leaf']) else None
            r['ino_map']['staging_leaf'] = ({'dev': st.st_dev,
                                             'ino': st.st_ino} if st else None)
        if r.get('published') and os.path.lexists(ctx['destino']):
            st = os.lstat(ctx['destino'])
            r['ino_map']['publicado'] = {'dev': st.st_dev, 'ino': st.st_ino}
        r['uso'] = None
        return r

    # -- instrumentación determinista (copia privada, sin alterar lógica) ---
    def instrumentar_post_frontera(self, callback):
        """callback(parent, hoja) se ejecuta JUSTO tras
        create_staging_and_copy (post-frontera simulated)."""
        orig = self.mod.SimulatedPriv.create_staging_and_copy

        def wrapper(spriv, origen, staging_base, hoja_nombre, j):
            parent, hoja = orig(spriv, origen, staging_base, hoja_nombre, j)
            callback(parent, hoja)
            return parent, hoja
        self.mod.SimulatedPriv.create_staging_and_copy = wrapper

    # -- mutantes de copia privada (una mutación, anclaje único) ------------
    def mutante(self, work: str, tag: str, old: str, new: str):
        """Copia privada del orquestador con UNA mutación (anclaje único);
        los módulos hermanos (c5_ancla/c5_acl) se copian junto al mutante
        para que sus imports resuelvan aislados."""
        src = os.path.join(self.src_dir, 'c5_orquestador.py')
        with open(src, encoding='utf-8') as f:
            contenido = f.read()
        n = contenido.count(old)
        if n != 1:
            raise RuntimeError('mutante %s: anclaje no único (%d)' % (tag, n))
        dir_mut = os.path.join(work, 'mut_%s' % tag)
        os.makedirs(dir_mut, exist_ok=True)
        for hermano in ('c5_ancla.py', 'c5_acl.py'):
            shutil.copyfile(os.path.join(self.src_dir, hermano),
                            os.path.join(dir_mut, hermano))
        mut = contenido.replace(old, new)
        path = os.path.join(dir_mut, 'c5_orquestador.py')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(mut)
        mod = cargar_orquestador(dir_mut,
                                 'c5_orq_mut_%s_%d' % (tag, os.getpid()))
        return {'tag': tag, 'path': path, 'mod': mod,
                'sha_base': sha256_file(src), 'sha_mutante': sha256_file(path)}
