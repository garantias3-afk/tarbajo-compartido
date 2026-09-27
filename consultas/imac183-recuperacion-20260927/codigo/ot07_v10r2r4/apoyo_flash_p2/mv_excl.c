/*
 * mv_excl — renombrado atómico sin sobrescritura ni seguimiento de enlaces.
 * OT07-P2 punto 4: primitiva macOS concreta (renamex_np, sys/stdio.h):
 *   RENAME_EXCL          -> EEXIST si el destino existe (sea lo que sea)
 *   RENAME_NOFOLLOW_ANY  -> error si aparece un symlink en old o new
 * Semántica demostrada en fixtures por harness (no se ejecuta contra /Applications).
 * Uso: mv_excl <origen> <destino>   |  RC 0 = movido, 17 = EEXIST, otro != 0 = error
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stdio.h>   /* RENAME_EXCL, RENAME_NOFOLLOW_ANY */

int main(int argc, char **argv){
    if (argc != 3){ fprintf(stderr, "uso: mv_excl <origen> <destino>\n"); return 2; }
    errno = 0;
    int r = renamex_np(argv[1], argv[2], RENAME_EXCL | RENAME_NOFOLLOW_ANY);
    if (r == 0){ printf("MOVED\n"); return 0; }
    int e = errno;
    printf("ERRNO=%d (%s)\n", e, strerror(e));
    return e == EEXIST ? 17 : 1;
}
