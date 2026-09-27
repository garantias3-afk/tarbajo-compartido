# PROCEDIMIENTO_H1.md — trabajo local privilegiado acotado (NO EJECUTADO)

**Estado: PREPARADO · NO ACTIVADO.** Root queda cerrado hasta que OPERADOR
apruebe H1 explícita sobre este procedimiento con hashes y alcance exactos.
Ninguna autorización implícita desde el GO de Max ni desde esta entrega.

## Por qué hace falta H1

- `lchown(2)` a `0:0` exige superusuario.
- `fchmodat` + ACL `deny write` sobre inodos creados dentro de la frontera
  exige sesión privilegiada para fijar dueño root y política ACL real.
- La validación nativa de N1–N8 (inaccesibilidad de escritura para uid 501,
  fd previo, ACL, AT_UNIQUE en syscall real) **no** es demostrable sin root.
- La preparación del instalador real (sección separada) está condicionada a
  éxito nativo completo del fixture.

## Identidades verificadas (recalcular al sellar)

| Objeto | Ruta | SHA-256 (placeholder al escribir; sellar rellena) |
|---|---|---|
| Helper fuente | `src/c5_helper.c` | ver SHA256SUMS.txt |
| Helper binario | `build/c5_helper` | ver SHA256SUMS.txt (tras compilar) |
| Orquestador | `src/c5_orquestador.py` | ver SHA256SUMS.txt |
| Ancla C-1 | `src/c5_ancla.py` | ver SHA256SUMS.txt |
| ACL | `src/c5_acl.py` | ver SHA256SUMS.txt |
| Bootstrap | `src/c5_bootstrap.py` | ver SHA256SUMS.txt |
| Contrato | `INTERFAZ_C5.json` | ver SHA256SUMS.txt |
| Intérprete | `/usr/bin/python3` | del sistema (no del uid) |
| Compilador | `/usr/bin/clang` | del sistema |

**Regla N0:** ningún binario/intérprete/dependencia **mutable del uid** se
ejecuta como root. El helper se compila con clang del sistema; los fuentes se
verifican por hash **dentro de la frontera** antes de `sudo`/`doas`/prompt.

## Fixture desechable (<1 MiB)

- Ruta propuesta: `fixtures/h1_fixture/` (crearlo vacío, umask 077).
- Contenido: 2 archivos regulares + 1 subdirectorio + 1 symlink interno. Máx 1 MiB.
- **Modos del fixture (D2, re-ejecución):** `dirs 0755` / `archivos 0644`
  (umask 022 solo al crear el fixture) para que `verify`/`ls -le` como uid 501
  funcionen tras copiar con modos del origen menos `g+w/o+w`.
- Destino propio: `fixtures/h1_destino/` **ausente** al inicio.
- Staging base: `fixtures/h1_staging_base/` (solo nuestros `ot07_c5_staging.*`).

## Protocolo de ejecución (OBLIGATORIO en la re-ejecución)

- **Abortar al PRIMER RC≠0.** Registrar el RC/errno real y detener la secuencia.
  Nada se publica tras un fallo. (En la corrida A anterior se continuó tras
  `copy-tree` RC=2 — prohibido.)
- **C5_AUTH_BASE=$H1** exportado antes de las lecturas del destino publicado
  (D3): el helper lo soporta y habilita `verify`/`ls` del publicado.
- Verificar `shasum -a 256 build/c5_helper` **antes de cada sudo**. Si difiere
  del hash de la aprobación H1-bis, abortar.

## Operaciones exactas (en orden)

1. **selfcheck** (sin root aún):
   ```bash
   python3 -B src/c5_bootstrap.py .
   ./build/c5_helper selfcheck
   ./build/c5_helper probe-at fixtures/h1_fixture
   ```
2. **Compilar si falta** (sin root):
   ```bash
   clang -O2 -Wall -Wextra -Werror -std=c11 -mmacosx-version-min=14.0 \
     -o build/c5_helper src/c5_helper.c
   ```
3. **Crear fixture** (sin root, umask 077):
   ```bash
   mkdir -p fixtures/h1_fixture/sub fixtures/h1_staging_base
   echo 'hello' > fixtures/h1_fixture/a.txt
   echo 'world' > fixtures/h1_fixture/sub/b.txt
   ln -s a.txt fixtures/h1_fixture/link
   # inventario + ancla
   python3 -B - <<'PY'
   import sys; sys.path.insert(0,'src')
   import c5_orquestador as O, json, hashlib
   from pathlib import Path
   inv = O.inventory_tree('fixtures/h1_fixture')
   Path('fixtures/h1_ancla.json').write_text(json.dumps(inv, sort_keys=True))
   print(hashlib.sha256(Path('fixtures/h1_ancla.json').read_bytes()).hexdigest())
   PY
   ```
4. **Sesión privilegiada (H1)** — SOLO si OPERADOR aprueba este alcance:
   ```bash
   # a) helper: proteger el árbol copiado en staging
   sudo ./build/c5_helper protect <staging_leaf>
   # b) verificar metadata
   ./build/c5_helper verify <staging_leaf>
   # c) publicar
   sudo ./build/c5_helper publish <staging_leaf> fixtures/h1_destino
   # d) limpiar
   ./build/c5_helper cleanup <staging_parent>
   ```
   El orquestador invoca estas acciones vía `NativePriv` cuando `--priv native`.
   **No usar `sudo python3`** ni importar módulos desde la carpeta del uid.

5. **Oráculos nativos a registrar** (N1–N8):
   - N1: `stat` dueño 0:0 y `go-w` en raíz e hijos; intento `open(O_WRONLY)` como uid 501 → errno esperado (EACCES/EPERM).
   - N2 (H-R5-1, oráculo real — no textual): **fd-sobre-staging**. Durante `mkdir-staging`+`copy-tree` el helper crea root:0 0700. Inmediatamente después de que el helper retorna, y ANTES de `protect`, intentar `open(staging_leaf/…, O_WRONLY|O_RDWR)` como uid 501 → **debe fallar** (EACCES/EPERM). También: abrir fd sobre un inodo del **origen** antes de la frontera y confirmar que no alcanza el objeto publicado (inodos nuevos). La PoC de Max (fd entre F4 y F6) queda cerrada porque F3+F4 son una sola operación de frontera.
   - N2bis: entre `verify` y `publish`, intentar sustituir la hoja → el re-pin debe abortar (swap-de-hoja).
   - N3: `ls -le` de cada entrada; ACE allow-write ajena ⇒ abortar; deny-write operador documentada.
   - N4: `fstatat(AT_SYMLINK_NOFOLLOW|AT_UNIQUE)` sobre hardlink de prueba → rechazo (errno ENOTCAPABLE/EMLINK); symlink escapado → rechazo.
   - N5: ancla con evidencia C-1 (hash en manifiesto sellado); mutar snapshot ⇒ abortar antes de efectos.
   - N6: forzar EEXIST (crear destino en la ventana) ⇒ sin anidar, sin borrar ganador, staging retenido; swap-de-hoja ⇒ abortar.
   - N7: entre verify y exec del helper de prueba, mutar la ruta ⇒ debe abortar o ejecutar el triple verificado.
   - N8: `journal` + relectura; intento fuera de `fixtures/` o sin prefijo `ot07_c5_staging.` ⇒ cero efectos (confinamiento del helper).

## UID / ACL esperados tras protect

| Campo | Esperado |
|---|---|
| uid:gid de cada no-symlink | `0:0` |
| modo archivos | sin `g+w` ni `o+w` |
| modo dirs | sin `g+w` ni `o+w`; `r-x` de otros si origen 0755 |
| ACL | sin `allow` write ajena; `deny write` para uid 501 documentada |
| symlinks | sin chown/chmod/ACL |

## Limpieza y residuos

- `rmdir` del padre staging (la hoja sale con el rename).
- Si falla: `RC=3`, `limpieza_ok=false`, ruta exacta del residual.
- `c5_helper` / `list-stale` lista huérfanos `ot07_c5_staging.*`.
- **Jamás** borrar por glob ni diferencia de listados globales.
- Residuos posibles: staging retenido; destino publicado **no se borra**.

## Alcance de H1 (pedido concreto al usuario)

1. Cambiar propietario/permisos con root **solo** sobre `fixtures/h1_*` y el staging propio.
2. Ejecutar `build/c5_helper protect/publish/cleanup` **solo** sobre esas rutas.
3. **Sección separada del mismo pedido** (condicionada a éxito nativo completo):
   preparación local del instalador real — tamaño medido, ancla/firma, rutas
   protegidas y efectos — **sin** crear USB, sin arranque, sin OCLP en host.

**No** se pide autorización genérica del equipo. Si cambia el helper autorizado
o el alcance material, la aprobación anterior no cubre el nuevo objeto.

## Lo que H1 NO autoriza

- USB / `createinstallmedia` / borrado de discos (eso es H2).
- Arranque / picker / Recovery (eso es H3).
- Instalación OCLP en el host o EFI interna.
- Señales a procesos ajenos ni interrupción de rescates.
- `sudoers`, LaunchDaemons, helpers persistentes, setuid instalados.
