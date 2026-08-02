#!/bin/bash
# keep-alive.sh — Ping Render services every 10 min to prevent cold starts
# Render free tier sleeps after 15 min of no requests

SERVICES=(
  "https://architect-gateway.onrender.com/health"
  "https://ai-arch-blender3d.onrender.com/health"
  "https://architect-blender.onrender.com/health"
  "https://architect-llm-1s1j.onrender.com/health"
)

LOG="/home/work/.openclaw/workspace/AI_Arhitector/keep-alive.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] Keep-alive ping..." >> "$LOG"

for url in "${SERVICES[@]}"; do
  name=$(echo "$url" | sed 's|https://||;s|\.onrender\.com.*||')
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 15 --max-time 30 "$url" 2>&1)
  if [ "$code" = "200" ]; then
    echo "[$TIMESTAMP] ✅ $name" >> "$LOG"
  else
    echo "[$TIMESTAMP] ❌ $name ($code)" >> "$LOG"
  fi
done

# Keep log last 500 lines
tail -500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
