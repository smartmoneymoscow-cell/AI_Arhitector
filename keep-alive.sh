#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Keep-alive daemon для Render Free Tier.
# Пингует health endpoints каждые 10 минут, предотвращает cold start.
#
# Запуск:
#   chmod +x keep-alive.sh
#   nohup ./keep-alive.sh &
#
# Cron (альтернатива):
#   */10 * * * * /path/to/keep-alive.sh --once
# ═══════════════════════════════════════════════════════════════

GATEWAY="https://architect-gateway.onrender.com"
LLM="https://architect-llm-1s1j.onrender.com"
BLENDER="https://ai-arch-blender3d.onrender.com"

INTERVAL=600  # 10 минут

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

ping_service() {
    local name=$1
    local url=$2
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 15 "$url/health" 2>/dev/null)
    if [ "$status" = "200" ]; then
        log "✅ $name: alive (HTTP $status)"
        return 0
    else
        log "❌ $name: dead (HTTP $status)"
        return 1
    fi
}

do_round() {
    local ok=0 fail=0
    ping_service "Gateway"  "$GATEWAY"  && ((ok++)) || ((fail++))
    ping_service "LLM"      "$LLM"      && ((ok++)) || ((fail++))
    ping_service "Blender"  "$BLENDER"  && ((ok++)) || ((fail++))
    log "Round: $ok alive, $fail dead"
}

if [ "$1" = "--once" ]; then
    do_round
    exit 0
fi

log "Keep-alive started (interval: ${INTERVAL}s)"
while true; do
    do_round
    sleep $INTERVAL
done
