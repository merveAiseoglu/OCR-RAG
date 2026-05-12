import os
from typing import TypedDict, List
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

# Durum şeması
class ValidationState(TypedDict):
    extracted_text: str
    validation_results: dict

# Çıktı şeması
class ValidationResult(BaseModel):
    missing_fields: List[str] = Field(description="Belgede eksik olan veya doğrulanması gereken alanlar (örn: TC Kimlik No, Tarih, İmza)")
    is_complete: bool = Field(description="Belge tam mı?")
    suggestions: str = Field(description="Eksiklerin nasıl giderileceğine dair kısa öneri")

def validate_document(state: ValidationState):
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(ValidationResult)
    
    prompt = (
        "Sen bir belge denetçisisin. Sana verilen metni incele ve şu alanların eksik olup olmadığını kontrol et: "
        "TC Kimlik No, Ad Soyad, Tarih, IBAN, E-posta, Telefon. "
        "Eksik olanları listele. Eğer metin çok kısaysa veya anlamsızsa kritik her şeyin eksik olduğunu belirt.\n\n"
        f"METİN:\n{state['extracted_text']}"
    )
    
    result = structured_llm.invoke(prompt)
    return {"validation_results": result.dict()}

# Graph kurulumu
workflow = StateGraph(ValidationState)
workflow.add_node("validator", validate_document)
workflow.set_entry_point("validator")
workflow.add_edge("validator", END)

validator_app = workflow.compile()
