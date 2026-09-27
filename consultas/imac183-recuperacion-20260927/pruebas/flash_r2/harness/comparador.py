#!/usr/bin/env python3
# =====================================================================
# NO_PRODUCTIVO_NO_AUTORIZADO — OT07-P7 GLM Flash (RUN.20260927T131419Z.C5IMAC1)
# comparador — metadata AFIRMADA vs capacidad REAL medida por el lector
# independiente. Es el objetivo de la mutación MUT-C1 (sensibilidad N3):
# la copia mutada ignora la capacidad cuando hay ACL — el bypass debe
# dejar de detectarse SOLO por esa mutación única (disciplina de
# mutación: base positiva detecta, mutante pierde la aserción prevista).
# =====================================================================
"""Comparador metadata↔capacidad del harness C5 (pequeño y mutable a propósito)."""


def evaluar(afirmacion: dict, medicion: dict, verificar_acl: bool = True) -> list:
    """afirmacion: {'escribible_por_lector': bool, 'acl_allow_afirmada': bool}
    medicion: {'open_escritura': 'SUCCEDE'|'RECHAZA'|'AUSENTE',
               'ace_allow_encontrada': bool, 'creacion_en_dir': 'SUCCEDE'|'RECHAZA'|'AUSENTE'}
    Devuelve lista de problemas (vacía = coherente)."""
    problemas = []
    if medicion.get('open_escritura') == 'SUCCEDE' and \
            not afirmacion.get('escribible_por_lector', True):
        problemas.append('capacidad_excede_metadata(open)')
    if medicion.get('creacion_en_dir') == 'SUCCEDE' and \
            not afirmacion.get('creable_por_lector', True):
        problemas.append('capacidad_excede_metadata(create)')
    if verificar_acl and medicion.get('ace_allow_encontrada') and \
            not afirmacion.get('acl_allow_afirmada', False):
        problemas.append('ace_allow_no_afirmada(bypass)')
    return problemas
