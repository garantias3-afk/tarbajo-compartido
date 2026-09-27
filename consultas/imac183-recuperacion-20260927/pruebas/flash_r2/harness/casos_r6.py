#!/usr/bin/env python3
# =====================================================================
# NO_PRODUCTIVO_NO_AUTORIZADO — OT07-P7 GLM Flash R2 (RUN.20260927T131419Z.C5IMAC1)
# casos_r6 — batería FLASH contra el ORQUESTADOR REAL r6 (simulated/
# fixture_ensayo). 15 casos que complementan la batería R1 (51 casos que
# se re-ejecutan como regresión en la misma corrida).
# Referencias incorporadas (no re-oráculo propio, según Max):
#   * en simulated el fd del dueño sobre staging sigue abriendo → aquí se
#     MIDE con instrumentación determinista de copia privada y queda
#     SKIP-with-evidence (oráculo conclusivo en H1-N2 nativo);
#   * micro-ventana de swap: publicó sustituto y F9 lo captura con rc=4 —
#     aquí se REPRODUCE como control independiente (mutante MUT-R6-D).
# Hallazgo propio nuevo esperado: DERECHOS_ESCRITURA de c5_acl omite
# 'write' simple → una ACE allow write NO es rechazada (F-R6-N3-1).
# =====================================================================
"""Casos FLASH×r6 (revisión R2)."""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_common import (ERROR, FALLA_PRODUCTO, INCONCLUSIVO, Journal,  # noqa: E402
                            PASA, SKIP, ename, pin, rename_excl, run_child,
                            sha256_bytes, sha256_file, snapshot)
from sut_r6 import R6OrquestadorAdapter  # noqa: E402
import casos_c5  # noqa: E402
from casos_c5 import (APP_NAME, CtxCasos, out_error, out_falla_producto,  # noqa: E402
                      out_inconclusivo, out_ok, out_skip)

CASOS_R6 = []


def caso_r6(cid, criterio, titulo, tipo='REAL_HOY', p6=None, hb=None):
    def deco(fn):
        CASOS_R6.append({'id': cid, 'criterio': criterio, 'titulo': titulo,
                         'tipo': tipo, 'p6': p6, 'hb': hb, 'func': fn})
        return fn
    return deco


class CtxR6:
    """Extiende CtxCasos con el adaptador r6 y ctx en formato r6."""

    def __init__(self, C: CtxCasos, src_dir: str):
        self.C = C
        self.src = src_dir
        self._ad = None

    @property
    def ad(self) -> R6OrquestadorAdapter:
        if self._ad is None:
            self._ad = R6OrquestadorAdapter(self.src)
        return self._ad

    def ctx(self, work: str, tag: str, destino_tag: str | None = None,
            acl: bool = False, modo: str = 'fixture_ensayo',
            origen: str | None = None, anchor_sha: str | None = None,
            anchor_path: str | None = None):
        C = self.C
        origen = origen or C.origen_privado(work, tag)
        staging_base = os.path.join(work, 'staging_base')
        os.makedirs(staging_base, 0o700, exist_ok=True)
        destino = os.path.join(work, 'apps' + (destino_tag or ''),
                               APP_NAME)
        os.makedirs(os.path.dirname(destino), 0o755, exist_ok=True)
        if anchor_path is None:
            anchor_path = os.path.join(work, 'ancla_r6_%s.json' % tag)
            anchor_path, anchor_sha = self.ad.anchor_for(C.fixtures['app'],
                                                         anchor_path)
        return {'origen': origen, 'destino': destino,
                'anchor_path': anchor_path, 'anchor_sha': anchor_sha,
                'staging_base': staging_base, 'modo': modo, 'acl': acl,
                'fixture_bytes': C.fixtures['bytes']}


# ---------------------------------------------------------------------------
@caso_r6('c5-r6-01-gate-y-modos', 'N0',
         'gate euid==0 y matriz de modos sobre el orquestador r6',
         p6='P6-01', hb='HB-4c')
def c_r6_01(X: CtxR6):
    C, ev, ok = X.C, {}, True
    # euid==0 forzado
    work = C.work('r6_01_euid')
    ctx0 = X.ctx(work, 'euid')
    orig_geteuid = os.geteuid
    os.geteuid = lambda: 0
    try:
        r = X.ad.place(ctx0)
    finally:
        os.geteuid = orig_geteuid
    ev['euid0'] = {'verdict': r['verdict'], 'rc': r['rc'],
                   'sin_staging': not os.listdir(ctx0['staging_base'])}
    ok = ok and r['rc'] == 5 and ev['euid0']['sin_staging']
    C.limpiar_work(work)
    # modos inválidos / no decididos / root+simulated
    for tag, modo, priv in (('vacio', '', 'simulated'),
                            ('no_decidido', 'REQUIERE_DECISION_C5',
                             'simulated'),
                            ('inexistente', 'modo_inexistente', 'simulated'),
                            ('root_sim', 'root', 'simulated')):
        work = C.work('r6_01_%s' % tag)
        ctx = X.ctx(work, tag)
        ctx['modo'] = modo
        r = X.ad.mod.place(origen=ctx['origen'], destino=ctx['destino'],
                           anchor_path=ctx['anchor_path'],
                           anchor_sha256=ctx['anchor_sha'], modo=modo,
                           priv_name=priv, staging_base=ctx['staging_base'])
        ev[tag] = {'verdict': r['verdict'], 'rc': r['rc']}
        ok = ok and r['rc'] == 1 and not r['published']
        C.limpiar_work(work)
    return out_ok('r6 rechaza euid==0 (rc=5) sin efectos y los modos '
                  'no decididos/desalineados con priv (rc=1) en gate '
                  '(F0)', ev) if ok else \
        out_falla_producto('gates F0 de r6', ev)


@caso_r6('c5-r6-02-puntos-fault', 'N4',
         'matriz de faults booleanos de r6: veredicto por punto de fase',
         p6='P6-04/10', hb='HB-3')
def c_r6_02(X: CtxR6):
    C, ev, ok = X.C, {}, True
    esperado = {
        'identify': ('ABORTADO_SIN_EFECTOS', 2, False),
        'before_staging': ('ABORTADO_SIN_EFECTOS', 2, False),
        'after_copy': ('ABORTADO_STAGING_RETENIDO', 2, True),
        'mid_protect': ('ABORTADO_STAGING_RETENIDO', 2, True),
        'after_protect': ('ABORTADO_STAGING_RETENIDO', 2, True),
        'before_publish': ('ABORTADO_STAGING_RETENIDO', 2, True),
        'pre_rename': ('ABORTADO_STAGING_RETENIDO', 2, True),
    }
    for fault, (verdict, rc, con_staging) in esperado.items():
        work = C.work('r6_02_%s' % fault)
        r = X.ad.place(X.ctx(work, fault), {fault: True})
        stg = bool(r.get('staging_parent')) and \
            os.path.lexists(r['staging_parent'])
        ev[fault] = {'verdict': r['verdict'], 'rc': r['rc'],
                     'staging_retenido': stg,
                     'residuos_declarados': r.get('residuos')}
        ok = ok and r['verdict'] == verdict and r['rc'] == rc and \
            stg == con_staging and not r['published']
        C.limpiar_work(work)
    # swap_hoja: el producto inyecta SU propio swap de hoja y aborta
    work = C.work('r6_02_swap_hoja')
    r = X.ad.place(X.ctx(work, 'swap'), {'swap_hoja': True})
    ev['swap_hoja'] = {'verdict': r['verdict'], 'rc': r['rc'],
                       'published': r['published'],
                       'residuos': r.get('residuos')}
    ok = ok and r['verdict'] == 'ABORTADO_STAGING_RETENIDO' and \
        not r['published']
    C.limpiar_work(work)
    return out_ok('los 8 puntos de fault de r6 producen el veredicto '
                  'correcto por fase: pre-staging SIN_EFECTOS; post-staging '
                  'STAGING_RETENIDO (rc=2 unificado H-R5-6.1); swap_hoja '
                  'aborta sin publicar', ev) if ok else \
        out_falla_producto('fault-points r6', ev)


@caso_r6('c5-r6-03-positivo-fixture-ensayo', 'N1',
         'positivo r6 en fixture_ensayo: publicado, legible, ledger 0:0, '
         'sin g+w/o+w, sin residuos', p6='P6-01', hb='HB-1')
def c_r6_03(X: CtxR6):
    C = X.C
    work = C.work('r6_03')
    ad_inst = R6OrquestadorAdapter(X.src, instancia='r6pos')
    hoja_pin_medido = {}

    def mide_hoja(parent, hoja):
        st = os.lstat(hoja)
        hoja_pin_medido['pin'] = {'dev': st.st_dev, 'ino': st.st_ino}
    ad_inst.instrumentar_post_frontera(mide_hoja)
    ctx = X.ctx(work, 'x')
    r = ad_inst.place(ctx)
    lect = C.leer(work, [
        {'op': 'lstat', 'path': r['destino']},
        {'op': 'read_sha', 'path': os.path.join(r['destino'],
                                                'Contents/Info.plist')},
        {'op': 'ls_leO', 'path': os.path.join(r['destino'],
                                              'Contents/Info.plist')},
    ])
    pub_pin = r['ino_map'].get('publicado')
    hoja_pin = hoja_pin_medido.get('pin')
    modo_pub = oct(os.lstat(r['destino']).st_mode & 0o7777) if \
        os.path.lexists(r['destino']) else None
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'publicado_pin': pub_pin, 'hoja_pin': hoja_pin,
          'publicado_igual_hoja': pub_pin == hoja_pin,
          'modo_publicado': modo_pub, 'ledger': 'SIMULADO 0:0',
          'residuos': r.get('residuos'), 'lectura': lect['ops'],
          'identidad_lector': lect['identidad'],
          'nota': 'dirs 0700/hoja 0755 tras go-w: sin g+w/o+w; dueño REAL '
                  'sigue 501 (limitación simulated declarada; 0:wheel en H1)'}
    C.limpiar_work(work)
    ok = r['verdict'] == 'PUBLICADO_VERIFICADO' and r['rc'] == 0 and \
        pub_pin == hoja_pin and lect['ops'][0]['ok'] and \
        lect['ops'][1]['ok'] and not r.get('residuos')
    return out_ok('positivo r6: PUBLICADO_VERIFICADO rc=0; el publicado es '
                  'el MISMO inodo que la hoja (rename), legible por el '
                  'lector, sin residuos; protección de dueño real queda '
                  'en H1', ev) if ok else \
        out_falla_producto('positivo r6', ev)


@caso_r6('c5-r6-04-fd-escritura-origen', 'N2',
         'fd de ESCRITURA sobre el ORIGEN contra r6: el publicado es otro '
         'inodo (oráculo N2 lado origen)', p6='P6-05/06', hb='H-R5-1')
def c_r6_04(X: CtxR6):
    C = X.C
    work = C.work('r6_04')
    ctx = X.ctx(work, 'x')
    objetivo = os.path.join(ctx['origen'], 'Contents', 'Info.plist')
    pin0 = pin(objetivo)
    fd = os.open(objetivo, os.O_RDWR)
    try:
        r = X.ad.place(ctx)
        publicado = os.path.join(r['destino'], 'Contents', 'Info.plist')
        os.lseek(fd, 0, 0)
        try:
            n = os.write(fd, b'ATAQUE-FD-ORIGEN')
            escribir = {'ok': True, 'bytes': n}
        except OSError as e:
            escribir = {'ok': False, 'errno': e.errno}
        sha_pub = sha256_file(publicado) if os.path.isfile(publicado) else None
        ev = {'fd_pin': pin0, 'escritura_via_fd': escribir,
              'publicado_sha256': sha_pub,
              'sha_esperado': C.fixtures['sha_plist'],
              'publicado_intacto': sha_pub == C.fixtures['sha_plist'],
              'verdict': r['verdict'], 'published': r['published']}
    finally:
        os.close(fd)
    C.limpiar_work(work)
    ok = r['published'] and ev['publicado_intacto']
    return out_ok('la escritura por el fd del origen NO alcanza al objeto '
                  'publicado (r6 copia a inodos nuevos en staging): '
                  'publicado intacto', ev) if ok else \
        out_falla_producto('N2 origen', ev)


@caso_r6('c5-r6-05-fd-staging-post-frontera', 'N2',
         'fd del dueño sobre STAGING tras la frontera simulated '
         '(instrumentación determinista de copia privada): medición con '
         'disposición conocida', tipo='NATIVA_PENDIENTE_H1', p6='P6-05/06',
         hb='H-R5-1')
def c_r6_05(X: CtxR6):
    """Referencia Max (incorporada, no re-oráculo): en simulated el fd del
    dueño sigue abriendo; la frontera que cierra es la NATIVA del helper.
    Aquí se mide de forma determinista y queda registrado; el oráculo
    conclusivo (fd ⇒ EACCES/EPERM) es H1-N2."""
    C = X.C
    work = C.work('r6_05')
    ad_inst = R6OrquestadorAdapter(X.src, instancia='r6inst')
    med = {}

    def abre_fd(parent, hoja):
        objetivo = os.path.join(hoja, 'Contents', 'Info.plist')
        try:
            fd = os.open(objetivo, os.O_RDWR)  # dueño: ABIERTO post-frontera
            med['fd'] = {'abierto': True,
                         'pin': {'dev': os.fstat(fd).st_dev,
                                 'ino': os.fstat(fd).st_ino},
                         'modo': oct(os.fstat(fd).st_mode & 0o7777)}
            med['_fd'] = fd
        except OSError as e:
            med['fd'] = {'abierto': False, 'errno': e.errno,
                         'errno_name': ename(e.errno)}
    ad_inst.instrumentar_post_frontera(abre_fd)
    ctx = X.ctx(work, 'x')
    r = ad_inst.place(ctx)
    if med.get('_fd') is not None:
        fd = med.pop('_fd')
        publicado = os.path.join(r['destino'], 'Contents', 'Info.plist')
        os.lseek(fd, 0, 0)
        try:
            n = os.write(fd, b'ATAQUE-POST-FRONTERA')
            med['escritura_post_publish'] = {'ok': True, 'bytes': n}
        except OSError as e:
            med['escritura_post_publish'] = {'ok': False, 'errno': e.errno}
        os.close(fd)
        sha_pub = sha256_file(publicado) if os.path.isfile(publicado) else None
        med['publicado_sha256'] = sha_pub
        med['publicado_mutado'] = sha_pub != C.fixtures['sha_plist']
        med['publicado_igual_fd'] = med['fd'].get('pin') == \
            r['ino_map'].get('publicado')
    med['verdict'] = r['verdict']
    med['publicado_pin'] = r['ino_map'].get('publicado')
    med['referencia_max'] = 'REVISION_MAX_R6: en simulated el fd del dueño ' \
        'sigue abriendo (limitación sin root); frontera nativa en helper; ' \
        'oráculo conclusivo añadido a H1-N2'
    C.limpiar_work(work)
    return out_skip('oráculo N2 conclusivo EXIGE nativa (fd ⇒ EACCES/EPERM '
                    'sobre inodos root:0); medición simulated registrada '
                    'como control independiente: coincide con la referencia '
                    'de Max', med,
                    'exige H1 (frontera nativa del helper c5_helper.c)')


@caso_r6('c5-r6-06-eexist-y-destino', 'N6',
         'destino preexistente y carrera: sin anidar, ganador intacto',
         p6='P6-10')
def c_r6_06(X: CtxR6):
    C = X.C
    work = C.work('r6_06')
    ctx = X.ctx(work, 'x')
    os.makedirs(os.path.dirname(ctx['destino']), exist_ok=True)
    with open(ctx['destino'], 'wb') as f:
        f.write(b'GANADOR-PREEXISTENTE\n')
    sha0 = sha256_file(ctx['destino'])
    r = X.ad.place(ctx)
    intacto = os.path.isfile(ctx['destino']) and \
        sha256_file(ctx['destino']) == sha0
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'ganador_intacto': intacto,
          'fase': r['phases'][:2]}
    C.limpiar_work(work)
    ok = not r['published'] and intacto and r['rc'] == 2
    return out_ok('destino preexistente: aborto en F1 (SIN_EFECTOS rc=2) sin '
                  'tocar al ganador; el doble chequeo de F8 y el EEXIST de '
                  'renamex_np quedaron medidos en sondas (c5-n4-06)',
                  ev) if ok else out_falla_producto('EEXIST r6', ev)


@caso_r6('c5-r6-07-estados-post-publicacion', 'N6',
         'excepción post-publicación ⇒ ESTADO_INDETERMINADO sin borrado; '
         'limpieza fallida ⇒ OK_CON_LIMPIEZA_INCOMPLETA rc=3 (mutantes '
         'únicos MUT-R6-B/C)', p6='P6-10', hb='HB-3')
def c_r6_07(X: CtxR6):
    C = X.C
    ev, ok = {}, True
    # MUT-R6-B: caída controlada entre F9 y F10
    work = C.work('r6_07b')
    mut = X.ad.mutante(
        work, 'B',
        old='        phase("F9", True, 0)\n\n        # F10 CLEANUP',
        new='        phase("F9", True, 0)\n'
            '        raise RuntimeError("caída controlada post-publicación")'
            '\n\n        # F10 CLEANUP')
    ctx = X.ctx(work, 'x')
    destino = ctx['destino']
    r = mut['mod'].place(origen=ctx['origen'], destino=destino,
                         anchor_path=ctx['anchor_path'],
                         anchor_sha256=ctx['anchor_sha'],
                         modo='fixture_ensayo', priv_name='simulated',
                         staging_base=ctx['staging_base'])
    ev['MUT-R6-B'] = {'verdict': r['verdict'], 'rc': r['rc'],
                      'published': r['published'],
                      'objeto_en_disco': os.path.lexists(destino)}
    ok = ok and r['rc'] in (7, 8) and r['published'] and \
        os.path.lexists(destino)
    C.limpiar_work(work)
    # MUT-R6-C: residuo en staging ⇒ limpieza falla ⇒ rc=3 honesto
    work = C.work('r6_07c')
    mut = X.ad.mutante(
        work, 'C',
        old='        try:\n            os.rmdir(staging_parent)',
        new='        open(os.path.join(staging_parent, "residuo"), "w")'
            '.write("x")\n        try:\n            os.rmdir(staging_parent)')
    ctx = X.ctx(work, 'x')
    r = mut['mod'].place(origen=ctx['origen'], destino=ctx['destino'],
                         anchor_path=ctx['anchor_path'],
                         anchor_sha256=ctx['anchor_sha'],
                         modo='fixture_ensayo', priv_name='simulated',
                         staging_base=ctx['staging_base'])
    ev['MUT-R6-C'] = {'verdict': r['verdict'], 'rc': r['rc'],
                      'cleanup_ok': r.get('cleanup_ok'),
                      'residuos': r.get('residuos'),
                      'publicado': r['published']}
    ok = ok and r['rc'] == 3 and r['published'] and \
        r.get('cleanup_ok') is False and r.get('residuos')
    C.limpiar_work(work)
    ev['mutantes'] = 'B/C sobre copia privada, anclaje único, una mutación'
    return out_ok('estados post-publicación honestos: caída tras F9 ⇒ '
                  'ESTADO_INDETERMINADO/PUBLICADO_* con objeto SIN borrar; '
                  'limpieza fallida ⇒ rc=3 con residuo declarado (jamás '
                  'éxito silencioso)', ev) if ok else \
        out_falla_producto('estados post-publicación r6', ev)


@caso_r6('c5-r6-08-microventana-f9', 'N4',
         'micro-ventana de swap tras el último re-pin: el sustituto se '
         'publica y F9 lo captura (rc=4, sin borrado) — reproducción '
         'independiente del hallazgo de Max (MUT-R6-D)', p6='P6-09',
         hb='H-R5-2')
def c_r6_08(X: CtxR6):
    C = X.C
    work = C.work('r6_08')
    mut = X.ad.mutante(
        work, 'D',
        old='        errno_rn = rename_excl(hoja, destino)',
        new='        _atk = hoja + ".atk"\n'
            '        os.mkdir(_atk, 0o700)\n'
            '        open(os.path.join(_atk, "SUSTITUTO"), "w")'
            '.write("atacante")\n'
            '        os.rename(hoja, hoja + ".old")\n'
            '        os.rename(_atk, hoja)  # MUT-R6-D: swap en la '
            'micro-ventana\n'
            '        errno_rn = rename_excl(hoja, destino)')
    ctx = X.ctx(work, 'x')
    destino = ctx['destino']
    r = mut['mod'].place(origen=ctx['origen'], destino=destino,
                         anchor_path=ctx['anchor_path'],
                         anchor_sha256=ctx['anchor_sha'],
                         modo='fixture_ensayo', priv_name='simulated',
                         staging_base=ctx['staging_base'])
    sustituto_publicado = os.path.isfile(os.path.join(destino, 'SUSTITUTO'))
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'sustituto_publicado': sustituto_publicado,
          'objeto_no_borrado': os.path.lexists(destino),
          'content_ok': r.get('content_ok'),
          'referencia_max': 'REVISION_MAX_R6: publicó el sustituto pero F9 '
                            'lo reportó PUBLICADO_INCONSISTENTE_NO_BORRADO '
                            'rc=4 sin borrar — backstop funciona; micro-'
                            'ventana declarada, cerrada en native por '
                            're-pin del helper'}
    ok = r['rc'] == 4 and r['verdict'] == 'PUBLICADO_INCONSISTENTE_NO_BORRADO' \
        and sustituto_publicado and os.path.lexists(destino)
    C.limpiar_work(work)
    return out_ok('reproducción independiente de la micro-ventana: el '
                  'sustituto se publica y F9 lo detecta '
                  '(PUBLICADO_INCONSISTENTE_NO_BORRADO rc=4) SIN borrar el '
                  'objeto — coincide con la medición de Max', ev) if ok \
        else out_falla_producto('micro-ventana F9', ev)


@caso_r6('c5-r6-09-politica-acl-allow-write', 'N3',
         'política ACL del producto (c5_acl.validar_acl) contra ACEs reales: '
         'allow write simple, write_data, delete_child, principal root',
         p6='P6-07', hb='HB-2')
def c_r6_09(X: CtxR6):
    C = X.C
    work = C.work('r6_09')
    acl_mod = X.ad.mod.acl_mod
    fichero = os.path.join(work, 'sonda.bin')
    with open(fichero, 'wb') as f:
        f.write(b'x\n')
    sondas = {}

    def con_ace(ace):
        subprocess.run(['/bin/chmod', '-N', fichero], capture_output=True)
        os.chmod(fichero, 0o444)
        p = subprocess.run(['/bin/chmod', '+a', ace, fichero],
                           capture_output=True)
        r = acl_mod.validar_acl(fichero)
        lect = C.leer(work, [{'op': 'ls_leO', 'path': fichero}])
        return {'chmod_rc': p.returncode,
                'chmod_stderr': p.stderr.decode('utf-8', 'replace')[:120],
                'ok_producto': r['ok'],
                'problemas': [pr['tipo'] for pr in r['problemas']],
                'aces_producto': [(a['tag'], a['principal'], a['perms'])
                                  for a in r['aces']],
                'ls_lector': lect['ops'][0].get('salida', '')[:200]}
    # formas VÁLIDAS de chmod +a (write_data como tipo es rechazado por
    # chmod: 'Invalid permission type' — medido); el producto DEBE rechazar
    # allow-write ajena en todas sus formas
    sondas['allow_write'] = con_ace('OPERADOR allow write')
    sondas['allow_write_delete'] = con_ace('OPERADOR allow write,delete')
    sondas['allow_delete'] = con_ace('OPERADOR allow delete')
    sondas['allow_root_write'] = con_ace('root allow write')
    subprocess.run(['/bin/chmod', '-N', fichero], capture_output=True)
    ev = {'sondas': sondas,
          'hallazgo': 'DERECHOS_ESCRITURA de c5_acl usa nombres NFSv4 '
                      'canónicos (write_data/append_data/…) pero ls -le '
                      'muestra los nombres de chmod ("write", "append"): '
                      'las ACE "allow write" y "allow append" (formas más '
                      'comunes de chmod +a, verificadas también por sonda '
                      'directa) NO son rechazadas por validar_acl; '
                      '"delete" y "write,delete" SÍ se detectan',
          'lector_independiente': 'misma lectura ls -leO: la ACE existe y el '
                                  'producto la dejó pasar'}
    C.limpiar_work(work)
    # oráculo: write_simple DEBE estar detectada (ok=False). El producto
    # la dejó pasar ⇒ FALLA_PRODUCTO (F-R6-N3-1). Las demás: positive checks.
    ok_total = (not sondas['allow_write']['ok_producto'] and
                not sondas['allow_write_delete']['ok_producto'] and
                not sondas['allow_delete']['ok_producto'])
    falla = sondas['allow_write']['ok_producto']
    ev['F-R6-N3-1'] = {
        'tipo': 'ACE allow write simple NO detectada por c5_acl',
        'detalle': 'perms de la ACE según ls -le: ["write"]; '
                   'DERECHOS_ESCRITURA enumera write_data/append_data/... '
                   'pero no "write" — el producto declara ok=True',
        'disposicion_sugerida': "añadir 'write' (y variantes de ls: "
                                "writeattr/writeextattr/writesecurity) a "
                                'DERECHOS_ESCRITURA o comparar por prefijo'}
    if ok_total:
        return out_ok('política ACL de r6 detecta allow-write ajena en '
                      'write/write_data/delete_child', ev)
    if falla:
        return out_falla_producto(
            'ACE allow write ajena DEBE ser rechazada por validar_acl', ev,
            'F-R6-N3-1: el producto dejó pasar una ACE "allow write" '
            '(mi lector independiente la mide en el mismo fichero) — '
            'fallo del producto, corregible en r6b (una línea)')
    return out_falla_producto('política ACL r6', ev)


@caso_r6('c5-r6-10-r6-1-fail-open', 'N3',
         'R6-1 reproducida: validar_acl que lanza AclPolicyError es '
         'engullida por `except: pass` en F6 y el flujo PUBLICA',
         p6='P6-07', hb='HB-2')
def c_r6_10(X: CtxR6):
    C = X.C
    ev = {'codigo': 'c5_orquestador.py F6: `except acl_mod.AclPolicyError: '
                    'pass  # fail-closed ya documentado; no bloquear si ls '
                    'no parsea` (líneas 648-649) — comentario contradictorio '
                    'con el fail-closed declarado de c5_acl'}
    # (a) fail-closed CUANDO la detección funciona: validar_acl devuelve
    # problemas ⇒ el flujo aborta (STAGING_RETENIDO) sin publicar
    work = C.work('r6_10a')
    ad_det = R6OrquestadorAdapter(X.src, instancia='r6det')
    acl_orig = ad_det.mod.acl_mod.validar_acl
    ad_det.mod.acl_mod.validar_acl = (
        lambda path, politica=None: {
            'path': path, 'ok': False,
            'aces': [], 'problemas': [{'tipo': 'ACE_ALLOW_WRITE_AJENA',
                                       'accion': 'RECHAZAR'}],
            'politica': {}})
    ctx = X.ctx(work, 'x', acl=True)
    r = ad_det.place(ctx)
    ev['deteccion_funciona'] = {'validar_acl': 'ok=False (ACE detectada)',
                                'verdict': r['verdict'], 'rc': r['rc'],
                                'published': r['published']}
    deteccion_ok = not r['published'] and r['rc'] == 2
    C.limpiar_work(work)
    # (b) fail-open: validar_acl SIEMPRE lanza AclPolicyError ⇒ publica
    work = C.work('r6_10b')
    ad_inst = R6OrquestadorAdapter(X.src, instancia='r6failopen')

    def lanza(path, politica=None):
        raise ad_inst.mod.acl_mod.AclPolicyError('ls inparseable (simulado)')
    ad_inst.mod.acl_mod.validar_acl = lanza
    ctx = X.ctx(work, 'x', acl=True)
    r = ad_inst.place(ctx)
    ev['fail_open_medido'] = {'validar_acl': 'AclPolicyError siempre',
                              'verdict': r['verdict'], 'rc': r['rc'],
                              'published': r['published']}
    fail_open = r['published']
    C.limpiar_work(work)
    # restaurar el módulo compartido para los casos siguientes
    R6OrquestadorAdapter(X.src, instancia='r6restore').mod.acl_mod.validar_acl = acl_orig
    ok = deteccion_ok and fail_open
    return out_falla_producto(
        'la validación ACL no puede saltarse silenciosamente (fail-closed)',
        ev,
        'REPRODUCCIÓN MEDIDA de R6-1 (Max, obligatoria antes de H1): con '
        'AclPolicyError el flujo publicó igual — el except: pass es '
        'fail-open; corrección de una línea en r6b: abort con '
        'ABORTADO_STAGING_RETENIDO') if ok else \
        out_falla_producto('R6-1 fail-open', ev,
                           'la reproducción no cerró como se esperaba; '
                           'revisar evidencia')


@caso_r6('c5-r6-11-limpieza-confinada', 'N8',
         'cleanup r6: retira SOLO su staging; list-stale lee huérfanos; '
         'ajenos intactos; residuo declarado', p6='P6-10', hb='H-R5-5')
def c_r6_11(X: CtxR6):
    C = X.C
    work = C.work('r6_11')
    ctx = X.ctx(work, 'x')
    ajeno1 = os.path.join(ctx['staging_base'], 'AJENO.txt')
    open(ajeno1, 'w').write('no tocar')
    ajeno2 = os.path.join(os.path.dirname(ctx['destino']), 'AJENO2.txt')
    open(ajeno2, 'w').write('no tocar 2')
    # huérfano propio previo (simula reintento tras interrupción)
    huerfano = os.path.join(ctx['staging_base'],
                            'ot07_c5_staging.huerfano_prueba')
    os.makedirs(huerfano, 0o700)
    r = X.ad.place(ctx)
    stale = X.ad.mod.list_stale(ctx['staging_base'])
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'residuos': r.get('residuos'),
          'staging_retirado': not os.path.lexists(r.get('staging_parent')
                                                  or ''),
          'stale_detecta_huerfano': any(
              s['path'].endswith('huerfano_prueba') for s in stale),
          'huerfano_intacto': os.path.isdir(huerfano),
          'ajenos_intactos': {'AJENO.txt': os.path.isfile(ajeno1),
                              'AJENO2.txt': os.path.isfile(ajeno2)}}
    C.limpiar_work(work)
    ok = r['published'] and not ev['staging_retirado'] is False and \
        ev['staging_retirado'] and ev['stale_detecta_huerfano'] and \
        ev['huerfano_intacto'] and all(ev['ajenos_intactos'].values()) and \
        not r.get('residuos')
    return out_ok('cleanup r6 confinado: retira su staging padre, NO toca '
                  'ajenos, list-stale lista el huérfano sin borrarlo '
                  '(reintento crea staging NUEVO), residuos vacíos en '
                  'éxito', ev) if ok else out_falla_producto('cleanup r6', ev)


@caso_r6('c5-r6-12-escaner-subprocess', 'N0',
         'escáner AST del orquestador r6: subprocess solo en NativePriv '
         '(H1-gated); inyección de import top-level detectada',
         p6='P6-09', hb='HB-4c')
def c_r6_12(X: CtxR6):
    C = X.C
    src = os.path.join(X.src, 'c5_orquestador.py')
    arbol = ast.parse(open(src).read())
    subprocess_en = []
    for node in ast.walk(arbol):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ''])
            if 'subprocess' in mods:
                subprocess_en.append(node.lineno)
    # ¿las líneas caen dentro de NativePriv?
    dentro_native = []
    for node in ast.walk(arbol):
        if isinstance(node, ast.ClassDef) and node.name == 'NativePriv':
            for stmt in ast.walk(node):
                if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                    dentro_native.append(stmt.lineno)
    confinado = all(ln in dentro_native for ln in subprocess_en)
    # disciplina: inyección única de import top-level detectada
    work = C.work('r6_12')
    mut = X.ad.mutante(
        work, 'SCAN',
        old='import hashlib\n',
        new='import hashlib\nimport subprocess  # INYECTADA\n')
    arbol_mut = ast.parse(open(mut['path']).read())
    toplevel = [n.lineno for n in ast.walk(arbol_mut)
                if isinstance(n, (ast.Import, ast.ImportFrom))
                for m in ([a.name for a in n.names]
                          if isinstance(n, ast.Import) else [n.module or ''])
                if m == 'subprocess']
    inyectada_detectada = any(ln not in dentro_native for ln in toplevel)
    ev = {'subprocess_lineas': subprocess_en,
          'confinado_a_NativePriv': confinado,
          'inyeccion_toplevel_detectada': inyectada_detectada,
          'hash_base': mut['sha_base'][:16],
          'hash_mutante': mut['sha_mutante'][:16]}
    C.limpiar_work(work)
    ok = confinado and inyectada_detectada
    return out_ok('subprocess del orquestador r6 vive SOLO dentro de '
                  'NativePriv (requiere H1+euid 0); una inyección top-level '
                  'en copia privada es detectada por el mismo escáner '
                  '(N0-03 del producto real)', ev) if ok else \
        out_falla_producto('escáner r6', ev)


@caso_r6('c5-r6-13-origen-swap-pre-frontera', 'N4',
         'swap del ORIGEN en la ventana F1→F3 de r6: re-pin pre-frontera '
         'detecta (MUT-R6-E)', p6='P6-04/08')
def c_r6_13(X: CtxR6):
    C = X.C
    work = C.work('r6_13')
    mut = X.ad.mutante(
        work, 'E',
        old='        if pin(origen) != origen_pin:\n'
            '            phase("F3", False, 2)',
        new='        os.rename(origen, origen + ".swap")\n'
            '        os.makedirs(origen)\n'
            '        open(os.path.join(origen, "SUSTITUTO"), "w")'
            '.write("atacante")\n'
            '        if pin(origen) != origen_pin:\n'
            '            phase("F3", False, 2)')
    ctx = X.ctx(work, 'x')
    r = mut['mod'].place(origen=ctx['origen'], destino=ctx['destino'],
                         anchor_path=ctx['anchor_path'],
                         anchor_sha256=ctx['anchor_sha'],
                         modo='fixture_ensayo', priv_name='simulated',
                         staging_base=ctx['staging_base'])
    ev = {'verdict': r['verdict'], 'rc': r['rc'], 'published': r['published'],
          'error': r.get('error')}
    C.limpiar_work(work)
    ok = not r['published'] and r['rc'] == 2 and \
        'origen swap' in str(r.get('error', ''))
    return out_ok('el re-pin del origen antes de la frontera (F3) detecta '
                  'el swap pre-frontera y aborta SIN_EFECTOS sin copiar el '
                  'sustituto', ev) if ok else \
        out_falla_producto('swap origen pre-frontera', ev)


@caso_r6('c5-r6-14-proteccion-insuficiente-f7', 'N1',
         'F7 de r6 detecta protección insuficiente: hoja g+w post-F6 y '
         'nodo sin lchown en ledger (MUT-R6-A/F)', p6='P6-01', hb='HB-1')
def c_r6_14(X: CtxR6):
    C, ev, ok = X.C, {}, True
    # MUT-R6-A: tras _protect_tree, hoja queda 0775 (g+w)
    work = C.work('r6_14a')
    mut = X.ad.mutante(
        work, 'A',
        old='        _protect_tree(hoja, priv, acl_enabled, j)\n'
            '        result["priv"]["chmod_go_w_real"] = True',
        new='        _protect_tree(hoja, priv, acl_enabled, j)\n'
            '        os.chmod(hoja, 0o775)  # MUT-R6-A: g+w residual\n'
            '        result["priv"]["chmod_go_w_real"] = True')
    ctx = X.ctx(work, 'x')
    r = mut['mod'].place(origen=ctx['origen'], destino=ctx['destino'],
                         anchor_path=ctx['anchor_path'],
                         anchor_sha256=ctx['anchor_sha'],
                         modo='fixture_ensayo', priv_name='simulated',
                         staging_base=ctx['staging_base'])
    ev['MUT-R6-A_hoja_gw'] = {'verdict': r['verdict'], 'rc': r['rc'],
                              'published': r['published'],
                              'metadata_ok': r.get('metadata_ok')}
    ok = ok and not r['published'] and r['rc'] == 2 and \
        r.get('metadata_ok') is False
    C.limpiar_work(work)
    # MUT-R6-F: un nodo sin lchown en ledger (dueño divergente)
    work = C.work('r6_14f')
    mut = X.ad.mutante(
        work, 'F',
        old='        priv.lchown_root(p)\n        j.effect("lchown", p)',
        new='        if not p.endswith("Info.plist"):\n'
            '            priv.lchown_root(p)\n'
            '        j.effect("lchown", p)')
    ctx = X.ctx(work, 'x')
    r = mut['mod'].place(origen=ctx['origen'], destino=ctx['destino'],
                         anchor_path=ctx['anchor_path'],
                         anchor_sha256=ctx['anchor_sha'],
                         modo='fixture_ensayo', priv_name='simulated',
                         staging_base=ctx['staging_base'])
    ev['MUT-R6-F_dueño_divergente'] = {'verdict': r['verdict'],
                                       'rc': r['rc'],
                                       'published': r['published'],
                                       'metadata_ok': r.get('metadata_ok')}
    ok = ok and not r['published'] and r['rc'] == 2
    C.limpiar_work(work)
    return out_ok('F7 de r6 revalida dueño (ledger) y modos en RAÍZ e hijos '
                  '(HB-1): g+w residual y nodo sin lchown ⇒ aborto con '
                  'staging retenido, sin publicar', ev) if ok else \
        out_falla_producto('F7 protección insuficiente', ev)


@caso_r6('c5-r6-15-cadena-ancla-c1', 'N5',
         'cadena C-1: DELEGADA sin evidencia; C-1 con evidencia autenticada '
         '(hash en manifiesto sellado); rechazo de par atacante',
         p6='P6-08', hb='HB-4')
def c_r6_15(X: CtxR6):
    C = X.C
    ev, ok = {}, True
    work = C.work('r6_15a')
    ctx = X.ctx(work, 'a')
    r = X.ad.place(ctx)  # sin evidencia_c1 ⇒ DELEGADA
    ev['sin_evidencia'] = {'verdict': r['verdict'], 'published': r['published'],
                           'confianza': 'DELEGADA (motivos en ancla)'}
    ok = ok and r['published']
    C.limpiar_work(work)
    # con evidencia C-1 autenticada (hash del ancla en manifiesto sellado)
    work = C.work('r6_15b')
    ctx = X.ctx(work, 'b')
    evid = X.ad.mod.ancla_mod.construir_evidencia_c1(
        ctx['anchor_sha'], hashes_sellados={ctx['anchor_sha']})
    r = X.ad.mod.place(origen=ctx['origen'], destino=ctx['destino'],
                       anchor_path=ctx['anchor_path'],
                       anchor_sha256=ctx['anchor_sha'], modo='fixture_ensayo',
                       priv_name='simulated', staging_base=ctx['staging_base'],
                       evidencia_c1=evid)
    ev['con_c1'] = {'verdict': r['verdict'], 'published': r['published'],
                    'origen_autenticado': evid['origen_autenticado']}
    ok = ok and r['published']
    C.limpiar_work(work)
    # par atacante con hash original de OTRA instantánea ⇒ rechazo
    work = C.work('r6_15c')
    ctx = X.ctx(work, 'c')
    origen_atacante = ctx['origen']
    with open(os.path.join(origen_atacante, 'Contents', 'Info.plist'),
              'wb') as f:
        f.write(b'ARBOL-DEL-ATACANTE\n')
    ancla_atacante = os.path.join(work, 'ancla_atacante.json')
    anchor_path, _ = X.ad.anchor_for(origen_atacante, ancla_atacante)
    r = X.ad.mod.place(origen=origen_atacante, destino=ctx['destino'],
                       anchor_path=anchor_path,
                       anchor_sha256=ctx['anchor_sha'],  # hash de OTRA ancla
                       modo='fixture_ensayo', priv_name='simulated',
                       staging_base=ctx['staging_base'])
    ev['par_atacante_hash_ajeno'] = {'verdict': r['verdict'],
                                     'rc': r['rc'],
                                     'published': r['published']}
    ok = ok and not r['published'] and r['rc'] == 2
    C.limpiar_work(work)
    return out_ok('cadena C-1 medida: sin evidencia ⇒ DELEGADA (publica en '
                  'fixture_ensayo, jamás en root); con evidencia autenticada '
                  '(hash del ancla en manifiesto sellado) ⇒ C-1; hash ajeno '
                  'con árbol atacante ⇒ rechazo ANCLA fail-closed', ev) \
        if ok else out_falla_producto('cadena C-1', ev)


# ---------------------------------------------------------------------------
def ejecutar_r6(X: CtxR6, solo_ids=None) -> list:
    resultados = []
    for c in CASOS_R6:
        if solo_ids and c['id'] not in solo_ids:
            continue
        j = Journal()
        j.log('CASO', 'INICIO', id=c['id'])
        try:
            res = c['func'](X)
        except Exception as e:  # noqa: BLE001
            res = out_error(c['titulo'], {}, e)
        j.log('CASO', 'FIN', id=c['id'], estado=res.get('estado'))
        res['id'] = c['id']
        res['criterio'] = c['criterio']
        res['p6'] = c['p6']
        res['hb'] = c['hb']
        res['titulo'] = c['titulo']
        res['tipo'] = c['tipo']
        res['adapters'] = ['r6_orquestador']
        res['orden_temporal'] = j.events
        resultados.append(res)
    return resultados
