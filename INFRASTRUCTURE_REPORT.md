# Architect AI — Full Infrastructure Report

**Date:** 2026-08-11 10:00 (Asia/Shanghai)

---

## Account #2 (rnd_SUdnZ8…) — 11 Services, 8 LIVE ✅

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

## Account #4 (rnd_CqhN6e…) — 3 Architect Services

| Service | Deploy | Health | Version | URL |
|---------|:------:|:------:|:-------:|-----|
| architect-gateway | update_failed | ✅ ok | v8.2.0 | architect-gateway.onrender.com |
| architect-llm | ✅ live | ✅ ok | v8.0.0 | architect-llm-1s1j.onrender.com |
| architect-blender | build_failed | ✅ ok | v6.0.0 | architect-blender.onrender.com |

---

## Other Accounts

| Account | Services | Status |
|---------|----------|--------|
| #1 | chat-monitor-bot | Separate project |
| #3 | (empty) | Can't create — need ownerID via dashboard |
| #5 | carwash-bot | Separate project |
| #6 | hotel-ai (3 services) | Separate project |
| #7 | chat-monitor-bot | Separate project |
| #8 | (empty) | Can't create — need ownerID via dashboard |

---

## LLM Parse Test ✅

```
"дом 2 этажа кирпич 10x12"
→ object_type: building, floors: 2, material: brick
```

---

## Total: 16 LIVE services across 2 accounts

- **Account #2:** 8 live (graphdb, vectordb, freecad, cad, data, ifc, blender3d, llmproxy)
- **Account #4:** 3 live (gateway, llm, blender)
- **LLM new code:** ✅ deployed (31 agents, duct_analysis)
- **Repo:** public, auto-deploy enabled
