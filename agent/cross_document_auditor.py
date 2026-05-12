from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

class AuditorChange(BaseModel):
    type: str = Field(description="ekleme, silme, degisiklik veya risk")
    title: str = Field(description="Kısa başlık")
    description: str = Field(description="Detaylı açıklama")
    severity: str = Field(description="low, medium veya high")

class AuditorResult(BaseModel):
    risk_score: int = Field(description="0-10 arası risk skoru")
    executive_summary: str = Field(description="Yönetici özeti")
    changes: List[AuditorChange] = Field(description="Değişikliklerin listesi")
    missing_clauses: List[str] = Field(description="Eksik maddelerin listesi")

class AuditorState(TypedDict):
    doc1_text: str
    doc2_text: str
    comparison_results: dict
    executive_summary: str

def audit_documents(state: AuditorState):
    """
    İki dokümanı karşılaştırarak farklılıkları ve riskleri analiz eder.
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2)
    structured_llm = llm.with_structured_output(AuditorResult)
    
    prompt = f"""
    Sen kıdemli bir hukuk denetçisisin. Aşağıdaki iki belge metnini karşılaştır. 
    Birinci belge (REFERANS) ile ikinci belgeyi (YENİ) karşılaştırarak aradaki farkları, 
    eklenen/silinen maddeleri ve risk teşkil eden değişiklikleri raporla.
    
    REFERANS BELGE:
    {state['doc1_text'][:8000]}
    
    YENİ BELGE:
    {state['doc2_text'][:8000]}
    
    Lütfen sonuçları structured formatta dön. Risk skorunu 0 (güvenli) ile 10 (kritik) arasında belirle.
    """
    
    result = structured_llm.invoke(prompt)
    return {
        "comparison_results": {
            "risk_score": result.risk_score,
            "executive_summary": result.executive_summary,
            "changes": [c.dict() for c in result.changes],
            "missing_clauses": result.missing_clauses
        },
        "executive_summary": result.executive_summary
    }

workflow = StateGraph(AuditorState)
workflow.add_node("auditor", audit_documents)
workflow.set_entry_point("auditor")
workflow.add_edge("auditor", END)

auditor_app = workflow.compile()
