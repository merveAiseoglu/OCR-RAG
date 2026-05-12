import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv, find_dotenv
from openai import RateLimitError, AuthenticationError, APITimeoutError
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

load_dotenv(find_dotenv(), override=True)

from agent.graph_builder import graph as task_graph, AgentState, graph_invoke_with_timeout
from agent.task_extractor import CikartmaSonucu
from agent.proactive_graph import graph as proactive_graph, ProactiveState
from agent.cross_document_auditor import auditor_app
from agent.missing_info_agent import validator_app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s — %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("AgentAPI")

app = FastAPI(
    title="LangGraph Agent API",
    version="2.0",
    description="LangGraph akışlarını dışa açan FastAPI sunucusu"
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
    logger.error(f"Yakalanmamış hata: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": True, "message": str(exc), "code": 500}
    )


# ─── Pydantic Modelleri ───────────────────────────────────────────────────────
class TaskRequest(BaseModel):
    metin: str

class ProactiveRequest(BaseModel):
    sohbet_gecmisi: List[str]

class AuditorRequest(BaseModel):
    doc1_text: str
    doc2_text: str

class ValidatorRequest(BaseModel):
    extracted_text: str


# ─── Endpoints ────────────────────────────────────────────────────────────────
@app.post("/agent/task-extract")
async def extract_task_endpoint(req: TaskRequest):
    logger.info(f"/agent/task-extract isteği alındı ({len(req.metin)} karakter).")
    try:
        baslangic = {
            "metin": req.metin,
            "cikarim_sonucu": None,
            "islem_durumu": "BAŞLADI",
            "error": None
        }
        tamamlanmis = graph_invoke_with_timeout(baslangic, timeout=30)

        if tamamlanmis.get("error"):
            logger.warning(f"Agent hata ile tamamlandı: {tamamlanmis['error']}")
            return JSONResponse(
                status_code=500,
                content={"error": True, "message": tamamlanmis["error"], "code": 500}
            )

        sonuc_model = tamamlanmis.get("cikarim_sonucu")
        sonuc_dict = sonuc_model.dict() if sonuc_model else None
        logger.info("Görev çıkarımı başarıyla tamamlandı.")
        return {
            "success": True,
            "islem_durumu": tamamlanmis.get("islem_durumu"),
            "data": sonuc_dict
        }
    except TimeoutError as e:
        logger.error(f"Timeout: {e}")
        raise HTTPException(status_code=504, detail=str(e))
    except RateLimitError:
        logger.error("OpenAI rate limit aşıldı.")
        raise HTTPException(status_code=429, detail="OpenAI rate limit aşıldı. Lütfen bekleyin.")
    except AuthenticationError:
        logger.error("OpenAI kimlik doğrulama hatası.")
        raise HTTPException(status_code=401, detail="OpenAI API kimlik hatası.")
    except APITimeoutError:
        logger.error("OpenAI API zaman aşımı.")
        raise HTTPException(status_code=504, detail="OpenAI API zaman aşımı.")
    except Exception as e:
        logger.error(f"Görev çıkarımı hatası: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Görev çıkarımı sırasında hata: {str(e)}")


@app.post("/agent/proactive-search")
async def proactive_search_endpoint(req: ProactiveRequest):
    logger.info(f"/agent/proactive-search isteği alındı ({len(req.sohbet_gecmisi)} mesaj).")
    try:
        baslangic = {
            "sohbet_gecmisi": req.sohbet_gecmisi,
            "ilgi_alanlari": [],
            "arama_sonuclari": {},
            "error": None
        }
        sonuc = proactive_graph.invoke(baslangic)
        if sonuc.get("error"):
            logger.warning(f"Proaktif arama hata ile tamamlandı: {sonuc['error']}")
        logger.info("Proaktif arama tamamlandı.")
        return {
            "success": True,
            "ilgi_alanlari": sonuc.get("ilgi_alanlari", []),
            "arama_sonuclari": sonuc.get("arama_sonuclari", {}),
            "error": sonuc.get("error")
        }
    except RateLimitError:
        raise HTTPException(status_code=429, detail="OpenAI rate limit aşıldı.")
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="OpenAI API kimlik hatası.")
    except APITimeoutError:
        raise HTTPException(status_code=504, detail="OpenAI API zaman aşımı.")
    except Exception as e:
        logger.error(f"Proaktif arama hatası: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Proaktif arama sırasında hata: {str(e)}")


@app.post("/agent/audit-documents")
async def audit_documents_endpoint(req: AuditorRequest):
    logger.info("/agent/audit-documents isteği alındı.")
    try:
        initial_state = {
            "doc1_text": req.doc1_text,
            "doc2_text": req.doc2_text,
            "comparison_results": {},
            "executive_summary": "",
            "error": None
        }
        final_state = await auditor_app.ainvoke(initial_state)

        if final_state.get("error"):
            logger.warning(f"Denetim hata ile tamamlandı: {final_state['error']}")
            return JSONResponse(
                status_code=500,
                content={"error": True, "message": final_state["error"], "code": 500}
            )

        logger.info("Doküman denetimi başarıyla tamamlandı.")
        return {
            "success": True,
            "comparison_results": final_state.get("comparison_results", {}),
            "executive_summary": final_state.get("executive_summary", "")
        }
    except RateLimitError:
        raise HTTPException(status_code=429, detail="OpenAI rate limit aşıldı.")
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="OpenAI API kimlik hatası.")
    except APITimeoutError:
        raise HTTPException(status_code=504, detail="OpenAI API zaman aşımı.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Doküman denetimi hatası: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Doküman denetimi sırasında hata: {str(e)}")


@app.post("/agent/validate-document")
async def validate_document_endpoint(req: ValidatorRequest):
    logger.info("/agent/validate-document isteği alındı.")
    try:
        initial_state = {
            "extracted_text": req.extracted_text,
            "validation_results": {},
            "error": None
        }
        final_state = await validator_app.ainvoke(initial_state)

        if final_state.get("error"):
            logger.warning(f"Doğrulama hata ile tamamlandı: {final_state['error']}")
            return JSONResponse(
                status_code=500,
                content={"error": True, "message": final_state["error"], "code": 500}
            )

        logger.info("Belge doğrulaması başarıyla tamamlandı.")
        return {
            "success": True,
            "validation_results": final_state.get("validation_results", {})
        }
    except RateLimitError:
        raise HTTPException(status_code=429, detail="OpenAI rate limit aşıldı.")
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="OpenAI API kimlik hatası.")
    except APITimeoutError:
        raise HTTPException(status_code=504, detail="OpenAI API zaman aşımı.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Belge doğrulama hatası: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Belge doğrulaması sırasında hata: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 LangGraph Agent API başlatılıyor (http://localhost:8001)")
    uvicorn.run("agent_api:app", host="0.0.0.0", port=8001, reload=True)
