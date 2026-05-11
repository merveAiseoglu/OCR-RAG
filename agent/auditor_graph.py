from typing import TypedDict, List
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

class ComparisonResult(BaseModel):
    degisen_maddeler: List[str] = Field(description="Orijinal belgeye göre ikinci belgede değiştirilmiş, eklenmiş veya farklı yazılmış maddeler/cümleler.")
    fiyat_farklari: List[str] = Field(description="Varsa iki belge arasındaki tutar, oran veya fiyat uyuşmazlıkları.")
    eksik_maddeler: List[str] = Field(description="İlk belgede olup ikinci belgede tamamen çıkarılmış/unutulmuş kısımlar.")
    risk_skoru: int = Field(description="1 ile 10 arasında, bu farklılıkların yaratabileceği risk seviyesi.")

class AuditorState(TypedDict):
    doc1_text: str
    doc2_text: str
    differences: dict
    status: str

def compare_documents(state: AuditorState):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    structured_llm = llm.with_structured_output(ComparisonResult)
    
    system_prompt = "Sen uzman bir kurumsal denetmensin (Auditor). Görevin, sana verilen 'Orijinal Belge' ile 'Yeni Belge' metinlerini inceleyip aralarındaki farklılıkları, eksiklikleri ve riskleri bulmaktır. Asla kendi yorumunu katma, sadece metinlerdeki somut uyuşmazlıkları tespit et."
    
    human_prompt = f"Orijinal Belge:\n{state['doc1_text']}\n\nYeni Belge:\n{state['doc2_text']}"
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt)
    ]
    
    result = structured_llm.invoke(messages)
    
    return {"differences": result.model_dump(), "status": "compared"}

def generate_report(state: AuditorState):
    # Rapor oluşturma mantığı buraya gelecek
    pass

# Grafiği oluştur
builder = StateGraph(AuditorState)

# Düğümleri ekle
builder.add_node("compare_documents", compare_documents)
builder.add_node("generate_report", generate_report)

# Kenarları (edges) bağla
builder.add_edge(START, "compare_documents")
builder.add_edge("compare_documents", "generate_report")
builder.add_edge("generate_report", END)

# Grafiği derle
app = builder.compile()
