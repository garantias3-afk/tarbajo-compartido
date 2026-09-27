# FUENTE.md — v10r2r2 (estados separados)

| Estado | Valor | Base |
|---|---|---|
| Autenticidad criptográfica PKG | **ACREDITADA** | SHA-256 `ecc36bf1…8173` + `signed Apple Software` → `Apple Root CA` |
| Versión/build del SO | **PENDIENTE** | `Assets[0]` del MobileAsset (etapa E) |
| Metadata primaria catálogo | **NO acreditada** | 403/404 documentados (ver `apoyo_flash_p2/ERRATA_ADQUISICION.md`) |
| Protección C-5 | **NO implementada** | `root` bloqueada en gate; `aceptar_usuario` = aceptación del operador sin chown |

## Transformación permitida (M-10)

Al derivar del PKG, la **única** diferencia permitida entre payload y app es:

- `Contents/SharedSupport/` (directorio)
- `Contents/SharedSupport/SharedSupport.dmg`

Todo lo demás debe ser **idéntico** (rutas, tipo, tamaño, sha256, destinos de
enlaces). El DMG de nivel PKG debe ser idéntico al de la app (sha256 64 hex).

## Dependencias /var/tmp (I-5)

PKG y app extraída viven en `/var/tmp/ot07_E2R1_candidato.gMdKSX/`. Su ausencia
aborta antes de efectos. No se reconstruyen por nombre ni fecha. No se mueve el
PKG real. Conservación a futuro: decisión operativa, fuera de esta OT.

## Límites

- C-5 sin implementar: con `aceptar_usuario` el bundle quedaría `OPERADOR:wheel`.
- Sin montaje DMG en esta OT. Sin colocación/E/F/G/USB.
