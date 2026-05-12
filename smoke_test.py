"""
Smoke Test Suite — OCR RAG Backend
Tests: root, /sor empty, /sor/fotograf corrupt, /agent/validate-document empty, proactive cooldown
"""
import time
import json
import struct
import zlib
import requests

API_BASE = "http://127.0.0.1:8000"
AGENT_BASE = "http://127.0.0.1:8001"

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"

results = []

def log_result(test_name: str, passed: bool, response_data, notes=""):
    status = PASS if passed else FAIL
    results.append((test_name, passed))
    print(f"\n{'='*60}")
    print(f"{status}  {test_name}")
    if notes:
        print(f"  NOTE: {notes}")
    print(f"  Response: {json.dumps(response_data, ensure_ascii=False, indent=2)[:600]}")


def make_minimal_png() -> bytes:
    """Creates a 1x1 white PNG — valid but contains no text for OCR."""
    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1 RGB
    idat_data = zlib.compress(b"\x00\xFF\xFF\xFF")  # filter=0, white pixel
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat_data)
        + chunk(b"IEND", b"")
    )


def wait_for_server(url: str, timeout=180, label="server"):
    """Polls url until 200 or timeout."""
    print(f"\nWaiting for {label} ({url})...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code < 500:
                print(f"  -> {label} ready ({time.time()-start:.1f}s)")
                return True
        except Exception:
            pass
        time.sleep(3)
    print(f"  -> {label} not ready after {timeout}s!")
    return False


# ─── Wait for both servers ────────────────────────────────────────────────────
api_ready   = wait_for_server(f"{API_BASE}/",    label="api.py (port 8000)")
agent_ready = wait_for_server(f"{AGENT_BASE}/docs", label="agent_api.py (port 8001)")

if not api_ready:
    print("[FAIL] api.py server did not start — aborting tests.")
    exit(1)

# ─── TEST 1: Root endpoint ────────────────────────────────────────────────────
print("\n\n" + "="*60)
print("TEST 1: GET / — Sunucu çalışıyor mu?")
try:
    r = requests.get(f"{API_BASE}/", timeout=10)
    passed = r.status_code == 200 and "message" in r.json()
    log_result("GET / (root ping)", passed, r.json(),
               f"HTTP {r.status_code}")
except Exception as e:
    log_result("GET / (root ping)", False, {"exception": str(e)})

# ─── TEST 2: /sor — empty question ───────────────────────────────────────────
print("\n\nTEST 2: POST /sor — Boş soru gönder")
try:
    r = requests.post(
        f"{API_BASE}/sor",
        json={"soru": ""},
        timeout=15
    )
    data = r.json()
    # Expect either structured {"cevap": "Geçersiz soru."} or {"error": true, ...}
    # Both are acceptable — not a 500 crash
    no_unhandled_crash = r.status_code != 500 or data.get("error") is True
    has_message = "cevap" in data or "message" in data or "error" in data
    passed = no_unhandled_crash and has_message
    log_result("POST /sor — boş soru", passed, data,
               f"HTTP {r.status_code} | error field: {data.get('error')} | cevap: {data.get('cevap','—')[:80]}")
except Exception as e:
    log_result("POST /sor — boş soru", False, {"exception": str(e)})

# ─── TEST 3: /sor/fotograf — 1x1 white PNG (no text) ────────────────────────
print("\n\nTEST 3: POST /sor/fotograf — Boş/bozuk görüntü")
try:
    png_bytes = make_minimal_png()
    r = requests.post(
        f"{API_BASE}/sor/fotograf",
        files={"file": ("test.png", png_bytes, "image/png")},
        data={"soru": "Bu belgede ne yazıyor?"},
        timeout=60
    )
    data = r.json()
    # Expect ocr_warning field (new structured output)
    has_warning_field = "ocr_warning" in data
    no_crash = r.status_code < 500 or data.get("error") is True
    passed = has_warning_field and no_crash
    log_result("POST /sor/fotograf — bozuk görüntü", passed, data,
               f"HTTP {r.status_code} | ocr_warning: {data.get('ocr_warning')} | ocr_confidence: {data.get('ocr_confidence')}")
except Exception as e:
    log_result("POST /sor/fotograf — bozuk görüntü", False, {"exception": str(e)})

# ─── TEST 4: /agent/validate-document — empty text ───────────────────────────
print("\n\nTEST 4: POST /agent/validate-document — Boş belge metni")
if not agent_ready:
    log_result("POST /agent/validate-document — boş metin", False,
               {"skipped": "agent_api.py başlamadı"})
else:
    try:
        r = requests.post(
            f"{AGENT_BASE}/agent/validate-document",
            json={"extracted_text": ""},
            timeout=30
        )
        data = r.json()
        # Expect graceful: error field or validation_results = {}, not a raw 500 crash
        graceful = (
            data.get("error") is True
            or "validation_results" in data
            or (r.status_code == 500 and isinstance(data.get("message"), str))
        )
        passed = graceful
        log_result("POST /agent/validate-document — boş metin", passed, data,
                   f"HTTP {r.status_code} | graceful: {graceful}")
    except Exception as e:
        log_result("POST /agent/validate-document — boş metin", False, {"exception": str(e)})

# ─── TEST 5: Proactive agent cooldown ────────────────────────────────────────
print("\n\nTEST 5: POST /agent/proactive-search — Cooldown testi (2 çağrı < 10s)")
if not agent_ready:
    log_result("Proactive cooldown", False, {"skipped": "agent_api.py başlamadı"})
else:
    TOPIC = "KPSS 2026 sınav tarihleri"
    payload = {"sohbet_gecmisi": [f"Yakında {TOPIC} açıklanacak diye duydum."]}

    try:
        print(f"  >> 1st call starting (topic: '{TOPIC}')...")
        t0 = time.time()
        r1 = requests.post(f"{AGENT_BASE}/agent/proactive-search", json=payload, timeout=60)
        d1 = r1.json()
        elapsed1 = time.time() - t0
        print(f"  >> 1st call done ({elapsed1:.1f}s)")

        print(f"  >> 2nd call immediately (cooldown expected)...")
        t1 = time.time()
        r2 = requests.post(f"{AGENT_BASE}/agent/proactive-search", json=payload, timeout=60)
        d2 = r2.json()
        elapsed2 = time.time() - t1
        print(f"  >> 2nd call done ({elapsed2:.1f}s)")

        # Cooldown aktifse: 2. çağrıda arama_sonuclari boş olmalı
        first_had_results = bool(d1.get("arama_sonuclari"))
        second_empty = not d2.get("arama_sonuclari")
        cooldown_worked = second_empty

        log_result(
            "Proactive cooldown",
            cooldown_worked,
            {"call1_results_count": len(d1.get("arama_sonuclari", {})),
             "call2_results_count": len(d2.get("arama_sonuclari", {})),
             "call1_error": d1.get("error"),
             "call2_error": d2.get("error")},
            f"1st call had results: {first_had_results} | 2nd call empty (cooldown): {second_empty}"
        )
    except Exception as e:
        log_result("Proactive cooldown", False, {"exception": str(e)})

# ─── SUMMARY ─────────────────────────────────────────────────────────────────
print("\nSMOKE TEST RESULTS")
print("="*60)
passed_count = sum(1 for _, p in results if p)
for name, passed in results:
    icon = "[PASS]" if passed else "[FAIL]"
    print(f"  {icon}  {name}")
print(f"\n  Total: {passed_count}/{len(results)} passed")
print("="*60)

if passed_count < len(results):
    exit(1)
