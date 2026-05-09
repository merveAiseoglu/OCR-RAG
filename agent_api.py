import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# Çevre değişkenlerini yükleyelim (graph kurulumlarında gerekiyor olabilir)
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

# LangGraph akışlarımızı (Agent'ları) içe aktaralım
# Agent 1: Metinden görev çıkaran akış (graph_builder.py)
from agent.graph_builder import graph as task_graph, AgentState
from agent.task_extractor import CikartmaSonucu # Çıktıyı modellemek için yararlı olabilir

# Agent 2: Sohbet geçmişinden ilgi alanı çıkarıp arayan proaktif akış (proactive_graph.py)
from agent.proactive_graph import graph as proactive_graph, ProactiveState

# Agent 3: Çapraz Doküman Denetçisi (cross_document_auditor.py)
from agent.cross_document_auditor import auditor_app

# Agent 4: Dinamik Eksik Bilgi Denetçisi (missing_info_agent.py)
from agent.missing_info_agent import validator_app

# FastAPI uygulamasını başlatalım
app = FastAPI(
    title="LangGraph Agent API", 
    version="1.0",
    description="LangGraph akışlarını dışa açan FastAPI sunucusu"
)

# CORS Ayarları (Web arayüzünden doğrudan erişim için gerekli)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Prod ortamında spesifik origin'ler verilmeli (örn: http://localhost:3000)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Modelleri (Gelen İstekler İçin) ---

class TaskRequest(BaseModel):
    metin: str

class ProactiveRequest(BaseModel):
    sohbet_gecmisi: List[str]

class AuditorRequest(BaseModel):
    doc1_text: str
    doc2_text: str

class ValidatorRequest(BaseModel):
    extracted_text: str

# --- Endpoints ---

@app.post("/agent/task-extract")
async def extract_task_endpoint(req: TaskRequest):
    """
    Kullanıcının girdiği metinden görevleri (task) çıkartan langgraph akışını tetikler.
    """
    try:
        # graph_builder.py içindeki baslangic_durumu formatı
        baslangic_durumu = {
            "metin": req.metin,
            "cikarim_sonucu": None,
            "islem_durumu": "BAŞLADI"
        }
        
        # LangGraph invoke() senkron çalışır. Eğer ağır bloklayan bir akış ise
        # fastapi.concurrency.run_in_threadpool kullanılabilir.
        tamamlanmis_durum = task_graph.invoke(baslangic_durumu)
        
        # cikarim_sonucu bir Pydantic modeli olduğu için serialize etmek için dict() alabiliriz
        sonuc_model = tamamlanmis_durum.get("cikarim_sonucu")
        sonuc_dict = sonuc_model.dict() if sonuc_model else None
        
        return {
            "success": True,
            "islem_durumu": tamamlanmis_durum.get("islem_durumu"),
            "data": sonuc_dict
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Görev çıkarımı sırasında hata: {str(e)}")


@app.post("/agent/proactive-search")
async def proactive_search_endpoint(req: ProactiveRequest):
    """
    Sohbet geçmişini alıp kullanıcının ilgi alanlarını çıkaran
    ve eğer ilgi alanı varsa web'de arayıp sonuç döndüren LangGraph akışını tetikler.
    """
    try:
        # proactive_graph.py içindeki baslangic_durumu formatı
        baslangic_durumu = {
            "sohbet_gecmisi": req.sohbet_gecmisi,
            "ilgi_alanlari": [],
            "arama_sonuclari": {}
        }
        
        sonuc = proactive_graph.invoke(baslangic_durumu)
        
        return {
            "success": True,
            "ilgi_alanlari": sonuc.get("ilgi_alanlari", []),
            "arama_sonuclari": sonuc.get("arama_sonuclari", {})
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proaktif arama sırasında hata: {str(e)}")


@app.post("/agent/audit-documents")
async def audit_documents_endpoint(req: AuditorRequest):
    """
    İki dokümanı karşılaştırarak farklılıkları, eksiklikleri ve riskleri raporlayan LangGraph akışını tetikler.
    """
    try:
        initial_state = {
            "doc1_text": req.doc1_text,
            "doc2_text": req.doc2_text,
            "comparison_results": {},
            "executive_summary": ""
        }
        
        # ainvoke() ile asenkron grafiği çalıştır
        final_state = await auditor_app.ainvoke(initial_state)
        
        return {
            "success": True,
            "comparison_results": final_state.get("comparison_results", {}),
            "executive_summary": final_state.get("executive_summary", "")
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Doküman denetimi sırasında hata oluştu: {str(e)}")


@app.post("/agent/validate-document")
async def validate_document_endpoint(req: ValidatorRequest):
    """
    Belgeden çıkarılan metni analiz ederek doküman türünü belirler ve eksik alanları raporlayan LangGraph akışını tetikler.
    """
    try:
        initial_state = {
            "extracted_text": req.extracted_text,
            "validation_results": {}
        }
        
        # ainvoke() ile asenkron grafiği çalıştır
        final_state = await validator_app.ainvoke(initial_state)
        
        return {
            "success": True,
            "validation_results": final_state.get("validation_results", {})
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Doküman doğrulaması sırasında hata oluştu: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    # Doğrudan python agent_api.py ile çalıştırmak isterseniz
    print("🚀 LangGraph API Sunucusu başlatılıyor... (http://localhost:8001)")
    uvicorn.run("agent_api:app", host="0.0.0.0", port=8001, reload=True)
