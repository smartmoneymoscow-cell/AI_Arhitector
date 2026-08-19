"""
Keep-Alive daemon для Render free tier.
Пингует все сервисы каждые 10 минут, чтобы не засыпали.

Запуск: python3 keep-alive-daemon.py
Или через cron: */10 * * * * python3 /path/to/keep-alive-daemon.py --once
"""

import urllib.request
import json
import time
import sys
import os
from datetime import datetime

SERVICES = [
    {"name": "Gateway",  "url": "https://architect-gateway-3guo.onrender.com/health"},
    {"name": "LLM",      "url": "https://architect-llm-1s1j.onrender.com/health"},
    {"name": "Blender1", "url": "https://ai-arch-blender3d.onrender.com/health"},
    {"name": "Blender2", "url": "https://architect-blender.onrender.com/health"},
]

INTERVAL = 600  # 10 минут
TIMEOUT = 30

def ping_services():
    results = []
    ts = datetime.now().strftime("%H:%M:%S")
    for svc in SERVICES:
        try:
            req = urllib.request.Request(svc["url"], headers={"User-Agent": "keep-alive/1.0"})
            resp = urllib.request.urlopen(req, timeout=TIMEOUT)
            data = json.loads(resp.read())
            status = data.get("status", "unknown")
            results.append(f"  ✅ {svc['name']}: {status}")
        except Exception as e:
            results.append(f"  ❌ {svc['name']}: {str(e)[:50]}")
    
    log = f"[{ts}] Ping {len(SERVICES)} services:\n" + "\n".join(results)
    print(log)
    return log

def main():
    if "--once" in sys.argv:
        ping_services()
        return

    print(f"Keep-alive daemon started. Interval: {INTERVAL}s")
    print(f"Services: {len(SERVICES)}")
    print("Press Ctrl+C to stop\n")
    
    while True:
        try:
            ping_services()
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            print("\nStopped.")
            break

if __name__ == "__main__":
    main()
