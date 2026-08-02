#!/usr/bin/env python3
"""Keep-alive daemon for Render free tier services.
Pings all services every 10 minutes to prevent cold starts.
Run: python3 keep-alive-daemon.py
"""
import subprocess
import time
import os
import sys

LOG = os.path.join(os.path.dirname(__file__), 'keep-alive.log')
SERVICES = [
    'https://architect-gateway.onrender.com/health',
    'https://ai-arch-blender3d.onrender.com/health',
    'https://architect-blender.onrender.com/health',
    'https://architect-llm-1s1j.onrender.com/health',
]
INTERVAL = 600  # 10 minutes

def ping_all():
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    results = []
    for url in SERVICES:
        name = url.split('//')[1].split('.onrender')[0]
        try:
            r = subprocess.run(
                ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                 '--connect-timeout', '15', '--max-time', '30', url],
                capture_output=True, text=True, timeout=45
            )
            code = r.stdout.strip()
            status = '✅' if code == '200' else '❌'
            results.append(f'[{ts}] {status} {name} ({code})')
        except Exception as e:
            results.append(f'[{ts}] ❌ {name} (error: {e})')
    
    # Write to log
    with open(LOG, 'a') as f:
        f.write(f'[{ts}] Keep-alive ping...\n')
        for r in results:
            f.write(r + '\n')
    
    # Trim log
    try:
        with open(LOG) as f:
            lines = f.readlines()
        if len(lines) > 500:
            with open(LOG, 'w') as f:
                f.writelines(lines[-500:])
    except:
        pass
    
    # Print to stdout
    print(f'[{ts}] Keep-alive: {sum(1 for r in results if "✅" in r)}/{len(results)} services up')
    sys.stdout.flush()

if __name__ == '__main__':
    print(f'Starting keep-alive daemon (interval: {INTERVAL}s)')
    while True:
        try:
            ping_all()
        except Exception as e:
            print(f'Error: {e}')
        time.sleep(INTERVAL)
