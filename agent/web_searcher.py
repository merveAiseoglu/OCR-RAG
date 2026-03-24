import os
from dotenv import load_dotenv

load_dotenv(override=True)

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

def sonucu_duzenle(konu: str, ham_metin: str) -> str:
    """
    Kopuk arama sonuçlarını LLM kullanarak düzgün, akıcı 2-3 cümlelik bir özete çevirir.
    """
    llm = ChatOpenAI(model="gpt-4o")
    
    prompt = ChatPromptTemplate.from_template(
        "Sen bir editörsün. Aşağıda \"{konu}\" hakkında internetten çekilmiş karmaşık ve kopuk arama sonuçları var. "
        "Bu ham metni oku, gereksiz tarihleri/linkleri temizle ve 2-3 cümlelik, akıcı, net ve anlamlı bir Türkçe özet haline getir.\n"
        "Ham Metin: {ham_metin}"
    )
    
    chain = prompt | llm
    
    try:
        response = chain.invoke({"konu": konu, "ham_metin": ham_metin})
        return response.content
    except Exception as e:
        return f"Özetleme sırasında hata oluştu: {str(e)}"

def ilgi_alanlarini_arastir(ilgi_alanlari: list[str]) -> dict:
    """
    Verilen ilgi alanları listesindeki ilk 2 eleman için DuckDuckGo üzerinden web araması yapar
    ve sonuçları editör LLM'i ile özetler.
    """
    search_tool = DuckDuckGoSearchRun()
    sonuclar = {}
    
    # Sadece ilk 2 ilgi alanını al (sistemi yormamak adına sınırlandırıyoruz)
    for ilgi_alani in ilgi_alanlari[:2]:
        try:
            # DuckDuckGo ile arama yap
            sonuc = search_tool.invoke(ilgi_alani)
            # Ham sonucu düzenle
            duzenlenmis_sonuc = sonucu_duzenle(ilgi_alani, sonuc)
            sonuclar[ilgi_alani] = duzenlenmis_sonuc
        except Exception as e:
            sonuclar[ilgi_alani] = f"Arama sırasında bir hata oluştu: {str(e)}"
            
    return sonuclar

if __name__ == "__main__":
    # Test verisi (3. haftadan edilen liste)
    test_verisi = ["İngilizce B2 seviyesi", "Vodafone sınavı"]
    
    print("Arama ve özetleme başlatılıyor...")
    print(f"Aranacak konular: {', '.join(test_verisi)}\n")
    
    # Arama fonksiyonunu çalıştır
    arama_sonuclari = ilgi_alanlarini_arastir(test_verisi)
    
    print("="*50)
    print("DÜZENLENMİŞ ARAMA SONUÇLARI")
    print("="*50)
    
    # Sonuçları okunaklı bir şekilde terminale yazdır
    for ilgi_alani, sonuc in arama_sonuclari.items():
        print(f"\n[İlgi Alanı]: {ilgi_alani}")
        print(f"[Özet]:\n{sonuc}")
        print("-" * 50)
