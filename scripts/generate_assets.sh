#!/bin/bash
# Generate CLIPZIDA pipeline assets (music bed, SFX, meme overlays)
set -e

ASSETS_DIR="/Users/mohamedalsayed/clipping_tools/assets"
MUSIC_DIR="$ASSETS_DIR/audio"
MEME_DIR="$ASSETS_DIR/memes"

mkdir -p "$MUSIC_DIR" "$MEME_DIR"

echo "=== Generating music bed (simple synth loop) ==="
ffmpeg -y -f lavfi -i "aevalsrc=0.3*sin(220*t)+0.15*sin(440*t)+0.1*sin(660*t):d=30" -ar 44100 \
  -c:a libmp3lame -b:a 128k "$MUSIC_DIR/music_bed.mp3" 2>&1 | tail -3

echo "=== Generating SFX: boom ==="
ffmpeg -y -f lavfi -i "aevalsrc=0.8*sin(80*t)*exp(-t*4):d=1.5" -ar 44100 \
  -c:a libmp3lame -b:a 128k "$MUSIC_DIR/boom.mp3" 2>&1 | tail -3

echo "=== Generating meme overlay: reaction.png ==="
ffmpeg -y -f lavfi -i "color=c=red:s=300x300:d=1" \
  -vf "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='REACT':fontsize=60:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" \
  -frames:v 1 "$MEME_DIR/reaction.png" 2>&1 | tail -3

echo "=== Assets generated ==="
ls -la "$MUSIC_DIR/" "$MEME_DIR/"
