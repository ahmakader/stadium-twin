#!/usr/bin/env bash
# Rebuild everything from the Python sources: textures -> Blender model -> web assets.
# Needs: Python 3.11+ with `pip install bpy shapely numpy pillow`, Node 18+ (for gltf-transform).
#   ./build.sh            # writes out/ (blend, glb, seat + escape-route data) and refreshes web/v2/
set -euo pipefail
cd "$(dirname "$0")"   # run from the folder that holds blender/ sim/ web/
OUT=${OUT:-out}; WEB=web/v2
mkdir -p "$OUT"
[ -d blender/tex ] || python3 blender/textures2.py blender/tex
python3 blender/build_v2.py -- "$OUT" | tee "$OUT/build.log" | grep -E "seats:|interior|egress nodes" || true
python3 blender/players.py -- "$OUT" >/dev/null 2>&1 || echo "players.py skipped (optional)"
[ -f "$OUT/player.glb" ] && base64 -w0 "$OUT/player.glb" > "$WEB/player.glb.txt"
GT="npx -y @gltf-transform/cli@4"
for f in old_trafford interior; do
  $GT weld "$OUT/$f.glb" "$OUT/w_$f.glb" >/dev/null
  $GT meshopt "$OUT/w_$f.glb" "$OUT/${f}_web.glb" >/dev/null
done
# the page loads these as base64 text so it can also be published as a single self-contained artifact
base64 -w0 "$OUT/old_trafford_web.glb" > "$WEB/stadium.glb.txt"
base64 -w0 "$OUT/interior_web.glb" > "$WEB/interior.glb.txt"
base64 -w0 "$OUT/seats.bin" > "$WEB/seats.bin.txt"
base64 -w0 "$OUT/egress.bin" > "$WEB/egress.bin.txt"
cp "$OUT/seats.json" "$OUT/egress.json" "$OUT/interior.json" "$WEB/"
echo "done: open the web app with  npx serve web  (or  python3 -m http.server -d web)"
