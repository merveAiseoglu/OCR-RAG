import os
import sys
from dotenv import load_dotenv

# .env dosyasını en başta yüklüyoruz
load_dotenv()

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union, cast
import logging
import json
import re
import io
import uuid
import numpy as np
import cv2
import datetime
import math
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# --- AGENT ---
from agent.web_searcher import WebSearcher
from agent.task_extractor import TaskExtractor, CikartmaSonucu
from agent.graph_builder import graph_invoke_with_timeout, AgentState
from agent.proactive_graph import graph as proactive_graph, ProactiveState
from agent.cross_document_auditor import auditor_app
from agent.missing_info_agent import validator_app

# --- OPENAI ENTEGRASYONU ---
from openai import OpenAI, RateLimitError, AuthenticationError, APITimeoutError

# --- DİĞER KÜTÜPHANELER ---
import aiofiles
import easyocr
import chromadb
from chromadb.config import Settings
from chromadb import Documents, EmbeddingFunction, Embeddings
from sentence_transformers import SentenceTransformer
import fitz  # PyMuPDF
from PIL import Image

# --- ORTAM DEĞİŞKENLERİ ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("⚠️ UYARI: OPENAI_API_KEY bulunamadı! .env dosyanızı kontrol edin.")
    client = None
else:
    client = OpenAI(api_key=OPENAI_API_KEY)

# --- LOGLAMA ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s — %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("OCR_API")

# --- EMBEDDING ---
class MyEmbeddingFunction(EmbeddingFunction):
    def __init__(self, model):
        self.model = model

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = self.model.encode(input, convert_to_numpy=True)
        return embeddings.tolist()

def metadata_temizle(metadata: dict) -> dict:
    if not metadata: return {}
    temiz = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)) and value is not None:
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)): continue
            if isinstance(value, str) and not value.strip(): continue
            temiz[key] = value
    return temiz

# --- GLOBAL STATE ---
class AppState:
    def __init__(self):
        self.ocr_reader = None
        self.embedding_model = None
        self.chroma_client = None
        self.collection = None
        self.documents_folder = "documents"
        self.db_path = "./chroma_db_store"

state = AppState()

app = FastAPI(
    title="OCR RAG API",
    version="4.0",
    description="OCR + RAG + LangGraph Agent — Tek sunucu (port 8000)"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Global Exception Handler ────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Yakalanmamış hata [{request.method} {request.url}]: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": True, "message": str(exc), "code": 500}
    )

## mobilden gelen ping istekleri için endpoint --
@app.get("/")
def read_root():
    return {"message": "Server is running"}

@app.on_event("startup")
async def startup_event():
    logger.info("🎬 SİSTEM BAŞLATILIYOR...")
    try:
        state.ocr_reader = easyocr.Reader(['tr', 'en'], gpu=False)
        logger.info("✅ EasyOCR yüklendi.")
    except Exception as e:
        logger.critical(f"EasyOCR yüklenemedi: {e}")
        sys.exit(1)

    try:
        state.embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        logger.info("✅ Embedding modeli yüklendi.")
    except Exception as e:
        logger.critical(f"Embedding modeli yüklenemedi: {e}")
        sys.exit(1)

    try:
        state.chroma_client = chromadb.PersistentClient(path=state.db_path)
        state.collection = state.chroma_client.get_or_create_collection(
            name="hukuk_dokumanlari",
            embedding_function=MyEmbeddingFunction(state.embedding_model),
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"✅ SİSTEM HAZIR. Koleksiyondaki belge sayısı: {state.collection.count()}")
    except Exception as e:
        logger.critical(f"ChromaDB başlatılamadı: {e} — Sunucu kapatılıyor.")
        sys.exit(1)

# ==========================================
# 1. OCR GÖRÜNTÜ İŞLEME MANTIĞI (Senin Kodun)
# ==========================================
def goruntu_isleyerek_oku(image_bytes) -> dict:
    """
    ocr_engine.py'deki mantığı kullanarak görüntüyü okur.
    Returns: {"text": str, "confidence": float, "warning": str|None}
    """
    from ocr_engine import ocr_ile_oku as _ocr_ile_oku
    logger.info("Görüntü OCR işlemi başlatılıyor (goruntu_isleyerek_oku).")
    try:
        result = _ocr_ile_oku(image_bytes)
        logger.info(f"OCR tamamlandı — güven: {result.get('confidence', 0):.2f}, uyarı: {result.get('warning')}")
        return result
    except Exception as e:
        logger.error(f"OCR İşleme Hatası: {e}")
        return {"text": "", "confidence": 0.0, "warning": f"OCR hatası: {str(e)}"}

# ==========================================
# 2. PDF PARÇALAMA MANTIĞI
# ==========================================
def pdf_ocr_yap_advanced(pdf_path: str) -> Dict[int, str]:
    logger.info(f"📄 PDF İşleniyor: {pdf_path}")
    doc = fitz.open(pdf_path)
    sayfa_metinleri = {}
    for sayfa_no in range(len(doc)):
        sayfa = doc[sayfa_no]
        # Önce dijital metni al
        metin = sayfa.get_text().strip()
        logger.info(f"📄 Sayfa {sayfa_no+1}: Dijital metin uzunluğu = {len(metin)}")
        
        # Eğer metin çok kısaysa veya boşsa OCR dene (ama dijital metni kaybetme)
        if len(metin) < 150:
            try:
                logger.info(f"🔍 Sayfa {sayfa_no+1}: Metin yetersiz, OCR başlatılıyor...")
                pix = sayfa.get_pixmap(matrix=fitz.Matrix(3, 3))
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                if state.ocr_reader is not None:
                    ocr_res = state.ocr_reader.readtext(np.array(img), detail=0, paragraph=True)
                    ocr_metin = " ".join(str(o) for o in ocr_res)
                    logger.info(f"🔍 Sayfa {sayfa_no+1}: OCR tamamlandı. OCR metin uzunluğu = {len(ocr_metin)}")
                    if ocr_metin.strip():
                        metin = metin + "\n" + ocr_metin
            except Exception as e:
                logger.error(f"❌ OCR Hatası (Sayfa {sayfa_no+1}): {e}")
        
        sayfa_metinleri[sayfa_no + 1] = metin or ""
    return sayfa_metinleri

def chunking_logic(metin: str, sayfa_no: int, dosya_adi: str, baslangic_index: int) -> List[Dict]:
    chunks = []
    regex = r'(?:^|\n|\s)(\d+)[\.\)\-\s]\s+([A-ZİĞÜŞÖÇ].+)'
    maddeler = list(re.finditer(regex, metin))
    
    if not maddeler:
        words = metin.split()
        if not words and metin.strip():
            # Eğer boşluklardan dolayı kelime yoksa ama metin varsa direkt al
            words = [metin.strip()]
            
        if not words:
            return []

        for i in range(0, len(words), 300):
            t = " ".join(words[i:i+450]) # Biraz daha geniş pencere
            if len(t.strip()) > 5:
                chunks.append({
                    "metin": t,
                    "metadata": {
                        "dosya": dosya_adi, "sayfa": sayfa_no, "madde_no": "genel",
                        "chunk_index": baslangic_index + len(chunks)
                    }
                })
        return chunks

    for i, m in enumerate(maddeler):
        try:
            m_no = m.group(1)
            start = m.start()
            end = maddeler[i+1].start() if i+1 < len(maddeler) else len(metin)
            content = metin[start:end].strip()
            if len(content) > 10:
                chunks.append({
                    "metin": content,
                    "metadata": {
                        "dosya": dosya_adi, "sayfa": sayfa_no, "madde_no": str(m_no),
                        "chunk_index": baslangic_index + len(chunks)
                    }
                })
        except: continue
    return chunks

def worker_process(pdf_path: str, dosya_adi: str):
    logger.info(f"⚙️ İşlemci çalışıyor: {dosya_adi}")
    sayfa_metinleri = pdf_ocr_yap_advanced(pdf_path)
    tum_chunks = []
    idx = 0
    for s_no in sorted(sayfa_metinleri.keys()):
        yeni = chunking_logic(sayfa_metinleri[s_no], s_no, dosya_adi, idx)
        tum_chunks.extend(yeni)
        idx += len(yeni)
    return tum_chunks

def get_full_text_by_filename(filename: str) -> str:
    """ChromaDB'den belirli bir dosyanın tüm parçalarını çekip birleştirir."""
    if state.collection is None: return ""
    try:
        results = state.collection.get(where={"dosya": filename})
        if not results or not results.get('documents'):
            return ""
        
        # Parçaları chunk_index'e göre sırala (metadata içinden)
        docs_with_meta = []
        for i in range(len(results['documents'])):
            docs_with_meta.append({
                "text": results['documents'][i],
                "index": results['metadatas'][i].get('chunk_index', 0) if results['metadatas'] else 0
            })
        
        docs_with_meta.sort(key=lambda x: x['index'])
        return "\n".join([d['text'] for d in docs_with_meta])
    except Exception as e:
        logger.error(f"Dosya metni çekilirken hata ({filename}): {e}")
        return ""

async def get_missing_info(text: str) -> List[str]:
    """
    LangGraph validator_app kullanarak metindeki eksik alanları bulur.
    """
    try:
        if not text or len(text.strip()) < 10:
            return []
        
        initial_state = {
            "extracted_text": text,
            "validation_results": {}
        }
        final_state = await validator_app.ainvoke(initial_state)
        results = final_state.get("validation_results", {})
        return results.get("missing_fields", [])
    except Exception as e:
        logger.error(f"Eksik bilgi tespiti hatası: {e}")
        return []

# ==========================================
# 3. ENDPOINTS
# ==========================================
class SoruModel(BaseModel):
    soru: str
    top_k: Optional[int] = 10
    dosya_adi: Optional[str] = None
    dosya_adlari: Optional[List[str]] = None
    session_id: Optional[str] = None

class ValidationCompleteModel(BaseModel):
    dosya_adi: str
    alanlar: Dict[str, str]
    session_id: Optional[str] = None

async def dosya_isle_ve_kaydet(file: UploadFile):
    """Tek bir dosyayı işler, OCR yapar ve ChromaDB'ye kaydeder."""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(400, f"Sadece PDF kabul edilir: {file.filename}")
    
    path = os.path.join(state.documents_folder, file.filename)
    try:
        if state.collection is not None:
            try:
                old_data = state.collection.get(where={"dosya": file.filename})
                if old_data and old_data.get('ids'):
                    state.collection.delete(ids=old_data['ids'])
            except: pass

        async with aiofiles.open(path, 'wb') as f:
            content = await file.read()
            await f.write(content)
            
        chunks = await run_in_threadpool(worker_process, path, file.filename)
        logger.info(f"✅ İşleme Tamamlandı: {file.filename} -> {len(chunks)} parça oluşturuldu.")
        
        if chunks and state.collection is not None:
            ids = [f"{file.filename}_{c['metadata']['chunk_index']}_{uuid.uuid4().hex[:6]}" for c in chunks]
            docs = [c["metin"] for c in chunks]
            metas = [metadata_temizle(c["metadata"]) for c in chunks]
            
            for m in metas:
                if 'dosya' not in m: m['dosya'] = file.filename

            state.collection.add(ids=ids, documents=docs, metadatas=metas)
            logger.info(f"📥 {len(chunks)} parça ChromaDB'ye eklendi.")
        
        full_text = "\n".join([c["metin"] for c in chunks])
        missing_info = await get_missing_info(full_text)
        
        return {
            "filename": file.filename,
            "chunk_sayisi": len(chunks),
            "missing_info": missing_info
        }
    except Exception as e:
        logger.error(f"Dosya İşleme Hatası ({file.filename}): {e}")
        raise e

@app.post("/yukle")
async def yukle(files: List[UploadFile] = File(...)):
    processed_files = []
    total_chunks = 0
    
    try:
        for file in files:
            res = await dosya_isle_ve_kaydet(file)
            processed_files.append(res)
            total_chunks += res["chunk_sayisi"]
            
        return {
            "success": True, 
            "mesaj": f"{len(processed_files)} dosya yüklendi.", 
            "chunk_sayisi": total_chunks,
            "files": processed_files,
            "missing_info": processed_files[0]["missing_info"] if processed_files else []
        }
    except Exception as e:
        return JSONResponse(500, {"detail": str(e)})

@app.post("/api/validator/complete")
async def validator_complete(req: ValidationCompleteModel):
    try:
        logger.info(f"✅ Bilgiler güncellendi: {req.dosya_adi} -> {req.alanlar}")
        return {"success": True, "mesaj": "Bilgiler başarıyla güncellendi."}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/sor")
async def soru_sor(req: SoruModel):
    if not client: raise HTTPException(500, "OpenAI API Key yok!")

    soru = req.soru.strip()
    if not soru or len(soru) < 3:
        return {"cevap": "Geçersiz soru.", "kaynaklar": [], "missing_info": []}

    logger.info(f"/sor isteği: '{soru[:80]}...' (top_k={req.top_k})")

    # ── Intent Detection 1: Cross-Document Audit ───────────────────────────────
    AUDIT_TRIGGERS = [
        "kıyasla", "kiyasla", "karşılaştır", "karsilastir",
        "fark nedir", "değişen maddeler", "degisen maddeler",
        "çapraz denetle", "capraz denetle", "iki belge", "belgeler arasında",
        "belgeler arasinda"
    ]
    soru_lower = soru.lower()
    if any(trigger in soru_lower for trigger in AUDIT_TRIGGERS):
        logger.info("🔍 Audit intent algılandı — belge karşılaştırması yönlendiriliyor.")
        try:
            # Hangi dosyalar var? dosya_adlari öncelikli, yoksa ChromaDB'den bul
            audit_filenames: List[str] = []
            if req.dosya_adlari and len(req.dosya_adlari) >= 2:
                audit_filenames = req.dosya_adlari[:2]
            elif state.collection is not None:
                # En son eklenen benzersiz dosya adlarından ilk 2'yi al
                try:
                    all_meta = state.collection.get()
                    seen: list = []
                    for m in (all_meta.get("metadatas") or []):
                        fn = (m or {}).get("dosya")
                        if fn and fn not in seen:
                            seen.append(fn)
                    audit_filenames = seen[:2]
                except Exception as _e:
                    logger.warning(f"ChromaDB dosya listesi alınamadı: {_e}")

            if len(audit_filenames) < 2:
                return {
                    "cevap": "Karşılaştırma için iki belge yükleyin.",
                    "kaynaklar": [],
                    "missing_info": [],
                    "intent": "audit"
                }

            # Dosyaların tam metinlerini çek
            doc1_text = get_full_text_by_filename(audit_filenames[0])
            doc2_text = get_full_text_by_filename(audit_filenames[1])

            if not doc1_text or not doc2_text:
                return {
                    "cevap": "Karşılaştırma için her iki belgenin de içeriği gerekli. Belgeleri yeniden yükleyin.",
                    "kaynaklar": [],
                    "missing_info": [],
                    "intent": "audit"
                }

            audit_initial = {
                "doc1_text": doc1_text,
                "doc2_text": doc2_text,
                "comparison_results": {},
                "executive_summary": "",
                "error": None
            }
            audit_final = await auditor_app.ainvoke(audit_initial)

            if audit_final.get("error"):
                return {
                    "cevap": f"Belge karşılaştırması sırasında hata oluştu: {audit_final['error']}",
                    "kaynaklar": [],
                    "missing_info": [],
                    "intent": "audit"
                }

            comp = audit_final.get("comparison_results", {})
            summary = audit_final.get("executive_summary", "")
            comp["timestamp"] = datetime.datetime.now().isoformat()

            logger.info(f"✅ Audit tamamlandı ({audit_filenames[0]} vs {audit_filenames[1]})")
            return {
                "cevap": summary or "Karşılaştırma tamamlandı.",
                "kaynaklar": [
                    {"source": audit_filenames[0], "page": 0, "type": "audit", "score": 1.0},
                    {"source": audit_filenames[1], "page": 0, "type": "audit", "score": 1.0},
                ],
                "missing_info": [],
                "intent": "audit",
                "audit_result": {
                    "success": True,
                    "comparison_results": comp,
                    "executive_summary": summary,
                    "doc1": audit_filenames[0],
                    "doc2": audit_filenames[1]
                }
            }
        except Exception as _ae:
            logger.error(f"Audit intent işleme hatası: {_ae}", exc_info=True)
            # Hata durumunda RAG'a düş
    # ── Intent Detection 2: Missing Info Validator ─────────────────────────────
    VALIDATOR_TRIGGERS = [
        "eksik bilgi", "eksik alan", "belgeyi doğrula", "belgeyi dogrula",
        "belge tam mı", "belge tam mi", "eksik", "doğrula", "dogrula",
        "neyi eksik", "ne eksik"
    ]
    if any(trigger in soru_lower for trigger in VALIDATOR_TRIGGERS):
        logger.info("🔍 Validator intent algılandı — eksik bilgi kontrolü yönlendiriliyor.")
        try:
            # Hangi belge metni kullanılacak?
            val_text = ""
            val_filenames = req.dosya_adlari or ([req.dosya_adi] if req.dosya_adi else [])
            if val_filenames and state.collection is not None:
                val_text = get_full_text_by_filename(val_filenames[0])
            elif state.collection is not None:
                # Hiç dosya belirtilmediyse koleksiyondaki tüm metni al (ilk dosya)
                try:
                    all_meta = state.collection.get()
                    seen_val: list = []
                    for m in (all_meta.get("metadatas") or []):
                        fn = (m or {}).get("dosya")
                        if fn and fn not in seen_val:
                            seen_val.append(fn)
                    if seen_val:
                        val_text = get_full_text_by_filename(seen_val[0])
                except Exception as _e:
                    logger.warning(f"ChromaDB dosya listesi alınamadı (validator): {_e}")

            if not val_text.strip():
                return {
                    "cevap": "Doğrulanacak belge bulunamadı. Lütfen önce bir belge yükleyin.",
                    "kaynaklar": [],
                    "missing_info": [],
                    "intent": "validator"
                }

            val_initial = {
                "extracted_text": val_text,
                "validation_results": {},
                "error": None
            }
            val_final = await validator_app.ainvoke(val_initial)

            if val_final.get("error"):
                return {
                    "cevap": f"Belge doğrulama sırasında hata: {val_final['error']}",
                    "kaynaklar": [],
                    "missing_info": [],
                    "intent": "validator"
                }

            vres = val_final.get("validation_results", {})
            missing = vres.get("missing_fields", [])
            is_complete = vres.get("is_complete", False)
            doc_type = vres.get("document_type", "Bilinmiyor")

            if is_complete:
                cevap_val = f"✅ Belge tam görünüyor ({doc_type}). Eksik alan tespit edilmedi."
            else:
                cevap_val = (
                    f"⚠️ Belge türü: {doc_type}. "
                    f"Eksik alanlar: {', '.join(missing) if missing else 'Yok'}."
                )

            logger.info(f"✅ Validator tamamlandı. Eksik: {missing}")
            return {
                "cevap": cevap_val,
                "kaynaklar": [],
                "missing_info": missing,
                "intent": "validator",
                "validation_result": {
                    "success": True,
                    "validation_results": vres
                }
            }
        except Exception as _ve:
            logger.error(f"Validator intent işleme hatası: {_ve}", exc_info=True)
            # Hata durumunda RAG'a düş
    # ── End Intent Detection ────────────────────────────────────────────────────

    try:
        if state.collection is None:
            return {"cevap": "Veritabanı hazır değil.", "kaynaklar": [], "missing_info": []}

        # Vektör Arama (dosya_adi veya dosya_adlari varsa filtrele)
        query_kwargs: Dict[str, Any] = {
            "query_texts": [soru],
            "n_results": req.top_k
        }
        if req.dosya_adlari and len(req.dosya_adlari) > 0:
            logger.info(f"🔍 Çoklu Dosya Filtresi Uygulanıyor: {req.dosya_adlari}")
            query_kwargs["where"] = {"dosya": {"$in": req.dosya_adlari}}
        elif req.dosya_adi:
            logger.info(f"🔍 Sorgu Filtresi Uygulanıyor: {req.dosya_adi}")
            query_kwargs["where"] = {"dosya": req.dosya_adi}
        else:
            logger.info("🌐 Genel Sorgu Yapılıyor (Filtre Yok)")

        results = state.collection.query(**query_kwargs)
        if not results.get('documents') or not results['documents'][0]:
            return {"cevap": "Bu soruyla ilgili yeterli bilgi bulunamadı.", "kaynaklar": [], "missing_info": []}

        raw_docs: List[str] = list(results['documents'][0])
        raw_metas: List[Dict[str, Any]] = list(results['metadatas'][0])  # type: ignore
        raw_dists: List[float] = list(results['distances'][0])  # type: ignore

        if not raw_dists:
            return {"cevap": "Bu soruyla ilgili yeterli bilgi bulunamadı.", "kaynaklar": [], "missing_info": []}

        en_iyi_skor = 1 - raw_dists[0]
        dinamik_esik = en_iyi_skor * 0.85 if en_iyi_skor > 0.75 else max(en_iyi_skor * 0.70, 0.30)

        # ── Reranking: dinamik eşik kullanan filtreleme ─────────────────
        combined = []
        for i in range(len(raw_docs)):
            score = 1.0 - (raw_dists[i] if i < len(raw_dists) else 1.0)
            if score >= dinamik_esik:
                combined.append({
                    "text": raw_docs[i],
                    "meta": raw_metas[i] if i < len(raw_metas) else {},
                    "score": score
                })

        logger.info(f"Reranking sonucu: {len(combined)}/{len(raw_docs)} chunk eşiği geçti (dinamik_esik={dinamik_esik:.4f}).")

        if not combined:
            return {"cevap": "Bu soruyla ilgili yeterli bilgi bulunamadı.", "kaynaklar": [], "missing_info": []}

        # Skor'a göre (yüksekten düşüğe) sırala, ardından chunk_index'e göre normalize et
        combined.sort(key=lambda x: int(cast(dict, x["meta"]).get("chunk_index", 9999)) if isinstance(x["meta"], dict) else 9999)
        ai_baglam = "\n---\n".join([str(item['text']) for item in combined])
        kaynaklar = [
            {
                "source": str(cast(dict, c["meta"]).get("dosya", "")),
                "page": int(cast(dict, c["meta"]).get("sayfa", 0)),
                "type": str(cast(dict, c["meta"]).get("madde_no", "")),
                "score": round(c.get("score", 0.0), 4)
            }
            for c in combined if isinstance(c["meta"], dict)
        ]

        # ChatGPT
        logger.info("OpenAI GPT-4o çağrısı yapılıyor...")
        system_msg = (
            "Sen bir hukuk asistanısın. Verilen BAĞLAM'a göre SORU'yu yanıtla. "
            "Eğer belgede kritik bilgiler (TC No, IBAN, E-posta, Ad Soyad, Tarih vb.) eksikse "
            "yanıtının sonuna JSON formatında 'MISSING_INFO: [\"alan1\", \"alan2\"]' şeklinde bir not ekle."
        )

        try:
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": f"BAĞLAM:\n{ai_baglam}\n\nSORU: {soru}"}
                ],
                temperature=0.3
            )
            logger.info("GPT-4o yanıtı alındı.")
            
            full_cevap = resp.choices[0].message.content or ""
            cevap = full_cevap
            
            # Önce regex ile GPT'nin kendi cevabındaki notu temizle (varsa)
            match = re.search(r"MISSING_INFO:\s*(\[.*?\])", full_cevap)
            if match:
                cevap = cevap.replace(match.group(0), "").strip()
                
            # Daha güvenilir LangGraph validator_app ile kontrol et
            kontrol_metni = f"{ai_baglam}\n{cevap}"
            missing_fields = await get_missing_info(kontrol_metni)

            return {
                "cevap": cevap, 
                "kaynaklar": kaynaklar,
                "missing_info": missing_fields
            }
        except RateLimitError:
            logger.error("OpenAI rate limit aşıldı.")
            raise HTTPException(429, "OpenAI rate limit aşıldı. Lütfen bekleyin.")
        except AuthenticationError:
            logger.error("OpenAI kimlik doğrulama hatası.")
            raise HTTPException(401, "OpenAI API anahtarı geçersiz.")
        except APITimeoutError:
            logger.error("OpenAI API zaman aşımı.")
            raise HTTPException(504, "OpenAI yanıt vermedi. Lütfen tekrar deneyin.")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"/sor hatası: {e}", exc_info=True)
        raise HTTPException(500, str(e))

# --- EKLENEN KISIM: FOTOĞRAF ENDPOINT ---
@app.post("/sor/fotograf")
async def foto_analiz(file: UploadFile = File(...), soru: str = Form("Bu belgede ne yazıyor?")):
    """
    Frontend'den gelen fotoğrafı OCR ile okur ve ChatGPT'ye yorumlatır.
    """
    if not client: raise HTTPException(500, "OpenAI API Key yok!")

    req_id = uuid.uuid4().hex[:6]
    logger.info(f"[{req_id}] 📷 Fotoğraf Analizi İsteği: {file.filename}")

    try:
        contents = await file.read()

        # OCR — Thread içinde çalıştır
        ocr_result = await run_in_threadpool(goruntu_isleyerek_oku, contents)

        okunan_metin = ocr_result.get("text", "")
        ocr_guven = ocr_result.get("confidence", 0.0)
        ocr_uyari = ocr_result.get("warning")

        if ocr_uyari:
            logger.warning(f"[{req_id}] OCR uyarısı: {ocr_uyari}")

        if not okunan_metin or len(okunan_metin.strip()) < 5:
            return {
                "cevap": "Fotoğraftan anlamlı bir metin okunamadı. Lütfen daha net bir fotoğraf yükleyin.",
                "okunan_ham_veri": "",
                "ocr_confidence": ocr_guven,
                "ocr_warning": ocr_uyari,
                "missing_info": []
            }

        logger.info(f"[{req_id}] ✅ OCR Başarılı. {len(okunan_metin)} karakter, güven: {ocr_guven:.2f}")

        prompt = f"""
        Aşağıda bir belgenin fotoğrafından OCR ile okunmuş metin var.
        Bu metni kullanarak kullanıcı sorusunu cevapla. Metindeki olası harf hatalarını düzelt.

        OCR METNİ:
        {okunan_metin}

        KULLANICI SORUSU:
        {soru}
        """

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Sen OCR hatalarını düzelten zeki bir asistansın."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4
            )
            ai_cevabi = response.choices[0].message.content
        except RateLimitError:
            raise HTTPException(429, "OpenAI rate limit aşıldı.")
        except AuthenticationError:
            raise HTTPException(401, "OpenAI API anahtarı geçersiz.")
        except APITimeoutError:
            raise HTTPException(504, "OpenAI yanıt vermedi. Lütfen tekrar deneyin.")

        missing_info = await get_missing_info(okunan_metin)

        return {
            "cevap": ai_cevabi,
            "okunan_ham_veri": okunan_metin,
            "ocr_confidence": ocr_guven,
            "ocr_warning": ocr_uyari,
            "missing_info": missing_info
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{req_id}] Fotoğraf Analiz Hatası: {e}", exc_info=True)
        raise HTTPException(500, f"İşlem başarısız: {str(e)}")

# --- NOT YÖNETİMİ ---
def get_user_file(user_email: str, filename: str) -> str:
    safe_email = user_email.replace('@', '_').replace('.', '_')
    user_dir = os.path.join("data", safe_email)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, filename)

class NoteCreate(BaseModel):
    content: str
    title: Optional[str] = None

class NoteUpdate(BaseModel):
    content: Optional[str] = None
    title: Optional[str] = None
    pinned: Optional[bool] = None

@app.get("/api/notes")
async def get_notes(x_user_email: str = Header(default="default_user")):
    notes_file = get_user_file(x_user_email, "notes.json")
    if not os.path.exists(notes_file):
        return []
    try:
        async with aiofiles.open(notes_file, mode='r', encoding='utf-8') as f:
            content = await f.read()
            if not content.strip():
                return []
            return json.loads(content)
    except Exception as e:
        logger.error(f"Notları okurken hata: {e}")
        return []

@app.post("/api/notes")
async def create_note(note: NoteCreate, x_user_email: str = Header(default="default_user")):
    notes_file = get_user_file(x_user_email, "notes.json")
    notes = []
    if os.path.exists(notes_file):
        try:
            async with aiofiles.open(notes_file, mode='r', encoding='utf-8') as f:
                content = await f.read()
                if content.strip():
                    notes = json.loads(content)
        except Exception as e:
            logger.error(f"Notları okurken hata (ekleme öncesi): {e}")
            raise HTTPException(status_code=500, detail="Mevcut notlar okunamadı.")
            
    new_note = {
        "id": str(uuid.uuid4()),
        "content": note.content,
        "title": note.title or "İsimsiz Not",
        "pinned": False,
        "timestamp": datetime.datetime.now().isoformat()
    }
    notes.append(new_note)
    
    try:
        async with aiofiles.open(notes_file, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(notes, ensure_ascii=False, indent=4))
        return new_note
    except Exception as e:
        logger.error(f"Not yazma hatası: {e}")
        raise HTTPException(status_code=500, detail=f"Dosyaya yazma hatası: Not kaydedilemedi ({str(e)}).")

@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: str, x_user_email: str = Header(default="default_user")):
    notes_file = get_user_file(x_user_email, "notes.json")
    if not os.path.exists(notes_file):
        raise HTTPException(status_code=404, detail="Not bulunamadı.")
        
    try:
        async with aiofiles.open(notes_file, mode='r', encoding='utf-8') as f:
            content = await f.read()
            if not content.strip():
                raise HTTPException(status_code=404, detail="Not bulunamadı.")
            notes = json.loads(content)
            
        initial_length = len(notes)
        notes = [n for n in notes if n.get("id") != note_id]
        
        if len(notes) == initial_length:
            raise HTTPException(status_code=404, detail="Not bulunamadı.")
            
        async with aiofiles.open(notes_file, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(notes, ensure_ascii=False, indent=4))
            
        return {"success": True, "detail": "Not başarıyla silindi."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Not silme hatası: {e}")
        raise HTTPException(status_code=500, detail=f"Not silinirken hata oluştu: ({str(e)}).")

@app.put("/api/notes/update/{note_id}")
async def update_note(note_id: str, note: NoteUpdate, x_user_email: str = Header(default="default_user")):
    notes_file = get_user_file(x_user_email, "notes.json")
    if not os.path.exists(notes_file):
        raise HTTPException(status_code=404, detail="Not bulunamadı.")
        
    try:
        async with aiofiles.open(notes_file, mode='r', encoding='utf-8') as f:
            content = await f.read()
            if not content.strip():
                raise HTTPException(status_code=404, detail="Not bulunamadı.")
            notes = json.loads(content)
            
        updated = False
        for n in notes:
            if n.get("id") == note_id:
                if note.content is not None:
                    n["content"] = note.content
                if note.title is not None:
                    n["title"] = note.title
                if note.pinned is not None:
                    n["pinned"] = note.pinned
                updated = True
                break
                
        if not updated:
            raise HTTPException(status_code=404, detail="Not bulunamadı.")
            
        async with aiofiles.open(notes_file, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(notes, ensure_ascii=False, indent=4))
            
        return {"success": True, "detail": "Not başarıyla güncellendi."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Not güncelleme hatası: {e}")
        raise HTTPException(status_code=500, detail=f"Not güncellenirken hata oluştu: ({str(e)}).")

# --- GEÇMİŞ YÖNETİMİ ---
@app.get("/api/history")
async def get_history(x_user_email: str = Header(default="default_user")):
    history_file = get_user_file(x_user_email, "history.json")
    if not os.path.exists(history_file):
        return []
    try:
        async with aiofiles.open(history_file, mode='r', encoding='utf-8') as f:
            content = await f.read()
            if not content.strip():
                return []
            return json.loads(content)
    except Exception as e:
        logger.error(f"Geçmiş okuma hatası: {e}")
        return []

@app.post("/api/history")
async def save_history(history_data: list, x_user_email: str = Header(default="default_user")):
    history_file = get_user_file(x_user_email, "history.json")
    try:
        async with aiofiles.open(history_file, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(history_data, ensure_ascii=False, indent=4))
        return {"success": True}
    except Exception as e:
        logger.error(f"Geçmiş yazma hatası: {e}")
        raise HTTPException(status_code=500, detail="Geçmiş kaydedilemedi.")

@app.post("/api/migrate-guest")
async def migrate_guest_data(x_user_email: str = Header(default="default_user")):
    if x_user_email == "guest" or x_user_email == "default_user":
        return {"status": "skipped", "message": "Geçersiz veya eksik hedef e-posta."}
        
    guest_dir = get_user_file("guest", "")
    if not os.path.exists(guest_dir):
        return {"status": "skipped", "message": "Aktarılacak misafir verisi bulunamadı."}
        
    target_dir = get_user_file(x_user_email, "")
    files_to_merge = ["notes.json", "calendar.json", "history.json"]
    
    merged_any = False
    
    for filename in files_to_merge:
        guest_file = os.path.join(guest_dir, filename)
        target_file = os.path.join(target_dir, filename)
        
        if os.path.exists(guest_file):
            try:
                # Guest datasını oku
                with open(guest_file, 'r', encoding='utf-8') as f:
                    guest_data = json.load(f)
                    
                if not isinstance(guest_data, list) or len(guest_data) == 0:
                    continue
                    
                # Hedef veriyi oku
                target_data = []
                if os.path.exists(target_file):
                    with open(target_file, 'r', encoding='utf-8') as f:
                        target_data = json.load(f)
                
                if isinstance(target_data, list):
                    # Birleştir (id çakışmalarını önlemek için basitçe ekleyebiliriz)
                    # Aynı içeriğe sahip olanları elemeyi deneyebiliriz ama şimdilik direkt ekliyoruz.
                    # ID'ler uuid/date.now olduğu için çakışma ihtimali çok düşük.
                    merged_data = target_data + guest_data
                    
                    # Hedefe yaz
                    with open(target_file, 'w', encoding='utf-8') as f:
                        json.dump(merged_data, f, ensure_ascii=False, indent=4)
                    
                    merged_any = True
            except Exception as e:
                logger.error(f"{filename} aktarılırken hata: {e}")
                
    # Migration bittikten sonra guest klasörünün içini temizle
    try:
        if os.path.exists(guest_dir):
            for filename in os.listdir(guest_dir):
                file_path = os.path.join(guest_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    logger.error(f"Guest dosyası silinirken hata {file_path}: {e}")
    except Exception as e:
        logger.error(f"Guest dizini temizlenirken hata: {e}")
        
    return {"status": "success", "message": "Misafir verileri başarıyla hesabınıza aktarıldı." if merged_any else "Aktarılacak veri yoktu."}


# --- GOOGLE CALENDAR ENTEGRASYONU ---
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service(access_token: str):
    """Google Calendar API'sine erişim sağlamak için frontend'den gelen tokeni kullanır."""
    if not access_token:
        raise ValueError("Google erişim izni (token) bulunamadı.")
        
    creds = Credentials(token=access_token)
    service = build('calendar', 'v3', credentials=creds)
    return service

class ExecuteTaskRequest(BaseModel):
    task_id: Union[int, str]
    action: str
    task_title: Optional[str] = "Bilinmeyen Görev"
    task_date: Optional[str] = None

@app.get("/api/calendar/events")
async def get_calendar_events(x_user_email: str = Header(default="default_user"), x_google_token: str = Header(default="")):
    events_list = []
    
    # 1. Google Takvim'den çek
    if x_google_token:
        try:
            service = get_calendar_service(x_google_token)
            now = datetime.datetime.utcnow().isoformat() + 'Z'
            events_result = service.events().list(calendarId='primary', timeMin=now,
                                                  maxResults=10, singleEvents=True,
                                                  orderBy='startTime').execute()
            google_events = events_result.get('items', [])
            for ge in google_events:
                start = ge['start'].get('dateTime', ge['start'].get('date'))
                events_list.append({
                    "id": ge['id'],
                    "title": ge.get('summary', 'İsimsiz Etkinlik'),
                    "start": start,
                    "source": "google"
                })
        except Exception as e:
            logger.error(f"Google Calendar GET hatası: {e}")

    # 2. Yerel calendar.json'dan çek
    calendar_file = get_user_file(x_user_email, "calendar.json")
    if os.path.exists(calendar_file):
        try:
            with open(calendar_file, 'r', encoding='utf-8') as f:
                local_events = json.load(f)
            # Zaman filtresi uygula
            now_dt = datetime.datetime.now()
            for le in local_events:
                try:
                    le_dt = datetime.datetime.fromisoformat(le['start'])
                    if le_dt > now_dt:
                        events_list.append(le)
                except:
                    pass
        except Exception as e:
            logger.error(f"Yerel takvim okuma hatası: {e}")
            
    # Geriye dönmeden önce zamana göre sırala
    events_list.sort(key=lambda x: x['start'])
    return {"events": events_list}

@app.post("/api/action/calendar/add")
async def execute_task(req: ExecuteTaskRequest, x_user_email: str = Header(default="default_user"), x_google_token: str = Header(default="")):
    if req.action == "calendar_event":
        basarisiz_mesaj = f"BAŞARILI: '{req.task_title}' Google Takvim'e ekleniyor..."
        logger.info(basarisiz_mesaj)
        
        event_link = ""
        start_time_iso = ""
        
        # 1. Google Takvim'e kaydet
        if x_google_token:
            try:
                service = get_calendar_service(x_google_token)
                
                now = datetime.datetime.now()
                start_time = now + datetime.timedelta(hours=1)
                end_time = start_time + datetime.timedelta(hours=1)
                
                if req.task_date:
                    try:
                        selected_date = datetime.datetime.strptime(req.task_date, "%Y-%m-%d")
                        if selected_date.date() != now.date():
                            start_time = selected_date.replace(hour=10, minute=0, second=0)
                            end_time = start_time + datetime.timedelta(hours=1)
                    except Exception as e:
                        pass
                        
                start_time_iso = start_time.isoformat()
                
                event = {
                    'summary': req.task_title,
                    'description': 'AI Asistan tarafından uygulamanız aracılığıyla eklendi.',
                    'start': {'dateTime': start_time.isoformat() + '+03:00', 'timeZone': 'Europe/Istanbul'},
                    'end': {'dateTime': end_time.isoformat() + '+03:00', 'timeZone': 'Europe/Istanbul'},
                }
                
                event_result = service.events().insert(calendarId='primary', body=event).execute()
                event_link = event_result.get('htmlLink')
            except Exception as e:
                logger.error(f"Google Calendar API Hatası: {e}")
            # Hata olsa bile local'e kaydetmeye devam et
            
        # 2. Yerel calendar.json'a yedekle (Dual Save)
        local_event = {
            "id": str(uuid.uuid4()),
            "title": req.task_title,
            "start": start_time_iso or datetime.datetime.now().isoformat(),
            "source": "local"
        }
        
        calendar_file = get_user_file(x_user_email, "calendar.json")
        local_events = []
        if os.path.exists(calendar_file):
            try:
                with open(calendar_file, 'r', encoding='utf-8') as f:
                    local_events = json.load(f)
            except: pass
            
        local_events.append(local_event)
        
        try:
            with open(calendar_file, 'w', encoding='utf-8') as f:
                json.dump(local_events, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Yerel takvim yazma hatası: {e}")

        return {
            "status": "success", 
            "message": "Etkinlik başarıyla eklendi!",
            "event_link": event_link
        }
    
    return {"status": "error", "message": "Geçersiz action."}


# =============================================================================
# AGENT ENDPOINTS (Merge from agent_api.py — port 8001 is no longer needed)
# =============================================================================

class TaskRequest(BaseModel):
    metin: str

class ProactiveRequest(BaseModel):
    sohbet_gecmisi: List[str]

class AuditorRequest(BaseModel):
    doc1_text: Optional[str] = None
    doc2_text: Optional[str] = None
    doc1_name: Optional[str] = None
    doc2_name: Optional[str] = None
    filenames: Optional[List[str]] = None

class ValidatorRequest(BaseModel):
    extracted_text: str


@app.post("/agent/task-extract")
async def extract_task_endpoint(req: TaskRequest):
    logger.info(f"/agent/task-extract istegi alindi ({len(req.metin)} karakter).")
    try:
        baslangic = {
            "metin": req.metin,
            "cikarim_sonucu": None,
            "islem_durumu": "BASLADI",
            "error": None
        }
        tamamlanmis = graph_invoke_with_timeout(baslangic, timeout=30)

        if tamamlanmis.get("error"):
            logger.warning(f"Agent hata ile tamamlandi: {tamamlanmis['error']}")
            return JSONResponse(
                status_code=500,
                content={"error": True, "message": tamamlanmis["error"], "code": 500}
            )

        sonuc_model = tamamlanmis.get("cikarim_sonucu")
        sonuc_dict = sonuc_model.dict() if sonuc_model else None
        logger.info("Gorev cikarimi basariyla tamamlandi.")
        return {
            "success": True,
            "islem_durumu": tamamlanmis.get("islem_durumu"),
            "data": sonuc_dict
        }
    except TimeoutError as e:
        logger.error(f"Timeout: {e}")
        raise HTTPException(status_code=504, detail=str(e))
    except RateLimitError:
        logger.error("OpenAI rate limit asildi.")
        raise HTTPException(status_code=429, detail="OpenAI rate limit asildi. Lutfen bekleyin.")
    except AuthenticationError:
        logger.error("OpenAI kimlik dogrulama hatasi.")
        raise HTTPException(status_code=401, detail="OpenAI API kimlik hatasi.")
    except APITimeoutError:
        logger.error("OpenAI API zaman asimi.")
        raise HTTPException(status_code=504, detail="OpenAI API zaman asimi.")
    except Exception as e:
        logger.error(f"Gorev cikarimi hatasi: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Gorev cikarimi sirasinda hata: {str(e)}")


@app.post("/agent/proactive-search")
async def proactive_search_endpoint(req: ProactiveRequest):
    logger.info(f"/agent/proactive-search istegi alindi ({len(req.sohbet_gecmisi)} mesaj).")
    try:
        baslangic = {
            "sohbet_gecmisi": req.sohbet_gecmisi,
            "ilgi_alanlari": [],
            "arama_sonuclari": {},
            "error": None
        }
        sonuc = proactive_graph.invoke(baslangic)
        if sonuc.get("error"):
            logger.warning(f"Proaktif arama hata ile tamamlandi: {sonuc['error']}")
        logger.info("Proaktif arama tamamlandi.")
        return {
            "success": True,
            "ilgi_alanlari": sonuc.get("ilgi_alanlari", []),
            "arama_sonuclari": sonuc.get("arama_sonuclari", {}),
            "error": sonuc.get("error")
        }
    except RateLimitError:
        raise HTTPException(status_code=429, detail="OpenAI rate limit asildi.")
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="OpenAI API kimlik hatasi.")
    except APITimeoutError:
        raise HTTPException(status_code=504, detail="OpenAI API zaman asimi.")
    except Exception as e:
        logger.error(f"Proaktif arama hatasi: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Proaktif arama sirasinda hata: {str(e)}")


@app.post("/agent/audit-documents")
async def audit_documents_endpoint(req: AuditorRequest):
    logger.info("/agent/audit-documents istegi alindi.")
    try:
        texts = []
        if req.filenames:
            for fname in req.filenames:
                txt = get_full_text_by_filename(fname)
                if txt: texts.append({"name": fname, "text": txt})
        
        # Geriye dönük uyumluluk
        if not texts:
            doc1 = req.doc1_text or (get_full_text_by_filename(req.doc1_name) if req.doc1_name else None)
            doc2 = req.doc2_text or (get_full_text_by_filename(req.doc2_name) if req.doc2_name else None)
            if doc1: texts.append({"name": req.doc1_name or "Belge 1", "text": doc1})
            if doc2: texts.append({"name": req.doc2_name or "Belge 2", "text": doc2})

        if len(texts) < 2:
            raise HTTPException(400, "Karşılaştırılacak en az iki belge gereklidir.")

        initial_state = {
            "doc1_text": texts[0]["text"],
            "doc2_text": texts[1]["text"],
            "comparison_results": {},
            "executive_summary": "",
            "error": None
        }
        final_state = await auditor_app.ainvoke(initial_state)

        if final_state.get("error"):
            logger.warning(f"Denetim hata ile tamamlandi: {final_state['error']}")
            return JSONResponse(
                status_code=500,
                content={"error": True, "message": final_state["error"], "code": 500}
            )

        res = final_state.get("comparison_results", {})
        res["timestamp"] = datetime.datetime.now().isoformat()

        logger.info("Dokuman denetimi basariyla tamamlandi.")
        return {
            "success": True,
            "comparison_results": res,
            "executive_summary": final_state.get("executive_summary", "")
        }
    except HTTPException:
        raise
    except RateLimitError:
        raise HTTPException(status_code=429, detail="OpenAI rate limit asildi.")
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="OpenAI API kimlik hatasi.")
    except APITimeoutError:
        raise HTTPException(status_code=504, detail="OpenAI API zaman asimi.")
    except Exception as e:
        logger.error(f"Dokuman denetimi hatasi: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Dokuman denetimi sirasinda hata: {str(e)}")


@app.post("/agent/validate-document")
async def validate_document_endpoint(req: ValidatorRequest):
    logger.info("/agent/validate-document istegi alindi.")
    try:
        initial_state = {
            "extracted_text": req.extracted_text,
            "validation_results": {},
            "error": None
        }
        final_state = await validator_app.ainvoke(initial_state)

        if final_state.get("error"):
            logger.warning(f"Dogrulama hata ile tamamlandi: {final_state['error']}")
            return JSONResponse(
                status_code=500,
                content={"error": True, "message": final_state["error"], "code": 500}
            )

        logger.info("Belge dogrulamasi basariyla tamamlandi.")
        return {
            "success": True,
            "validation_results": final_state.get("validation_results", {})
        }
    except RateLimitError:
        raise HTTPException(status_code=429, detail="OpenAI rate limit asildi.")
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="OpenAI API kimlik hatasi.")
    except APITimeoutError:
        raise HTTPException(status_code=504, detail="OpenAI API zaman asimi.")
    except Exception as e:
        logger.error(f"Belge dogrulama hatasi: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Belge dogrulamasi sirasinda hata: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)