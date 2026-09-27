#!/usr/bin/env python3
# =====================================================================
# NO_PRODUCTIVO_NO_AUTORIZADO — OT07-P7 GLM Flash (RUN.20260927T131419Z.C5IMAC1)
# sut_adapters — interfaz ÚNICA del harness hacia el sistema ensayado.
#   - P5rAdapter: prototipo sellado P5r desde COPIA PRIVADA (jamás in-place).
#     Soporta hooks deterministas (faults) del propio prototipo.
#   - RefFrontierAdapter / RefRenameAdapter: flujos referenciales PROPIOS que
#     materializan los dos diseños discutidos: frontera con inodos finales
#     nuevos (seguro para N2) vs rename del staging (patrón vulnerable).
#     Ambos con hooks deterministas en cada frontera de fase.
#   - InterfazC5Adapter: ranura para el contrato de MiMo; sin
#     INTERFAZ_C5.json los casos correspondientes quedan SKIP con motivo.
# Contrato de resultado de place(): ver docs/CONTRATO_SALIDAS_HARNESS.md.
# =====================================================================
"""Adaptadores SUT del harness C5."""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_common import (Journal, compare_content, ename, inventory_tree,  # noqa: E402
                            physical_path, pin, pin_equal, rename_excl,
                            run_child, sha256_bytes, sha256_file)

STAGING_PREFIX = 'ot07_c5_staging.'
GID_WHEEL = 0  # solo como valor esperado de LEDGER simulado; sin chown real

VERDICT_OK_ROOT = 'COLOCADO_PROTEGIDO_VERIFICADO'
VERDICT_OK_ACEPTADO = 'COLOCADO_SIN_PROTECCION_RIESGO_ACEPTADO'
VERDICT_GATE = 'RECHAZADO_GATE_SIN_EFECTOS'
VERDICT_ABORT_LIMPIO = 'ABORTADO_SIN_EFECTOS'
VERDICT_ABORT_STAGING = 'ABORTADO_STAGING_RETENIDO'
VERDICT_INCONSISTENTE = 'PUBLICADO_INCONSISTENTE_NO_BORRADO'
VERDICT_INCOMPLETO = 'PUBLICADO_VERIFICACION_INCOMPLETA_NO_BORRADO'
VERDICT_INDETERMINADO = 'ESTADO_INDETERMINADO_NO_BORRADO'
VERDICT_NO_AUTH = 'NO_AUTORIZADO_PROTOTIPO_SIMULADO'


class Abort(Exception):
    pass


class NoAutorizado(Exception):
    pass


# ---------------------------------------------------------------------------
class P5rAdapter:
    """Prototipo P5r (sellado) desde copia privada. Hook points nativos del
    prototipo: anchor_read, identify, before_staging, before_copy,
    after_copy, mid_protect, after_protect, before_publish, pre_rename,
    verify_begin, cleanup_fail."""
    name = 'p5r_prototipo'
    hooks_disponibles = ['anchor_read', 'identify', 'before_staging',
                         'before_copy', 'after_copy', 'mid_protect',
                         'after_protect', 'before_publish', 'pre_rename',
                         'verify_begin', 'cleanup_fail']

    def __init__(self, ruta_privada: str):
        self.ruta = ruta_privada
        spec = importlib.util.spec_from_file_location(
            'c5_protect_p5r_%d' % os.getpid(), ruta_privada)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def place(self, ctx: dict, faults: dict | None = None) -> dict:
        j = Journal()
        r = self.mod.place(ctx['origen'], ctx['destino'], ctx['anchor_path'],
                           ctx['anchor_sha'], ctx['modo'], 'simulated',
                           ctx['staging_base'], j, faults=faults,
                           acl_enabled=ctx.get('acl', False))
        r['events'] = j.events
        r['adapter'] = self.name
        r['ino_map'] = {'origen': pin(ctx['origen'])}
        if r.get('staging_pin'):
            r['ino_map']['staging_leaf'] = r['staging_pin']
        if r.get('published') and os.path.lexists(ctx['destino']):
            r['ino_map']['publicado'] = pin(ctx['destino'])
        r['uso'] = None
        return r

    def use_published(self, result: dict, ctx: dict, faults=None) -> dict:
        raise NotImplementedError('P5r no expone paso de uso (uso futuro)')


# ---------------------------------------------------------------------------
class _RefFlow:
    """Flujo referencial propio con hooks deterministas. Dos variantes:
    frontier (inodos finales NUEVOS creados dentro de una carpeta frontera
    creada ex profeso) y rename (publica el staging por renombrar: patrón
    vulnerable a fds preabiertos). Contrato de veredictos igual al de P5r."""
    name = 'ref'
    variante = 'frontier'
    hooks_disponibles = ['after_anchor', 'before_staging', 'after_staging',
                         'after_copy', 'mid_protect', 'after_protect',
                         'before_publish', 'after_publish', 'before_verify',
                         'before_exec', 'during_exec', 'cleanup_fail']

    def __init__(self, exec_binding: str = 'fd'):
        assert exec_binding in ('fd', 'rehash_ruta')
        self.exec_binding = exec_binding

    # -- utilidades ---------------------------------------------------------
    def _fault(self, name, faults, ctx):
        h = (faults or {}).get(name)
        if h:
            h(ctx)

    def _read_aces(self, path: str) -> list:
        """ACEs reales vía /bin/ls -leO (lector independiente dentro del
        flujo: herramienta nativa, solo lectura)."""
        import subprocess
        p = subprocess.run(['/bin/ls', '-dleO', '--', path],
                           capture_output=True)
        linea = p.stdout.decode('utf-8', 'replace').strip()
        aces = []
        if p.returncode == 0 and ' allow ' in linea or ' deny ' in linea:
            for parte in linea.splitlines()[1:]:
                aces.append(parte.strip())
        return aces

    def _copy_tree(self, src, dst, ctx):
        for name in sorted(os.listdir(src)):
            s, d = os.path.join(src, name), os.path.join(dst, name)
            st = os.lstat(s)
            if stat.S_ISLNK(st.st_mode):
                target = os.readlink(s)
                if target.startswith('/') or '..' in target.split('/'):
                    raise Abort('enlace no confinado: %s -> %s' % (s, target))
                resolved = os.path.realpath(s)
                if not (resolved + os.sep).startswith(
                        os.path.realpath(src) + os.sep):
                    raise Abort('enlace escapa: %s' % s)
                if not os.path.lexists(resolved):
                    raise Abort('enlace roto: %s' % s)
                os.symlink(target, d)
            elif stat.S_ISDIR(st.st_mode):
                os.mkdir(d, st.st_mode & 0o7777)
                self._copy_tree(s, d, ctx)
            elif stat.S_ISREG(st.st_mode):
                if st.st_nlink > 1:
                    raise Abort('hardlink prohibido: %s' % s)
                with open(s, 'rb') as fi, open(d, 'wb') as fo:
                    for chunk in iter(lambda: fi.read(1 << 20), b''):
                        fo.write(chunk)
                os.chmod(d, st.st_mode & 0o7777)
            else:
                raise Abort('tipo especial prohibido: %s' % s)
        ctx['events'].append({'phase': 'F4', 'event': 'copiado', 'src': src,
                              'dst': dst})

    def _protect_entry(self, path, ctx, j):
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode):
            return
        aces = self._read_aces(path)
        for ace in aces:
            if ' allow ' in ace:
                # política: ACE allow ⇒ rechazar (no normalizar sin privilegio)
                ctx['events'].append({'phase': 'F6', 'event': 'ACL_ALLOW_RECHAZADA',
                                      'path': path, 'ace': ace})
                j.log('F6_PROTECT', 'ACL_ALLOW_RECHAZADA', path=path, ace=ace)
                raise Abort('ACE allow inaceptable: %s (%s)' % (path, ace))
        before = st.st_mode & 0o7777
        nuevo = before & ~(stat.S_IWGRP | stat.S_IWOTH)
        os.chmod(path, nuevo)
        # dueño: LEDGER SIMULADO (sin chown real: exige H1); clave (dev,ino)
        ctx['owner_ledger'][(st.st_dev, st.st_ino)] = (0, GID_WHEEL)
        ctx['events'].append({'phase': 'F6', 'event': 'protegida', 'path': path,
                              'modo_antes': oct(before),
                              'modo_despues': oct(nuevo),
                              'dueño_simulado': '0:0'})
        j.log('F6_PROTECT', 'ENTRADA_PROTEGIDA', path=path, antes=oct(before),
              despues=oct(nuevo))

    def _meta_problemas(self, root, ctx):
        problemas = []
        for dirpath, dirnames, filenames in os.walk(root):
            for name in sorted(dirnames) + sorted(filenames):
                p = os.path.join(dirpath, name)
                st = os.lstat(p)
                if stat.S_ISLNK(st.st_mode):
                    continue
                dueño_real = (st.st_uid, st.st_gid)
                dueño_ledger = ctx['owner_ledger'].get(
                    (st.st_dev, st.st_ino), dueño_real)
                if dueño_ledger != (0, GID_WHEEL):
                    problemas.append('%s: dueño ledger %s != 0:0'
                                     % (p, dueño_ledger))
                if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                    problemas.append('%s: conserva W grupo/otros' % p)
                for ace in self._read_aces(p):
                    if ' allow ' in ace:
                        problemas.append('%s: ACE allow: %s' % (p, ace))
        st = os.lstat(root)
        if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            problemas.append('%s: raíz conserva W' % root)
        return problemas

    # -- flujo ---------------------------------------------------------------
    def place(self, ctx: dict, faults: dict | None = None) -> dict:
        j = Journal()
        result = {'adapter': self.name + ':' + self.variante,
                  'verdict': None, 'rc': None, 'published': False,
                  'staging': None, 'staging_parent': None, 'destino': ctx['destino'],
                  'cleanup_ok': None, 'ino_map': {}, 'uso': None,
                  'owner_ledger': None, 'events': [], 'frontier': None}
        ctx = dict(ctx)
        ctx['events'] = result['events']
        ctx['owner_ledger'] = {}
        ctx['j'] = j
        result['owner_ledger'] = ctx['owner_ledger']
        try:
            # F0 GATE
            if os.geteuid() == 0:
                raise NoAutorizado('euid==0: el flujo referencial no opera '
                                   'con privilegios reales')
            if ctx['modo'] not in ('root', 'aceptar_usuario'):
                j.log('F0_GATE', 'C5_INVALIDA', modo=ctx['modo'])
                result['verdict'], result['rc'] = VERDICT_GATE, 1
                return result
            j.log('F0_GATE', 'GATE_OK', modo=ctx['modo'], variante=self.variante)
            # F1 IDENTIFY: ancla por hash EXTERNO (instantánea única)
            if os.path.islink(ctx['anchor_path']) or \
                    not os.path.isfile(ctx['anchor_path']):
                raise Abort('ancla ausente o symlink')
            with open(ctx['anchor_path'], 'rb') as f:
                anchor_bytes = f.read()
            got = sha256_bytes(anchor_bytes)
            if got != ctx['anchor_sha']:
                raise Abort('ANCLA_HASH_INCORRECTO: esperado %s observado %s'
                            % (ctx['anchor_sha'], got))
            inv_ref = json.loads(anchor_bytes.decode())
            j.log('F1_IDENTIFY', 'ANCLA_FIJADA', sha256=got)
            self._fault('after_anchor', faults, ctx)
            if os.path.islink(ctx['origen']) or not os.path.isdir(ctx['origen']):
                raise Abort('origen inválido: %s' % ctx['origen'])
            pin_origen = pin(ctx['origen'])
            result['ino_map']['origen'] = pin_origen
            dest_parent = os.path.dirname(os.path.abspath(ctx['destino']))
            pin_dest_parent0 = pin(dest_parent)
            modo_dest_parent0 = os.lstat(dest_parent).st_mode & 0o7777
            if os.path.lexists(ctx['destino']):
                raise Abort('DESTINO ya existe')
            # F2 SPACE
            sv = os.statvfs(dest_parent)
            need = ctx.get('fixture_bytes', 1 << 20) + 2 * (1 << 30)
            if sv.f_bavail * sv.f_frsize < need:
                raise Abort('espacio insuficiente')
            # F3 STAGING
            self._fault('before_staging', faults, ctx)
            st_parent = tempfile.mkdtemp(prefix=STAGING_PREFIX,
                                         dir=ctx['staging_base'])
            os.chmod(st_parent, 0o700)
            leaf = os.path.join(st_parent, os.path.basename(
                os.path.normpath(ctx['destino'])))
            os.mkdir(leaf, 0o700)
            pin_staging = pin(leaf)
            result['staging'], result['staging_parent'] = leaf, st_parent
            ctx['staging_leaf'], ctx['staging_parent'] = leaf, st_parent
            result['ino_map']['staging_leaf'] = pin_staging
            j.log('F3_STAGING', 'STAGING_OK', leaf=leaf, pin=pin_staging)
            self._fault('after_staging', faults, ctx)
            # F4 COPY
            if not pin_equal(pin(ctx['origen']), pin_origen):
                raise Abort('origen cambió de identidad antes de copiar')
            self._copy_tree(ctx['origen'], leaf, ctx)
            os.chmod(leaf, os.lstat(ctx['origen']).st_mode & 0o7777)
            self._fault('after_copy', faults, ctx)
            # F5 REFCHK
            inv_st = inventory_tree(leaf)
            if not compare_content(inv_ref, inv_st):
                raise Abort('contenido staging != instantánea del ancla')
            j.log('F5_REFCHK', 'CONTENIDO_IGUAL')
            # F6 PROTECT
            self._fault('mid_protect', faults, ctx)
            for dirpath, dirnames, filenames in os.walk(leaf):
                for name in sorted(filenames):
                    self._protect_entry(os.path.join(dirpath, name), ctx, j)
                for name in sorted(dirnames):
                    self._protect_entry(os.path.join(dirpath, name), ctx, j)
            self._protect_entry(leaf, ctx, j)
            j.log('F6_PROTECT', 'PROTECCION_APLICADA',
                  ledger='SIMULADO (sin chown real; exige H1)')
            self._fault('after_protect', faults, ctx)
            # F7 REVALID
            inv_re = inventory_tree(leaf)
            if not pin_equal(pin(leaf), pin_staging):
                raise Abort('staging cambió de identidad tras protección')
            if not compare_content(inv_ref, inv_re):
                raise Abort('contenido staging mutado tras protección')
            problemas = self._meta_problemas(leaf, ctx)
            if problemas:
                raise Abort('metadata insuficiente: %s' % '; '.join(problemas[:4]))
            if not pin_equal(pin(st_parent), pin(st_parent)):
                raise Abort('padre de staging cambió')
            j.log('F7_REVALID', 'REVALIDACION_OK')
            # F8 PUBLISH
            self._fault('before_publish', faults, ctx)
            if not pin_equal(pin(dest_parent), pin_dest_parent0):
                raise Abort('padre destino cambió de identidad')
            if os.lstat(dest_parent).st_mode & 0o7777 != modo_dest_parent0:
                raise Abort('modo padre destino cambió')
            if os.path.lexists(ctx['destino']):
                raise Abort('destino apareció en la ventana (carrera)')
            if self.variante == 'frontier':
                frontier = tempfile.mkdtemp(prefix='.c5frontier.',
                                            dir=dest_parent)
                os.chmod(frontier, 0o700)
                result['frontier'] = frontier
                ctx['frontier'] = frontier
                fleaf = os.path.join(frontier, os.path.basename(
                    os.path.normpath(ctx['destino'])))
                # inodos FINALES NUEVOS: se llenan con dir 0700 y luego se
                # "cierra" cada dir a su modo final (post-orden)
                for dirpath, dirnames, filenames in os.walk(leaf):
                    rel = os.path.relpath(dirpath, leaf)
                    tdir = os.path.join(fleaf, rel) if rel != '.' else fleaf
                    os.mkdir(tdir, 0o700)
                    for name in sorted(filenames):
                        sp = os.path.join(dirpath, name)
                        sst = os.lstat(sp)
                        if stat.S_ISLNK(sst.st_mode):
                            os.symlink(os.readlink(sp),
                                       os.path.join(tdir, name))
                            continue
                        modo_final = sst.st_mode & 0o555
                        fd = os.open(os.path.join(tdir, name),
                                     os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                                     os.O_TRUNC, modo_final)
                        with open(sp, 'rb') as fi:
                            for chunk in iter(lambda: fi.read(1 << 20), b''):
                                os.write(fd, chunk)
                        os.close(fd)
                        _stn = os.lstat(os.path.join(tdir, name))
                        ctx['owner_ledger'][(_stn.st_dev, _stn.st_ino)] = \
                            (0, GID_WHEEL)
                # HALLAZGO MEDIDO: macOS rechaza renamex_np de un directorio
                # fuente sin W (EACCES) — con root real el DAC no bloquea;
                # en sintético se publica con dirs 0700 y se CIERRAN los
                # modos DESPUÉS del rename (el pin no cambia con chmod).
                # (los archivos ya se crearon con su modo final 0o444/0o555)
                for dirpath, _d, _f in os.walk(leaf, topdown=False):
                    rel = os.path.relpath(dirpath, leaf)
                    tdir = os.path.join(fleaf, rel) if rel != '.' else fleaf
                    _std = os.lstat(tdir)
                    ctx['owner_ledger'][(_std.st_dev, _std.st_ino)] = \
                        (0, GID_WHEEL)
                _str = os.lstat(fleaf)
                ctx['owner_ledger'][(_str.st_dev, _str.st_ino)] = (0, GID_WHEEL)
                # re-verificación del contenido de la frontera
                inv_f = inventory_tree(fleaf)
                if not compare_content(inv_ref, inv_f):
                    raise Abort('contenido frontera divergente (sin publicar)')
                pin_fleaf = pin(fleaf)
                result['ino_map']['frontera_leaf'] = pin_fleaf
                e = rename_excl(fleaf, ctx['destino'])
                if e != 0:
                    raise Abort('renamex_np errno %d (%s): sin publicar'
                                % (e, ename(e)))
                # cierre de modos de los DIRECTORIOS sobre lo ya publicado
                for dirpath, _d, _f in os.walk(leaf, topdown=False):
                    rel = os.path.relpath(dirpath, leaf)
                    tdir = os.path.join(ctx['destino'], rel) if rel != '.' \
                        else ctx['destino']
                    os.chmod(tdir, os.lstat(dirpath).st_mode & 0o555)
                try:
                    os.rmdir(frontier)
                    result['frontier'] = None
                except OSError as oe:
                    result['frontier'] = frontier
                    ctx['events'].append({'phase': 'F8',
                                          'event': 'frontera_retención',
                                          'errno': ename(oe.errno)})
            else:
                e = rename_excl(leaf, ctx['destino'])
                if e != 0:
                    raise Abort('renamex_np errno %d (%s): sin publicar'
                                % (e, ename(e)))
            result['published'] = True
            result['ino_map']['publicado'] = pin(ctx['destino'])
            j.log('F8_PUBLISH', 'RENAME_EXCL_OK', variante=self.variante)
            self._fault('after_publish', faults, ctx)
            # F9 VERIFY
            self._fault('before_verify', faults, ctx)
            inv_fin = inventory_tree(ctx['destino'])
            if not compare_content(inv_ref, inv_fin):
                result['verdict'], result['rc'] = VERDICT_INCONSISTENTE, 4
                j.log('F9_VERIFY', 'CONTENIDO_DIVERGE_NO_SE_BORRA')
                return result
            problemas = self._meta_problemas(ctx['destino'], ctx)
            if problemas:
                result['verdict'], result['rc'] = VERDICT_INCONSISTENTE, 4
                j.log('F9_VERIFY', 'METADATA_DIVERGE', detalle=problemas[:4])
                return result
            j.log('F9_VERIFY', 'VERIFICACION_FINAL_OK')
            # USO (solo si se pidió): vinculación verificar→ejecutar
            if ctx.get('exec'):
                result['uso'] = self._uso_publicado(ctx, faults)
            # F10 CLEANUP (frontera: el staging NO se publicó; se retira el
            # árbol propio del staging antes de cerrar su padre)
            if self.variante == 'frontier' and os.path.isdir(leaf) and \
                    os.path.realpath(leaf).startswith(os.path.realpath(st_parent)):
                shutil.rmtree(leaf)
            self._fault('cleanup_fail', faults, ctx)
            try:
                os.rmdir(st_parent)
                result['cleanup_ok'] = True
            except OSError as oe:
                result['cleanup_ok'] = False
                result['verdict'], result['rc'] = VERDICT_OK_ROOT, 3
                j.log('F10_CLEANUP', 'LIMPIEZA_INCOMPLETA', errno=ename(oe.errno))
                return result
            result['verdict'], result['rc'] = VERDICT_OK_ROOT, 0
            return result
        except Abort as e:
            result['diagnostico_estado'] = str(e)
            result['verdict'], result['rc'] = self._verdict_estado(result, e)
            j.log('FALLO', 'ABORT', err=str(e))
            return result
        except NoAutorizado as e:
            result['verdict'], result['rc'] = VERDICT_NO_AUTH, 5
            result['diagnostico_estado'] = str(e)
            return result
        except Exception as e:  # noqa: BLE001
            result['excepcion'] = '%s: %s' % (type(e).__name__, e)
            result['verdict'], result['rc'] = self._verdict_estado(result, e)
            j.log('FALLO', 'EXCEPCION', err=result['excepcion'])
            return result

    def _verdict_estado(self, result, exc):
        try:
            if result['published']:
                return (VERDICT_INCOMPLETO, 7)
            stg = result.get('staging')
            if stg is None:
                return (VERDICT_ABORT_LIMPIO, 2)
            if os.path.lexists(stg) or \
                    (result.get('staging_parent') and
                     os.path.lexists(result['staging_parent'])) or \
                    (result.get('frontier') and os.path.lexists(
                        result['frontier'])):
                return (VERDICT_ABORT_STAGING, 6)
            destino = result.get('destino')
            if destino and os.path.lexists(destino):
                return (VERDICT_INDETERMINADO, 8)
            return (VERDICT_ABORT_LIMPIO, 2)
        except OSError:
            return (VERDICT_INDETERMINADO, 8)

    # -- uso publicado: vinculación verificar→ejecutar ----------------------
    def _uso_publicado(self, ctx, faults) -> dict:
        exe = os.path.join(ctx['destino'], 'Contents/MacOS/c5_marker')
        out = {'binding': self.exec_binding, 'exe': exe}
        st = os.lstat(exe)
        tripleta = {'dev': st.st_dev, 'ino': st.st_ino,
                    'sha256': sha256_file(exe)}
        out['tripleta_verificada'] = tripleta
        h = (faults or {}).get('before_exec')
        if h:
            h(ctx)
        if self.exec_binding == 'fd':
            fd = os.open(exe, os.O_RDONLY)
            fst = os.fstat(fd)
            if (fst.st_dev, fst.st_ino) != (tripleta['dev'], tripleta['ino']):
                os.close(fd)
                out['resultado'] = 'ABORTA_IDENTITY_MISMATCH'
                return out
            # sha del contenido VINCULADO al fd (lectura por fd)
            os.lseek(fd, 0, 0)
            hsh = __import__('hashlib').sha256()
            for chunk in iter(lambda: os.read(fd, 1 << 20), b''):
                hsh.update(chunk)
            os.lseek(fd, 0, 0)
            if hsh.hexdigest() != tripleta['sha256']:
                os.close(fd)
                out['resultado'] = 'ABORTA_HASH_FD_MISMATCH'
                return out
            # consistencia final ruta↔fd: tras el swap por rename la ruta
            # apunta a OTRO inodo → detectado ANTES de ejecutar
            _stp = os.lstat(exe)
            if (_stp.st_dev, _stp.st_ino) != (fst.st_dev, fst.st_ino):
                os.close(fd)
                out['resultado'] = 'ABORTA_PATH_FD_MISMATCH'
                return out
            h = (faults or {}).get('during_exec')
            if h:
                h(ctx)  # ventana residual irreducible: entre el último
                # chequeo y execve (medida: /dev/fd exec → EACCES en macOS,
                # sin fexecve; el cierre total exige contexto raíz)
            env = {'PATH': '/usr/bin:/bin', 'HOME': '/'}
            try:
                import subprocess
                p = subprocess.run([exe], capture_output=True,
                                   pass_fds=(fd,), env=env, timeout=20)
                out['resultado'] = 'EJECUTADO'
                out['rc'] = p.returncode
                out['stdout'] = p.stdout.decode('utf-8', 'replace')[:200]
            except OSError as e:
                out['resultado'] = 'ERROR_EJECUCION'
                out['errno'] = ename(e.errno)
            os.close(fd)
        else:  # rehash_ruta: re-estadear y ejecutar por RUTA (patrón débil)
            st2 = os.lstat(exe)
            if (st2.st_dev, st2.st_ino) != (tripleta['dev'], tripleta['ino']) \
                    or sha256_file(exe) != tripleta['sha256']:
                out['resultado'] = 'ABORTA_REHASH_MISMATCH'
                return out
            h = (faults or {}).get('during_exec')
            if h:
                h(ctx)
            import subprocess
            env = {'PATH': '/usr/bin:/bin', 'HOME': '/'}
            p = subprocess.run([exe], capture_output=True, env=env, timeout=20)
            out['resultado'] = 'EJECUTADO'
            out['rc'] = p.returncode
            out['stdout'] = p.stdout.decode('utf-8', 'replace')[:200]
        return out


class RefFrontierAdapter(_RefFlow):
    name = 'ref_frontier'
    variante = 'frontier'


class RefRenameAdapter(_RefFlow):
    name = 'ref_rename'
    variante = 'rename'


# --- mapeo de veredictos: P5r/harness ↔ INTERFAZ_C5 (R5-CONTRATO-1) --------
MAPA_VEREDICTOS_C5 = {
    'COLOCADO_PROTEGIDO_VERIFICADO': 'PUBLICADO_VERIFICADO',
    'ABORTADO_SIN_EFECTOS': 'ABORTADO_SIN_EFECTOS',
    'ABORTADO_STAGING_RETENIDO': 'ABORTADO_STAGING_RETENIDO',
    'PUBLICADO_INCONSISTENTE_NO_BORRADO': 'PUBLICADO_INCONSISTENTE_NO_BORRADO',
    'PUBLICADO_VERIFICACION_INCOMPLETA_NO_BORRADO':
        'PUBLICADO_VERIFICACION_INCOMPLETA',
    'OK_CON_LIMPIEZA_INCOMPLETA': 'OK_CON_LIMPIEZA_INCOMPLETA',
    'ESTADO_INDETERMINADO_NO_BORRADO': 'ESTADO_INDETERMINADO',
    'RECHAZADO_GATE_SIN_EFECTOS': 'RECHAZADO_GATE_SIN_EFECTOS',
    'NO_AUTORIZADO_PROTOTIPO_SIMULADO': 'NO_AUTORIZADO',
}
# diferencia documentada para adjudicación de Max: el contrato no define rc=6
# (P5r usaba 6 para ABORTADO_STAGING_RETENIDO; el contrato lo colapsa en
# rc=2 'aborto' según esquema_resultado.rc). El adaptador mapea por STRING.

class InterfazC5Adapter:
    """Adaptador derivado del contrato INTERFAZ_C5.json (R5-CONTRATO-1).
    Valida estructura mínima y deja preparada la invocación por ACCIONES
    (PREP→VERIF→PUBLISH→CLEANUP) contra el orquestador r5 cuando Max lo
    libere tras revisar el delta; hasta entonces los casos contra este
    adaptador quedan SKIP con motivo registrado (no se improvisa)."""
    name = 'interfaz_c5'
    hooks_disponibles = []  # el contrato no define hooks: sincronización por
    # sondeo determinista de transición de pin (ver PRERREQUISITOS_MIMO.md)
    CLAVES_REQUERIDAS = ('acciones', 'esquema_resultado',
                         'comportamiento_fallo', 'mapa_N', 'limites')

    def __init__(self, ruta_contrato: str, ruta_candidato: str | None = None):
        self.ruta = ruta_contrato
        self.sha_contrato = sha256_file(ruta_contrato)
        with open(ruta_contrato) as f:
            self.contrato = json.load(f)
        faltan = [k for k in self.CLAVES_REQUERIDAS if k not in self.contrato]
        if faltan:
            raise RuntimeError('INTERFAZ_C5 sin claves requeridas: %s' % faltan)
        self.verdicts = self.contrato['esquema_resultado']['propiedades'][
            'verdict']['enum']
        self.ruta_candidato = ruta_candidato

    def place(self, ctx, faults=None):
        if not self.ruta_candidato or not os.path.isfile(self.ruta_candidato):
            raise NotImplementedError(
                'contrato INTERFAZ_C5 derivado (sha %s); ejecución contra el '
                'orquestador r5 PENDIENTE de: revisión del delta por Max y '
                'liberación del candidato para ensayos no privilegiados '
                'independientes' % self.sha_contrato[:16])
        raise NotImplementedError(
            'invocación por acciones contra %s se activa en revisión nueva '
            'del harness tras liberación del candidato' % self.ruta_candidato)
