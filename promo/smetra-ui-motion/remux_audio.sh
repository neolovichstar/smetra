#!/usr/bin/env bash
# Replaces only the soundtrack in the finished MP4s (video stream copied as is).
set -e
cd "$(dirname "$0")"
FF=${FFMPEG:-ffmpeg}
for name in smetra-ui-motion-1920x1080.mp4 smetra-ui-motion-1080x1920.mp4; do
  "$FF" -v error -y -i "out/$name" -i out/mix.wav -map 0:v -map 1:a -c:v copy \
    -af "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000" -c:a aac -b:a 192k -ar 48000 \
    -movflags +faststart -shortest "out/tmp_$name"
  mv -f "out/tmp_$name" "out/$name"; echo "out/$name"
done
