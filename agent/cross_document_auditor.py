import logging
from typing import TypedDict, List, Optional

from pydantic import BaseModel, Field
from openai import RateLimitError, AuthenticationError, APITimeoutError
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

logger = logging.getLogger("CrossDocumentAuditor")


# ---------------------------------------------------------------------------
# State Definition
# ---------------------------------------------------------------------------
class AuditorState(TypedDict):
    doc1_text: str
    doc2_text: str
    comparison_results: dict
    executive_summary: str
    error: Optional[str]


# ---------------------------------------------------------------------------
# Structured Output Schema
# ---------------------------------------------------------------------------
class ComparisonResult(BaseModel):
    changed_clauses: List[str] = Field(
        description="Clauses that were altered between doc1 and doc2."
    )
    discrepancies: List[str] = Field(
        description="Mismatches in prices, ratios, or dates."
    )
    missing_sections: List[str] = Field(
        description="Parts present in doc1 but missing in doc2."
    )
    risk_score: int = Field(
        description="A score from 1 to 10 indicating the level of risk/discrepancy."
    )


# ---------------------------------------------------------------------------
# Retry Decorators
# ---------------------------------------------------------------------------
@retry(
    retry=retry_if_exception_type((RateLimitError, APITimeoutError)),
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),
    reraise=True
)
def _compare_with_llm(doc1_text: str, doc2_text: str) -> ComparisonResult:
    """Retry decorator'lı doküman karşılaştırma çağrısı."""
    logger.debug("LLM doküman karşılaştırması başlatılıyor.")
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    structured_llm = llm.with_structured_output(ComparisonResult)

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an analytical auditor. Your task is to strictly compare two versions of a document "
            "and identify changed clauses, discrepancies (like prices, ratios, or dates), and missing sections. "
            "Provide a risk score from 1 to 10 based on the severity of the differences."
        )),
        ("user", "Please compare the following documents.\n\nDocument 1:\n{doc1_text}\n\nDocument 2:\n{doc2_text}")
    ])

    chain = prompt | structured_llm
    return chain.invoke({"doc1_text": doc1_text, "doc2_text": doc2_text})


@retry(
    retry=retry_if_exception_type((RateLimitError, APITimeoutError)),
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),
    reraise=True
)
def _summarize_with_llm(comparison_results: dict) -> str:
    """Retry decorator'lı özet üretme çağrısı."""
    logger.debug("LLM özet üretimi başlatılıyor.")
    llm = ChatOpenAI(model="gpt-4o-mini")

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an executive assistant. Your task is to write a concise 2-3 sentence executive summary "
            "for top management based on document comparison results. Ensure you mention the risk score "
            "and major discrepancies/changes clearly."
        )),
        ("user", "Comparison Results:\n{comparison_results}")
    ])

    chain = prompt | llm
    result = chain.invoke({"comparison_results": comparison_results})
    return str(result.content)


# ---------------------------------------------------------------------------
# Node Function 1: Compare Documents
# ---------------------------------------------------------------------------
def compare_documents(state: AuditorState) -> dict:
    """
    Compares two document texts using gpt-4o with structured output.
    On failure, sets error in state and returns empty results instead of crashing.
    """
    logger.info("[compare_documents] Doküman karşılaştırması başlatılıyor.")
    try:
        result = _compare_with_llm(state["doc1_text"], state["doc2_text"])

        if hasattr(result, "model_dump"):
            comp_res = result.model_dump()
        elif hasattr(result, "dict"):
            comp_res = result.dict()
        elif isinstance(result, dict):
            comp_res = result
        else:
            comp_res = dict(result)

        logger.info(f"[compare_documents] Karşılaştırma tamamlandı. Risk skoru: {comp_res.get('risk_score', 'N/A')}")
        return {"comparison_results": comp_res, "error": None}

    except RateLimitError:
        logger.error("[compare_documents] OpenAI rate limit aşıldı.")
        return {"comparison_results": {}, "error": "Rate limit aşıldı — lütfen daha sonra tekrar deneyin."}
    except AuthenticationError:
        logger.error("[compare_documents] OpenAI kimlik doğrulama hatası.")
        return {"comparison_results": {}, "error": "API kimlik doğrulama hatası."}
    except APITimeoutError:
        logger.error("[compare_documents] OpenAI API zaman aşımı.")
        return {"comparison_results": {}, "error": "API zaman aşımı — lütfen tekrar deneyin."}
    except Exception as e:
        logger.error(f"[compare_documents] Beklenmeyen hata: {e}", exc_info=True)
        return {"comparison_results": {}, "error": f"Karşılaştırma hatası: {str(e)}"}


# ---------------------------------------------------------------------------
# Node Function 2: Generate Summary
# ---------------------------------------------------------------------------
def generate_summary(state: AuditorState) -> dict:
    """
    Reads the comparison results and generates an executive summary.
    If a previous error exists or results are empty, returns early.
    """
    logger.info("[generate_summary] Özet üretimi başlatılıyor.")

    # Önceki node'da hata varsa özetlemeye gerek yok
    if state.get("error"):
        logger.warning(f"[generate_summary] Önceki hata nedeniyle özet atlanıyor: {state['error']}")
        return {"executive_summary": f"Özet üretilemedi: {state['error']}"}

    if not state.get("comparison_results"):
        logger.warning("[generate_summary] Karşılaştırma sonucu boş — özet atlanıyor.")
        return {"executive_summary": "Karşılaştırma sonucu bulunamadı, özet üretilemedi."}

    try:
        summary = _summarize_with_llm(state["comparison_results"])
        logger.info("[generate_summary] Özet başarıyla üretildi.")
        return {"executive_summary": summary}

    except RateLimitError:
        logger.error("[generate_summary] OpenAI rate limit aşıldı.")
        return {"executive_summary": "Özet üretilemedi: Rate limit aşıldı."}
    except AuthenticationError:
        logger.error("[generate_summary] OpenAI kimlik doğrulama hatası.")
        return {"executive_summary": "Özet üretilemedi: API kimlik hatası."}
    except APITimeoutError:
        logger.error("[generate_summary] OpenAI zaman aşımı.")
        return {"executive_summary": "Özet üretilemedi: Zaman aşımı."}
    except Exception as e:
        logger.error(f"[generate_summary] Beklenmeyen hata: {e}", exc_info=True)
        return {"executive_summary": f"Özet üretilemedi: {str(e)}"}


# ---------------------------------------------------------------------------
# Build the StateGraph
# ---------------------------------------------------------------------------
workflow = StateGraph(AuditorState)

workflow.add_node("compare_documents", compare_documents)
workflow.add_node("generate_summary", generate_summary)

workflow.add_edge(START, "compare_documents")
workflow.add_edge("compare_documents", "generate_summary")
workflow.add_edge("generate_summary", END)

auditor_app = workflow.compile()
