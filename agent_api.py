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


if __name__ == "__main__":
    import uvicorn
    # Doğrudan python agent_api.py ile çalıştırmak isterseniz
    print("🚀 LangGraph API Sunucusu başlatılıyor... (http://localhost:8001)")
    uvicorn.run("agent_api:app", host="0.0.0.0", port=8001, reload=True)
