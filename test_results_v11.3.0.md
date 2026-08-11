# Architect AI — Test Results v11.3.0

**Date:** 2026-08-11 08:46 (Asia/Shanghai)  
**Tester:** QA Subagent  

---

## 1. Health Checks

| Service | URL | HTTP Status | Response |
|---------|-----|:-----------:|----------|
| Gateway | architect-gateway.onrender.com | ✅ 200 | `{"status":"ok","service":"gateway","version":"8.2.0","services":{"llm":"configured","blender":"configured"},"redis":"not_configured","blender_instances":1,"circuit_breakers":{"llm":{"failures":0,"is_open":false}}}` |
| LLM | architect-llm-1s1j.onrender.com | ✅ 200 | `{"status":"ok","service":"llm-service","version":"8.0.0","model":"google/gemini-2.0-flash-lite-001:free","services":{"gemini":"configured"}}` |
| Blender1 | ai-arch-blender3d.onrender.com | ✅ 200 | `{"status":"ok","service":"blender-service","version":"6.0.0"}` |
| Blender2 | architect-blender.onrender.com | ✅ 200 | `{"blender":"blender","service":"blender-service","status":"ok"}` |

---

## 2. Gateway Main Page (HTML)

| Check | Result |
|-------|:------:|
| HTTP Status | ✅ 200 |
| Content-Type | text/html; charset=utf-8 |
| `sendMessage` element | ✅ Found (4 occurrences) |
| `sendBtn` element | ✅ Found (5 occurrences) |
| Three.js (three@0.147.0) | ✅ Found (CDN: cdn.jsdelivr.net/npm/three@0.147.0) |
| GLTFLoader | ✅ Found (3 occurrences) |

**Page title:** Architect — AI Architecture Generator  
**Language:** ru (with EN toggle)  
**Theme:** Dark (default) + Light toggle  

---

## 3. POST /api/v1/parse

| Field | Value |
|-------|-------|
| **Endpoint** | `POST /api/v1/parse` |
| **Auth** | `X-API-Key: arch-prod-key-2024` |
| **Request Body** | `{"text":"дом 2 этажа кирпич 10x12"}` |
| **HTTP Status** | ✅ 200 OK |
| **Response Time** | < 5s |

**Response:**
```json
{
  "object_type": "building",
  "building_type": "house",
  "room_type": null,
  "floors": 2,
  "width_m": 10.0,
  "length_m": 12.0,
  "height_m": 6.5,
  "style": "classic",
  "material": "brick",
  "roof_type": "gable",
  "features": ["двухэтажный", "кирпичные стены", "двери и окна"],
  "furniture": []
}
```

---

## 4. POST /api/v1/orchestrator/execute

| Field | Value |
|-------|-------|
| **Endpoint** | `POST /api/v1/orchestrator/execute` |
| **Auth** | `X-API-Key: arch-prod-key-2024` |
| **Request Body** | `{"prompt":"дом 2 этажа","quality":"quick","skip_clarification":true,"export_formats":["glb"],"pipeline_profile":"quick"}` |
| **HTTP Status** | ⏱️ Timeout (>60s) |
| **Exit Code** | curl exit 28 (operation timeout) |

**Notes:** Orchestrator execution exceeded 60-second timeout. This may be expected for a full generation pipeline (parse → geometry → materials → render). The service was not confirmed to return an error — it simply did not complete within the timeout window. Recommend testing with a longer timeout or checking server logs.

---

## 5. GET /api/v1/keys/status

| Field | Value |
|-------|-------|
| **Endpoint** | `GET /api/v1/keys/status` |
| **Auth** | `X-API-Key: arch-prod-key-2024` |
| **HTTP Status** | ⚠️ 200 |
| **Content-Type** | text/html; charset=utf-8 |
| **Response Size** | 96,501 bytes |

**Issue:** Endpoint returns the SPA frontend HTML instead of a JSON API response. This indicates either:
- The `/api/v1/keys/status` route is not implemented on the gateway
- The SPA catch-all route is intercepting the request before it reaches the API handler
- The endpoint requires a different HTTP method or path

---

## Summary

| Test | Status | Notes |
|------|:------:|-------|
| Gateway Health | ✅ OK | v8.2.0, LLM + Blender configured |
| LLM Health | ✅ OK | v8.0.0, Gemini Flash Lite |
| Blender1 Health | ✅ OK | v6.0.0 |
| Blender2 Health | ✅ OK | No version info |
| Main Page HTML | ✅ OK | All required elements present |
| POST /parse | ✅ OK | Correctly parsed building params |
| POST /orchestrator/execute | ⏱️ Timeout | >60s, may need longer timeout |
| GET /keys/status | ⚠️ Broken | Returns SPA HTML, not JSON |

**Overall: 6/8 passed, 1 timeout, 1 broken endpoint**
