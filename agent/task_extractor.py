import logging
import os
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
from openai import RateLimitError, AuthenticationError, APITimeoutError
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger("TaskExtractor")

load_dotenv(find_dotenv(), override=True)

api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    logger.info(f"API Anahtarı başarıyla yüklendi! (Sonu: ...{api_key[-4:]})")
else:
    logger.warning("OPENAI_API_KEY bulunamadı! .env dosyanızı kontrol edin.")


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
    api_key=api_key,
    temperature=0
)

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


# --- RETRY DECORATOR ---
@retry(
    retry=retry_if_exception_type((RateLimitError, APITimeoutError)),
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),
    reraise=True
)
def _llm_cagir(metin: str) -> CikartmaSonucu:
    """Retry decorator'lı LLM çağrısı."""
    logger.debug(f"LLM çağrısı yapılıyor (metin uzunluğu: {len(metin)} karakter).")
    return chain.invoke({"metin": metin})


# --- ANA FONKSİYON ---
def metinden_cikar(metin: str) -> CikartmaSonucu:
    """OCR'dan gelen metni alır, görev ve tarihleri çıkarır."""
    logger.info(f"Metin analizi başlatılıyor ({len(metin)} karakter).")
    try:
        sonuc = _llm_cagir(metin)
        logger.info(f"Analiz tamamlandı: {len(sonuc.gorevler)} görev, {len(sonuc.onemli_tarihler)} tarih bulundu.")
        return sonuc
    except RateLimitError:
        logger.error("OpenAI rate limit aşıldı — boş sonuç dönülüyor.")
        return CikartmaSonucu(gorevler=[], onemli_tarihler=[], konular=[])
    except AuthenticationError:
        logger.error("OpenAI kimlik doğrulama hatası — API anahtarını kontrol edin.")
        return CikartmaSonucu(gorevler=[], onemli_tarihler=[], konular=[])
    except APITimeoutError:
        logger.error("OpenAI API zaman aşımı — boş sonuç dönülüyor.")
        return CikartmaSonucu(gorevler=[], onemli_tarihler=[], konular=[])
    except Exception as e:
        logger.error(f"Görev çıkarımında beklenmeyen hata: {e}", exc_info=True)
        return CikartmaSonucu(gorevler=[], onemli_tarihler=[], konular=[])


# --- TEST ---
if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s — %(message)s')

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


# --- CLASS YAPISI ---
class TaskExtractor:
    def extract(self, text: str) -> list:
        logger.info("TaskExtractor.extract() çağrıldı.")
        try:
            cikarilan_veri = metinden_cikar(text)
            findings = []

            for gorev in cikarilan_veri.gorevler:
                findings.append({
                    "title": gorev.baslik,
                    "date": gorev.son_tarih if gorev.son_tarih else "Belirtilmemiş"
                })

            if not findings and cikarilan_veri.onemli_tarihler:
                for tarih in cikarilan_veri.onemli_tarihler:
                    findings.append({
                        "title": "İlgili Etkinlik/Tarih",
                        "date": tarih
                    })

            logger.info(f"TaskExtractor: {len(findings)} bulgu çıkarıldı.")
            return findings

        except Exception as e:
            logger.error(f"TaskExtractor.extract() hatası: {e}", exc_info=True)
            return []