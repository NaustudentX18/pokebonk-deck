#!/usr/bin/env bash
# Generate the Steam capsule artwork for the PokéBonk Deck client.
#
# Steam reads these from ~/.steam/steam/app/<appid>/ for a non-Steam shortcut:
#   library_hero.jpg    3840x1240   the big library background
#   library_capsule.jpg 1438x810    the library capsule
#   capsule.jpg          616x353    the grid capsule
#   capsulev5.jpg        462x174   the small capsule
#   header.jpg           460x215    the library header
#   logo.png            1280x360    the transparent wordmark
#   icon.jpg             128x128    the small icon
#
# The wordmark and layout are original. The background is the project's own
# gameplay capture.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${1:-artwork}"
BG="${2:-site/media/05-gameplay.png}"
mkdir -p "$OUT"

say() { printf '\033[1;36m[artwork]\033[0m %s\n' "$*"; }

if [ ! -f "$BG" ]; then
  echo "no background image at $BG" >&2
  exit 1
fi

# --- the wordmark, as a transparent PNG --------------------------------------
# The mark is SVG (rsvg-convert renders it well). The type is drawn with the
# font engine instead: SVG <text> with a gradient <tspan> silently drops the
# surrounding characters in both renderers.
cat > /tmp/pb-mark.svg <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300">
  <defs>
    <linearGradient id="gold" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#ffd070"/>
      <stop offset="60%" stop-color="#f2b544"/>
      <stop offset="100%" stop-color="#e08a2c"/>
    </linearGradient>
    <linearGradient id="coral" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#ff6b78"/>
      <stop offset="100%" stop-color="#e94756"/>
    </linearGradient>
  </defs>
  <circle cx="130" cy="130" r="98" fill="none" stroke="url(#gold)" stroke-width="24"/>
  <path d="M32 130h196" stroke="#f2b544" stroke-width="24" opacity=".45" stroke-linecap="round"/>
  <path d="M130 32v196" stroke="#f2b544" stroke-width="24" stroke-linecap="round"/>
  <rect x="168" y="168" width="108" height="108" rx="29" fill="url(#coral)"/>
  <circle cx="199" cy="203" r="13" fill="#fff" opacity=".92"/>
  <circle cx="245" cy="203" r="13" fill="#fff" opacity=".92"/>
  <circle cx="199" cy="242" r="13" fill="#fff" opacity=".55"/>
  <circle cx="245" cy="242" r="13" fill="#fff" opacity=".55"/>
</svg>
SVG

FONT="${PB_FONT:-/usr/share/fonts/liberation/LiberationSans-Bold.ttf}"
[ -f "$FONT" ] || FONT="$(fc-match -f '%{file}' 'Liberation Sans:bold')"

rsvg-convert -w 300 -h 300 /tmp/pb-mark.svg -o /tmp/pb-mark.png

word() {  # word <text> <pointsize> <fill> -> prints the pixel width
  magick -font "$FONT" -pointsize "$2" -background none -fill "$3" \
    label:"$1" -format '%w' info:
}

# Compose the wordmark onto a transparent canvas.
W=1280; H=360
PS=112
W_POK=$(word "Pok" "$PS" white)
W_E=$(word "é" "$PS" "#f2b544")
W_BONK=$(word "Bonk" "$PS" white)
X0=330
X_E=$((X0 + W_POK))
X_BONK=$((X_E + W_E))

magick -size ${W}x${H} xc:none \
  /tmp/pb-mark.png -geometry +30+30 -composite \
  \( -size ${W}x${H} xc:none -font "$FONT" -pointsize $PS -background none -fill white \
     -gravity NorthWest -annotate +${X0}+150 "Pok" \) -compose over -composite \
  \( -size ${W}x${H} xc:none -font "$FONT" -pointsize $PS -background none -fill "#f2b544" \
     -gravity NorthWest -annotate +${X_E}+150 "é" \) -compose over -composite \
  \( -size ${W}x${H} xc:none -font "$FONT" -pointsize $PS -background none -fill white \
     -gravity NorthWest -annotate +${X_BONK}+150 "Bonk" \) -compose over -composite \
  \( -size ${W}x${H} xc:none -font "$FONT" -pointsize 62 -background none -fill "#f2b544" \
     -gravity NorthWest -kerning 12 -annotate +${X0}+262 "DECK" \) -compose over -composite \
  \( -size 330x8 xc:"#e94756" \) -geometry +${X0}+300 -compose over -composite \
  "$OUT/logo.png"

say "logo.png $(magick identify -format '%wx%h' "$OUT/logo.png")"

# --- the wide banner ---------------------------------------------------------
# Full-bleed gameplay, darkened, with the wordmark sitting on it.
make_banner() {
  local size="$1" out="$2" wordmark_w="$3" pad_x="$4" pad_y="$5"
  local W H
  W="${size%x*}"
  H="${size#*x}"

  # Scale and crop the gameplay to fill, then darken it so the text reads.
  magick "$BG" -resize "${W}x${H}^" -gravity center -extent "${W}x${H}" \
    -blur 0x1 \
    \( +clone -fill '#0b0816' -colorize 62% \) -compose over -composite \
    "$OUT/.bg.png"

  # Wordmark, scaled to the banner.
  magick "$OUT/logo.png" -resize "${wordmark_w}x" "$OUT/.wm.png"

  # A soft gradient from the left so the wordmark has room.
  local grad_w=$((W / 2))
  magick -size "${grad_w}x${H}" gradient:'#0b0816ee-#0b081600' "$OUT/.grad.png"

  magick "$OUT/.bg.png" \
    "$OUT/.grad.png" -geometry +0+0 -compose over -composite \
    \( "$OUT/.wm.png" -geometry "+${pad_x}+${pad_y}" \) -compose over -composite \
    -quality 92 "$OUT/$out"

  rm -f "$OUT/.bg.png" "$OUT/.wm.png" "$OUT/.grad.png"
  say "$out $(magick identify -format '%wx%h' "$OUT/$out")"
}

make_banner "3840x1240" library_hero.jpg 1500 180 220
make_banner "1438x810"  library_capsule.jpg 760 90 120
make_banner "616x353"   capsule.jpg 380 34 60
make_banner "462x174"   capsulev5.jpg 300 24 40
make_banner "460x215"   header.jpg 300 24 44

# --- the icon ----------------------------------------------------------------
magick -background none "$OUT/logo.png" -resize 128x128 \
  -gravity center -extent 128x128 "$OUT/icon.png"
magick "$OUT/icon.png" -background '#1e1638' -alpha remove -alpha off "$OUT/icon.jpg"
say "icon 128x128"

say "artwork written to $OUT"
ls -la "$OUT"
