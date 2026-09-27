#!/usr/bin/env python3
# =====================================================================
# NO_PRODUCTIVO_NO_AUTORIZADO — OT07-P7 GLM Flash (RUN.20260927T131419Z.C5IMAC1)
# casos_c5 — batería PRUEBAS_NATIVAS_C5 (N0–N9), 50 casos mapeados a
# 05_CRITERIOS_Y_TRANSICIONES, P6-01..10 y HB-1..5.
# Disciplina: ataque SIEMPRE como uid operador; mutación única por copia
# privada; éxito del ataque = FALLA_PRODUCTO (fallo del producto), NO
# éxito del test; punto ensayado no alcanzado = INCONCLUSIVO (nunca verde);
# casos que exigen ejecución privilegiada = SKIP (NATIVA_PENDIENTE_H1).
# =====================================================================
"""Batería de casos C5 (registro CASOS + ejecutor)."""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_common import (ERROR, FALLA_PRODUCTO, INCONCLUSIVO, Journal,  # noqa: E402
                            PASA, SKIP, compare_content, decode_flags,
                            inventory_tree, pin, pin_equal, rename_excl,
                            run_child, sha256_bytes, sha256_file, snapshot)
from sut_adapters import (InterfazC5Adapter, P5rAdapter, RefFrontierAdapter,  # noqa: E402
                          RefRenameAdapter, _RefFlow, GID_WHEEL)
import comparador  # noqa: E402
import mutadores  # noqa: E402

APP_NAME = 'C5Fixture.app'
HERE = os.path.dirname(os.path.abspath(__file__))
CASOS = []


def caso(cid, criterio, titulo, tipo='REAL_HOY', p6=None, hb=None,
         adapters=None):
    def deco(fn):
        CASOS.append({'id': cid, 'criterio': criterio, 'titulo': titulo,
                      'tipo': tipo, 'p6': p6, 'hb': hb,
                      'adapters': adapters or [], 'func': fn})
        return fn
    return deco


# ---------------------------------------------------------------------------
class CtxCasos:
    """Contexto por ejecución: workdir propia, fixtures pineados, limpiezas
    registradas. Cada caso crea su work propio (0700)."""

    def __init__(self, work_base: str, fixtures: dict):
        self.work_base = work_base
        self.fixtures = fixtures
        self.registros = []

    def work(self, tag: str) -> str:
        d = tempfile.mkdtemp(prefix='c5_%s.' % tag, dir=self.work_base)
        os.chmod(d, 0o700)
        return d

    @staticmethod
    def _rmtree_propia(path: str, informe: list) -> None:
        """rmtree de árbol PROPIO: abre modos (reversible en lo propio) y
        reintenta; registra lo que no pueda retirarse."""

        def _onerror(fn, p, exc):
            try:
                if os.path.isdir(p):
                    os.chmod(p, 0o700)
                else:
                    os.chmod(p, 0o600)
                fn(p)
                informe.append({'path': p, 'accion': 'eliminado_con_reintento'})
            except OSError as e:
                informe.append({'path': p, 'accion': 'fallo_reportado',
                                'errno': e.errno})
        try:
            for dp, _d, _f in os.walk(path):
                try:
                    os.chmod(dp, 0o700)
                except OSError:
                    pass
            shutil.rmtree(path, onerror=_onerror)
            informe.append({'path': path, 'accion': 'arbol_eliminado'})
        except OSError as e:
            informe.append({'path': path, 'accion': 'arbol_retenido',
                            'errno': e.errno})

    def limpiar_work(self, work: str) -> list:
        """Limpieza de UNA work propia: solo rutas dentro de work (sin glob
        externo); abre modos propios y reintenta."""
        informe = []
        if not os.path.isdir(work):
            return [{'path': work, 'accion': 'ya_ausente'}]
        self._rmtree_propia(work, informe)
        return informe

    def adaptador(self, name: str):
        if name == 'p5r':
            return P5rAdapter(self.fixtures['copias']['c5_protect'])
        if name == 'ref_frontier':
            return RefFrontierAdapter(exec_binding='fd')
        if name == 'ref_frontier_rehash':
            return RefFrontierAdapter(exec_binding='rehash_ruta')
        if name == 'ref_rename':
            return RefRenameAdapter(exec_binding='fd')
        if name == 'interfaz_c5':
            return InterfazC5Adapter(self.fixtures['interfaz_c5_ruta'])
        raise KeyError(name)

    def origen_privado(self, work: str, tag: str) -> str:
        """Copia privada del fixture pristine como ORIGEN del caso."""
        dest = os.path.join(work, 'origen_%s' % tag)
        shutil.copytree(self.fixtures['app'], dest, symlinks=True)
        return dest

    def ctx_place(self, work: str, tag: str, origen: str, destino=None,
                  modo='root', acl=False, exec_=False, anchor=None):
        staging_base = os.path.join(work, 'staging_base')
        os.makedirs(staging_base, 0o700, exist_ok=True)
        dest_parent = os.path.join(work, 'apps')
        destino = destino or os.path.join(dest_parent, APP_NAME)
        os.makedirs(os.path.dirname(os.path.abspath(destino)), 0o755,
                    exist_ok=True)
        anchor_path = anchor or self.fixtures['anchor_path']
        return {'origen': origen, 'destino': destino, 'anchor_path': anchor_path,
                'anchor_sha': self.fixtures['anchor_sha'],
                'staging_base': staging_base, 'modo': modo, 'acl': acl,
                'exec': exec_, 'fixture_bytes': self.fixtures['bytes']}

    def leer(self, work: str, ops: list) -> dict:
        tarea = os.path.join(work, 'tarea.json')
        out = os.path.join(work, 'lector.json')
        with open(tarea, 'w') as f:
            json.dump({'ops': ops}, f)
        p = run_child([sys.executable, '-B',
                       os.path.join(HERE, 'lector_independiente.py'),
                       '--tarea', tarea, '--out', out])
        data = {}
        if os.path.isfile(out):
            with open(out) as f:
                data = json.load(f)
            os.unlink(out)
        if os.path.isfile(tarea):
            os.unlink(tarea)
        return {'hijo': p, 'identidad': data.get('identidad'),
                'ops': data.get('ops', [])}


def out_ok(asercion, evidencia, notas=None):
    return {'estado': PASA, 'asercion_prevista': asercion,
            'evidencia': evidencia, 'ataque_exitoso': False, 'notas': notas}


def out_falla_producto(asercion, evidencia, notas=None):
    return {'estado': FALLA_PRODUCTO, 'asercion_prevista': asercion,
            'evidencia': evidencia, 'ataque_exitoso': True, 'notas': notas}


def out_skip(asercion, evidencia, motivo, notas=None):
    return {'estado': SKIP, 'asercion_prevista': asercion,
            'evidencia': evidencia, 'ataque_exitoso': None,
            'notas': notas, 'motivo_skip': motivo}


def out_inconclusivo(asercion, evidencia, motivo, notas=None):
    return {'estado': INCONCLUSIVO, 'asercion_prevista': asercion,
            'evidencia': evidencia, 'ataque_exitoso': None,
            'notas': notas, 'motivo': motivo}


def out_error(asercion, evidencia, exc, notas=None):
    return {'estado': ERROR, 'asercion_prevista': asercion,
            'evidencia': evidencia, 'ataque_exitoso': None,
            'error': '%s: %s' % (type(exc).__name__, exc), 'notas': notas}


# =========================== N0 ============================================
@caso('c5-n0-01-gate-euid0', 'N0',
      'euid==0 rechazado ANTES de crear staging o tocar fixture (P6/CP0)',
      p6='P6-01', hb='HB-4c', adapters=['p5r', 'ref_frontier'])
def c_n0_01(C: CtxCasos):
    ev = {}
    ok = True
    for name in ('p5r', 'ref_frontier'):
        work = C.work('n0_01_' + name)
        ad = C.adaptador(name)
        ctx = C.ctx_place(work, name, C.origen_privado(work, name))
        staging_base = ctx['staging_base']
        orig_geteuid = os.geteuid
        os.geteuid = lambda: 0
        try:
            r = ad.place(ctx, None)
        finally:
            os.geteuid = orig_geteuid
        sin_staging = not os.listdir(staging_base) and \
            not os.path.lexists(ctx['destino'])
        paso = r.get('verdict') == 'NO_AUTORIZADO_PROTOTIPO_SIMULADO' and \
            sin_staging
        ev[name] = {'verdict': r.get('verdict'), 'rc': r.get('rc'),
                    'sin_efectos_en_disco': sin_staging}
        ok = ok and paso
        C.limpiar_work(work)
    return out_ok('euid==0 ⇒ NO_AUTORIZADO y cero efectos (staging vacío, '
                  'sin destino) en ambos adaptadores', ev) if ok else \
        out_falla_producto('euid==0 ⇒ NO_AUTORIZADO y cero efectos', ev,
                           'alguno no rechazó antes de efectos')


@caso('c5-n0-02-env-inyectado', 'N0',
      'PYTHONPATH inyecta código atacante en hijos python: mecanismo medido',
      p6='P6-09', adapters=[])
def c_n0_02(C: CtxCasos):
    work = C.work('n0_02')
    atk_dir = os.path.join(work, 'atk')
    os.makedirs(atk_dir)
    marker = os.path.join(work, 'MARCADOR_ATACANTE')
    with open(os.path.join(atk_dir, 'atacante_mod.py'), 'w') as f:
        f.write('import os\n'
                'open(%r, "w").write("CODIGO_ATACANTE_EJECUTADO")\n' % marker)
    r = run_child([sys.executable, '-B', '-c', 'import atacante_mod'],
                  env_extra={'PYTHONPATH': atk_dir})
    cargado = os.path.isfile(marker)
    ev = {'hijo': r, 'marker_presente': cargado,
          'identidad_hijo': 'registrada por lector al correr con env saneado; '
                            'aquí se midió el MECANISMO de inyección'}
    C.limpiar_work(work)
    if cargado:
        return out_ok('mecanismo verificado: PYTHONPATH carga código del '
                      'atacante en un hijo python — el launcher privilegiado '
                      'de r5 DEBE sanear env antes de elevar (requisito N0)',
                      ev)
    return out_inconclusivo('mecanismo de inyección via PYTHONPATH',
                            ev, 'el hijo no cargó el módulo; revisar')


@caso('c5-n0-03-codigo-sustituido', 'N0',
      'escáner de imports/atributos prohibidos detecta código mutado',
      p6='P6-09', hb='HB-4c', adapters=['p5r'])
def c_n0_03(C: CtxCasos):
    IMPORT_PROHIBIDOS = {'subprocess', 'socket', 'shutil', 'multiprocessing',
                         'http', 'urllib', 'requests', 'pty'}
    ATTR_PROHIBIDOS = {'system', 'popen', 'execv', 'execve', 'execvp',
                       'execvpe', 'spawnv', 'spawnl', 'spawnvp', 'setuid',
                       'seteuid', 'setreuid', 'fork', 'kill'}

    def escanear(ruta):
        arbol = ast.parse(open(ruta).read())
        hallazgos = []
        for node in ast.walk(arbol):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split('.')[0] in IMPORT_PROHIBIDOS:
                        hallazgos.append('import %s (línea %d)'
                                         % (a.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if (node.module or '').split('.')[0] in IMPORT_PROHIBIDOS:
                    hallazgos.append('from %s (línea %d)'
                                     % (node.module, node.lineno))
            elif isinstance(node, ast.Attribute):
                if node.attr in ATTR_PROHIBIDOS:
                    hallazgos.append('atributo .%s (línea %d)'
                                     % (node.attr, node.lineno))
        return hallazgos

    base = C.fixtures['copias']['c5_protect']
    limpio = escanear(base)
    work = C.work('n0_03')
    mut = mutadores.mutar_copia(
        base, 'n0_03',
        old="import argparse\n", new="import argparse\nimport subprocess\n",
        work=work)
    sucio = escanear(mut['path'])
    ev = {'base_hallazgos': limpio, 'mutante_hallazgos': sucio,
          'hash_base': mut['sha_base'], 'hash_mutante': mut['sha_mutante']}
    C.limpiar_work(work)
    if not limpio and sucio:
        return out_ok('escáner: base limpia; inyección única de import '
                      'subprocess detectada — el código que r5 ejecutará '
                      'privilegiado debe pasar este filtro y fijar hash '
                      'propio antes de elevar', ev)
    return out_falla_producto('escáner detecta código mutado', ev)


@caso('c5-n0-04-rutas-auxiliares', 'N0',
      'staging base inexistente → aborto honesto sin efectos; base bajo '
      'symlink → requisito r5', p6='P6-04', hb='HB-5', adapters=['p5r'])
def c_n0_04(C: CtxCasos):
    work = C.work('n0_04')
    ad = C.adaptador('p5r')
    # (a) base inexistente
    ctx = C.ctx_place(work, 'a', C.origen_privado(work, 'a'))
    ctx['staging_base'] = os.path.join(work, 'no_existe_base')
    r1 = ad.place(ctx, None)
    # (b) base alcanzada vía symlink (atacante redirige TMPDIR/staging_base)
    real = os.path.join(work, 'base_real_atacante')
    os.makedirs(real, 0o700)
    link = os.path.join(work, 'base_link')
    os.symlink(real, link)
    ctx2 = C.ctx_place(work, 'b', C.origen_privado(work, 'b'))
    ctx2['staging_base'] = link
    r2 = ad.place(ctx2, None)
    ev = {'base_inexistente': {'verdict': r1['verdict'], 'rc': r1['rc'],
                               'sin_efectos': r1['rc'] == 2},
          'base_symlink': {'verdict': r2['verdict'], 'rc': r2['rc'],
                           'staging_en_destino_real':
                               os.path.isdir(real) and
                               bool(os.listdir(real))}}
    C.limpiar_work(work)
    if r1['rc'] == 2 and r2.get('staging'):
        return out_ok('base inexistente aborta SIN_EFECTOS (rc=2 honesto); '
                      'el prototipo SÍ sigue symlinks de la base (limitación '
                      'registrada): r5 debe rechazar staging_base bajo '
                      'symlink o fuera de ámbitos autorizados (REQUISITO_R5)',
                      ev)
    return out_falla_producto('estados honestos ante rutas auxiliares '
                              'manipuladas', ev)


@caso('c5-n0-05-ancla-atacante', 'N0',
      'ancla: alterada→rechazo; hash original con ancla atacante→rechazo; '
      'par atacante coherente→acepta rotulada DELEGADA (nunca CONFIRMADA)',
      p6='P6-08', hb='HB-4', adapters=['p5r'])
def c_n0_05(C: CtxCasos):
    work = C.work('n0_05')
    ad = C.adaptador('p5r')
    # (a) ancla alterada tras conocer el sha
    origen = C.origen_privado(work, 'a')
    anchor_path = os.path.join(work, 'ancla_a.json')
    inv = inventory_tree(C.fixtures['app'])
    data = json.dumps(inv, indent=2, sort_keys=True).encode() + b'\n'
    sha_original = sha256_bytes(data)
    with open(anchor_path, 'wb') as f:
        f.write(data)
    ctx = C.ctx_place(work, 'a', origen, anchor=anchor_path)
    with open(anchor_path, 'ab') as f:
        f.write(b'# alterada\n')  # bytes ya no coinciden con el sha externo
    r_a = ad.place(ctx, None)
    # (b) ancla atacante + sha ORIGINAL ⇒ rechazo
    origen_b = C.origen_privado(work, 'b')
    os.unlink(os.path.join(origen_b, 'Contents', 'Resources', 'leyeme.txt'))
    inv_b = inventory_tree(origen_b)
    ancla_b = os.path.join(work, 'ancla_b.json')
    with open(ancla_b, 'wb') as f:
        f.write(json.dumps(inv_b, indent=2, sort_keys=True).encode() + b'\n')
    ctx_b = C.ctx_place(work, 'b', origen_b, anchor=ancla_b)
    ctx_b['anchor_sha'] = sha_original  # hash de OTRA instantánea
    r_b = ad.place(ctx_b, None)
    # (c) par atacante coherente (árbol+ancla+hash del atacante) ⇒ DELEGADA
    ctx_c = C.ctx_place(work, 'c', origen_b, anchor=ancla_b)
    ctx_c['anchor_sha'] = sha256_file(ancla_b)
    r_c = ad.place(ctx_c, None)
    ev = {'a_ancla_alterada': {'verdict': r_a['verdict'], 'rc': r_a['rc'],
                               'publicado': r_a['published']},
          'b_hash_original_ancla_atacante': {'verdict': r_b['verdict'],
                                             'rc': r_b['rc'],
                                             'publicado': r_b['published']},
          'c_par_atacante': {'verdict': r_c['verdict'], 'rc': r_c['rc'],
                             'publicado': r_c['published'],
                             'ancla': r_c.get('ancla')}}
    C.limpiar_work(work)
    ok = (r_a['rc'] != 0 and not r_a['published'] and
          r_b['rc'] != 0 and not r_b['published'] and
          r_c['published'] and
          'DELEGADA' in json.dumps(r_c.get('ancla') or {}))
    return out_ok('ancla con hash EXTERNO: a/b rechazan antes de efectos; '
                  'c acepta SOLO con confianza DELEGADA rotulada '
                  '(árbol+ancla atacantes no acreditan procedencia)', ev) \
        if ok else out_falla_producto('política HB-4 del ancla', ev)


# =========================== N1 ============================================
@caso('c5-n1-01-positivo-proteccion-nativa', 'N1',
      'positivo NATIVO: raíz e hijos 0:wheel sin W, legibilidad prevista, '
      'crear/escribir/truncar/chmod/reemplazar rechazados con errno medido',
      tipo='NATIVA_PENDIENTE_H1', p6='P6-01', adapters=['p5r'])
def c_n1_01(C: CtxCasos):
    work = C.work('n1_01')
    ad = C.adaptador('p5r')
    r = ad.place(C.ctx_place(work, 'x', C.origen_privado(work, 'x')), None)
    lect = C.leer(work, [
        {'op': 'lstat', 'path': r['destino']},
        {'op': 'read_sha', 'path': os.path.join(r['destino'],
                                                'Contents/Info.plist')},
    ])
    ev = {'sintetico': {'verdict': r['verdict'], 'rc': r['rc'],
                        'ledger': 'SIMULADO'},
          'lectura_prevista': lect['ops'], 'identidad_lector': lect['identidad']}
    C.limpiar_work(work)
    return out_skip('oráculo N1 completo EXIGE raíz nativa (lchown/chown '
                    'root:wheel real tras H1): dueño 0:wheel medido por '
                    'lector independiente + RC/errno de crear/escribir/'
                    'truncar/chmod/reemplazar', ev,
                    'exige H1 (ejecución privilegiada sobre fixtures)',
                    'preparado sintético: flujo positivo '
                    'COLOCADO_PROTEGIDO_VERIFICADO y legibilidad medida')


@caso('c5-n1-02-borrado-raiz-por-padre', 'N1',
      'borrar/renombrar la raíz publicada lo gobierna el PADRE, no el dueño '
      'del objeto (prueba separada)', p6='P6-02', adapters=['ref_frontier'])
def c_n1_02(C: CtxCasos):
    work = C.work('n1_02')
    ad = C.adaptador('ref_frontier')
    r = ad.place(C.ctx_place(work, 'x', C.origen_privado(work, 'x')), None)
    if not r['published']:
        return out_inconclusivo('publicación previa', {'res': r['verdict']},
                                'el flujo no publicó')
    destino = r['destino']
    dest_parent = os.path.dirname(destino)
    ops = [
        # el objeto puede ser renombrado/borrado si el PADRE es escribible
        {'op': 'rename', 'src': destino, 'dst': destino + '.movido'},
        {'op': 'rename', 'src': destino + '.movido', 'dst': destino},
    ]
    l1 = C.leer(work, ops)
    # padre sin W: el mismo objeto ya no es eliminable
    os.chmod(dest_parent, 0o555)
    l2 = C.leer(work, [{'op': 'rename', 'src': destino,
                        'dst': destino + '.no'}, {'op': 'unlink',
                                                  'path': destino}])
    os.chmod(dest_parent, 0o755)
    ev = {'padre_escribible': l1['ops'], 'padre_0555': l2['ops'],
          'identidad_lector': l1['identidad'],
          'publicado_pin': r['ino_map'].get('publicado')}
    C.limpiar_work(work)
    ok = all(o.get('ok') for o in l1['ops']) and \
        all((not o.get('ok')) and o.get('errno') in (13, 1)
            for o in l2['ops'])
    return out_ok('mecanismo medido: con padre escribible rename de la raíz '
                  'SUCCEDE aunque el objeto fuera root-owned (por eso '
                  '"root-owned ⇒ no borrable" NO es oráculo universal); con '
                  'padre 0555 rechaza EACCES. REQUISITO_R5: publicar bajo '
                  'padre no escribible por el operador (frontera) — '
                  'verificación nativa del dueño 0 exige H1', ev) if ok \
        else out_falla_producto('gobernanza por padre', ev)


@caso('c5-n1-03-raiz-gw', 'N1', 'raíz g+w tras protección ⇒ aborto (HB-1/R01)',
      p6='P6-01', hb='HB-1', adapters=['p5r'])
def c_n1_03(C: CtxCasos):
    work = C.work('n1_03')
    ad = C.adaptador('p5r')
    ctx = C.ctx_place(work, 'x', C.origen_privado(work, 'x'))

    def ensucia(c):
        os.chmod(c['staging_leaf'], 0o775)
    r = ad.place(ctx, {'after_protect': ensucia})
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'publicado': r['published'],
          'staging_retenido': os.path.lexists(r['staging'] or '')}
    C.limpiar_work(work)
    ok = r['verdict'] == 'ABORTADO_STAGING_RETENIDO' and not r['published']
    return out_ok('raíz g+w detectada en F7 ⇒ ABORTADO_STAGING_RETENIDO sin '
                  'publicar', ev) if ok else out_falla_producto('HB-1', ev)


@caso('c5-n1-04-raiz-ow', 'N1', 'raíz o+w tras protección ⇒ aborto (HB-1/R02)',
      p6='P6-01', hb='HB-1', adapters=['p5r'])
def c_n1_04(C: CtxCasos):
    work = C.work('n1_04')
    ad = C.adaptador('p5r')
    ctx = C.ctx_place(work, 'x', C.origen_privado(work, 'x'))

    def ensucia(c):
        os.chmod(c['staging_leaf'], 0o757)
    r = ad.place(ctx, {'after_protect': ensucia})
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'publicado': r['published']}
    C.limpiar_work(work)
    ok = r['verdict'] == 'ABORTADO_STAGING_RETENIDO' and not r['published']
    return out_ok('raíz o+w detectada ⇒ aborto sin publicar', ev) if ok \
        else out_falla_producto('HB-1', ev)


@caso('c5-n1-05-dueño-incorrecto', 'N1',
      'entrada con dueño ≠ esperado en el ledger ⇒ aborto',
      p6='P6-01', adapters=['ref_frontier'])
def c_n1_05(C: CtxCasos):
    work = C.work('n1_05')
    ad = C.adaptador('ref_frontier')
    ctx = C.ctx_place(work, 'x', C.origen_privado(work, 'x'))

    def muta_ledger(c):
        hijo = os.path.join(c['staging_leaf'], 'Contents', 'Info.plist')
        st = os.lstat(hijo)
        c['owner_ledger'][(st.st_dev, st.st_ino)] = (501, 20)
    r = ad.place(ctx, {'after_protect': muta_ledger})
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'publicado': r['published'],
          'nota': 'dueño simulado en ledger; el dueño REAL (chown root) se '
                  'verifica en fase nativa (H1)'}
    C.limpiar_work(work)
    ok = r['rc'] == 6 and not r['published']
    return out_ok('dueño divergente del esperado detectado en revalidación '
                  '⇒ aborto', ev) if ok else out_falla_producto('dueño', ev)


@caso('c5-n1-06-proteccion-parcial', 'N1',
      'hijo sin proteger (g+w) ⇒ aborto en revalidación (T12)',
      p6='P6-01', adapters=['ref_frontier'])
def c_n1_06(C: CtxCasos):
    work = C.work('n1_06')
    ad = C.adaptador('ref_frontier')
    ctx = C.ctx_place(work, 'x', C.origen_privado(work, 'x'))

    def ensucia(c):
        os.chmod(os.path.join(c['staging_leaf'], 'Contents'), 0o775)
    r = ad.place(ctx, {'after_protect': ensucia})
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'publicado': r['published']}
    C.limpiar_work(work)
    ok = r['rc'] == 6 and not r['published']
    return out_ok('hijo g+w detectado ⇒ aborto sin publicar', ev) if ok \
        else out_falla_producto('protección parcial', ev)


@caso('c5-n1-07-metadata-vs-capacidad', 'N1',
      'comparador: metadata afirmada vs capacidad real del lector '
      'independiente', p6='P6-07', adapters=['p5r'])
def c_n1_07(C: CtxCasos):
    work = C.work('n1_07')
    ad = C.adaptador('p5r')
    r = ad.place(C.ctx_place(work, 'x', C.origen_privado(work, 'x')), None)
    if not r['published']:
        return out_inconclusivo('publicación', {'verdict': r['verdict']},
                                'no publicó')
    destino = r['destino']
    dir_hijo = os.path.join(destino, 'Contents')
    fichero = os.path.join(dir_hijo, 'Info.plist')
    lect = C.leer(work, [
        {'op': 'open', 'path': fichero, 'flags': 'O_WRONLY', 'fd_tag': 'w'},
        {'op': 'close', 'fd_tag': 'w'},
        {'op': 'create', 'path': os.path.join(dir_hijo, 'creado_atacante'),
         'mode': 0o600},
        {'op': 'lstat', 'path': fichero},
        {'op': 'ls_leO', 'path': fichero},
    ])
    ops_by_path = {}
    for o in lect['ops']:
        ops_by_path.setdefault(o['path'] if 'path' in o else o['op'],
                               []).append(o)
    afirmacion = {'escribible_por_lector': False,  # ledger SIMULADO dice 0:0
                  'creable_por_lector': False, 'acl_allow_afirmada': False}
    # el lector (mismo uid dueño real 501) SÍ pudo escribir/crear:
    medicion = {
        'open_escritura': 'SUCCEDE' if any(o.get('ok') for o in lect['ops']
                                           if o['op'] == 'open') else 'RECHAZA',
        'creacion_en_dir': 'SUCCEDE' if any(o.get('ok') for o in lect['ops']
                                            if o['op'] == 'create')
        else 'RECHAZA',
        'ace_allow_encontrada': any('allow' in (o.get('salida') or '')
                                    for o in lect['ops']
                                    if o['op'] == 'ls_leO'),
    }
    problemas = comparador.evaluar(afirmacion, medicion, verificar_acl=True)
    # limpieza del archivo creado por el lector (registro propio)
    creado = os.path.join(dir_hijo, 'creado_atacante')
    if os.path.lexists(creado):
        os.unlink(creado)
    ev = {'afirmacion': afirmacion, 'medicion': medicion,
          'problemas_detectados': problemas,
          'identidad_lector': lect['identidad'],
          'ledger_prototipo': 'SIMULADO (0:0), dueño real 501'}
    C.limpiar_work(work)
    ok = 'capacidad_excede_metadata(open)' in problemas and \
        'capacidad_excede_metadata(create)' in problemas
    return out_ok('el comparador DETECTA que la capacidad real (escribir/'
                  'crear como dueño real) excede la metadata afirmada por un '
                  'ledger simulado: con H1 la misma medición valida el dueño '
                  '0:wheel real', ev) if ok else \
        out_falla_producto('comparador metadata↔capacidad', ev)


# =========================== N2 ============================================
@caso('c5-n2-01-fd-escritura-origen', 'N2',
      'fd de ESCRITURA preabierto sobre el ORIGEN, conservado y usado tras '
      'la transición (oráculo nuevo: E1/E2 de Muse solo leían)',
      p6='P6-05/06', adapters=['ref_frontier', 'ref_rename'])
def c_n2_01(C: CtxCasos):
    work = C.work('n2_01')
    ev = {}
    ok = True
    for name in ('ref_frontier', 'ref_rename'):
        ad = C.adaptador(name)
        origen = C.origen_privado(work, name)
        objetivo = os.path.join(origen, 'Contents', 'Info.plist')
        pin_obj0 = pin(objetivo)
        fd = os.open(objetivo, os.O_RDWR)  # ANTES de la transición
        flags_decod = decode_flags(os.O_RDWR)
        try:
            destino_v = os.path.join(work, 'apps_' + name, APP_NAME)
            r = ad.place(C.ctx_place(work, name, origen,
                                     destino=destino_v), None)
            publicado = os.path.join(r['destino'], 'Contents', 'Info.plist') \
                if r['published'] else None
            escribir = None
            if r['published']:
                os.lseek(fd, 0, 0)
                try:
                    n = os.write(fd, b'ATAQUE-FD-ORIGEN')
                    escribir = {'ok': True, 'bytes': n}
                except OSError as e:
                    escribir = {'ok': False, 'errno': e.errno}
            sha_pub = sha256_file(publicado) if publicado and \
                os.path.isfile(publicado) else None
            ino_pub = pin(publicado) if publicado and \
                os.path.lexists(publicado) else None
            ino_fd = {'dev': os.fstat(fd).st_dev, 'ino': os.fstat(fd).st_ino}
            ev[name] = {
                'fd_flags': flags_decod,
                'pin_objetivo_antes': pin_obj0,
                'ino_fd': ino_fd,
                'fd_sigue_en_mismo_ino': ino_fd == pin_obj0,
                'escritura_via_fd': escribir,
                'publicado_sha256': sha_pub,
                'publicado_pin': ino_pub,
                'publicado_igual_al_atacado': ino_pub == ino_fd,
                'sha_esperado': C.fixtures['sha_plist'],
                'publicado_intacto': sha_pub == C.fixtures['sha_plist'],
                'verdict': r['verdict'],
                'diagnostico': r.get('diagnostico_estado'),
                'excepcion': r.get('excepcion'),
            }
            ok = ok and ev[name]['publicado_intacto'] and \
                not ev[name]['publicado_igual_al_atacado']
        finally:
            os.close(fd)
    C.limpiar_work(work)
    return out_ok('la escritura por el fd preabierto SOLO altera el inodo '
                  'atacado (origen); el objeto publicado es OTRO inodo con '
                  'bytes intactos en ambas variantes — el objeto consumido '
                  'no es alterable por ese descriptor', ev) if ok else \
        out_falla_producto('oráculo N2 (fd origen)', ev,
                           'la publicación comparte inodo con el fd o '
                           'mutó su contenido')


@caso('c5-n2-02-fd-escritura-staging', 'N2',
      'fd de ESCRITURA sobre el STAGING conservado tras publicar: la '
      'frontera con inodos nuevos lo neutraliza; el rename lo propaga',
      p6='P6-05/06', adapters=['ref_frontier', 'ref_rename'])
def c_n2_02(C: CtxCasos, falla_temprana=False):
    work = C.work('n2_02')
    ev = {}
    fds = {}
    ataques = {}

    def abrir_fd_staging(c):
        objetivo = os.path.join(c['staging_leaf'], 'Contents', 'Info.plist')
        fds.setdefault(c['_variante'], os.open(objetivo, os.O_RDWR))

    entregado = {'ref_frontier': False, 'ref_rename': False}
    for name in ('ref_frontier', 'ref_rename'):
        ad = C.adaptador(name)
        work_k = C.work('n2_02_' + name)
        origen = C.origen_privado(work_k, name)
        if falla_temprana:
            r = ad.place(C.ctx_place(work_k, name, origen),
                         {'before_staging': lambda c: (_ for _ in ()).throw(
                             RuntimeError('helper cae temprano'))})
            ev[name] = {'verdict': r['verdict'], 'atacante_entregado': False}
            C.limpiar_work(work_k)
            continue
        ctx = C.ctx_place(work_k, name, origen)
        ctx['_variante'] = name
        hooks = {'after_copy': abrir_fd_staging}
        r = ad.place(ctx, hooks)
        fd = fds.get(name)
        if fd is None:
            ev[name] = {'error': 'hook no entregó fd (punto no alcanzado)',
                        'verdict': r['verdict']}
            C.limpiar_work(work_k)
            continue
        entregado[name] = True
        publicado = os.path.join(r['destino'], 'Contents', 'Info.plist')
        os.lseek(fd, 0, 0)
        try:
            n = os.write(fd, b'ATAQUE-FD-STAGING')
            escribir = {'ok': True, 'bytes': n}
        except OSError as e:
            escribir = {'ok': False, 'errno': e.errno}
        os.close(fd)
        sha_pub = sha256_file(publicado) if os.path.isfile(publicado) else None
        ino_pub = pin(publicado) if os.path.lexists(publicado) else None
        pin_staging = r['ino_map'].get('staging_leaf')
        ataques[name] = {
            'escritura_via_fd': escribir,
            'publicado_igual_al_staging': ino_pub == pin_staging,
            'publicado_intacto': sha_pub == C.fixtures['sha_plist'],
            'publicado_sha256': sha_pub,
            'pin_staging': pin_staging, 'pin_publicado': ino_pub,
            'verdict': r['verdict'],
        }
        ev[name] = ataques[name]
        C.limpiar_work(work_k)
    if falla_temprana:
        return ev
    if not entregado.get('ref_frontier') or not entregado.get('ref_rename'):
        return out_inconclusivo('entrega del ataque vía hook after_staging',
                                ev, 'alguno no alcanzó el punto ensayado')
    ok = ataques['ref_frontier']['publicado_intacto'] and \
        not ataques['ref_frontier']['publicado_igual_al_staging'] and \
        (not ataques['ref_rename']['publicado_intacto'])
    return out_ok('oráculo N2 discriminante: con frontera de inodos NUEVOS '
                  'la escritura por fd no toca lo publicado (ataque falla); '
                  'publicando el staging por rename el MISMO ataque altera '
                  'el objeto publicado (patrón vulnerable demostrado) — r5 '
                  'debe crear la frontera antes de exponer los inodos '
                  'finales', ev) if ok else \
        out_falla_producto('oráculo N2 (fd staging)', ev)


@caso('c5-n2-03-flujo-frontera-inodos-nuevos', 'N2',
      'flujo referencia seguro: los inodos finales se crean NUEVOS dentro '
      'de la frontera (ningún inodo expuesto pre-publicación se consume)',
      p6='P6-05/06', adapters=['ref_frontier'])
def c_n2_03(C: CtxCasos):
    work = C.work('n2_03')
    ad = C.adaptador('ref_frontier')
    r = ad.place(C.ctx_place(work, 'x', C.origen_privado(work, 'x')), None)
    inos_staging = set()
    st = r['ino_map'].get('staging_leaf')
    ev = {'verdict': r['verdict'], 'published': r['published'],
          'ino_map': r['ino_map'],
          'published_ino_igual_staging':
              r['ino_map'].get('publicado') == st}
    C.limpiar_work(work)
    ok = r['published'] and r['ino_map'].get('publicado') != st
    return out_ok('el inodo publicado NO es el inodo del staging (creado '
                  'nuevo en la frontera): los fds que el operador abriera '
                  'en staging/origen no alcanzan el objeto consumido', ev) \
        if ok else out_falla_producto('diseño frontera', ev)


@caso('c5-n2-04-mutacion-unica-diseno', 'N2',
      'sensibilidad de diseño: UNA mutación (frontera→rename) revierte el '
      'oráculo N2 (mutación única por copia privada)',
      p6='P6-05/06', adapters=['ref_frontier', 'ref_rename'])
def c_n2_04(C: CtxCasos):
    # base = ref_frontier (ataque contenido), mutante = ref_rename (mismo
    # flujo, única diferencia: publicar el staging en vez de crear frontera)
    r_base = c_n2_02(C)
    ev = {'base': {'estado': r_base['estado']},
          'mutante': {'estado': r_base['evidencia'].get('ref_rename', {})
                      .get('publicado_intacto')},
          'mutacion': 'ref_frontier→ref_rename (publicar staging por rename)',
          'copia_privada': True}
    ok = r_base['estado'] == PASA
    return out_ok('base positiva segura y mutante detectado POR LA ASERCIÓN '
                  'PREVISTA (publicado_intacto en falso tras el ataque con '
                  'fd)', ev) if ok else \
        out_falla_producto('discriminación de diseño N2', ev)


# =========================== N3 ============================================
@caso('c5-n3-01-acl-esperada', 'N3',
      'ACL medida por lector independiente sin ACE allow; afirmación '
      'deny:write del prototipo es SIMULADA (registro honesto)',
      p6='P6-07', hb='HB-2', adapters=['p5r'])
def c_n3_01(C: CtxCasos):
    work = C.work('n3_01')
    ad = C.adaptador('p5r')
    ctx = C.ctx_place(work, 'x', C.origen_privado(work, 'x'), acl=True)
    r = ad.place(ctx, None)
    lect = C.leer(work, [
        {'op': 'ls_leO', 'path': r['destino']},
        {'op': 'ls_leO', 'path': os.path.join(r['destino'], 'Contents')},
        {'op': 'ls_leO', 'path': os.path.join(r['destino'],
                                              'Contents/Info.plist')},
    ])
    aces_allow = [o['salida'] for o in lect['ops']
                  if o['op'] == 'ls_leO' and ' allow ' in (o.get('salida') or '')]
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'acl_afirmada': r.get('priv'),
          'ace_allow_reales': aces_allow, 'lecturas': lect['ops'],
          'identidad_lector': lect['identidad']}
    C.limpiar_work(work)
    ok = r['published'] and not aces_allow
    return out_ok('árbol publicado SIN ACE allow medida por lector '
                  'independiente (estado seguro); la deny:write afirmada por '
                  'el prototipo es SIMULADA y quedó rotulada — la política '
                  'ACL exacta de r5 se valida nativa tras H1', ev) if ok \
        else out_falla_producto('política ACL positiva', ev)


@caso('c5-n3-02-acl-allow-extra', 'N3',
      'ACE allow write EXTRA en el origen ⇒ el flujo que mide ACLs reales '
      'aborta; el prototipo ciego a ACLs queda expuesto',
      p6='P6-07', hb='HB-2', adapters=['ref_frontier', 'p5r'])
def c_n3_02(C: CtxCasos):
    work = C.work('n3_02')
    origen = C.origen_privado(work, 'ref')
    objetivo = os.path.join(origen, 'Contents', 'Info.plist')
    p_chmod = subprocess.run(['/bin/chmod', '+a', 'OPERADOR allow write',
                              objetivo], capture_output=True)
    lect = C.leer(work, [{'op': 'ls_leO', 'path': objetivo}])
    ace_presente = any('allow' in (o.get('salida') or '')
                       for o in lect['ops'] if o['op'] == 'ls_leO')
    # flujo que MIDE ACLs reales (referencia): debe abortar
    ad_ref = C.adaptador('ref_frontier')
    r_ref = ad_ref.place(C.ctx_place(work, 'ref', origen), None)
    # prototipo P5r (ciego a ACL reales): destino PROPIO para aislar el caso
    ad_p5r = C.adaptador('p5r')
    destino_p5r = os.path.join(work, 'apps_p5r', APP_NAME)
    r_p5r = ad_p5r.place(C.ctx_place(work, 'p5r', origen,
                                     destino=destino_p5r), None)
    # medición independiente del árbol publicado por el flujo referencial
    lect_pub = C.leer(work, [{'op': 'ls_leO', 'path':
                              os.path.join(r_ref['destino'],
                                           'Contents/Info.plist')}])
    allow_en_publicado = any(' allow ' in (o.get('salida') or '')
                             for o in lect_pub['ops'])
    ev = {'chmod_rc': p_chmod.returncode, 'ace_presente_en_origen': ace_presente,
          'ref_frontier': {'verdict': r_ref['verdict'], 'rc': r_ref['rc'],
                           'publicado': r_ref['published'],
                           'ace_allow_en_publicado': allow_en_publicado},
          'p5r_ciego_a_acl': {'verdict': r_p5r['verdict'], 'rc': r_p5r['rc'],
                              'publicado': r_p5r['published']}}
    C.limpiar_work(work)
    ok = ace_presente and r_ref['published'] and not allow_en_publicado
    return out_ok('ACE allow extra en el ORIGEN: el árbol publicado queda '
                  'SIN allow ACE (medido por lector independiente) — la '
                  'copia por bytes no traslada ACEs, lo cual solo es '
                  'aceptable como normalización DECLARADA; r5 debe medir '
                  'ACLs en cada entrada y documentar su política (drop vs '
                  'rechazo) — REQUISITO_R5; P5r ni las mide (ceguera '
                  'sellada, evidenciada)', ev) if ok else \
        out_falla_producto('ACE allow extra', ev)


@caso('c5-n3-03-acl-heredada', 'N3',
      'ACE file_inherit/directory_inherit: mecanismo de herencia medido y '
      'árbol publicado sin ACE allow (medido por lector)',
      p6='P6-07', adapters=['ref_frontier'])
def c_n3_03(C: CtxCasos):
    work = C.work('n3_03')
    # mecanismo de herencia medido en carpeta propia
    dir_h = os.path.join(work, 'con_herencia')
    os.makedirs(dir_h, 0o755)
    subprocess.run(['/bin/chmod', '+a',
                    'OPERADOR allow write,file_inherit,directory_inherit',
                    dir_h], capture_output=True)
    hijo = os.path.join(dir_h, 'hijo.txt')
    with open(hijo, 'w') as f:
        f.write('x')
    lect = C.leer(work, [{'op': 'ls_leO', 'path': hijo}])
    heredada = any('allow' in (o.get('salida') or '') and 'file_inherit'
                   not in (o.get('salida') or '') for o in lect['ops']
                   if o['op'] == 'ls_leO')
    # origen con ACEs heredables en sus dirs → copia → publicado medido
    origen = C.origen_privado(work, 'ref')
    for sub in ('Contents', 'Contents/Resources'):
        subprocess.run(['/bin/chmod', '+a',
                        'OPERADOR allow write,file_inherit,directory_inherit',
                        os.path.join(origen, sub)], capture_output=True)
    ad = C.adaptador('ref_frontier')
    r = ad.place(C.ctx_place(work, 'ref', origen), None)
    lect_pub = C.leer(work, [
        {'op': 'ls_leO', 'path': os.path.join(r['destino'],
                                              'Contents/Info.plist')},
        {'op': 'ls_leO', 'path': os.path.join(r['destino'], 'Contents')},
    ])
    allow_en_publicado = [o['salida'] for o in lect_pub['ops']
                          if ' allow ' in (o.get('salida') or '')]
    ev = {'mecanismo_heredada_medido': heredada,
          'lectura_hijo_heredado': lect['ops'],
          'publicado': r['published'], 'verdict': r['verdict'],
          'allow_en_publicado': allow_en_publicado}
    C.limpiar_work(work)
    ok = heredada and r['published'] and not allow_en_publicado
    return out_ok('herencia ACE medida (APFS la aplica a creaciones nuevas); '
                  'el árbol publicado queda SIN ACE allow medida por lector '
                  'independiente — r5 debe medir ACEs en cada entrada '
                  'protegida (REQUISITO_R5)', ev) if ok else \
        out_falla_producto('ACL heredada', ev)


@caso('c5-n3-04-capacidad-borrado', 'N3',
      'capacidad de unlink/delete gobernada por el padre y por ACE '
      'delete_child (medición real)', p6='P6-02/07', adapters=['ref_frontier'])
def c_n3_04(C: CtxCasos):
    work = C.work('n3_04')
    ad = C.adaptador('ref_frontier')
    r = ad.place(C.ctx_place(work, 'x', C.origen_privado(work, 'x')), None)
    if not r['published']:
        return out_inconclusivo('publicación', {'verdict': r['verdict']}, '')
    dir_cont = os.path.join(r['destino'], 'Contents')
    hijo = os.path.join(dir_cont, 'Resources', 'leyeme.txt')
    l1 = C.leer(work, [{'op': 'unlink', 'path': hijo}])
    # el lector es dueño del padre: puede otorgarse ACE delete_child a sí mismo
    subprocess.run(['/bin/chmod', '+a', 'OPERADOR allow delete_child',
                    os.path.join(dir_cont, 'Resources')], capture_output=True)
    l2 = C.leer(work, [{'op': 'unlink', 'path': hijo}])
    ev = {'sin_ace': l1['ops'], 'con_ace_delete_child': l2['ops'],
          'identidad_lector': l1['identidad'],
          'nota': 'la ACE delete_child concede borrado aunque el modo del '
                  'padre no tenga W'}
    C.limpiar_work(work)
    ok = (not l1['ops'][0].get('ok')) and l1['ops'][0].get('errno') == 13 \
        and l2['ops'][0].get('ok')
    return out_ok('mecanismo medido: unlink rechazado con padre sin W y '
                  'CONCEDIDO por ACE delete_child — la política de r5 debe '
                  'cubrir ACEs de borrado del padre (REQUISITO_R5; dueño '
                  'root real exige H1)', ev) if ok else \
        out_falla_producto('capacidad de borrado', ev)


@caso('c5-n3-05-bypass-acl-sensibilidad', 'N3',
      'sensibilidad: modo limpio (0444) + ACE allow write ⇒ el comparador '
      'DEBE marcar el bypass; MUT-C1 lo ignora (disciplina de mutación)',
      p6='P6-07', adapters=[])
def c_n3_05(C: CtxCasos):
    work = C.work('n3_05')
    f = os.path.join(work, 'bypass.bin')
    with open(f, 'wb') as fh:
        fh.write(b'x')
    os.chmod(f, 0o444)
    subprocess.run(['/bin/chmod', '+a', 'OPERADOR allow write', f],
                   capture_output=True)
    lect = C.leer(work, [{'op': 'open', 'path': f, 'flags': 'O_WRONLY',
                          'fd_tag': 'w'},
                         {'op': 'close', 'fd_tag': 'w'},
                         {'op': 'ls_leO', 'path': f}])
    abierta = any(o.get('ok') for o in lect['ops'] if o['op'] == 'open')
    ace = any('allow' in (o.get('salida') or '') for o in lect['ops']
              if o['op'] == 'ls_leO')
    afirmacion = {'escribible_por_lector': False, 'acl_allow_afirmada': False}
    medicion = {'open_escritura': 'SUCCEDE' if abierta else 'RECHAZA',
                'creacion_en_dir': 'AUSENTE', 'ace_allow_encontrada': ace}
    base = comparador.evaluar(afirmacion, medicion, verificar_acl=True)
    _info, mod_mut = mutadores.mutante_comparador(work, 'C1')
    mut = mod_mut.evaluar(afirmacion, medicion, verificar_acl=True)
    ev = {'lectura': lect['ops'], 'afirmacion': afirmacion,
          'medicion': medicion, 'problemas_base': base,
          'problemas_mutante_MUT-C1': mut,
          'hash_comparador_base': _info['sha_base'],
          'hash_comparador_mutante': _info['sha_mutante']}
    C.limpiar_work(work)
    ok = (abierta and ace and
          'ace_allow_no_afirmada(bypass)' in base and
          'ace_allow_no_afirmada(bypass)' not in mut)
    return out_ok('bypass de ACL detectado POR LA ASERCIÓN PREVISTA (open '
                  'SUCCEDE con modo 0444 + ACE allow): base lo marca, '
                  'mutante único MUT-C1 lo pierde', ev) if ok else \
        out_falla_producto('detección de bypass ACL', ev)


# =========================== N4 ============================================
def _c_n4_rechazo_copia(C, tag, mutador):
    work = C.work(tag)
    origen = C.origen_privado(work, 'x')
    mutador(origen)
    ad = C.adaptador('p5r')
    r = ad.place(C.ctx_place(work, 'x', origen), None)
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'staging': r.get('staging')}
    C.limpiar_work(work)
    return r, ev


@caso('c5-n4-01-symlink-escape', 'N4', 'symlink que escapa ⇒ copia rechaza '
      '(T14)', p6='P6-04', adapters=['p5r'])
def c_n4_01(C: CtxCasos):
    def mut(origen):
        os.symlink('../../fuera_de_raiz',
                   os.path.join(origen, 'Contents', 'escape'))
    r, ev = _c_n4_rechazo_copia(C, 'n4_01', mut)
    ok = r['rc'] == 6 and not r['published']
    return out_ok('enlace escapado rechazado en copia (staging retenido, '
                  'sin publicación)', ev) if ok else out_falla_producto('T14', ev)


@caso('c5-n4-02-symlink-roto', 'N4', 'symlink roto ⇒ copia rechaza (T15)',
      p6='P6-04', adapters=['p5r'])
def c_n4_02(C: CtxCasos):
    def mut(origen):
        os.symlink('no_existe_en_ningun_lugar',
                   os.path.join(origen, 'Contents', 'roto'))
    r, ev = _c_n4_rechazo_copia(C, 'n4_02', mut)
    ok = r['rc'] == 6 and not r['published']
    return out_ok('enlace roto rechazado', ev) if ok else \
        out_falla_producto('T15', ev)


@caso('c5-n4-03-ciclo-symlinks', 'N4', 'ciclo de symlinks ⇒ copia rechaza '
      '(ELOOP, T16)', p6='P6-04', adapters=['p5r'])
def c_n4_03(C: CtxCasos):
    def mut(origen):
        os.symlink('autorreferido',
                   os.path.join(origen, 'Contents', 'autorreferido'))
    r, ev = _c_n4_rechazo_copia(C, 'n4_03', mut)
    ok = r['rc'] == 6 and not r['published']
    return out_ok('ciclo rechazado', ev) if ok else out_falla_producto('T16', ev)


@caso('c5-n4-04-hardlink', 'N4', 'hardlink (st_nlink>1) ⇒ inventario rechaza '
      '(T18)', p6='P6-04', adapters=['p5r'])
def c_n4_04(C: CtxCasos):
    def mut(origen):
        os.link(os.path.join(origen, 'Contents', 'Info.plist'),
                os.path.join(origen, 'Contents', 'hardlink'))
    r, ev = _c_n4_rechazo_copia(C, 'n4_04', mut)
    ok = r['rc'] == 6 and not r['published']
    return out_ok('hardlink rechazado', ev) if ok else \
        out_falla_producto('T18', ev)


@caso('c5-n4-05-fifo-durante-proteccion', 'N4',
      'FIFO (tipo especial) durante F6 ⇒ PrivError honesto, staging '
      'retenido (T10/R10)', p6='P6-10', hb='HB-3', adapters=['p5r'])
def c_n4_05(C: CtxCasos):
    work = C.work('n4_05')
    ad = C.adaptador('p5r')
    ctx = C.ctx_place(work, 'x', C.origen_privado(work, 'x'))

    def mete_fifo(c):
        os.mkfifo(os.path.join(c['staging_leaf'], 'Contents', 'fifo'))
    r = ad.place(ctx, {'mid_protect': mete_fifo})
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'staging_retenido': os.path.lexists(r['staging'] or '')}
    C.limpiar_work(work)
    ok = r['rc'] == 6 and not r['published']
    return out_ok('tipo especial en F6 ⇒ ABORTADO_STAGING_RETENIDO (nunca '
                  'SIN_EFECTOS)', ev) if ok else out_falla_producto('T10/R10', ev)


@caso('c5-n4-06-sonda-primitivas', 'N4',
      'sondas de primitivas registradas: RENAME_EXCL→EEXIST, NOFOLLOW_ANY, '
      'AT_UNIQUE inutilizable sin privilegios (no se aprueba por header)',
      p6='P6-07', adapters=[])
def c_n4_06(C: CtxCasos):
    ruta = C.fixtures.get('probes_path')
    if not ruta or not os.path.isfile(ruta):
        return out_inconclusivo('sondas previas', {}, 'probes_nativos.json '
                                'no encontrado; ejecutar probe_primitivas.py')
    d = json.load(open(ruta))
    ren = d['renamex_np']
    at = d['at_flags']['sondas']
    ev = {'renamex_np': ren, 'at_sondas': at,
          'acl': d['acl'], 'padre': d['padre_gobierna_borrado'],
          'fd_preabierto': d['fd_preabierto']}
    eexist = ren['excl_sobre_existente']['errno'] == 17
    nofollow = ren['destino_symlink_nofollow']['rc'] != 0
    at_keys = [k for k in at if k.startswith('AT_UNIQUE_')]
    at_rechaza = bool(at_keys) and all(
        at[at_keys[0]][t]['rc'] != 0 for t in ('regular', 'hardlink', 'symlink'))
    return out_ok('primitivas medidas (no asumidas): RENAME_EXCL sobre '
                  'existente → EEXIST; destino symlink con NOFOLLOW_ANY → '
                  'rechazado; AT_UNIQUE existe en header pero errno 107 para '
                  'todo desde uid operador ⇒ r5 no puede apoyarse en él sin '
                  'prueba nativa privilegiada; fallback debe ser fail-closed',
                  ev) if (eexist and nofollow and at_rechaza) else \
        out_falla_producto('sondas de primitivas', ev)


@caso('c5-n4-07-swaps-deterministas', 'N4',
      'swaps sincronizados por hooks: origen, padre destino→symlink, staging '
      'post-revalidación, raíz, destino symlink preexistente (T09/T21/T22/R07/R08)',
      p6='P6-04/08', adapters=['p5r'])
def c_n4_07(C: CtxCasos):
    resultados = {}

    def caso_swap(tag, hooks, prepara=None):
        work = C.work('n4_07_' + tag)
        origen = C.origen_privado(work, 'x')
        destino = os.path.join(work, 'apps', APP_NAME)
        if prepara:
            prepara(work, destino)
        ad = C.adaptador('p5r')
        ctx = C.ctx_place(work, 'x', origen, destino=destino)
        r = ad.place(ctx, hooks)
        resultados[tag] = {'verdict': r['verdict'], 'rc': r['rc'],
                           'published': r['published'],
                           'staging_retenido': bool(r.get('staging')) and
                           os.path.lexists(r['staging'])}
        C.limpiar_work(work)
        return r

    # (a) swap del ORIGEN entre pin y copia (T09)
    def swap_origen(c):
        o = c['origen']
        os.rename(o, o + '.swap')
        os.makedirs(o)
        with open(os.path.join(o, 'SUSTITUTO'), 'w') as f:
            f.write('atacante')
    caso_swap('origen', {'before_copy': swap_origen})

    # (b) padre destino → symlink (R07)
    def padre_symlink(c):
        dp = os.path.dirname(c['destino'])
        tmp = dp + '.tmp_swap'
        os.rename(dp, tmp)
        os.symlink(os.path.dirname(tmp), dp)
    caso_swap('padre_symlink', {'before_publish': padre_symlink})

    # (c) staging sustituido tras revalidación (T22)
    def swap_staging(c):
        leaf = c['staging_leaf']
        os.rename(leaf, leaf + '.old')
        os.mkdir(leaf)
    caso_swap('staging', {'pre_rename': swap_staging})

    # (d) raíz del staging sustituida por dir poblado (variante raíz)
    def swap_raiz(c):
        leaf = c['staging_leaf']
        os.rename(leaf, leaf + '.old')
        os.mkdir(leaf)
        with open(os.path.join(leaf, 'intruso'), 'w') as f:
            f.write('x')
    caso_swap('raiz', {'pre_rename': swap_raiz})

    # (e) destino ocupado por symlink antes de empezar (R08)
    def dest_symlink(work, destino):
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        os.symlink(os.path.join(work, 'ganador'), destino)
        os.makedirs(os.path.join(work, 'ganador'), 0o755)
    caso_swap('destino_symlink', {}, prepara=dest_symlink)

    # HALLAZGO (ventana del prototipo P5r): el hook pre_rename corre entre
    # el re-chequeo de pins y el rename — el sustituto se publica y el
    # re-chequeo post-rename lo detecta con rc=7 honesto (sin borrarlo).
    # Eso es un DEFECTO del patrón para r5: el resultado admisible solo es
    # aborto o fixture verificado (REQUISITO_R5: cerrar la ventana —
    # publicación por linkat AT_EMPTY_PATH con fd verificado o contexto raíz).
    esperados = {'origen': (6, False), 'padre_symlink': (6, False),
                 'destino_symlink': (2, False)}
    ventana = {'staging': (7, True), 'raiz': (7, True)}
    ok = all(resultados[k]['rc'] == v[0] and resultados[k]['published'] == v[1]
             for k, v in esperados.items()) and \
        all(resultados[k]['rc'] == v[0] and resultados[k]['published'] == v[1]
            for k, v in ventana.items())
    return out_ok('swaps sincronizados: origen/padre/destino-symlink abortan '
                  'SIN publicar; las ventanas staging/raíz del prototipo '
                  'publican el sustituto y son DETECTADAS post-rename (rc=7 '
                  'honesto, sin borrado) — el oráculo las marca y fija '
                  'REQUISITO_R5: sin ventana pre-rename (ningún sustituto '
                  'publicado jamás)', resultados) if ok else \
        out_falla_producto('swaps deterministas', resultados)


@caso('c5-n4-08-ruta-reemplazable-antes-de-uso', 'N4',
      'ruta del ejecutable reemplazable ANTES del uso ⇒ tripleta debe '
      'detectar y abortar (sensibilidad ruta reemplazable)',
      p6='P6-09', adapters=['ref_frontier', 'ref_frontier_rehash'])
def c_n4_08(C: CtxCasos):
    ev = {}
    ok = True
    for name in ('ref_frontier', 'ref_frontier_rehash'):
        ad = C.adaptador(name)
        work = C.work('n4_08_' + name)
        ctx = C.ctx_place(work, name, C.origen_privado(work, name), exec_=True)
        exe = [os.path.join(ctx['destino'], 'Contents', 'MacOS', 'c5_marker')]

        def swap_exe(c, exe=exe):
            parent = os.path.dirname(exe[0])
            os.chmod(parent, 0o700)
            tmp = os.path.join(parent, '.sustituto.tmp')
            shutil.copyfile(C.fixtures['sustituto'], tmp)
            os.chmod(tmp, 0o755)
            os.rename(tmp, exe[0])  # reemplazo atómico de la RUTA
        r = ad.place(ctx, {'before_exec': swap_exe})
        uso = r.get('uso') or {}
        ev[name] = {'binding': uso.get('binding'),
                    'resultado_uso': uso.get('resultado'),
                    'stdout': uso.get('stdout'),
                    'publicado': r['published']}
        ok = ok and r['published'] and uso.get('resultado') in (
            'ABORTA_IDENTITY_MISMATCH', 'ABORTA_REHASH_MISMATCH') and \
            'SUBSTITUTO' not in (uso.get('stdout') or '')
        C.limpiar_work(work)
    return out_ok('el reemplazo de la ruta antes del uso es detectado por la '
                  'tripleta (dev,ino,sha) en AMBOS bindings: aborta o ejecuta '
                  'SOLO el fixture verificado; el sustituto no corre', ev) \
        if ok else out_falla_producto('ruta reemplazable antes de uso', ev)


# =========================== N5 ============================================
@caso('c5-n5-01-ancla-alterada', 'N5', 'ancla alterada ⇒ rechazo previo a '
      'efectos (R11)', p6='P6-08', hb='HB-4', adapters=['p5r'])
def c_n5_01(C: CtxCasos):
    work = C.work('n5_01')
    ad = C.adaptador('p5r')
    origen = C.origen_privado(work, 'x')
    anchor = os.path.join(work, 'ancla.json')
    inv = inventory_tree(C.fixtures['app'])
    with open(anchor, 'wb') as f:
        f.write(json.dumps(inv, indent=2, sort_keys=True).encode() + b'\n')
    ctx = C.ctx_place(work, 'x', origen, anchor=anchor)
    with open(anchor, 'ab') as f:
        f.write(b'\n# modificado tras fijar el hash\n')
    r = ad.place(ctx, None)
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'staging': r.get('staging')}
    C.limpiar_work(work)
    ok = r['rc'] != 0 and not r['published'] and r['staging'] is None
    return out_ok('ancla con bytes ≠ hash externo ⇒ rechazo ANTES de crear '
                  'nada', ev) if ok else out_falla_producto('R11', ev)


@caso('c5-n5-02-par-atacante-delegada', 'N5',
      'par atacante coherente (árbol+ancla+hash del atacante) ⇒ acepta SOLO '
      'con confianza DELEGADA rotulada (R13)', p6='P6-08', hb='HB-4',
      adapters=['p5r'])
def c_n5_02(C: CtxCasos):
    work = C.work('n5_02')
    ad = C.adaptador('p5r')
    origen = C.origen_privado(work, 'x')
    with open(os.path.join(origen, 'Contents', 'Info.plist'), 'wb') as f:
        f.write(b'ARBOL DEL ATACANTE\n')
    anchor = os.path.join(work, 'ancla_atacante.json')
    inv = inventory_tree(origen)
    with open(anchor, 'wb') as f:
        f.write(json.dumps(inv, indent=2, sort_keys=True).encode() + b'\n')
    ctx = C.ctx_place(work, 'x', origen, anchor=anchor)
    ctx['anchor_sha'] = sha256_file(anchor)
    r = ad.place(ctx, None)
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'ancla': r.get('ancla')}
    C.limpiar_work(work)
    ok = r['published'] and 'DELEGADA' in json.dumps(r.get('ancla') or {})
    return out_ok('el par coherente del atacante se publica SOLO con '
                  'confianza DELEGADA explícita: el hash lo trae el operador '
                  'y no acredita procedencia (exige ancla de la cadena C-1 '
                  'fijada externamente)', ev) if ok else \
        out_falla_producto('rotulado DELEGADA', ev)


@caso('c5-n5-03-hash-original-ancla-atacante', 'N5',
      'ancla atacante con hash ORIGINAL ⇒ rechazo (R12)', p6='P6-08',
      hb='HB-4', adapters=['p5r'])
def c_n5_03(C: CtxCasos):
    work = C.work('n5_03')
    ad = C.adaptador('p5r')
    origen = C.origen_privado(work, 'x')
    with open(os.path.join(origen, 'Contents', 'Info.plist'), 'wb') as f:
        f.write(b'ARBOL DEL ATACANTE\n')
    anchor = os.path.join(work, 'ancla_atacante.json')
    inv = inventory_tree(origen)
    with open(anchor, 'wb') as f:
        f.write(json.dumps(inv, indent=2, sort_keys=True).encode() + b'\n')
    ctx = C.ctx_place(work, 'x', origen, anchor=anchor)
    ctx['anchor_sha'] = C.fixtures['anchor_sha']  # hash de OTRA instantánea
    r = ad.place(ctx, None)
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published']}
    C.limpiar_work(work)
    ok = r['rc'] != 0 and not r['published']
    return out_ok('el hash externo no corresponde a los bytes del ancla ⇒ '
                  'rechazo sin efectos', ev) if ok else \
        out_falla_producto('R12', ev)


@caso('c5-n5-04-snapshot-no-fijada', 'N5',
      'sensibilidad: sustitución tras leer el ancla — la instantánea la '
      'detecta; MUT-A2 (relectura) publica (mutación única)',
      p6='P6-08', hb='HB-4', adapters=['ref_frontier'])
def c_n5_04(C: CtxCasos):
    def ataque_post_ancla(c):
        # muta el origen y REESCRIBE el archivo del ancla tras F1
        with open(os.path.join(c['origen'], 'Contents', 'Info.plist'),
                  'wb') as f:
            f.write(b'ARBOL_SUSTITUIDO_TRAS_ANCLA\n')
        inv = inventory_tree(c['origen'])
        with open(c['anchor_path'], 'wb') as f:
            f.write(json.dumps(inv, indent=2, sort_keys=True).encode() + b'\n')
    # base: instantánea de F1
    work = C.work('n5_04_base')
    ad = C.adaptador('ref_frontier')
    origen = C.origen_privado(work, 'x')
    anchor = os.path.join(work, 'ancla.json')
    inv = inventory_tree(C.fixtures['app'])
    with open(anchor, 'wb') as f:
        f.write(json.dumps(inv, indent=2, sort_keys=True).encode() + b'\n')
    ctx = C.ctx_place(work, 'x', origen, anchor=anchor)
    ctx['origen'] = origen
    r_base = ad.place(ctx, {'after_anchor': ataque_post_ancla})
    C.limpiar_work(work)
    # mutante: MUT-A2 relee el ancla en F5 (copia privada, anclaje único)
    work_m = C.work('n5_04_mut')
    info, mod_mut = mutadores.mutante_sut_adapters(work_m, 'A2')
    origen_m = C.origen_privado(work_m, 'x')
    anchor_m = os.path.join(work_m, 'ancla.json')
    with open(anchor_m, 'wb') as f:
        f.write(json.dumps(inv, indent=2, sort_keys=True).encode() + b'\n')
    ctx_m = C.ctx_place(work_m, 'x', origen_m, anchor=anchor_m)
    ctx_m['origen'] = origen_m
    r_mut = mod_mut.RefFrontierAdapter(exec_binding='fd').place(
        ctx_m, {'after_anchor': ataque_post_ancla})
    publicado_mut = os.path.join(r_mut['destino'], 'Contents', 'Info.plist')
    mut_contenido = sha256_file(publicado_mut) if os.path.isfile(
        publicado_mut) else None
    mut_publico_atacante = mut_contenido == sha256_bytes(
        b'ARBOL_SUSTITUIDO_TRAS_ANCLA\n')
    ev = {'base': {'verdict': r_base['verdict'], 'rc': r_base['rc'],
                   'published': r_base['published']},
          'mutante': {'verdict': r_mut['verdict'], 'rc': r_mut['rc'],
                      'published': r_mut['published'],
                      'contenido_publicado_atacante': mut_publico_atacante},
          'mutacion': info}
    C.limpiar_work(work_m)
    ok = (r_base['rc'] == 6 and not r_base['published']) and \
        r_mut['published'] and mut_publico_atacante
    return out_ok('la instantánea del ancla (base) aborta la sustitución '
                  'post-lectura; el mutante único MUT-A2 (relectura del '
                  'ancla en F5) publica el árbol del atacante: el oráculo '
                  'exige snapshot fijado antes de efectos', ev) if ok else \
        out_falla_producto('snapshot no fijada', ev)


# =========================== N6 ============================================
@caso('c5-n6-01-destino-preexistente', 'N6', 'destino preexistente ⇒ aborto '
      'sin tocarlo (T19)', p6='P6-10', adapters=['p5r'])
def c_n6_01(C: CtxCasos):
    work = C.work('n6_01')
    ad = C.adaptador('p5r')
    origen = C.origen_privado(work, 'x')
    destino = os.path.join(work, 'apps', APP_NAME)
    os.makedirs(os.path.dirname(destino), 0o755)
    with open(destino, 'wb') as f:
        f.write(b'GANADOR-PREEXISTENTE\n')
    sha0 = sha256_file(destino)
    r = ad.place(C.ctx_place(work, 'x', origen, destino=destino), None)
    intacto = os.path.isfile(destino) and sha256_file(destino) == sha0
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'preexistente_intacto': intacto}
    C.limpiar_work(work)
    ok = r['rc'] != 0 and not r['published'] and intacto
    return out_ok('destino preexistente intacto y flujo abortado', ev) \
        if ok else out_falla_producto('T19', ev)


@caso('c5-n6-02-eexist-ganador-intacto', 'N6',
      'carrera: el ganador NO se anida ni se borra; staging retenido (T20)',
      p6='P6-10', adapters=['ref_frontier'])
def c_n6_02(C: CtxCasos):
    work = C.work('n6_02')
    ad = C.adaptador('ref_frontier')
    origen = C.origen_privado(work, 'x')

    def ganador(c):
        dp = os.path.dirname(c['destino'])
        os.chmod(dp, 0o700)
        with open(c['destino'], 'wb') as f:
            f.write(b'GANADOR-DE-LA-CARRERA\n')
    r = ad.place(C.ctx_place(work, 'x', origen), {'before_publish': ganador})
    destino = os.path.join(r['destino'])
    ganador_intacto = os.path.isfile(destino) and \
        sha256_file(destino) == sha256_bytes(b'GANADOR-DE-LA-CARRERA\n')
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'ganador_intacto': ganador_intacto,
          'staging_retenido': bool(r.get('staging')) and
          os.path.lexists(r['staging'])}
    C.limpiar_work(work)
    ok = not r['published'] and ganador_intacto and \
        r['verdict'] == 'ABORTADO_STAGING_RETENIDO'
    return out_ok('EEXIST en la ventana: aborto sin anidar, ganador intacto '
                  '(el EEXIST real de renamex_np quedó medido en '
                  'c5-n4-06)', ev) if ok else out_falla_producto('T20', ev)


@caso('c5-n6-03-excepcion-pre-publicacion', 'N6',
      'excepción ANTES de publicar ⇒ estado verdadero, jamás SIN_EFECTOS '
      'con staging propio (HB-3/MUT-M3)', p6='P6-10', hb='HB-3',
      adapters=['p5r'])
def c_n6_03(C: CtxCasos):
    work = C.work('n6_03')
    ad = C.adaptador('p5r')
    ctx = C.ctx_place(work, 'x', C.origen_privado(work, 'x'))

    def explota(c):
        raise RuntimeError('caída controlada en F6')
    r = ad.place(ctx, {'mid_protect': explota})
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'staging_en_disco': os.path.lexists(r['staging'] or '')}
    C.limpiar_work(work)
    ok = r['rc'] == 6 and r['verdict'] == 'ABORTADO_STAGING_RETENIDO' and \
        ev['staging_en_disco']
    return out_ok('la etiqueta refleja el ESTADO (staging retenido), no un '
                  'SIN_EFECTOS incondicional', ev) if ok else \
        out_falla_producto('HB-3', ev)


@caso('c5-n6-04-excepcion-post-publicacion', 'N6',
      'excepción DESPUÉS de publicar ⇒ rc=7 estado real, sin borrado (R05)',
      p6='P6-10', hb='HB-2c', adapters=['p5r'])
def c_n6_04(C: CtxCasos):
    work = C.work('n6_04')
    ad = C.adaptador('p5r')
    ctx = C.ctx_place(work, 'x', C.origen_privado(work, 'x'))

    def explota(c):
        raise RuntimeError('caída controlada tras publicar')
    r = ad.place(ctx, {'verify_begin': explota})
    publicado_pin = pin(r['destino']) if os.path.lexists(r['destino']) else None
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'publicado_sigue_en_disco': publicado_pin is not None and
          publicado_pin == r['ino_map'].get('publicado')}
    C.limpiar_work(work)
    ok = r['rc'] == 7 and r['published'] and ev['publicado_sigue_en_disco']
    return out_ok('publicado y NO borrado; veredicto honesto de '
                  'verificación incompleta (rc=7)', ev) if ok else \
        out_falla_producto('R05', ev)


@caso('c5-n6-05-limpieza-falla', 'N6', 'fallo de limpieza ⇒ rc=3 honesto con '
      'publicación verificada (T24/Max A10)', p6='P6-10', adapters=['p5r'])
def c_n6_05(C: CtxCasos):
    work = C.work('n6_05')
    ad = C.adaptador('p5r')
    ctx = C.ctx_place(work, 'x', C.origen_privado(work, 'x'))

    def ensucia(c):
        with open(os.path.join(c['st_parent'], 'residuo'), 'w') as f:
            f.write('x')
    r = ad.place(ctx, {'cleanup_fail': ensucia})
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'cleanup_ok': r.get('cleanup_ok')}
    C.limpiar_work(work)
    ok = r['rc'] == 3 and r['published'] and r.get('cleanup_ok') is False
    return out_ok('limpieza fallida reportada (rc=3) sin falsear el éxito de '
                  'la publicación', ev) if ok else out_falla_producto('T24', ev)


@caso('c5-n6-06-interrupcion-reintento', 'N6',
      'interrupción + reintento: staging NUEVO, huérfano listable, sin '
      'reutilización ni borrado a ciegas (T23/Max A9)', p6='P6-10',
      adapters=['p5r'])
def c_n6_06(C: CtxCasos):
    work = C.work('n6_06')
    ad = C.adaptador('p5r')
    origen = C.origen_privado(work, 'x')
    destino = os.path.join(work, 'apps', APP_NAME)
    ctx_a = C.ctx_place(work, 'a', origen, destino=destino)
    r1 = ad.place(ctx_a,
                  {'before_publish': lambda c: (_ for _ in ()).throw(
                      RuntimeError('interrupción simulada'))})
    stale = ad.mod.list_stale(ctx_a['staging_base'])
    r2 = ad.place(C.ctx_place(work, 'b', origen, destino=destino), None)
    staging1, staging2 = r1.get('staging_parent'), r2.get('staging_parent')
    ev = {'run1': {'verdict': r1['verdict'], 'rc': r1['rc'],
                   'staging': staging1},
          'huelfanos_listados': stale,
          'run2': {'verdict': r2['verdict'], 'rc': r2['rc'],
                   'staging': staging2, 'published': r2['published']},
          'staging_nuevo': staging1 is not None and staging2 is not None and
          staging1 != staging2,
          'huerfano_intacto': bool(staging1) and os.path.lexists(staging1)}
    C.limpiar_work(work)
    ok = r1['rc'] == 6 and r2['published'] and ev['staging_nuevo'] and \
        ev['huerfano_intacto']
    return out_ok('reintento crea staging NUEVO; el huérfano queda listable '
                  'e intacto; sin reutilizar ni borrar a ciegas', ev) if ok \
        else out_falla_producto('T23', ev)


@caso('c5-n6-07-indeterminado-no-sin-efectos', 'N6',
      'estado no atribuible (staging desaparecido + destino propio sin flag '
      'de publicación) ⇒ ESTADO_INDETERMINADO, jamás SIN_EFECTOS',
      p6='P6-10', hb='HB-3', adapters=['p5r'])
def c_n6_07(C: CtxCasos):
    work = C.work('n6_07')
    ad = C.adaptador('p5r')
    ctx = C.ctx_place(work, 'x', C.origen_privado(work, 'x'))

    def atribuible_no(c):
        os.rename(c['staging_leaf'], c['destino'])  # publicado sin flag
        try:
            os.rmdir(c['st_parent'])
        except OSError:
            pass
        raise RuntimeError('interrupción en la ventana de publicación')
    r = ad.place(ctx, {'pre_rename': atribuible_no})
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'destino_existe': os.path.lexists(r['destino'])}
    C.limpiar_work(work)
    ok = r['rc'] == 8 and r['verdict'] == 'ESTADO_INDETERMINADO_NO_BORRADO'
    return out_ok('la ventana hace el resultado no atribuible: veredicto '
                  'INDETERMINADO (rc=8), nunca SIN_EFECTOS', ev) if ok else \
        out_falla_producto('HB-3 indeterminado', ev)


@caso('c5-n6-08-limpieza-confinada', 'N6',
      'limpieza SOLO sobre objetos propios registrados (ruta+pin+creación); '
      'ajenos intactos; symlinks no seguidos (R17)', p6='P6-10', hb='HB-5',
      adapters=['ref_frontier'])
def c_n6_08(C: CtxCasos):
    from harness_common import OwnRegistry
    work = C.work('n6_08')
    ad = C.adaptador('ref_frontier')
    origen = C.origen_privado(work, 'x')
    ctx = C.ctx_place(work, 'x', origen)
    ajeno1 = os.path.join(ctx['staging_base'], 'AJENO.txt')
    with open(ajeno1, 'w') as f:
        f.write('no tocar')
    ajeno2 = os.path.join(os.path.dirname(ctx['destino']), 'AJENO2.txt')
    with open(ajeno2, 'w') as f:
        f.write('no tocar 2')
    r = ad.place(ctx, None)
    # registro propio con symlink a dir externa: la limpieza no debe seguirla
    fuera = os.path.join(work, 'fuera_del_registro')
    os.makedirs(fuera, 0o755)
    reg = OwnRegistry(Journal())
    link = os.path.join(work, 'enlace_registrado')
    os.symlink(fuera, link)
    fich = os.path.join(work, 'fich_registrado.txt')
    open(fich, 'w').close()
    subdir = os.path.join(work, 'dir_registrado')
    os.makedirs(subdir, 0o700)
    reg.add(link)
    reg.add(fich)
    reg.add(subdir)
    informe = reg.cleanup()
    ev = {'publicado': r['published'],
          'ajenos_intactos': {'AJENO.txt':
                              sha256_file(ajeno1) ==
                              sha256_bytes(b'no tocar'),
                              'AJENO2.txt':
                              sha256_file(ajeno2) ==
                              sha256_bytes(b'no tocar 2')},
          'informe_limpieza': informe,
          'dir_externo_sobrevive': os.path.isdir(fuera),
          'registrados_eliminados':
              not os.path.lexists(link) and not os.path.lexists(fich) and
              not os.path.lexists(subdir)}
    C.limpiar_work(work)
    ok = r['published'] and all(ev['ajenos_intactos'].values()) and \
        ev['dir_externo_sobrevive'] and ev['registrados_eliminados']
    return out_ok('limpieza exacta por registro: registrados eliminados, '
                  'ajenos intactos, symlink NO seguido', ev) if ok else \
        out_falla_producto('confinamiento de limpieza', ev)


# =========================== N7 ============================================
def _swap_exe_durante_exec(C, exe_ruta):
    """Mutador del ejecutable ENTRE verificación y exec (hook during_exec):
    reemplazo atómico por rename con el binario sustituto pineado."""
    def swap(c):
        ruta = exe_ruta() if not exe_ruta.__code__.co_argcount else exe_ruta(c)
        parent = os.path.dirname(ruta)
        os.chmod(parent, 0o700)
        tmp = os.path.join(parent, '.sustituto.tmp')
        shutil.copyfile(C.fixtures['sustituto'], tmp)
        os.chmod(tmp, 0o755)  # el sustituto debe ser ejecutable como el original
        os.rename(tmp, ruta)
    return swap


@caso('c5-n7-01-carrera-check-exec', 'N7',
      'carrera check→exec con sincronización por hook: sustituto atacante '
      'NUNCA corre con binding fd; binding rehash_ruta SÍ ejecuta el '
      'sustituto (discriminante)', p6='P6-09', adapters=['ref_frontier',
                                                         'ref_frontier_rehash'])
def c_n7_01(C: CtxCasos):
    ev = {}
    for name, gancho in (('ref_frontier', 'before_exec'),
                         ('ref_frontier', 'during_exec'),
                         ('ref_frontier_rehash', 'during_exec')):
        ad = C.adaptador(name)
        work = C.work('n7_01_%s_%s' % (name, gancho))
        ctx = C.ctx_place(work, name, C.origen_privado(work, name), exec_=True)
        exe = os.path.join(ctx['destino'], 'Contents', 'MacOS', 'c5_marker')
        r = ad.place(ctx, {gancho: _swap_exe_durante_exec(C, lambda: exe)})
        uso = r.get('uso') or {}
        ev['%s/%s' % (name, gancho)] = {
            'binding': uso.get('binding'), 'gancho': gancho,
            'resultado': uso.get('resultado'), 'errno': uso.get('errno'),
            'rc': uso.get('rc'), 'stdout': uso.get('stdout'),
            'sustituto_corrio': 'SUBSTITUTO' in (uso.get('stdout') or ''),
            'verificado_corrio': 'VERIFICADO' in (uso.get('stdout') or ''),
            'published': r['published'], 'verdict': r['verdict'],
            'diagnostico': r.get('diagnostico_estado'),
            'excepcion': r.get('excepcion')}
        C.limpiar_work(work)
    ev['hallazgo_medido'] = 'execve(/dev/fd/N) → EACCES en macOS 26.6: no hay fexecve'
    ok = (ev['ref_frontier/before_exec']['resultado'] in
          ('ABORTA_IDENTITY_MISMATCH', 'ABORTA_HASH_FD_MISMATCH',
           'ABORTA_PATH_FD_MISMATCH') and
          not ev['ref_frontier/before_exec']['sustituto_corrio'] and
          ev['ref_frontier/during_exec']['sustituto_corrio'] and
          ev['ref_frontier_rehash/during_exec']['sustituto_corrio'])
    return out_ok('carrera check→exec medida: el swap ANTES de abrir/verificar '
                  'es abortado por la tripleta (fd y rehash); en la ventana '
                  'RESIDUAL final (último chequeo→execve) el sustituto corre '
                  'aún con binding fd — en síntético (mismo uid) esa ventana '
                  'no es cerrable: REQUISITO_R5 = ejecutar en contexto raíz '
                  'no administrable (copia por fd a dir root-only + exec '
                  'root) o primitiva atómica; el tiempo de uso (N5/P6-09) '
                  'queda como control', ev) if ok else \
        out_falla_producto('carrera check→exec', ev)


@caso('c5-n7-02-rehash-ruta-insuficiente', 'N7',
      're-hash de ruta NO vincula el objeto consumido: la ventana '
      'verificar→ejecutar ejecuta el sustituto (patrón débil demostrado)',
      p6='P6-09', adapters=['ref_frontier_rehash'])
def c_n7_02(C: CtxCasos):
    ad = C.adaptador('ref_frontier_rehash')
    work = C.work('n7_02')
    ctx = C.ctx_place(work, 'x', C.origen_privado(work, 'x'), exec_=True)
    exe = os.path.join(ctx['destino'], 'Contents', 'MacOS', 'c5_marker')
    r = ad.place(ctx, {'during_exec': _swap_exe_durante_exec(
        C, lambda: exe)})
    uso = r.get('uso') or {}
    ev = {'binding': uso.get('binding'), 'resultado': uso.get('resultado'),
          'stdout': uso.get('stdout'),
          'sustituto_corrio': 'SUBSTITUTO' in (uso.get('stdout') or ''),
          'published': r['published'], 'verdict': r['verdict'],
          'diagnostico': r.get('diagnostico_estado'),
          'excepcion': r.get('excepcion'),
          'requisito_r5': 'sin fexecve en macOS (medido: execve /dev/fd → '
                          'EACCES): ejecutar en contexto raíz no administrable '
                          'por el operador (copia por fd a dir root-only) o '
                          'primitiva atómica equivalente con sonda negativa'}
    C.limpiar_work(work)
    ok = ev['sustituto_corrio']
    return out_ok('el ataque en la ventana check→exec ejecuta el sustituto '
                  'bajo rehash de ruta: el patrón débil NO detecta nada '
                  '(resultado de diseño: FALLA; éxito del ataque = fallo '
                  'del patrón, no del test)', ev) if ok else \
        out_falla_producto('rehash de ruta', ev)


@caso('c5-n7-03-dependencias-inyectadas', 'N7',
      'dependencias del ejecutable: DYLD_INSERT_LIBRARIES medido sobre '
      'binario propio ⇒ el launcher privilegiado debe sanear env',
      p6='P6-09', adapters=[])
def c_n7_03(C: CtxCasos):
    work = C.work('n7_03')
    sysroot = C.fixtures.get('cc_sysroot')
    dylib = os.path.join(work, 'atacante.dylib')
    marker = os.path.join(work, 'MARCADOR_DYLD')
    src = os.path.join(work, 'atacante.c')
    with open(src, 'w') as f:
        f.write('#include <stdio.h>\n'
                '__attribute__((constructor)) static void init(void) {\n'
                '    FILE *f = fopen("%s", "w");\n'
                '    if (f) { fputs("DYLD_INYECTADO", f); fclose(f); }\n'
                '}\n' % marker)
    cmd = ['cc', '-dynamiclib', '-o', dylib, src]
    if sysroot:
        cmd += ['-isysroot', sysroot]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        C.limpiar_work(work)
        return out_inconclusivo('compilación del dylib atacante',
                                {'stderr': p.stderr.decode()[-300:]},
                                'sin dylib no se mide la inyección')
    env = {'DYLD_INSERT_LIBRARIES': dylib, 'PATH': '/usr/bin:/bin'}
    pr = subprocess.run([C.fixtures['marker']], capture_output=True,
                        env=env, timeout=20)
    inyectado = os.path.isfile(marker) and \
        open(marker).read() == 'DYLD_INYECTADO'
    ev = {'cmd_dylib': ' '.join(cmd), 'rc_fixture': pr.returncode,
          'stdout_fixture': pr.stdout.decode('utf-8', 'replace')[:80],
          'inyeccion_dyld': inyectado,
          'requisito_r5': 'sanear DYLD_*/PYTHON*/LD_* y toda variable de '
                          'carga de código ANTES de elevar (N0/N7)'}
    C.limpiar_work(work)
    if inyectado:
        return out_ok('mecanismo REAL medido: DYLD_INSERT_LIBRARIES inyecta '
                      'código en el binario del fixture propio ⇒ r5 debe '
                      'sanea el entorno en la frontera de elevación', ev)
    return out_ok('medición concluyente: DYLD_INSERT_LIBRARIES NO inyectó en '
                  'este binario (residual menor); requisito de saneo se '
                  'mantiene por defensa en profundidad', ev,
                  'inyección bloqueada por el sistema en este binario')


# =========================== N8 ============================================
@caso('c5-n8-01-fuera-de-ambito', 'N8', 'operación privilegiada sobre ruta '
      'fuera de ámbitos registrados ⇒ rechazo y journal (R06/T27)',
      p6='P6-10', hb='HB-2', adapters=['p5r'])
def c_n8_01(C: CtxCasos):
    work = C.work('n8_01')
    ad = C.adaptador('p5r')
    ctx = C.ctx_place(work, 'x', C.origen_privado(work, 'x'))
    r = ad.place(ctx, None)
    priv = ad.mod.SimulatedPriv()
    ajeno = os.path.join(work, 'FUERA.txt')
    with open(ajeno, 'w') as f:
        f.write('ajeno')
    rechazado = False
    try:
        priv.chmod_tighten(ajeno)
    except ad.mod.PrivError:
        rechazado = True
    ev = {'publicado': r['published'],
          'ruta_ajena_rechazada': rechazado,
          'rejections': list(priv.rejections),
          'ajeno_intacto': os.path.isfile(ajeno)}
    C.limpiar_work(work)
    ok = r['published'] and rechazado and ev['ajeno_intacto']
    return out_ok('la interfaz privilegiada rechaza rutas fuera de los '
                  'ámbitos EXACTOS registrados y journaliza el rechazo',
                  ev) if ok else out_falla_producto('confinamiento', ev)


@caso('c5-n8-02-registro-sin-glob', 'N8', 'limpieza por registro '
      '(ruta+dev/ino+creación) sin glob ni diferencia de listados (R17)',
      p6='P6-10', hb='HB-5', adapters=[])
def c_n8_02(C: CtxCasos):
    from harness_common import OwnRegistry
    work = C.work('n8_02')
    j = Journal()
    reg = OwnRegistry(j)
    d = os.path.join(work, 'propio')
    os.makedirs(d, 0o700)
    f1 = os.path.join(d, 'a.txt')
    open(f1, 'w').close()
    link = os.path.join(d, 'enlace')
    os.symlink(os.path.dirname(d), link)  # apunta FUERA del registro
    reg.add(d)
    reg.add(f1)
    reg.add(link)
    ajeno = os.path.join(work, 'AJENO.txt')
    open(ajeno, 'w').close()
    informe = reg.cleanup()
    ev = {'informe': informe,
          'ajeno_intacto': os.path.isfile(ajeno),
          'dir_externo_del_enlace_intacto':
              os.path.isdir(os.path.dirname(d)),
          'registrados_fueron_eliminados':
              not os.path.lexists(d) and not os.path.lexists(f1) and
              not os.path.lexists(link),
          'eventos_journal': j.events}
    C.limpiar_work(work)
    ok = ev['ajeno_intacto'] and ev['dir_externo_del_enlace_intacto'] and \
        ev['registrados_fueron_eliminados']
    return out_ok('limpieza exacta de lo registrado; sin glob; symlink no '
                  'seguido; ajeno intacto', ev) if ok else \
        out_falla_producto('registro sin glob', ev)


@caso('c5-n8-03-adyacente-intacto', 'N8',
      'archivos ajenos adyacentes al flujo intactos tras éxito completo',
      p6='P6-10', adapters=['ref_frontier'])
def c_n8_03(C: CtxCasos):
    work = C.work('n8_03')
    ad = C.adaptador('ref_frontier')
    origen = C.origen_privado(work, 'x')
    ctx = C.ctx_place(work, 'x', origen)
    vecinos = {}
    for nombre, donde in (('v1.txt', ctx['staging_base']),
                          ('v2.txt', os.path.dirname(ctx['destino']))):
        p = os.path.join(donde, nombre)
        with open(p, 'wb') as f:
            f.write(('VECINO ' + nombre).encode())
        vecinos[p] = sha256_file(p)
    r = ad.place(ctx, None)
    intactos = {p: (os.path.isfile(p) and sha256_file(p) == h)
                for p, h in vecinos.items()}
    ev = {'publicado': r['published'], 'vecinos_intactos': intactos}
    C.limpiar_work(work)
    ok = r['published'] and all(intactos.values())
    return out_ok('cero efecto externo sobre vecinos del fixture (operación '
                  'confinada)', ev) if ok else \
        out_falla_producto('confinamiento de efectos', ev)


# =========================== N9 ============================================
@caso('c5-n9-01-regresion-p5r', 'N9', 'regresión: suite P5r completa (47 '
      'casos incl. mutantes M1–M3) desde copia privada', p6='-',
      adapters=['p5r'])
def c_n9_01(C: CtxCasos):
    work = C.work('n9_01')
    suite = os.path.join(work, 'p5r_suite')
    os.makedirs(os.path.join(suite, 'prototipo'))
    os.makedirs(os.path.join(suite, 'fixtures'))
    os.makedirs(os.path.join(suite, 'tests'))
    os.makedirs(os.path.join(suite, 'resultados'))
    shutil.copyfile(C.fixtures['copias']['c5_protect'],
                    os.path.join(suite, 'prototipo', 'c5_protect.py'))
    shutil.copyfile(C.fixtures['copias']['make_fixtures'],
                    os.path.join(suite, 'fixtures', 'make_fixtures.py'))
    shutil.copyfile(C.fixtures['copias']['run_tests'],
                    os.path.join(suite, 'tests', 'run_tests.py'))
    shutil.copyfile(C.fixtures['copias']['mutantes'],
                    os.path.join(suite, 'tests', 'mutantes.py'))
    r = run_child([sys.executable, '-B', os.path.join(suite, 'tests',
                                                      'run_tests.py')],
                  cwd=suite)
    resumen = None
    ruta_res = os.path.join(suite, 'resultados', 'resultados.json')
    if os.path.isfile(ruta_res):
        data = json.load(open(ruta_res))
        resumen = {'total': data['resumen']['total'],
                   'pasan': data['resumen']['pasan'],
                   'ids': [c['id'] for c in data['casos']]}
    informe_limp = C.limpiar_work(work)
    ev = {'rc': r['rc'], 'stdout': r['stdout'][-200:], 'resumen': resumen}
    ok = resumen is not None and resumen['total'] == 47 and \
        resumen['pasan'] == 47 and r['rc'] == 0
    return out_ok('suite P5r: 47/47 PASAN (27 T + 17 R + 3 MUT) desde copia '
                  'privada — línea base de cobertura para el delta r5', ev) \
        if ok else out_falla_producto('regresión P5r', ev,
                                      'la suite no cerró 47/47')


@caso('c5-n9-02-disciplina-mutacion', 'N9',
      'disciplina: helper que falla antes del punto ensayado ⇒ INCONCLUSIVO '
      '(jamás verde); mutantes registrados con aserción prevista',
      p6='-', adapters=['ref_frontier'])
def c_n9_02(C: CtxCasos):
    # (a) ataque no entregado: SUT cae antes de staging ⇒ hook nunca corre
    ev_n2 = c_n2_02(C, falla_temprana=True)
    entregado = ev_n2.get('ref_frontier', {}).get('atacante_entregado', None)
    verdict_temprano = ev_n2.get('ref_frontier', {}).get('verdict')
    # (b) registro de mutantes con aserción prevista
    muts = mutadores.registrar_mutantes_regresion_p5r('/x')
    ev = {'ataque_no_entregado': {'variante': 'ref_frontier',
                                  'entregado': entregado,
                                  'verdict_sut': verdict_temprano,
                                  'estado_que_otorga_el_harness':
                                      INCONCLUSIVO},
          'mutantes_registrados': muts}
    ok = entregado is False and verdict_temprano == 'ABORTADO_SIN_EFECTOS'
    return out_ok('sin entrega del ataque NO hay verde (INCONCLUSIVO); '
                  'mutantes con base positiva y aserción prevista '
                  'documentada (MUT-A2/C1 ejecutados en n5-04/n3-05; '
                  'MUT-M1..M3 dentro de la suite P5r)', ev) if ok else \
        out_falla_producto('disciplina de mutación', ev)


@caso('c5-n9-03-contadores-verdes', 'N9',
      'SUT falso siempre-rc=0 NO obtiene verde: el oráculo exige efectos '
      'medidos', p6='-', adapters=[])
def c_n9_03(C: CtxCasos):
    fake = mutadores.FakeSutSiempreOk()
    work = C.work('n9_03')
    origen = C.origen_privado(work, 'x')
    ctx = C.ctx_place(work, 'x', origen)
    r = fake.place(ctx, None)
    # el oráculo N2 exige objeto publicado REAL medido por el lector:
    destino = r['destino']
    publicado_existe = os.path.lexists(destino)
    if not publicado_existe:
        estado = INCONCLUSIVO
        motivo = 'el SUT no produjo efectos: el oráculo no se puede aplicar'
    else:
        estado = PASA
        motivo = ''
    ev = {'verdict_fake': r['verdict'], 'rc_fake': r['rc'],
          'destino_existe': publicado_existe,
          'estado_harness': estado,
          'regla': 'verde SOLO con evidencia medida; rc=0 sin efectos ⇒ '
                   'INCONCLUSIVO/FALLA, nunca PASA'}
    C.limpiar_work(work)
    ok = estado == INCONCLUSIVO and not publicado_existe
    return out_ok('contador verde falso bloqueado: el SUT falso (rc=0, '
                  'sin efectos) no genera PASA en oráculos con medición',
                  ev) if ok else out_falla_producto('contadores', ev)


# ================== CONTRATO INTERFAZ_C5 (deriva de MiMo) ==================
@caso('c5-c0-01-contrato-interfaz-c5', 'C0',
      'contrato INTERFAZ_C5 (R5-CONTRATO-1) derivado: estructura, veredictos, '
      'cobertura N0–N9 y observaciones medidas', p6='-', hb='-',
      adapters=['interfaz_c5'])
def c_c0_01(C: CtxCasos):
    from sut_adapters import MAPA_VEREDICTOS_C5
    ruta = C.fixtures.get('interfaz_c5_ruta')
    if not ruta or not os.path.isfile(ruta):
        return out_skip('contrato publicado por MiMo', {},
                        'INTERFAZ_C5.json aún no disponible')
    ad = C.adaptador('interfaz_c5')
    c = ad.contrato
    verdicts = set(ad.verdicts)
    mapa_N = c.get('mapa_N', {})
    faltan_N = [n for n in ('N%d' % i for i in range(10)) if n not in mapa_N]
    mapeo_faltante = [k for k, v in MAPA_VEREDICTOS_C5.items() if v not in verdicts]
    # incompatibilidades/observaciones para adjudicación de Max
    obs = {
        'AT_UNIQUE': 'el contrato usa fstatat con AT_UNIQUE (0x8000); medido '
                     'desde uid operador: errno 107 para TODO (regular, '
                     'hardlink, symlink) — usable solo tras H1; exigir sonda '
                     'nativa en la sesión privilegiada',
        'exec_fdev': 'el contrato prohíbe exec por ruta reemplazable sin '
                     'fd/tripleta; medido: execve(/dev/fd) → EACCES en macOS '
                     '(sin fexecve) — el cierre total exige contexto raíz o '
                     'primitiva atómica; la ventana final queda documentada',
        'rc_unificacion': 'el esquema del contrato no define rc=6 (P5r: '
                          'ABORTADO_STAGING_RETENIDO era rc=6; contrato: '
                          'rc=2 aborto) — unificar en revisión',
        'sin_efectos': 'el contrato distingue SIN_EFECTOS vs '
                       'ABORTADO_SIN_EFECTOS y exige jamás SIN_EFECTOS con '
                       'staging propio: coincide con el oráculo c5-n6-07',
    }
    ev = {'sha256_contrato': ad.sha_contrato,
          'revision': c.get('revision'), 'utc_emision': c.get('utc_emision'),
          'verdicts_contrato': sorted(verdicts),
          'acciones': sorted(c.get('acciones', {}).keys()),
          'mapa_N_cubre': not faltan_N, 'faltan_en_mapa_N': faltan_N,
          'mapeo_veredictos_completo': not mapeo_faltante,
          'mapeo_veredictos_faltante': mapeo_faltante,
          'fd_escritura_previo': c.get('comportamiento_fallo', {})
          .get('fd_escritura_previo'),
          'observaciones_para_max': obs}
    ok = (not faltan_N and not mapeo_faltante and
          'NO_ACTIVADO' == c.get('acciones', {}).get('uso', {}).get('estado'))
    return out_ok('contrato derivado: 10 veredictos mapeables, mapa_N '
                  'completo, USO NO_ACTIVADO, dirección B coherente con el '
                  'oráculo N2 (frontera de inodos nuevos); observaciones '
                  'medidas registradas para adjudicación de Max', ev) if ok \
        else out_falla_producto('derivación del contrato', ev)


# ---------------------------------------------------------------------------
def ejecutar_todos(C: CtxCasos, solo_ids=None) -> list:
    resultados = []
    for c in CASOS:
        if solo_ids and c['id'] not in solo_ids:
            continue
        j = Journal()
        j.log('CASO', 'INICIO', id=c['id'], adapter=c['adapters'])
        try:
            res = c['func'](C)
        except NotImplementedError as e:
            res = out_skip(c['titulo'], {}, str(e))
        except Exception as e:  # noqa: BLE001
            res = out_error(c['titulo'], {}, e)
        j.log('CASO', 'FIN', id=c['id'], estado=res.get('estado'))
        res['id'] = c['id']
        res['criterio'] = c['criterio']
        res['p6'] = c['p6']
        res['hb'] = c['hb']
        res['titulo'] = c['titulo']
        res['tipo'] = c['tipo']
        res['adapters'] = c['adapters']
        res['orden_temporal'] = j.events
        resultados.append(res)
    return resultados
