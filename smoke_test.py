"""
Smoke Test Suite — OCR RAG Backend (Merged Single Server on Port 8000)
Tests: 
1. GET / (root ping)
2. POST /sor (empty question)
3. POST /sor/fotograf (corrupt image)
4. POST /agent/validate-document (empty text graceful failure)
5. POST /agent/validate-document (valid Turkish contract positive test)
6. POST /agent/proactive-search (LangGraph active search verification)
7. POST /agent/proactive-search (cooldown verification)
"""
import time
import json
import struct
import zlib
import requests

API_BASE = "http://127.0.0.1:8000"

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
    try:
        resp_str = json.dumps(response_data, ensure_ascii=False, indent=2)
    except Exception:
        resp_str = str(response_data)
    print(f"  Response: {resp_str[:800]}")


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


# ─── Wait for merged server on Port 8000 ──────────────────────────────────────
server_ready = wait_for_server(f"{API_BASE}/", label="api.py (port 8000)")

if not server_ready:
    print("[FAIL] api.py server on port 8000 did not start — aborting tests.")
    exit(1)

# ─── TEST 1: Root endpoint ────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 1: GET / — Sunucu calisiyor mu?")
try:
    r = requests.get(f"{API_BASE}/", timeout=10)
    passed = r.status_code == 200 and "message" in r.json()
    log_result("GET / (root ping)", passed, r.json(), f"HTTP {r.status_code}")
except Exception as e:
    log_result("GET / (root ping)", False, {"exception": str(e)})

# ─── TEST 2: /sor — empty question ────────────────────────────────────────────
print("\nTEST 2: POST /sor — Bos soru gonder")
try:
    r = requests.post(f"{API_BASE}/sor", json={"soru": ""}, timeout=15)
    data = r.json()
    no_unhandled_crash = r.status_code != 500 or data.get("error") is True
    has_message = "cevap" in data or "message" in data or "error" in data
    passed = no_unhandled_crash and has_message
    log_result("POST /sor — bos soru", passed, data, f"HTTP {r.status_code}")
except Exception as e:
    log_result("POST /sor — bos soru", False, {"exception": str(e)})

# ─── TEST 3: /sor/fotograf — minimal image (no text) ──────────────────────────
print("\nTEST 3: POST /sor/fotograf — Bos/bozuk goruntu")
try:
    png_bytes = make_minimal_png()
    r = requests.post(
        f"{API_BASE}/sor/fotograf",
        files={"file": ("test.png", png_bytes, "image/png")},
        data={"soru": "Bu belgede ne yaziyor?"},
        timeout=60
    )
    data = r.json()
    has_warning_field = "ocr_warning" in data
    no_crash = r.status_code < 500 or data.get("error") is True
    passed = has_warning_field and no_crash
    log_result("POST /sor/fotograf — bozuk goruntu", passed, data, f"HTTP {r.status_code}")
except Exception as e:
    log_result("POST /sor/fotograf — bozuk goruntu", False, {"exception": str(e)})

# ─── TEST 4: /agent/validate-document — empty text graceful failure ───────────
print("\nTEST 4: POST /agent/validate-document — Bos belge metni")
try:
    r = requests.post(f"{API_BASE}/agent/validate-document", json={"extracted_text": ""}, timeout=30)
    data = r.json()
    graceful = (
        data.get("error") is True
        or "validation_results" in data
        or (r.status_code == 500 and isinstance(data.get("message"), str))
    )
    log_result("POST /agent/validate-document — bos metin", graceful, data, f"HTTP {r.status_code}")
except Exception as e:
    log_result("POST /agent/validate-document — bos metin", False, {"exception": str(e)})

# ─── TEST 5: /agent/validate-document — positive Turkish contract test ────────
print("\nTEST 5: POST /agent/validate-document — Kisa Turkce sozlesme metni (Positive Test)")
contract_text = """
KIRA SOZLESMESI
Taraflar: Kiraya Veren Ahmet Yilmaz ile Kiraci Mehmet Demir arasinda asagidaki sartlarla anlasilmistir.
Kiralanan Tasinmazin Adresi: Ataturk Cad. No:10 Kadikoy/Istanbul
Kira Bedeli: Aylik 25.000 TL.
Sozlesme Baslangic Tarihi: 01.01.2026
Imzalar: Ahmet Yilmaz, Mehmet Demir
"""
try:
    r = requests.post(f"{API_BASE}/agent/validate-document", json={"extracted_text": contract_text.strip()}, timeout=45)
    data = r.json()
    # Confirm structured response success
    passed = r.status_code == 200 and data.get("success") is True and "validation_results" in data
    log_result("POST /agent/validate-document — gecerli sozlesme", passed, data, f"HTTP {r.status_code}")
except Exception as e:
    log_result("POST /agent/validate-document — gecerli sozlesme", False, {"exception": str(e)})

# ─── TEST 6: /agent/proactive-search — positive LangGraph version test ────────
print("\nTEST 6: POST /agent/proactive-search — LangGraph versiyonu dogrulama (Positive Test)")
chat_history = [
    "Merhabalar, TUBITAK 1512 girisimcilik destek programina basvurmayi dusunuyorum.",
    "Bununla ilgili basvuru tarihlerini ve sartlarini arastirabilir misiniz?"
]
try:
    print("  >> Calling proactive search agent (LangGraph version)...")
    t0 = time.time()
    r = requests.post(f"{API_BASE}/agent/proactive-search", json={"sohbet_gecmisi": chat_history}, timeout=90)
    data = r.json()
    elapsed = time.time() - t0
    # Confirm LangGraph version structure: success, ilgi_alanlari, arama_sonuclari
    is_langgraph = "ilgi_alanlari" in data and "arama_sonuclari" in data and "bulunanlar" not in data
    passed = r.status_code == 200 and is_langgraph
    log_result(
        "POST /agent/proactive-search — LangGraph yapisi",
        passed,
        data,
        f"HTTP {r.status_code} | {elapsed:.1f}s | is_langgraph: {is_langgraph}"
    )
except Exception as e:
    log_result("POST /agent/proactive-search — LangGraph yapisi", False, {"exception": str(e)})

# ─── TEST 7: Proactive agent cooldown verification ────────────────────────────
print("\nTEST 7: POST /agent/proactive-search — Cooldown testi (Ayni konu pes pese)")
TOPIC = "Gunes enerjisi paneli hibeleri 2026"
payload = {"sohbet_gecmisi": [f"Sirketimiz icin {TOPIC} hakkinda bilgi ariyorum."]}
try:
    print(f"  >> 1st call starting (topic: '{TOPIC}')...")
    t0 = time.time()
    r1 = requests.post(f"{API_BASE}/agent/proactive-search", json=payload, timeout=60)
    d1 = r1.json()
    elapsed1 = time.time() - t0
    print(f"  >> 1st call done ({elapsed1:.1f}s)")

    print(f"  >> 2nd call immediately (cooldown expected)...")
    t1 = time.time()
    r2 = requests.post(f"{API_BASE}/agent/proactive-search", json=payload, timeout=60)
    d2 = r2.json()
    elapsed2 = time.time() - t1
    print(f"  >> 2nd call done ({elapsed2:.1f}s)")

    # Cooldown verification: second call should have empty search results because it hits the cache
    first_results = d1.get("arama_sonuclari", {})
    second_results = d2.get("arama_sonuclari", {})
    second_empty = len(second_results) == 0
    passed = second_empty

    log_result(
        "Proactive cooldown",
        passed,
        {
            "call1_results_count": len(first_results),
            "call2_results_count": len(second_results),
            "call1_error": d1.get("error"),
            "call2_error": d2.get("error")
        },
        f"2nd call empty (cooldown active): {second_empty}"
    )
except Exception as e:
    log_result("Proactive cooldown", False, {"exception": str(e)})

# ─── SUMMARY ──────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("SMOKE TEST RESULTS (PORT 8000 ONLY)")
print("="*60)
passed_count = sum(1 for _, p in results if p)
for name, passed in results:
    icon = "[PASS]" if passed else "[FAIL]"
    print(f"  {icon}  {name}")
print(f"\n  Total: {passed_count}/{len(results)} passed")
print("="*60)

if passed_count < len(results):
    exit(1)
