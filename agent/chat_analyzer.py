import logging
import os
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv, find_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from openai import RateLimitError, AuthenticationError, APITimeoutError
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

logger = logging.getLogger("ChatAnalyzer")


class KullaniciProfili(BaseModel):
    ilgi_alanlari: List[str] = Field(
        description="Kullanıcının güncel ilgi alanları, hedefleri veya uğraştığı sorunlar"
    )


@retry(
    retry=retry_if_exception_type((RateLimitError, APITimeoutError)),
    stop=stop_after_attempt(3),    # İlk deneme + 2 retry = max 3 toplam
    wait=wait_fixed(2),            # Denemeler arası 2 saniye bekle
    reraise=True
)
def _llm_cagir(chain, gecmis_metni: str) -> KullaniciProfili:
    """Retry decorator'lı LLM çağrısı."""
    logger.debug("LLM çağrısı yapılıyor (ilgi alanı çıkarımı).")
    return chain.invoke({"gecmis_metni": gecmis_metni})


def ilgi_alanlarini_cikar(sohbet_gecmisi: List[str]) -> KullaniciProfili:
    """
    Sohbet geçmişini analiz ederek kullanıcının ilgi alanlarını çıkarır.
    Hata durumunda boş profil döner (crash etmez).
    """
    logger.info(f"İlgi alanı çıkarımı başlatılıyor ({len(sohbet_gecmisi)} mesaj).")

    if not sohbet_gecmisi:
        logger.warning("Boş sohbet geçmişi geldi — boş profil dönülüyor.")
        return KullaniciProfili(ilgi_alanlari=[])

    try:
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
        sonuc = _llm_cagir(chain, gecmis_metni)
        logger.info(f"İlgi alanları başarıyla çıkarıldı: {sonuc.ilgi_alanlari}")
        return sonuc

    except RateLimitError:
        logger.error("OpenAI rate limit aşıldı — boş profil dönülüyor.")
        return KullaniciProfili(ilgi_alanlari=[])
    except AuthenticationError:
        logger.error("OpenAI kimlik doğrulama hatası — API anahtarını kontrol edin.")
        return KullaniciProfili(ilgi_alanlari=[])
    except APITimeoutError:
        logger.error("OpenAI API zaman aşımı — boş profil dönülüyor.")
        return KullaniciProfili(ilgi_alanlari=[])
    except Exception as e:
        logger.error(f"İlgi alanı çıkarımında beklenmeyen hata: {e}", exc_info=True)
        return KullaniciProfili(ilgi_alanlari=[])


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s — %(message)s')
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
