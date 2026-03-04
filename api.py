"""
OCR RAG API v3.9 - Final Tam Sürüm
Özellikler:
1. OpenAI (ChatGPT) Entegrasyonu
2. PDF RAG Sistemi (Vektör Arama)
3. Fotoğraf Analizi (OpenCV + EasyOCR + GPT) -> EKLENDİ
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import time
import logging
import re
import math
import io
import uuid 
import shutil
import numpy as np # Resim işleme için
import cv2 # OpenCV

# --- OPENAI ENTEGRASYONU ---
from openai import OpenAI
from dotenv import load_dotenv

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
load_dotenv()
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

app = FastAPI(title="OCR RAG API", version="3.9")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    logger.info("🎬 SİSTEM BAŞLATILIYOR...")
    state.ocr_reader = easyocr.Reader(['tr', 'en'], gpu=False)
    state.embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    
    state.chroma_client = chromadb.PersistentClient(path=state.db_path)
    state.collection = state.chroma_client.get_or_create_collection(
        name="hukuk_dokumanlari",
        embedding_function=MyEmbeddingFunction(state.embedding_model),
        metadata={"hnsw:space": "cosine"}
    )
    os.makedirs(state.documents_folder, exist_ok=True)
    logger.info(f"✅ SİSTEM HAZIR. Koleksiyondaki belge sayısı: {state.collection.count()}")

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
                okunan = state.ocr_reader.readtext(roi, detail=0)
                if okunan:
                    bulunan_metinler.append(" ".join(okunan))
            except: pass
        
        # Eğer OpenCV yöntemiyle hiçbir şey çıkmazsa, resmi düz okumayı dene (Fallback)
        if not bulunan_metinler:
            return " ".join(state.ocr_reader.readtext(img, detail=0))

        return "\n".join(bulunan_metinler)
        
    except Exception as e:
        logger.error(f"OCR İşleme Hatası: {e}")
        return ""

# ==========================================
# 2. PDF PARÇALAMA MANTIĞI
# ==========================================
def pdf_ocr_yap_advanced(pdf_path: str) -> Dict[int, str]:
    doc = fitz.open(pdf_path)
    sayfa_metinleri = {}
    for sayfa_no in range(len(doc)):
        sayfa = doc[sayfa_no]
        metin = sayfa.get_text()
        if not metin or len(metin.strip()) < 100:
            try:
                pix = sayfa.get_pixmap(matrix=fitz.Matrix(3, 3))
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                ocr_res = state.ocr_reader.readtext(img, detail=0, paragraph=True)
                metin = " ".join(ocr_res)
            except Exception as e:
                logger.error(f"OCR Hatası (Sayfa {sayfa_no+1}): {e}")
        sayfa_metinleri[sayfa_no + 1] = metin or ""
    return sayfa_metinleri

def chunking_logic(metin: str, sayfa_no: int, dosya_adi: str, baslangic_index: int) -> List[Dict]:
    chunks = []
    regex = r'(?:^|\n|\s)(\d+)[\.\)\-\s]\s+([A-ZİĞÜŞÖÇ].+)'
    maddeler = list(re.finditer(regex, metin))
    
    if not maddeler:
        words = metin.split()
        for i in range(0, len(words), 300):
            t = " ".join(words[i:i+400])
            if len(t) > 20:
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

# ==========================================
# 3. ENDPOINTS
# ==========================================
class SoruModel(BaseModel):
    soru: str
    top_k: Optional[int] = 10 

@app.post("/yukle")
async def yukle(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(400, "Sadece PDF.")
    
    path = os.path.join(state.documents_folder, file.filename)
    try:
        try:
            old_data = state.collection.get(where={"dosya": file.filename})
            if old_data and old_data['ids']:
                state.collection.delete(ids=old_data['ids'])
        except: pass

        async with aiofiles.open(path, 'wb') as f:
            await f.write(await file.read())
            
        chunks = await run_in_threadpool(worker_process, path, file.filename)
        
        if chunks:
            ids = [f"{file.filename}_{c['metadata']['chunk_index']}_{uuid.uuid4().hex[:6]}" for c in chunks]
            docs = [c["metin"] for c in chunks]
            metas = [metadata_temizle(c["metadata"]) for c in chunks]
            state.collection.add(ids=ids, documents=docs, metadatas=metas)
            
        return {"success": True, "mesaj": f"Yüklendi: {len(chunks)} parça.", "chunk_sayisi": len(chunks)}
    except Exception as e:
        logger.error(f"Yükleme Hatası: {e}")
        return JSONResponse(500, {"detail": str(e)})

@app.post("/sor")
async def soru_sor(req: SoruModel):
    if not client: raise HTTPException(500, "OpenAI API Key yok!")
    
    soru = req.soru.strip()
    if not soru or len(soru) < 3: return {"cevap": "Geçersiz soru.", "kaynaklar": []}

    try:
        # Vektör Arama
        results = state.collection.query(query_texts=[soru], n_results=req.top_k)
        if not results['documents'] or not results['documents'][0]:
             return {"cevap": "Bilgi bulunamadı.", "kaynaklar": []}

        # Filtreleme
        raw_docs, raw_metas, raw_dists = results['documents'][0], results['metadatas'][0], results['distances'][0]
        en_iyi_skor = 1 - raw_dists[0]
        dinamik_esik = en_iyi_skor * 0.85 if en_iyi_skor > 0.75 else max(en_iyi_skor * 0.70, 0.30)

        combined = []
        for doc, meta, dist in zip(raw_docs, raw_metas, raw_dists):
            if (1 - dist) >= dinamik_esik:
                combined.append({"text": doc, "meta": meta})

        if not combined: return {"cevap": "Yeterli eşleşme yok.", "kaynaklar": []}

        # Context Hazırla
        combined.sort(key=lambda x: x["meta"].get("chunk_index", 9999))
        ai_baglam = "\n---\n".join([item['text'] for item in combined])
        kaynaklar = [{"source": c["meta"].get("dosya"), "page": c["meta"].get("sayfa"), "type": c["meta"].get("madde_no")} for c in combined]

        # ChatGPT
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Sen hukuk asistanısın. Bağlamı kullanarak cevapla."},
                {"role": "user", "content": f"BAĞLAM:\n{ai_baglam}\n\nSORU: {soru}"}
            ],
            temperature=0.3
        )
        return {"cevap": resp.choices[0].message.content, "kaynaklar": kaynaklar}

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

        return {
            "cevap": ai_cevabi,
            "okunan_ham_veri": okunan_metin # Frontend isterse ham halini de gösterebilir
        }

    except Exception as e:
        logger.error(f"Fotoğraf Analiz Hatası: {e}")
        raise HTTPException(500, f"İşlem başarısız: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=300)