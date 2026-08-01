"""
⚠️  DEPRECATED — THIS FILE IS A MONOLIT AND MUST NOT BE USED IN PRODUCTION ⚠️

This file exists ONLY for local development convenience.
Production architecture is strictly microservice:

    Client → Nginx (:80) → Gateway (:8080) → LLM Service (:8081)
                                             → Blender Service (:8082)
           Redis (:6379)

Use `docker-compose up` for production.
This file will be REMOVED in v8.0.
"""

import sys
import os

print(
    "\n"
    "╔══════════════════════════════════════════════════════════════╗\n"
    "║  WARNING: server.py is a MONOLIT. DO NOT use in production. ║\n"
    "║  Use: docker-compose up --build                             ║\n"
    "║  Architecture: Nginx → Gateway → LLM / Blender services    ║\n"
    "║  This file will be REMOVED in v8.0.                         ║\n"
    "╚══════════════════════════════════════════════════════════════╝\n",
    file=sys.stderr,
)

# Exit immediately in production
if os.environ.get("ENV") == "production":
    print("FATAL: server.py cannot run in production. Use docker-compose.", file=sys.stderr)
    sys.exit(1)

# For local dev only — redirect to gateway
print("Starting local dev server (redirecting to gateway architecture)...", file=sys.stderr)
print("Run: docker-compose up --build", file=sys.stderr)
print("Or for quick dev: uvicorn gateway.app:app --port 8080", file=sys.stderr)
sys.exit(0)
