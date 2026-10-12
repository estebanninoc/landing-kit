#!/usr/bin/env bash
# tools/frames.sh — video -> secuencia de frames f_NNN.webp para una escena scroll-scrub
# (initEscena()/initMotor() en engine/scrub.js), con los parametros EXACTOS medidos del
# repo de referencia (utec-motos-landing/pack-scroll, commit 972b233, ORDEN BA1).
#
# ORDEN KIT1 (CLAUDE.md "LANDINGS: CLONAR, NO REHACER"): estos parametros son del
# componente probado "pipeline de frames" — no se cambian sin OK explicito de Esteban.
#
# Uso:
#   tools/frames.sh despiece   video.mp4 img/dp-frames
#   tools/frames.sh motor-mini video.mp4 img/scroll-frames/motor
#
# Requiere: ffmpeg, cwebp (paquete libwebp) en PATH.
set -euo pipefail

ESCENA="${1:?uso: frames.sh <despiece|motor-mini> <video-origen> <dir-salida>}"
SRC="${2:?falta el video de origen}"
OUT="${3:?falta el directorio de salida}"

# --- constantes medidas del repo motos (img/*/f_001.webp, ver config.json "animaciones") ---
case "$ESCENA" in
  despiece)
    N=71
    DESK_W=1280; DESK_H=732
    MOB_W=720;   MOB_H=412
    # avg medido en motos: desk ~79070B/frame, mob ~38264B/frame (metodo 6, ver abajo)
    ;;
  motor-mini)
    N=137
    DESK_W=784;  DESK_H=1361
    MOB_W=403;   MOB_H=703
    # avg medido en motos: desk ~50731B/frame, mob ~24356B/frame (metodo 6, ver abajo)
    ;;
  *)
    echo "escena desconocida: $ESCENA (usar despiece|motor-mini)" >&2
    exit 2
    ;;
esac

# Calidad: en motos el -q exacto de cwebp no quedo documentado (no es recuperable del
# archivo ya codificado), pero el standard de pipeline mas reciente verificado en este
# taller para esta MISMA arquitectura de escena (ORDEN CA11, ver
# ca12-work/carros/pack-scroll/README-carros.md) es libwebp -q40 movil / -q55 escritorio,
# -m 6 (metodo 6, mejor compresion/mas lento). Usar como punto de partida y AJUSTAR hasta
# acercarse al avg medido en motos de esta escena (arriba) si hace falta calzar peso.
Q_MOB=40
Q_DESK=55
METHOD=6

mkdir -p "$OUT/mob" "$OUT/desk"

extract() {
  local w=$1 h=$2 outdir=$3 q=$4
  local raw="/tmp/frames-raw-$ESCENA-$$"
  mkdir -p "$raw"
  # N frames parejos a lo largo de todo el clip, escalados+recortados (crop centrado) a WxH.
  # El bbox/crop de motos fue medido a mano por contenido (no es una constante generica) —
  # si el sujeto no queda centrado, ajustar el filtro crop antes de correr en produccion.
  ffmpeg -y -i "$SRC" -vf "scale=${w}:${h}:force_original_aspect_ratio=increase,crop=${w}:${h},fps=$(ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -of csv=p=0 "$SRC")/$((N-1))" \
    -frames:v "$N" "$raw/f_%03d.png"
  for f in "$raw"/f_*.png; do
    base=$(basename "$f" .png)
    cwebp -q "$q" -m "$METHOD" "$f" -o "$outdir/${base}.webp" >/dev/null
  done
  rm -rf "$raw"
}

extract "$MOB_W"  "$MOB_H"  "$OUT/mob"  "$Q_MOB"
extract "$DESK_W" "$DESK_H" "$OUT/desk" "$Q_DESK"

echo "listo: $N frames en $OUT/mob (${MOB_W}x${MOB_H}) y $OUT/desk (${DESK_W}x${DESK_H})"
