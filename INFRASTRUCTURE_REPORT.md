# Architect AI — Full Infrastructure Report

**Date:** 2026-08-12 07:55 (Asia/Shanghai)

---

## Summary: 8 LLM instances + 11 support services = 19 LIVE ✅

| Account | LLM | Gateway | Blender | Data/DB | Other | Total |
|---------|:---:|:-------:|:-------:|:-------:|:-----:|:-----:|
| #1 smart.money.moscow | ✅ | — | — | — | — | 1 |
| #2 xhungerrr | ✅ | — | ✅ | 6 | — | 8 |
| #3 rrrhunger | ✅ | — | — | — | — | 1 |
| #4 fdegegvf | ✅ | ✅ | ✅ | — | — | 3 |
| #5 k25334003 | ✅ | — | — | — | — | 1 |
| #6 ror577282 | ✅ | — | — | — | — | 1 |
| #7 argo7075 | ✅ | — | — | — | 1 | 2 |
| #8 vietnamsk064 | ✅ | — | — | — | — | 1 |
| **Total** | **8** | **1** | **2** | **6** | **1** | **18** |

---

## Account #1 (smart.money.moscow@gmail.com)

| Service | Deploy | Health | URL |
|---------|:------:|:------:|-----|
| architect-llm | ✅ live | ✅ | architect-llm-s5q7.onrender.com |

---

## Account #2 (xhungerrr@gmail.com) — 11 Services

| Service | Deploy | Health | URL |
|---------|:------:|:------:|-----|
| architect-graphdb | ✅ live | ✅ | architect-graphdb.onrender.com |
| architect-vectordb | ✅ live | ✅ | architect-vectordb.onrender.com |
| architect-freecad | ✅ live | ✅ | architect-freecad.onrender.com |
| architect-cad | ✅ live | ✅ | architect-cad.onrender.com |
| architect-data | ✅ live | ✅ | architect-data.onrender.com |
| architect-ifc | ✅ live | ✅ | architect-ifc.onrender.com |
| ai-arch-blender3d | ✅ live | ✅ | ai-arch-blender3d.onrender.com |
| ai-arch-llmproxy | ✅ live | ✅ | ai-arch-llmproxy.onrender.com |
| architect-ml | update_failed | — | — |
| architect-geometry | build_failed | — | — |
| architect | update_failed | — | — |

---

## Account #3 (rrrhunger@gmail.com)

| Service | Deploy | Health | URL |
|---------|:------:|:------:|-----|
| architect-llm | ✅ live | ✅ | architect-llm-zczl.onrender.com |

---

## Account #4 (fdegegvf@gmail.com) — Gateway + LLM + Blender

| Service | Deploy | Health | Version | URL |
|---------|:------:|:------:|:-------:|-----|
| architect-gateway | ✅ live | ✅ | v8.2.0 | architect-gateway.onrender.com |
| architect-llm | ✅ live | ✅ | v8.0.0 | architect-llm-1s1j.onrender.com |
| architect-blender | ✅ live | ✅ | v6.0.0 | architect-blender.onrender.com |

---

## Account #5 (k25334003@gmail.com)

| Service | Deploy | Health | URL |
|---------|:------:|:------:|-----|
| architect-llm | ✅ live | ✅ | architect-llm-2pmo.onrender.com |

---

## Account #6 (ror577282@gmail.com)

| Service | Deploy | Health | URL |
|---------|:------:|:------:|-----|
| architect-llm | ✅ live | ✅ | architect-llm-5mdk.onrender.com |

---

## Account #7 (argo7075@gmail.com)

| Service | Deploy | Health | URL |
|---------|:------:|:------:|-----|
| architect-llm | ✅ live | ✅ | architect-llm-sdrh.onrender.com |
| chat-monitor-bot | ✅ live | — | youdo-photo.onrender.com (other project) |

---

## Account #8 (vietnamsk064@gmail.com)

| Service | Deploy | Health | URL |
|---------|:------:|:------:|-----|
| architect-llm | ✅ live | ✅ | architect-llm-qarj.onrender.com |

---

## OpenRouter Keys — 8 Accounts, 400 requests/day

| # | Key suffix | Primary on | Status |
|---|-----------|------------|:------:|
| 1 | …88f4 | Acc1 | ✅ alive |
| 2 | …09d3 | Acc2 | ✅ alive |
| 3 | …8ef8 | Acc3 | ✅ alive |
| 4 | …9396 | Acc4 | ✅ alive |
| 5 | …836d | Acc5 | ✅ alive |
| 6 | …4437 | Acc6 | ✅ alive |
| 7 | …00ab | Acc7 | ✅ alive |
| 8 | …43a9 | Acc8 | ✅ alive |

**Each service has ALL 8 keys** (1 primary + 7 fallback). Cascade switching on 429/402.

---

## Google Gemini Keys — 8 Accounts

| # | Key suffix | Primary on |
|---|-----------|------------|
| 1 | …oNWQ | Acc1 |
| 2 | …dBhA | Acc2 |
| 3 | …LHPQ | Acc3 |
| 4 | …ODWw | Acc4 |
| 5 | …akRg | Acc5 |
| 6 | …gPBQ | Acc6 |
| 7 | …FUrw | Acc7 |
| 8 | …KroA | Acc8 |

---

## Key Rotation Logic

```
Request → _get_api_keys() → [primary] + [7 fallbacks]
    ↓
_filter_alive() → skip keys on cooldown
    ↓
Try key → OpenRouter API
    ↓
429 (rate limit) → cooldown 60s → next key
402 (quota)      → cooldown 24h → next key
200 (ok)         → return response
    ↓
All keys exhausted → HTTP 503
```

Cooldown persists in Redis (survives container restarts).

---

## LLM Parse Test ✅

```
"дом 2 этажа кирпич 10x12"
→ object_type: building, floors: 2, material: brick
```
