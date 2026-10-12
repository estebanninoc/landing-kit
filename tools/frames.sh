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
  carro-despiece)
    # ORDEN CB4: mismo N/calidad que "despiece" de motos, pero W/H en la proporcion NATIVA
    # del video fuente (carro-motor-despiece.mp4, 1152x768, 1.5:1) en vez de la 1280x732
    # (1.748:1) de motos — forzar el aspect de motos recortaria contenido (la causa del bug
    # de piezas cortadas en los bordes que esta orden corrige: el box crop quedaba chico para
    # el cuadro totalmente explotado). Con W:H = aspect nativo, scale+crop de extract() no
    # recorta nada (crop==box ya escalado 1:1).
    N=71
    DESK_W=1152; DESK_H=768
    MOB_W=648;   MOB_H=432
    ;;
  carro-motor)
    # ORDEN CB4: mismo N/calidad que "motor-mini" de motos, W/H en proporcion nativa del
    # arnes (carro-arnes-rayosx.mp4, 1440x704, ~2.045:1) — ya es la misma proporcion que
    # carros traia (1080x528), sin recorte.
    N=137
    DESK_W=1440; DESK_H=704
    MOB_W=740;   MOB_H=362
    ;;
  *)
    echo "escena desconocida: $ESCENA (usar despiece|motor-mini|carro-despiece|carro-motor)" >&2
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

# Decodifica TODOS los frames nativos del clip una sola vez (escalados+recortados a WxH),
# sin resamplear tiempo con el filtro fps — ORDEN CB4: ese filtro (fps=N/duracion) es fragil,
# el ultimo sample cae justo en el borde del clip y segun el redondeo de duracion que use
# ffprobe (stream vs container) a veces lo descarta, dejando N-1 frames en vez de N (probado,
# reproducible). En vez de perseguir el redondeo exacto, se decodifican los frames nativos
# tal cual (uno por cada frame real del archivo) y la seleccion de cuales de esos frames
# nativos van a cada posicion de salida (con repeticion si N > nativos) se hace con
# aritmetica entera simple — determinista, siempre da exactamente N.
decode_native() {
  local w=$1 h=$2 rawdir=$3
  mkdir -p "$rawdir"
  ffmpeg -y -v error -i "$SRC" -vsync 0 \
    -vf "scale=${w}:${h}:force_original_aspect_ratio=increase,crop=${w}:${h}" \
    "$rawdir/n_%04d.png"
}

extract() {
  local w=$1 h=$2 outdir=$3 q=$4
  local raw="/tmp/frames-raw-$ESCENA-$$"
  decode_native "$w" "$h" "$raw"
  local nativeN; nativeN=$(ls "$raw"/n_*.png | wc -l)
  if [ "$nativeN" -lt 1 ]; then
    echo "ERROR: $SRC no produjo ningun frame nativo" >&2; exit 3
  fi
  # indice nativo (0-based) para la posicion j (0..N-1) de salida: round(j*(nativeN-1)/(N-1)),
  # primero y ultimo de salida == primer y ultimo frame nativo exactos.
  python3 -c "
nativeN=$nativeN; N=$N
for j in range(N):
    idx = round(j*(nativeN-1)/(N-1)) if N>1 else 0
    print(idx+1)
" > "$raw/idx.txt"
  local kept=0
  while IFS= read -r nidx; do
    kept=$((kept+1))
    src_png=$(printf "%s/n_%04d.png" "$raw" "$nidx")
    out_base=$(printf "f_%03d" "$kept")
    if command -v cwebp >/dev/null 2>&1; then
      cwebp -q "$q" -m "$METHOD" "$src_png" -o "$outdir/${out_base}.webp" >/dev/null
    else
      # sin cwebp en PATH (este taller no tiene sudo): fallback via Pillow, mismo
      # metodo de compresion (6) — ver tools/webp_encode.py
      "$(dirname "${BASH_SOURCE[0]}")/webp_encode.py" "$src_png" "$outdir/${out_base}.webp" "$q"
    fi
  done < "$raw/idx.txt"
  rm -rf "$raw"
  if [ "$kept" -ne "$N" ]; then
    echo "ERROR: $outdir esperaba $N frames, se generaron $kept" >&2
    exit 3
  fi
}

extract "$MOB_W"  "$MOB_H"  "$OUT/mob"  "$Q_MOB"
extract "$DESK_W" "$DESK_H" "$OUT/desk" "$Q_DESK"

echo "listo: $N frames en $OUT/mob (${MOB_W}x${MOB_H}) y $OUT/desk (${DESK_W}x${DESK_H})"
