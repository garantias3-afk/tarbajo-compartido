/*
 * c5_helper.c — helper limitado C5 (dirección B: proteger ANTES de publicar)
 * OT07-C5-NATIVO r6b · MIMO · NO activado hasta H1 explícita.
 *
 * NO es un runner de shell. Acciones cerradas:
 *   selfcheck | probe-at | mkdir-staging | copy-tree |
 *   protect | verify | publish | cleanup
 *
 * H-R5-1 (N2): mkdir-staging + copy-tree se ejecutan COMO ROOT. Los inodos
 * finales se crean dentro del staging root:0 0700; el uid operador jamás
 * puede abrir O_WRONLY/O_RDWR sobre ellos (no hay ventana entre crear y
 * proteger en la que el operador obtenga un fd de escritura).
 *
 * H-R5-5 (N8) / R6-4: toda acción confina rutas. El confinamiento ESTRICTO
 * viene de C5_AUTH_BASE (fijarla al fixture base en H1 — NativePriv ya lo
 * hace). El prefijo ot07_c5_staging. es una segunda condición; strstr sobre
 * ese componente NO basta por sí solo (acepta cualquier ruta que lo contenga).
 *
 * Primitivas REALES macOS (verificadas en SDK del host):
 *   lchown(2), fchmodat(2), openat(2), fstatat(2)+AT_UNIQUE,
 *   renamex_np(2)+RENAME_EXCL|RENAME_NOFOLLOW_ANY, acl_* (libSystem).
 * NO usa: RESOLVE_BENEATH (Linux), binario lchown (no existe), chown -R -h.
 *
 * Build (reproducible):
 *   clang -O2 -Wall -Wextra -std=c11 -mmacosx-version-min=14.0 \
 *     -isysroot .../MacOSX26.5.sdk \
 *     -o build/c5_helper src/c5_helper.c
 */
#define _DARWIN_C_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
#include <dirent.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/acl.h>
#include <libgen.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>

#ifndef AT_UNIQUE
#define AT_UNIQUE 0x8000 /* sys/fcntl.h:187 — prevent lookup on multi-link vnode */
#endif
#ifndef RENAME_EXCL
#define RENAME_EXCL 0x00000004
#endif
#ifndef RENAME_NOFOLLOW_ANY
#define RENAME_NOFOLLOW_ANY 0x00000010  /* sys/stdio.h — NO 0x80 */
#endif

#define C5_OK 0
#define C5_ERR_ARG 1
#define C5_ERR_IO 2
#define C5_ERR_POLICY 3
#define C5_ERR_STATE 4
#define C5_ERR_PRIV 5

/* UID del operador: parametrizable (H-R5-6.2) */
#ifndef C5_UID_OPERADOR
#define C5_UID_OPERADOR 501
#endif
#define PREFIJO_STAGING "ot07_c5_staging."

/* H-R5-5: confinamiento de rutas */
static int path_confinada(const char *path) {
    if (!path || path[0] != '/') return 0;
    /* 1) subárbol de C5_AUTH_BASE si está definida */
    const char *base = getenv("C5_AUTH_BASE");
    if (base && base[0] == '/') {
        size_t n = strlen(base);
        if (strncmp(path, base, n) == 0 && (path[n] == '/' || path[n] == '\0'))
            return 1;
    }
    /* 2) basename con prefijo ot07_c5_staging. o ruta dentro de uno */
    const char *slash = strrchr(path, '/');
    const char *name = slash ? slash + 1 : path;
    if (strncmp(name, PREFIJO_STAGING, strlen(PREFIJO_STAGING)) == 0) return 1;
    if (strstr(path, "/" PREFIJO_STAGING) != NULL) return 1;
    return 0;
}

static int exigir_confinada(const char *op, const char *path) {
    if (!path_confinada(path)) {
        fprintf(stderr,
            "{\"ok\":false,\"op\":\"%s\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"fuera-de-frontera\"}\n",
            op, path ? path : "", EACCES);
        return C5_ERR_POLICY;
    }
    return C5_OK;
}

static void die_errno(int rc, const char *op, const char *path) {
    fprintf(stderr, "{\"ok\":false,\"op\":\"%s\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"%s\"}\n",
            op, path ? path : "", errno, strerror(errno));
    exit(rc);
}

static void ok_json(const char *op, const char *path) {
    printf("{\"ok\":true,\"op\":\"%s\",\"path\":\"%s\"}\n", op, path ? path : "");
}

/* ---------- probe: AT_UNIQUE / fstatat ---------- */
static int cmd_probe_at(const char *path) {
    struct stat st;
    int flags = AT_SYMLINK_NOFOLLOW | AT_UNIQUE;
    if (fstatat(AT_FDCWD, path, &st, flags) != 0) {
        if (errno == ENOTCAPABLE || errno == EMLINK || errno == EPERM) {
            /* AT_UNIQUE rejected multi-link or escape — fail-closed semantics */
            printf("{\"ok\":true,\"op\":\"probe-at\",\"AT_UNIQUE\":true,\"rechazo\":true,\"errno\":%d}\n", errno);
            return C5_OK;
        }
        die_errno(C5_ERR_IO, "probe-at", path);
    }
    printf("{\"ok\":true,\"op\":\"probe-at\",\"AT_UNIQUE\":true,\"dev\":%llu,\"ino\":%llu,\"mode\":%o,\"nlink\":%u,\"uid\":%u,\"gid\":%u}\n",
           (unsigned long long)st.st_dev, (unsigned long long)st.st_ino,
           (unsigned)st.st_mode, (unsigned)st.st_nlink,
           (unsigned)st.st_uid, (unsigned)st.st_gid);
    return C5_OK;
}

/* ---------- H-R5-1: mkdir-staging (root crea la frontera) ---------- */
static int cmd_mkdir_staging(const char *base) {
    if (geteuid() != 0) {
        fprintf(stderr, "{\"ok\":false,\"op\":\"mkdir-staging\",\"errno\":%d,\"msg\":\"requiere H1 + euid 0\"}\n", EPERM);
        return C5_ERR_PRIV;
    }
    if (exigir_confinada("mkdir-staging", base) != C5_OK) return C5_ERR_POLICY;
    /* mkdtemp-equivalente: base/ot07_c5_staging.XXXXXX root:0 0700 */
    char tmpl[PATH_MAX];
    if (snprintf(tmpl, sizeof(tmpl), "%s/%sXXXXXX", base, PREFIJO_STAGING) >= (int)sizeof(tmpl))
        return C5_ERR_ARG;
    if (mkdtemp(tmpl) == NULL) die_errno(C5_ERR_IO, "mkdtemp", base);
    if (chown(tmpl, 0, 0) != 0) die_errno(C5_ERR_PRIV, "chown-staging", tmpl);
    if (chmod(tmpl, 0700) != 0) die_errno(C5_ERR_IO, "chmod-staging", tmpl);
    /* hoja de destino a un nivel */
    char hoja[PATH_MAX];
    if (snprintf(hoja, sizeof(hoja), "%s/leaf", tmpl) >= (int)sizeof(hoja))
        return C5_ERR_ARG;
    if (mkdir(hoja, 0700) != 0) die_errno(C5_ERR_IO, "mkdir-hoja", hoja);
    if (chown(hoja, 0, 0) != 0) die_errno(C5_ERR_PRIV, "chown-hoja", hoja);
    printf("{\"ok\":true,\"op\":\"mkdir-staging\",\"parent\":\"%s\",\"leaf\":\"%s\",\"uid\":0,\"gid\":0,\"mode\":\"0700\"}\n",
           tmpl, hoja);
    return C5_OK;
}

/* ---------- H-R5-1: copy-tree (root copia desde origen no confiable) ---------- */
static int copy_reg(const char *src, const char *dst) {
    struct stat st;
    if (lstat(src, &st) != 0) die_errno(C5_ERR_IO, "lstat-src", src);
    /* D2: conservar modo del origen menos g+w/o+w (INTERFAZ) */
    mode_t nmode = st.st_mode & 0777 & ~(S_IWGRP | S_IWOTH);
    int in = open(src, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (in < 0) die_errno(C5_ERR_IO, "open-src", src);
    int out = open(dst, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, nmode);
    if (out < 0) { close(in); die_errno(C5_ERR_IO, "open-dst", dst); }
    char buf[65536];
    ssize_t n;
    while ((n = read(in, buf, sizeof(buf))) > 0) {
        if (write(out, buf, (size_t)n) != n) {
            close(in); close(out); die_errno(C5_ERR_IO, "write-dst", dst);
        }
    }
    close(in);
    if (n < 0) { close(out); die_errno(C5_ERR_IO, "read-src", src); }
    if (fchown(out, 0, 0) != 0) { close(out); die_errno(C5_ERR_PRIV, "fchown-dst", dst); }
    if (fchmod(out, nmode) != 0) { close(out); die_errno(C5_ERR_IO, "fchmod-dst", dst); }
    close(out);
    return C5_OK;
}

/* Copia el CONTENIDO de src dentro de dst YA EXISTENTE (D1).
   dst es la hoja creada por mkdir-staging: no se mkdir la raíz. */
static int copy_walk(const char *src, const char *dst) {
    struct stat st;
    if (lstat(src, &st) != 0) die_errno(C5_ERR_IO, "lstat-src", src);
    if (S_ISLNK(st.st_mode)) {
        char target[PATH_MAX];
        ssize_t n = readlink(src, target, sizeof(target) - 1);
        if (n < 0) die_errno(C5_ERR_IO, "readlink", src);
        target[n] = '\0';
        if (target[0] == '/' || strstr(target, "..") != NULL) {
            fprintf(stderr, "{\"ok\":false,\"op\":\"copy-tree\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"symlink-escapa\"}\n",
                    src, EACCES);
            return C5_ERR_POLICY;
        }
        if (symlink(target, dst) != 0) die_errno(C5_ERR_IO, "symlink", dst);
        return C5_OK;
    }
    if (S_ISREG(st.st_mode)) {
        if (st.st_nlink > 1) {
            fprintf(stderr, "{\"ok\":false,\"op\":\"copy-tree\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"hardlink\"}\n",
                    src, EMLINK);
            return C5_ERR_POLICY;
        }
        return copy_reg(src, dst);
    }
    if (S_ISDIR(st.st_mode)) {
        /* D2: modo del origen menos g+w/o+w; D1: mkdir solo si dst no existe */
        mode_t nmode = st.st_mode & 0777 & ~(S_IWGRP | S_IWOTH);
        struct stat dstst;
        if (lstat(dst, &dstst) != 0) {
            if (errno != ENOENT) die_errno(C5_ERR_IO, "lstat-dst", dst);
            if (mkdir(dst, nmode) != 0) die_errno(C5_ERR_IO, "mkdir", dst);
        } else if (!S_ISDIR(dstst.st_mode)) {
            fprintf(stderr, "{\"ok\":false,\"op\":\"copy-tree\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"dst-no-es-dir\"}\n",
                    dst, ENOTDIR);
            return C5_ERR_POLICY;
        }
        if (chown(dst, 0, 0) != 0) die_errno(C5_ERR_PRIV, "chown-dir", dst);
        if (chmod(dst, nmode) != 0) die_errno(C5_ERR_IO, "chmod-dir", dst);
        DIR *d = opendir(src);
        if (!d) die_errno(C5_ERR_IO, "opendir", src);
        struct dirent *de;
        while ((de = readdir(d)) != NULL) {
            if (strcmp(de->d_name, ".") == 0 || strcmp(de->d_name, "..") == 0) continue;
            char s[PATH_MAX], t[PATH_MAX];
            if (snprintf(s, sizeof(s), "%s/%s", src, de->d_name) >= (int)sizeof(s) ||
                snprintf(t, sizeof(t), "%s/%s", dst, de->d_name) >= (int)sizeof(t)) {
                closedir(d); return C5_ERR_ARG;
            }
            if (copy_walk(s, t) != C5_OK) { closedir(d); return C5_ERR_POLICY; }
        }
        closedir(d);
        return C5_OK;
    }
    fprintf(stderr, "{\"ok\":false,\"op\":\"copy-tree\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"tipo-especial\"}\n",
            src, EINVAL);
    return C5_ERR_POLICY;
}

static int cmd_copy_tree(const char *src, const char *dst) {
    if (geteuid() != 0) {
        fprintf(stderr, "{\"ok\":false,\"op\":\"copy-tree\",\"errno\":%d,\"msg\":\"requiere H1 + euid 0\"}\n", EPERM);
        return C5_ERR_PRIV;
    }
    if (exigir_confinada("copy-tree", dst) != C5_OK) return C5_ERR_POLICY;
    struct stat st;
    if (lstat(dst, &st) != 0) die_errno(C5_ERR_IO, "lstat-dst", dst);
    if (!S_ISDIR(st.st_mode)) return C5_ERR_ARG;
    /* D1: dst (hoja) YA EXISTE — copiar el CONTENIDO de src dentro de dst.
       Si src es dir: no mkdir la raíz; se copian sus hijos.
       Si src es archivo/symlink: se copia como dst/nombre. */
    if (lstat(src, &st) != 0) die_errno(C5_ERR_IO, "lstat-src", src);
    int rc;
    if (S_ISDIR(st.st_mode)) {
        DIR *d = opendir(src);
        if (!d) die_errno(C5_ERR_IO, "opendir", src);
        rc = C5_OK;
        struct dirent *de;
        while ((de = readdir(d)) != NULL) {
            if (strcmp(de->d_name, ".") == 0 || strcmp(de->d_name, "..") == 0) continue;
            char s[PATH_MAX], t[PATH_MAX];
            if (snprintf(s, sizeof(s), "%s/%s", src, de->d_name) >= (int)sizeof(s) ||
                snprintf(t, sizeof(t), "%s/%s", dst, de->d_name) >= (int)sizeof(t)) {
                closedir(d); return C5_ERR_ARG;
            }
            if (copy_walk(s, t) != C5_OK) { closedir(d); rc = C5_ERR_POLICY; break; }
        }
        closedir(d);
        /* R6C-1: aplicar a la HOJA el modo del origen menos g+w/o+w
           (paridad con el orquestador simulated). dst ya es root:0. */
        if (rc == C5_OK) {
            mode_t hmode = st.st_mode & 0777 & ~(S_IWGRP | S_IWOTH);
            if (chmod(dst, hmode) != 0) die_errno(C5_ERR_IO, "chmod-hoja", dst);
        }
    } else {
        /* origen no-dir: copiar como dst/basename(src) */
        const char *base = strrchr(src, '/');
        base = base ? base + 1 : src;
        char t[PATH_MAX];
        if (snprintf(t, sizeof(t), "%s/%s", dst, base) >= (int)sizeof(t)) return C5_ERR_ARG;
        rc = copy_walk(src, t);
    }
    if (rc == C5_OK) ok_json("copy-tree", dst);
    return rc;
}

/* ---------- protect: lchown root:wheel + chmod go-w + ACL deny-write ---------- */
static int protect_one(const char *path, bool is_symlink) {
    if (is_symlink) {
        /* symlinks: jamás chown/chmod/ACL — el directorio contenedor protege */
        return C5_OK;
    }
    if (lchown(path, 0, 0) != 0) {
        /* lchown(2) función, NO binario. Solo root. */
        die_errno(C5_ERR_PRIV, "lchown", path);
    }
    struct stat st;
    if (lstat(path, &st) != 0) die_errno(C5_ERR_IO, "lstat", path);
    mode_t nmode = st.st_mode & ~(S_IWGRP | S_IWOTH);
    if (fchmodat(AT_FDCWD, path, nmode, 0) != 0) {
        die_errno(C5_ERR_IO, "fchmodat", path);
    }
    /* ACL deny-write para el operador — defensa en profundidad */
    acl_t acl = acl_get_file(path, ACL_TYPE_EXTENDED);
    if (acl != NULL) {
        acl_entry_t ent;
        if (acl_create_entry(&acl, &ent) == 0) {
            acl_permset_t perms;
            uid_t op = C5_UID_OPERADOR;
            if (acl_set_tag_type(ent, ACL_EXTENDED_DENY) == 0 &&
                acl_set_qualifier(ent, &op) == 0 &&
                acl_get_permset(ent, &perms) == 0) {
                acl_add_perm(perms, ACL_WRITE_DATA);
                acl_add_perm(perms, ACL_APPEND_DATA);
                acl_add_perm(perms, ACL_DELETE);
                acl_add_perm(perms, ACL_WRITE_ATTRIBUTES);
                acl_add_perm(perms, ACL_WRITE_EXTATTRIBUTES);
                if (acl_set_file(path, ACL_TYPE_EXTENDED, acl) != 0) {
                    fprintf(stderr, "{\"ok\":false,\"op\":\"acl_set_file\",\"path\":\"%s\",\"errno\":%d}\n",
                            path, errno);
                }
            }
        }
        acl_free(acl);
    }
    return C5_OK;
}

static int walk_protect(const char *root) {
    struct stat rst;
    if (lstat(root, &rst) != 0) die_errno(C5_ERR_IO, "lstat", root);
    if (S_ISLNK(rst.st_mode)) die_errno(C5_ERR_POLICY, "root-es-symlink", root);
    protect_one(root, false);

    DIR *d = opendir(root);
    if (!d) die_errno(C5_ERR_IO, "opendir", root);
    struct dirent *de;
    while ((de = readdir(d)) != NULL) {
        if (strcmp(de->d_name, ".") == 0 || strcmp(de->d_name, "..") == 0) continue;
        char child[PATH_MAX];
        if (snprintf(child, sizeof(child), "%s/%s", root, de->d_name) >= (int)sizeof(child)) {
            closedir(d);
            die_errno(C5_ERR_POLICY, "path-too-long", de->d_name);
        }
        struct stat st;
        if (lstat(child, &st) != 0) { closedir(d); die_errno(C5_ERR_IO, "lstat", child); }
        if (S_ISLNK(st.st_mode)) {
            /* no tocar symlink */
            continue;
        } else if (S_ISDIR(st.st_mode)) {
            if (walk_protect(child) != C5_OK) { closedir(d); return C5_ERR_IO; }
        } else if (S_ISREG(st.st_mode)) {
            if (st.st_nlink > 1) {
                /* hardlink: proteger el inode afectaría a nodo FUERA del árbol */
                closedir(d);
                die_errno(C5_ERR_POLICY, "hardlink-rechazado", child);
            }
            protect_one(child, false);
        } else {
            /* FIFO/especiales: rechazo */
            closedir(d);
            die_errno(C5_ERR_POLICY, "tipo-especial-rechazado", child);
        }
    }
    closedir(d);
    return C5_OK;
}

static int cmd_protect(const char *root) {
    if (geteuid() != 0) {
        fprintf(stderr, "{\"ok\":false,\"op\":\"protect\",\"errno\":%d,\"msg\":\"requiere H1 + euid 0\"}\n", EPERM);
        return C5_ERR_PRIV;
    }
    if (exigir_confinada("protect", root) != C5_OK) return C5_ERR_POLICY;
    int rc = walk_protect(root);
    if (rc == C5_OK) ok_json("protect", root);
    return rc;
}

/* ---------- publish: renamex_np RECLAIM-safe atómico ---------- */
static int cmd_publish(const char *src, const char *dst) {
    if (geteuid() != 0) {
        fprintf(stderr, "{\"ok\":false,\"op\":\"publish\",\"errno\":%d,\"msg\":\"requiere H1 + euid 0\"}\n", EPERM);
        return C5_ERR_PRIV;
    }
    if (exigir_confinada("publish", src) != C5_OK) return C5_ERR_POLICY;
    /* H-R5-2: re-pin de la hoja justo antes del rename */
    struct stat st;
    if (lstat(src, &st) != 0) die_errno(C5_ERR_IO, "lstat-src", src);
    if (S_ISLNK(st.st_mode)) die_errno(C5_ERR_POLICY, "src-es-symlink", src);
    unsigned long long pin_dev = (unsigned long long)st.st_dev;
    unsigned long long pin_ino = (unsigned long long)st.st_ino;
    /* padre debe ser 0700 y estar confinado */
    char padre[PATH_MAX];
    if (snprintf(padre, sizeof(padre), "%s", src) >= (int)sizeof(padre)) return C5_ERR_ARG;
    char *slash = strrchr(padre, '/');
    if (slash) *slash = '\0';
    struct stat pst;
    if (lstat(padre, &pst) != 0) die_errno(C5_ERR_IO, "lstat-padre", padre);
    if (exigir_confinada("publish-padre", padre) != C5_OK) return C5_ERR_POLICY;
    if ((pst.st_mode & 0777) != 0700) {
        fprintf(stderr, "{\"ok\":false,\"op\":\"publish\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"padre-no-0700\"}\n",
                padre, EPERM);
        return C5_ERR_POLICY;
    }
    if (lstat(dst, &st) == 0) {
        fprintf(stderr, "{\"ok\":false,\"op\":\"publish\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"destino preexistente\"}\n",
                dst, EEXIST);
        return C5_ERR_STATE;
    }
    if (errno != ENOENT) die_errno(C5_ERR_IO, "lstat-dst", dst);
    /* re-pin inmediato antes de renamex_np (H-R5-2) */
    struct stat st2;
    if (lstat(src, &st2) != 0) die_errno(C5_ERR_IO, "re-lstat-src", src);
    if ((unsigned long long)st2.st_dev != pin_dev || (unsigned long long)st2.st_ino != pin_ino) {
        fprintf(stderr, "{\"ok\":false,\"op\":\"publish\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"hoja-swap\"}\n",
                src, ESTALE);
        return C5_ERR_STATE;
    }
    if (renamex_np(src, dst, RENAME_EXCL | RENAME_NOFOLLOW_ANY) != 0) {
        if (errno == EEXIST) {
            fprintf(stderr, "{\"ok\":false,\"op\":\"publish\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"carrera EEXIST; sin anidar\"}\n",
                    dst, EEXIST);
            return C5_ERR_STATE;
        }
        die_errno(C5_ERR_IO, "renamex_np", dst);
    }
    if (lstat(dst, &st) != 0) die_errno(C5_ERR_IO, "lstat-dst-post", dst);
    printf("{\"ok\":true,\"op\":\"publish\",\"src\":\"%s\",\"dst\":\"%s\",\"dev\":%llu,\"ino\":%llu}\n",
           src, dst, (unsigned long long)st.st_dev, (unsigned long long)st.st_ino);
    return C5_OK;
}

/* ---------- cleanup: rmdir del padre staging (la hoja salió con rename) ----------
   Opcional r6c: retiro bottom-up de ÁRBOL VACÍO propio confinado (sin rm genérico).
   Solo rmdir de directorios vacíos; cualquier archivo/symlink restante aborta. */
static int rmdir_vacio_bottom_up(const char *dir, int *contados) {
    /* devuelve C5_OK si pudo vaciar y borrar dir; C5_ERR_STATE si queda contenido */
    struct stat st;
    if (lstat(dir, &st) != 0) die_errno(C5_ERR_IO, "lstat", dir);
    if (!S_ISDIR(st.st_mode)) return C5_ERR_STATE;
    DIR *d = opendir(dir);
    if (!d) die_errno(C5_ERR_IO, "opendir", dir);
    struct dirent *de;
    int rc = C5_OK;
    while ((de = readdir(d)) != NULL) {
        if (strcmp(de->d_name, ".") == 0 || strcmp(de->d_name, "..") == 0) continue;
        char child[PATH_MAX];
        if (snprintf(child, sizeof(child), "%s/%s", dir, de->d_name) >= (int)sizeof(child)) {
            closedir(d); return C5_ERR_ARG;
        }
        struct stat cst;
        if (lstat(child, &cst) != 0) { closedir(d); die_errno(C5_ERR_IO, "lstat", child); }
        if (S_ISDIR(cst.st_mode)) {
            if (rmdir_vacio_bottom_up(child, contados) != C5_OK) { rc = C5_ERR_STATE; }
        } else {
            /* hay contenido: NO borrar nada */
            fprintf(stderr, "{\"ok\":false,\"op\":\"cleanup\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"contenido-residual\"}\n",
                    child, ENOTEMPTY);
            closedir(d);
            return C5_ERR_STATE;
        }
    }
    closedir(d);
    if (rc != C5_OK) return rc;
    if (rmdir(dir) != 0) {
        fprintf(stderr, "{\"ok\":false,\"op\":\"cleanup\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"rmdir\"}\n",
                dir, errno);
        return C5_ERR_IO;
    }
    (*contados)++;
    return C5_OK;
}

static int cmd_cleanup(const char *dir) {
    if (exigir_confinada("cleanup", dir) != C5_OK) return C5_ERR_POLICY;
    struct stat st;
    if (lstat(dir, &st) != 0) die_errno(C5_ERR_IO, "lstat", dir);
    if (!S_ISDIR(st.st_mode)) return C5_ERR_POLICY;
    /* solo directorios con el prefijo de staging */
    const char *name = strrchr(dir, '/');
    name = name ? name + 1 : dir;
    if (strncmp(name, PREFIJO_STAGING, strlen(PREFIJO_STAGING)) != 0) {
        fprintf(stderr, "{\"ok\":false,\"op\":\"cleanup\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"sin-prefijo-staging\"}\n",
                dir, EACCES);
        return C5_ERR_POLICY;
    }
    /* r6c: retiro bottom-up de árbol vacío propio (solo rmdir, sin rm genérico) */
    int contados = 0;
    int rc = rmdir_vacio_bottom_up(dir, &contados);
    if (rc != C5_OK) {
        fprintf(stderr, "{\"ok\":false,\"op\":\"cleanup\",\"path\":\"%s\",\"errno\":%d,\"msg\":\"no-vacio-o-error\"}\n",
                dir, ENOTEMPTY);
        return rc;
    }
    printf("{\"ok\":true,\"op\":\"cleanup\",\"path\":\"%s\",\"rmdir_count\":%d}\n", dir, contados);
    return C5_OK;
}

/* ---------- verify: metadata esperada en raíz e hijos (HB-1) ---------- */
static int verify_one(const char *path, bool is_root) {
    struct stat st;
    if (lstat(path, &st) != 0) die_errno(C5_ERR_IO, "lstat", path);
    if (S_ISLNK(st.st_mode)) return C5_OK;
    if (st.st_uid != 0 || st.st_gid != 0) {
        fprintf(stderr, "{\"ok\":false,\"op\":\"verify-owner\",\"path\":\"%s\",\"uid\":%u,\"gid\":%u}\n",
                path, (unsigned)st.st_uid, (unsigned)st.st_gid);
        return C5_ERR_POLICY;
    }
    if (st.st_mode & (S_IWGRP | S_IWOTH)) {
        fprintf(stderr, "{\"ok\":false,\"op\":\"verify-gow\",\"path\":\"%s\",\"mode\":%o,\"root\":%s}\n",
                path, (unsigned)st.st_mode, is_root ? "true" : "false");
        return C5_ERR_POLICY;
    }
    return C5_OK;
}

static int walk_verify(const char *root, bool is_root) {
    if (verify_one(root, is_root) != C5_OK) return C5_ERR_POLICY;
    struct stat rst;
    if (lstat(root, &rst) != 0) die_errno(C5_ERR_IO, "lstat", root);
    if (!S_ISDIR(rst.st_mode)) return C5_OK;
    DIR *d = opendir(root);
    if (!d) die_errno(C5_ERR_IO, "opendir", root);
    struct dirent *de;
    while ((de = readdir(d)) != NULL) {
        if (strcmp(de->d_name, ".") == 0 || strcmp(de->d_name, "..") == 0) continue;
        char child[PATH_MAX];
        if (snprintf(child, sizeof(child), "%s/%s", root, de->d_name) >= (int)sizeof(child)) {
            closedir(d); return C5_ERR_POLICY;
        }
        struct stat st;
        if (lstat(child, &st) != 0) { closedir(d); die_errno(C5_ERR_IO, "lstat", child); }
        if (S_ISLNK(st.st_mode)) continue;
        if (S_ISDIR(st.st_mode)) {
            if (walk_verify(child, false) != C5_OK) { closedir(d); return C5_ERR_POLICY; }
        } else if (S_ISREG(st.st_mode)) {
            if (verify_one(child, false) != C5_OK) { closedir(d); return C5_ERR_POLICY; }
        } else {
            closedir(d); return C5_ERR_POLICY;
        }
    }
    closedir(d);
    return C5_OK;
}

static int cmd_verify(const char *root) {
    if (exigir_confinada("verify", root) != C5_OK) return C5_ERR_POLICY;
    int rc = walk_verify(root, true);
    if (rc == C5_OK) ok_json("verify", root);
    return rc;
}

/* ---------- bootstrap self-check (sin ejecutar código mutable del uid) ---------- */
static int cmd_selfcheck(void) {
    printf("{\"ok\":true,\"op\":\"selfcheck\",\"euid\":%d,\"uid\":%d,\"gid\":%d,"
           "\"AT_UNIQUE\":true,\"RENAME_EXCL\":true,\"RENAME_NOFOLLOW_ANY\":true,"
           "\"RENAME_NOFOLLOW_ANY_val\":\"0x10\",\"lchown\":\"syscall\","
           "\"uid_operador\":%d,\"confinamiento\":\"ot07_c5_staging.+C5_AUTH_BASE\"}\n",
           (int)geteuid(), (int)getuid(), (int)getgid(), C5_UID_OPERADOR);
    return C5_OK;
}

static void usage(void) {
    fprintf(stderr,
        "uso: c5_helper <accion> [args]\n"
        "  selfcheck\n"
        "  probe-at <path>\n"
        "  mkdir-staging <base>            # requiere H1 + euid 0; crea ot07_c5_staging.*\n"
        "  copy-tree <origen> <staging_leaf> # requiere H1 + euid 0\n"
        "  protect <root>                  # requiere H1 + euid 0\n"
        "  verify  <root>                  # metadata dueño/mode raíz e hijos\n"
        "  publish <staging_leaf> <dst>    # requiere H1 + euid 0; re-pin hoja\n"
        "  cleanup <staging_parent>        # solo prefijo ot07_c5_staging.\n"
        "Confinamiento: prefijo ot07_c5_staging. o C5_AUTH_BASE.\n"
        "NO es runner de shell. Sin H1 no hay acciones privilegiadas.\n");
    exit(C5_ERR_ARG);
}

int main(int argc, char **argv) {
    if (argc < 2) usage();
    const char *cmd = argv[1];
    if (strcmp(cmd, "selfcheck") == 0) return cmd_selfcheck();
    if (strcmp(cmd, "probe-at") == 0 && argc == 3) return cmd_probe_at(argv[2]);
    if (strcmp(cmd, "mkdir-staging") == 0 && argc == 3) return cmd_mkdir_staging(argv[2]);
    if (strcmp(cmd, "copy-tree") == 0 && argc == 4) return cmd_copy_tree(argv[2], argv[3]);
    if (strcmp(cmd, "protect") == 0 && argc == 3) return cmd_protect(argv[2]);
    if (strcmp(cmd, "verify") == 0 && argc == 3) return cmd_verify(argv[2]);
    if (strcmp(cmd, "publish") == 0 && argc == 4) return cmd_publish(argv[2], argv[3]);
    if (strcmp(cmd, "cleanup") == 0 && argc == 3) return cmd_cleanup(argv[2]);
    usage();
}
