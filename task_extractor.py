from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing import List, Optional
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
import os
from action_manager import takvime_ekle


load_dotenv(find_dotenv(), override=True)

api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    print(f"✅ API Anahtarı başarıyla yüklendi! (Sonu: ...{api_key[-4:]})\n")
else:
    print("❌ DİKKAT: .env dosyası veya içindeki OPENAI_API_KEY bulunamadı!\n")

# --- ÇIKTI FORMATI ---
class Gorev(BaseModel):
    baslik: str = Field(description="Görevin kısa başlığı")
    sorumlu: Optional[str] = Field(description="Sorumlu kişi veya kurum, yoksa null")
    son_tarih: Optional[str] = Field(description="Son tarih, yoksa null")

class CikartmaSonucu(BaseModel):
    gorevler: List[Gorev] = Field(description="Metinden çıkarılan görevler listesi")
    onemli_tarihler: List[str] = Field(description="Metinde geçen önemli tarihler")
    konular: List[str] = Field(description="Metnin ana konuları, ilgi alanları")

# --- LLM KURULUMU ---
llm = ChatOpenAI(
    model="gpt-4o",
    api_key=api_key, # Artık os.getenv ile güvenle alıyoruz
    temperature=0
)

# Structured output — LLM direkt Pydantic objesi döndürür
structured_llm = llm.with_structured_output(CikartmaSonucu)

# --- PROMPT ---
prompt = ChatPromptTemplate.from_messages([
    ("system", """Sen bir belge analiz uzmanısın.
Sana verilen metinden şunları çıkar:
- Yapılması gereken görevler ve sorumlular
- Önemli tarihler (başvuru, teslim, toplantı vb.)
- Metnin ana konuları (örn: KOSGEB, ihale, kira, proje)

Eğer bir bilgi yoksa null bırak."""),
    ("human", "Aşağıdaki metni analiz et:\n\n{metin}")
])

# --- CHAIN ---
chain = prompt | structured_llm

# --- ANA FONKSİYON ---
def metinden_cikar(metin: str) -> CikartmaSonucu:
    """OCR'dan gelen metni alır, görev ve tarihleri çıkarır."""
    sonuc = chain.invoke({"metin": metin})
    
    # --- YENİ EKLENEN KISIM: Görevleri aksiyon yöneticisine gönder ---
    takvime_ekle(sonuc.gorevler)
    
    return sonuc

# --- TEST ---
if __name__ == "__main__":
    # Mock OCR metni — gerçek OCR beklemeden test ediyoruz
    test_metni = """
    KOSGEB Girişimcilik Destek Programı Başvuru Duyurusu
    
    Başvuru tarihi: 15 Mart 2025
    Son başvuru tarihi: 30 Nisan 2025
    
    Başvuru sahiplerinin aşağıdaki belgeleri teslim etmesi gerekmektedir:
    - İş planı hazırlanacak (Sorumlu: Başvuru sahibi)
    - Nüfus cüzdanı fotokopisi eklenecek
    - Mali tablolar muhasebeci onaylı olacak (Sorumlu: Mali müşavir)
    
    Değerlendirme toplantısı: 15 Mayıs 2025
    Sonuç açıklaması: 1 Haziran 2025
    """

    print("🔍 Metin analiz ediliyor...\n")
    sonuc = metinden_cikar(test_metni)

    print("📋 GÖREVLER:")
    for g in sonuc.gorevler:
        print(f"  - {g.baslik} | Sorumlu: {g.sorumlu} | Tarih: {g.son_tarih}")

    print("\n📅 ÖNEMLİ TARİHLER:")
    for t in sonuc.onemli_tarihler:
        print(f"  - {t}")

    print("\n🏷️ KONULAR:")
    for k in sonuc.konular:
        print(f"  - {k}")