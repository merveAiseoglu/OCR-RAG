import os
from dotenv import load_dotenv

# .env dosyasını en başta yüklüyoruz
load_dotenv()

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union, cast
import time
import logging
import json
import re
import math
import io
import uuid 
import shutil
import numpy as np # Resim işleme için
import cv2 # OpenCV
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# --- AGENT ---
from agent.web_searcher import WebSearcher
from agent.task_extractor import TaskExtractor
# --- LANGGRAPH AJAN MODULLERİ ---
from agent.graph_builder import graph as task_graph, AgentState
from agent.task_extractor import CikartmaSonucu
from agent.proactive_graph import graph as proactive_graph, ProactiveState
from agent.cross_document_auditor import auditor_app
from agent.missing_info_agent import validator_app


# --- OPENAI ENTEGRASYONU ---
from openai import OpenAI

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
    format='%(asctime)s [%(levelname)s] %(message)s',
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

app = FastAPI(title="OCR-RAG Unified API", version="4.0", description="OCR, RAG ve LangGraph Ajanlarini birlestiren FastAPI sunucusu")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

## mobilden gelen ping istekleri için endpoint --
@app.get("/")
def read_root():
    return {"message": "Server is running"}

@app.on_event("startup")
async def startup_event():
    logger.info("🎬 SİSTEM BAŞLATILIYOR...")
    state.ocr_reader = easyocr.Reader(['tr', 'en'], gpu=False)
    state.embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    
    state.chroma_client = chromadb.PersistentClient(path=state.db_path)
    if state.chroma_client is not None:
        state.collection = state.chroma_client.get_or_create_collection(
            name="hukuk_dokumanlari",
            embedding_function=MyEmbeddingFunction(state.embedding_model),
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"✅ SİSTEM HAZIR. Koleksiyondaki belge sayısı: {state.collection.count() if state.collection else 0}")
    else:
        logger.warning("⚠️ ChromaDB Client başlatılamadı.")

# ==========================================
# 1. OCR GÖRÜNTÜ İŞLEME MANTIĞI (Senin Kodun)
# ==========================================
def goruntu_isleyerek_oku(image_bytes):
    """
    ocr_engine.py içindeki mantığın aynısı.
    OpenCV ile gürültü temizler ve okur.
    """
    try:
        # Byte'tan OpenCV formatına çevir
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None: return ""

        # Gri ton
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Blur (Gürültü azaltma)
        blur = cv2.GaussianBlur(gray, (7,7), 0)
        # Threshold (Siyah-Beyaz netleştirme)
        thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        
        # Metin bloklarını genişlet
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 2))
        dilate = cv2.dilate(thresh, kernel, iterations=1)
        
        # Konturları bul
        cnts = cv2.findContours(dilate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = cnts[0] if len(cnts) == 2 else cnts[1]
        
        # Yukarıdan aşağıya sırala
        cnts = sorted(cnts, key=lambda x: cv2.boundingRect(x)[1])

        bulunan_metinler = []
        for c in cnts:
            if cv2.contourArea(c) < 500: continue
            x, y, w, h = cv2.boundingRect(c)
            if h > w: continue # Dikey gürültüleri atla

            roi = img[y:y+h, x:x+w]
            try:
                # EasyOCR ile parça parça oku
                if state.ocr_reader is not None:
                    okunan = state.ocr_reader.readtext(roi, detail=0)
                    if okunan:
                        bulunan_metinler.append(" ".join(str(o) for o in okunan))
            except: pass
        
        # Eğer OpenCV yöntemiyle hiçbir şey çıkmazsa, resmi düz okumayı dene (Fallback)
        if not bulunan_metinler and state.ocr_reader is not None:
            okunan = state.ocr_reader.readtext(img, detail=0)
            return " ".join(str(o) for o in okunan)

        return "\n".join(bulunan_metinler)
        
    except Exception as e:
        logger.error(f"OCR İşleme Hatası: {e}")
        return ""

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
    dosya_adlari: Optional[List[str]] = None # [YENİ]
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
            "missing_info": processed_files[0]["missing_info"] if processed_files else [] # İlk dosyanınkini dön (fallback)
        }
    except Exception as e:
        return JSONResponse(500, {"detail": str(e)})

@app.post("/api/validator/complete")
async def validator_complete(req: ValidationCompleteModel):
    try:
        # Gerçek bir sistemde burada veritabanı veya PDF güncellenir.
        # Şimdilik başarılı simülasyonu yapıyoruz.
        logger.info(f"✅ Bilgiler güncellendi: {req.dosya_adi} -> {req.alanlar}")
        return {"success": True, "mesaj": "Bilgiler başarıyla güncellendi."}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/sor")
async def soru_sor(req: SoruModel):
    if not client: raise HTTPException(500, "OpenAI API Key yok!")
    
    soru = req.soru.strip()
    if not soru or len(soru) < 3: return {"cevap": "Geçersiz soru.", "kaynaklar": []}

    try:
        if state.collection is None:
            return {"cevap": "Veritabanı hazır değil.", "kaynaklar": []}

        # Vektör Arama (dosya_adi varsa yalnızca o belgeyi sorgula)
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
             logger.warning(f"⚠️ Sonuç Bulunamadı! Soru: {soru}")
             return {"cevap": "Bilgi bulunamadı. Belge düzgün okunmamış olabilir.", "kaynaklar": []}

        # Filtreleme
        raw_docs: List[str] = list(results['documents'][0]) if results.get('documents') and results['documents'] else []
        raw_metas: List[Dict[str, Any]] = list(results['metadatas'][0]) if results.get('metadatas') and results['metadatas'] else [] # type: ignore
        raw_dists: List[float] = list(results['distances'][0]) if results.get('distances') and results['distances'] else [] # type: ignore
        
        if not raw_dists:
            return {"cevap": "Uzaklık bilgisi bulunamadı.", "kaynaklar": []}

        en_iyi_skor = 1 - raw_dists[0]
        dinamik_esik = en_iyi_skor * 0.85 if en_iyi_skor > 0.75 else max(en_iyi_skor * 0.70, 0.30)

        combined = []
        for i in range(len(raw_docs)):
            doc = raw_docs[i]
            meta = raw_metas[i] if len(raw_metas) > i else {}
            dist = raw_dists[i] if len(raw_dists) > i else 1.0
            if (1 - dist) >= dinamik_esik:
                combined.append({"text": doc, "meta": meta})

        if not combined: return {"cevap": "Yeterli eşleşme yok.", "kaynaklar": []}

        # Context Hazırla
        combined.sort(key=lambda x: int(cast(dict, x["meta"]).get("chunk_index", 9999)) if isinstance(x["meta"], dict) else 9999)
        ai_baglam = "\n---\n".join([str(item['text']) for item in combined])
        kaynaklar = [
            {"source": str(cast(dict, c["meta"]).get("dosya", "")), "page": int(cast(dict, c["meta"]).get("sayfa", 0)), "type": str(cast(dict, c["meta"]).get("madde_no", ""))}
            for c in combined if isinstance(c["meta"], dict)
        ]

        # ChatGPT
        # Eksik bilgi tespiti için sistem mesajını güçlendiriyoruz
        system_msg = (
            "Sen bir hukuk asistanısın. Verilen BAĞLAM'a göre SORU'yu yanıtla. "
            "Eğer belgede kritik bilgiler (TC No, IBAN, E-posta, Ad Soyad, Tarih vb.) eksikse "
            "yanıtının sonuna JSON formatında 'MISSING_INFO: [\"alan1\", \"alan2\"]' şeklinde bir not ekle."
        )
        
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"BAĞLAM:\n{ai_baglam}\n\nSORU: {soru}"}
            ],
            temperature=0.3
        )
        
        full_cevap = resp.choices[0].message.content or ""
        cevap = full_cevap
        
        # Önce regex ile GPT'nin kendi cevabındaki notu temizle (varsa)
        match = re.search(r"MISSING_INFO:\s*(\[.*?\])", full_cevap)
        if match:
            cevap = cevap.replace(match.group(0), "").strip()
            
        # [YENİ] Daha güvenilir LangGraph validator_app ile kontrol et
        # Bağlamı ve cevabı birleştirip kontrol ediyoruz
        kontrol_metni = f"{ai_baglam}\n{cevap}"
        missing_fields = await get_missing_info(kontrol_metni)

        return {
            "cevap": cevap, 
            "kaynaklar": kaynaklar,
            "missing_info": missing_fields
        }

    except Exception as e:
        logger.error(f"Hata: {e}")
        raise HTTPException(500, str(e))

# --- EKLENEN KISIM: FOTOĞRAF ENDPOINT ---
@app.post("/sor/fotograf")
async def foto_analiz(file: UploadFile = File(...), soru: str = Form("Bu belgede ne yazıyor?")):
    """
    Frontend'den gelen fotoğrafı okur ve ChatGPT'ye yorumlatır.
    """
    if not client: raise HTTPException(500, "OpenAI API Key yok!")

    req_id = uuid.uuid4().hex[:6]
    logger.info(f"[{req_id}] 📷 Fotoğraf Analizi İsteği: {file.filename}")

    try:
        # 1. Dosyayı Oku
        contents = await file.read()
        
        # 2. OCR İşlemi (OpenCV + EasyOCR)
        # Thread içinde çalıştırıyoruz ki sunucuyu kilitlemesin
        okunan_metin = await run_in_threadpool(goruntu_isleyerek_oku, contents)

        if not okunan_metin or len(okunan_metin.strip()) < 5:
            return {
                "cevap": "Fotoğraftan anlamlı bir metin okunamadı. Lütfen daha net bir fotoğraf yükleyin.",
                "okunan_ham_veri": ""
            }
            
        logger.info(f"[{req_id}] ✅ OCR Başarılı. {len(okunan_metin)} karakter okundu.")

        # 3. ChatGPT Yorumlaması
        prompt = f"""
        Aşağıda bir belgenin fotoğrafından OCR (Optik Karakter Tanıma) ile okunmuş metin var.
        Bu metni kullanarak kullanıcı sorusunu cevapla. Metindeki olası harf hatalarını düzelt.
        
        OCR METNİ:
        {okunan_metin}
        
        KULLANICI SORUSU:
        {soru}
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Sen OCR hatalarını düzelten zeki bir asistansın."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4
        )
        
        ai_cevabi = response.choices[0].message.content
        
        # [YENİ] Fotoğraf analizi sonrası eksik bilgi kontrolü
        missing_info = await get_missing_info(okunan_metin)

        return {
            "cevap": ai_cevabi,
            "okunan_ham_veri": okunan_metin,
            "missing_info": missing_info
        }

    except Exception as e:
        logger.error(f"Fotoğraf Analiz Hatası: {e}")
        raise HTTPException(500, f"İşlem başarısız: {str(e)}")

# --- NOT YÖNETİMİ ---
from fastapi import Header

def get_user_file(user_email: str, filename: str) -> str:
    # E-postadaki özel karakterleri klasör ismine uygun hale getir
    safe_email = user_email.replace('@', '_').replace('.', '_')
    user_dir = os.path.join("data", safe_email)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, filename)

from typing import Optional

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
async def save_history(history_data: List[Any] = Body(...), x_user_email: str = Header(default="default_user")):
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

# --- BİLDİRİM PANEL KISMI ---
@app.get("/api/agent/proactive-search")
async def check_proactive_findings():
    """
    GERÇEK: Merve'nin ajanı çalışır, bulduğu veriyi NOTLARA kaydeder ve bildirim döner.
    """
    # 1. Merve'nin ajanlarını çalıştırıyoruz
    searcher = WebSearcher()
    raw_results = searcher.search("KPSS güncel tarihler 2026")
    
    extractor = TaskExtractor()
    findings = extractor.extract(raw_results)

    bulunanlar_listesi = []
    
    # --- NOTLARI YÜKLE (Eğer dosya yoksa boş liste oluştur) ---
    notes_file = "notes.json"
    if os.path.exists(notes_file):
        with open(notes_file, "r", encoding="utf-8") as f:
            try:
                current_notes = json.load(f)
            except:
                current_notes = []
    else:
        current_notes = []

    # 2. Bulguları işle ve Notlara ekle
    for finding in findings:
        item_id = uuid.uuid4().hex[:8]
        mesaj_metni = f"{finding['title']} bulundu! 🚀 Senin için buldum 👋"
        
        # Frontend'e gidecek obje
        new_entry = {
            "id": item_id,
            "mesaj": mesaj_metni,
            "tarih": finding['date'],
            "tip": "etkinlik"
        }
        bulunanlar_listesi.append(new_entry)

        # --- AYNI NOT VAR MI KONTROL ET VE EKLE ---
        # (Aynı mesajın tekrar tekrar notlara dolmaması için kontrol)
        if not any(n.get('mesaj') == mesaj_metni for n in current_notes):
            current_notes.append({
                "id": item_id,
                "content": mesaj_metni, # Senin not yapına göre 'content' veya 'mesaj' yapabilirsin
                "date": finding['date'],
                "type": "auto-agent"
            })

    # 3. Güncel notları dosyaya geri yaz
    with open(notes_file, "w", encoding="utf-8") as f:
        json.dump(current_notes, f, ensure_ascii=False, indent=4)

    # 4. Senin hazırladığın bildirim iskeletine uygun formatı dön
    return {
        "bulunanlar": bulunanlar_listesi
    }



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


# ==========================================
# AJAN PYDANTIC MODELLERİ
# ==========================================
class TaskRequest(BaseModel):
    metin: str

class ProactiveRequest(BaseModel):
    sohbet_gecmisi: List[str]

class AuditorRequest(BaseModel):
    doc1_text: Optional[str] = None
    doc2_text: Optional[str] = None
    doc1_name: Optional[str] = None
    doc2_name: Optional[str] = None
    filenames: Optional[List[str]] = None # [YENİ]

class ValidatorRequest(BaseModel):
    extracted_text: str

# ==========================================
# AJAN ENDPOINT'LERİ (LangGraph)
# ==========================================

@app.post("/agent/task-extract", tags=["Agents"])
async def extract_task_endpoint(req: TaskRequest):
    """Metinden görev çıkartan LangGraph akışını tetikler."""
    try:
        baslangic_durumu = {"metin": req.metin, "cikarim_sonucu": None, "islem_durumu": "BASLADI"}
        tamamlanmis_durum = task_graph.invoke(baslangic_durumu)
        sonuc_model = tamamlanmis_durum.get("cikarim_sonucu")
        sonuc_dict = sonuc_model.dict() if sonuc_model else None
        return {"success": True, "islem_durumu": tamamlanmis_durum.get("islem_durumu"), "data": sonuc_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Görev çıkarımı sırasında hata: {str(e)}")


@app.post("/agent/proactive-search", tags=["Agents"])
async def proactive_search_endpoint(req: ProactiveRequest):
    """Sohbet geçmişinden ilgi alanı çıkarıp web araması yapar."""
    try:
        baslangic_durumu = {"sohbet_gecmisi": req.sohbet_gecmisi, "ilgi_alanlari": [], "arama_sonuclari": {}}
        sonuc = proactive_graph.invoke(baslangic_durumu)
        return {"success": True, "ilgi_alanlari": sonuc.get("ilgi_alanlari", []), "arama_sonuclari": sonuc.get("arama_sonuclari", {})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proaktif arama sırasında hata: {str(e)}")


@app.post("/agent/audit-documents", tags=["Agents"])
async def audit_documents_endpoint(req: AuditorRequest):
    """Dokümanları karşılaştırarak farklılıkları raporlar."""
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

        # Auditor State'i hazırla (Şimdilik ilk ikisini karşılaştırıyor ama altyapı hazır)
        initial_state = {
            "doc1_text": texts[0]["text"], 
            "doc2_text": texts[1]["text"], 
            "comparison_results": {}, 
            "executive_summary": ""
        }
        
        final_state = await auditor_app.ainvoke(initial_state)
        res = final_state.get("comparison_results", {})
        res["timestamp"] = datetime.datetime.now().isoformat()

        return {"success": True, "comparison_results": res, "executive_summary": final_state.get("executive_summary", "")}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Doküman denetimi sırasında hata: {str(e)}")


@app.post("/agent/validate-document", tags=["Agents"])
async def validate_document_endpoint(req: ValidatorRequest):
    """Belgeyi analiz ederek eksik alanları raporlar."""
    try:
        initial_state = {"extracted_text": req.extracted_text, "validation_results": {}}
        final_state = await validator_app.ainvoke(initial_state)
        return {"success": True, "validation_results": final_state.get("validation_results", {})}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Doküman doğrulaması sırasında hata: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("OCR-RAG Unified API baslatiliyor... port 8000")
    uvicorn.run("main_api:app", host="0.0.0.0", port=8000, reload=True, timeout_keep_alive=300)
