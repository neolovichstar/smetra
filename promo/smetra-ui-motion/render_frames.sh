#!/usr/bin/env bash
# Renders all sub-frames for a format; resumes after a browser crash (existing frames are skipped).
fmt=${1:-h}
for i in 1 2 3 4 5 6; do node render.mjs frames "$fmt" 4 && exit 0; echo "retry $i"; done
exit 1
