#!/usr/bin/env bash
# Averages 4 sub-frames per output frame (non-overlapping groups), 60 fps, H.264 + AAC, faststart.
# usage: ./encode.sh h|v
set -e
cd "$(dirname "$0")"
fmt=${1:-h}
FF=${FFMPEG:-ffmpeg}
if [ "$fmt" = v ]; then name=smetra-ui-motion-1080x1920.mp4; else name=smetra-ui-motion-1920x1080.mp4; fi
"$FF" -v error -y -framerate 240 -i "out/frames_$fmt/%06d.png" -i out/mix.wav \
  -filter_complex "[0:v]format=rgb48le,tmix=frames=4:weights='1 1 1 1',select='eq(mod(n\,4)\,3)',setpts=N/60/TB,fps=60,format=yuv420p,setsar=1[v];[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[a]" \
  -map "[v]" -map "[a]" -r 60 -c:v libx264 -preset slow -crf 16 -profile:v high -pix_fmt yuv420p \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart -shortest "out/$name"
echo "out/$name"
