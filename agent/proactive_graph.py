import os
from typing import TypedDict, List, Dict, Any
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END

# Kendi modüllerimizden içe aktarma
from agent.chat_analyzer import ilgi_alanlarini_cikar
from agent.web_searcher import ilgi_alanlarini_arastir

class ProactiveState(TypedDict):
    sohbet_gecmisi: List[str]
    ilgi_alanlari: List[str]
    arama_sonuclari: Dict[str, Any]

def analiz_node(state: ProactiveState) -> ProactiveState:
    sohbet_gecmisi = state.get("sohbet_gecmisi", [])
    
    # Geçmiş sohbetteki metni (veya metinleri) çıkartma fonksiyonuna yolla
    sonuc_objesi = ilgi_alanlarini_cikar(sohbet_gecmisi)
    
    # Dönen nesnenin .ilgi_alanlari listesini state içine kaydet
    ilgi_alanlari = getattr(sonuc_objesi, 'ilgi_alanlari', [])
    
    return {"ilgi_alanlari": ilgi_alanlari}

def arama_gerekli_mi(state: ProactiveState) -> str:
    ilgi_alanlari = state.get("ilgi_alanlari", [])
    
    # LLM tarafından dönen 'Güncel ilgi alanları belirlenemedi', 'yok', 'bulunamadı' gibi ifadeleri filtrele
    gecerli_alanlar = []
    if ilgi_alanlari:
        for alan in ilgi_alanlari:
            alan_lower = str(alan).lower()
            if "belirlenemedi" not in alan_lower and "bulunamadı" not in alan_lower and alan_lower != "yok":
                gecerli_alanlar.append(alan)
    
    # Eğer geçerli bir ilgi alanı yoksa aramayı yapmadan bitir
    if not gecerli_alanlar:
        return "bitir"
    
    return "arama_yap"

def arama_node(state: ProactiveState) -> ProactiveState:
    ilgi_alanlari = state.get("ilgi_alanlari", [])
    
    # İlgi alanlarını DuckDuckGoSearchRun ve GPT üzerinden arama-düzenleme için ver
    sonuclar = ilgi_alanlarini_arastir(ilgi_alanlari)
    
    return {"arama_sonuclari": sonuclar}

def bildirim_node(state: ProactiveState) -> ProactiveState:
    arama_sonuclari = state.get("arama_sonuclari")
    
    if arama_sonuclari:
        print("\n🤖 PROAKTİF ASİSTAN BİLDİRİMİ 🤖")
        print("Sohbet geçmişinden odaklandığın konuları fark ettim ve senin için şu güncel bilgileri topladım:")
        for konu, ozet in arama_sonuclari.items():
            print(f"🎯 [{konu}]: {ozet}")
            print("-" * 50)
            
    return state

# Grafı İnşa Et
builder = StateGraph(ProactiveState)

# Düğümleri ekle
builder.add_node("analiz", analiz_node)
builder.add_node("arama", arama_node)
builder.add_node("bildirim", bildirim_node)

# Başlangıcı bağla
builder.add_edge(START, "analiz")

# Koşullu yönlendirmeyi ekle
builder.add_conditional_edges(
    "analiz",
    arama_gerekli_mi,
    {
        "arama_yap": "arama",
        "bitir": END
    }
)

# Arama düğümünden bildirim düğümüne geç, oradan da bitir
builder.add_edge("arama", "bildirim")
builder.add_edge("bildirim", END)

# Grafı derle
graph = builder.compile()

if __name__ == "__main__":
    load_dotenv(override=True)
    
    senaryo_1 = {"sohbet_gecmisi": ["Yarın KPSS sınavım var, bana dua et."]}
    senaryo_2 = {"sohbet_gecmisi": ["Merhaba, nasılsın?"]}
    
    print("=" * 60)
    print("SENARYO 1 (Dolu): Sistem analiz edip arama düğümüne gitmeli")
    print("Girdi:", senaryo_1)
    
    try:
        sonuc_1 = graph.invoke(senaryo_1)
        print("ÇIKTI DURUMU (State):")
        print(sonuc_1)
    except Exception as e:
        print(f"Senaryo 1 çalıştırılırken hata oluştu: {str(e)}")
        
    print("=" * 60)
    
    print("\n" + "=" * 60)
    print("SENARYO 2 (Boş): Sistem ilgi alanı bulamadığı için arama yapmadan bitirmeli")
    print("Girdi:", senaryo_2)
    
    try:
        sonuc_2 = graph.invoke(senaryo_2)
        print("ÇIKTI DURUMU (State):")
        print(sonuc_2)
    except Exception as e:
        print(f"Senaryo 2 çalıştırılırken hata oluştu: {str(e)}")
        
    print("=" * 60)
