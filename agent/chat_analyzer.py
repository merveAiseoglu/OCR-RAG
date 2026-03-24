import os
from typing import List
from pydantic import BaseModel, Field
from dotenv import load_dotenv, find_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

class KullaniciProfili(BaseModel):
    ilgi_alanlari: List[str] = Field(description="Kullanıcının güncel ilgi alanları, hedefleri veya uğraştığı sorunlar")

def ilgi_alanlarini_cikar(sohbet_gecmisi: List[str]) -> KullaniciProfili:
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    structured_llm = llm.with_structured_output(KullaniciProfili)
    
    system_prompt = (
        "Sen bir profil analiz uzmanısın. Sana verilen kullanıcı sohbet geçmişini incele "
        "ve kullanıcının güncel ilgi alanlarını, hazırlandığı sınavları, kariyer hedeflerini "
        "veya günlük hayatta çözmeye çalıştığı sorunları kısa anahtar kelimeler/kısa cümleler halinde listele."
    )
    
    gecmis_metni = "\n".join([f"- {mesaj}" for mesaj in sohbet_gecmisi])
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Aşağıdaki sohbet geçmişini analiz et:\n{gecmis_metni}")
    ])
    
    chain = prompt | structured_llm
    
    return chain.invoke({"gecmis_metni": gecmis_metni})

if __name__ == "__main__":
    load_dotenv(find_dotenv(), override=True)
    
    test_gecmisi = [
        'İngilizce B2 seviyesine gelmek için çalışıyorum, bir yandan da Vodafone ve Garanti BBVA sınavlarına hazırlanıyorum.', 
        'Son zamanlarda sağlıklı yulaf tarifleri deniyorum. Bir de çelik termosumdaki kahve lekelerini nasıl temizlerim?'
    ]
    
    profil = ilgi_alanlarini_cikar(test_gecmisi)
    
    print("\n💡 Tespit Edilen İlgi Alanları ve Hedefler:")
    print("-" * 45)
    for ilgi_alani in profil.ilgi_alanlari:
        print(f"• {ilgi_alani}")
    print("-" * 45 + "\n")
