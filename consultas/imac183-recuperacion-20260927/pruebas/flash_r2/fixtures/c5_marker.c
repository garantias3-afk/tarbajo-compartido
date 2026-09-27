/*
 * c5_marker.c — OT07-P7 (GLM Flash, RUN RUN.20260927T131419Z.C5IMAC1)
 * Programa INOCUO DETERMINISTA propio para fixtures: imprime un marcador
 * fijo y termina. Sin acceso a disco, red, procesos, señales ni argumentos.
 * NO es createinstallmedia ni toca dispositivos: es la fuente de dos binarios de
 * prueba compilados por make_fixtures_c5.py (marker y sustituto).
 * Determinismo: sin __DATE__/__TIME__, salida fija, sin aleatoriedad.
 */
#include <stdio.h>

int main(void) {
    puts(C5_MARKER_TEXT);
    return 0;
}
