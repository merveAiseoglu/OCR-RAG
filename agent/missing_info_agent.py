import logging
from typing import TypedDict, List, Optional

from pydantic import BaseModel, Field
from openai import RateLimitError, AuthenticationError, APITimeoutError
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

logger = logging.getLogger("MissingInfoAgent")


# ---------------------------------------------------------------------------
# State Definition
# ---------------------------------------------------------------------------
class ValidationState(TypedDict):
    extracted_text: str
    validation_results: dict
    error: Optional[str]


# ---------------------------------------------------------------------------
# Structured Output Schema
# ---------------------------------------------------------------------------
class ValidationResult(BaseModel):
    is_complete: bool = Field(
        description="True if the document has all standard required fields, False otherwise."
    )
    missing_fields: List[str] = Field(
        description="List of missing standard fields (e.g., 'tc_no', 'date'). Empty if is_complete is True."
    )
    document_type: str = Field(
        description="Inferred type of the document (e.g., 'Petition', 'Invoice', 'Application Form')."
    )


# ---------------------------------------------------------------------------
# Retry Decorator
# ---------------------------------------------------------------------------
@retry(
    retry=retry_if_exception_type((RateLimitError, APITimeoutError)),
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),
    reraise=True
)
def _validate_with_llm(extracted_text: str) -> ValidationResult:
    """Retry decorator'lı belge doğrulama çağrısı."""
    logger.debug(f"LLM belge doğrulaması başlatılıyor ({len(extracted_text)} karakter).")
    llm = ChatOpenAI(model="gpt-4o-mini")
    structured_llm = llm.with_structured_output(ValidationResult)

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an intelligent document validator. Your task is to read the extracted text, "
            "infer the type of document it is, and check if any standard required fields for that "
            "document type are missing. Be precise."
        )),
        ("user", "Extracted Document Text:\n{extracted_text}")
    ])

    chain = prompt | structured_llm
    return chain.invoke({"extracted_text": extracted_text})


# ---------------------------------------------------------------------------
# Node Function: Validate Document
# ---------------------------------------------------------------------------
def validate_document(state: ValidationState) -> dict:
    """
    Analyzes the extracted text to infer document type and find missing standard fields.
    On failure, sets error in state and returns partial results instead of crashing.
    """
    logger.info("[validate_document] Belge doğrulaması başlatılıyor.")

    extracted_text = state.get("extracted_text", "")
    if not extracted_text.strip():
        logger.warning("[validate_document] Boş metin geldi — doğrulama atlanıyor.")
        return {
            "validation_results": {},
            "error": "Doğrulanacak metin boş."
        }

    try:
        result = _validate_with_llm(extracted_text)

        # Robust serialization
        if hasattr(result, "model_dump"):
            res_dict = result.model_dump()
        elif hasattr(result, "dict"):
            res_dict = result.dict()
        elif isinstance(result, dict):
            res_dict = result
        else:
            res_dict = dict(result)

        logger.info(
            f"[validate_document] Doğrulama tamamlandı. "
            f"Tür: {res_dict.get('document_type', 'Bilinmiyor')}, "
            f"Tam: {res_dict.get('is_complete', False)}, "
            f"Eksik alanlar: {res_dict.get('missing_fields', [])}"
        )
        return {"validation_results": res_dict, "error": None}

    except RateLimitError:
        logger.error("[validate_document] OpenAI rate limit aşıldı.")
        return {"validation_results": {}, "error": "Rate limit aşıldı — lütfen daha sonra tekrar deneyin."}
    except AuthenticationError:
        logger.error("[validate_document] OpenAI kimlik doğrulama hatası.")
        return {"validation_results": {}, "error": "API kimlik doğrulama hatası."}
    except APITimeoutError:
        logger.error("[validate_document] OpenAI API zaman aşımı.")
        return {"validation_results": {}, "error": "API zaman aşımı — lütfen tekrar deneyin."}
    except Exception as e:
        logger.error(f"[validate_document] Beklenmeyen hata: {e}", exc_info=True)
        return {"validation_results": {}, "error": f"Doğrulama hatası: {str(e)}"}


# ---------------------------------------------------------------------------
# Build the StateGraph
# ---------------------------------------------------------------------------
workflow = StateGraph(ValidationState)
workflow.add_node("validate_document", validate_document)
workflow.add_edge(START, "validate_document")
workflow.add_edge("validate_document", END)

validator_app = workflow.compile()
