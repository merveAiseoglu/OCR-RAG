import os
from typing import TypedDict, Optional
from dotenv import load_dotenv, find_dotenv

from langgraph.graph import StateGraph, START, END

# task_extractor'dan gerekli bileşenleri içe aktarıyoruz
from agent.task_extractor import metinden_cikar, CikartmaSonucu

# Ortam değişkenlerini (.env) override ederek yükle
load_dotenv(find_dotenv(), override=True)

# 1. State (Durum) Tanımı
# Agent çalışırken geçiş yapacak olan verileri temsil eder
class AgentState(TypedDict):
    metin: str
    cikarim_sonucu: Optional[CikartmaSonucu]
    islem_durumu: str

# 2. Node (Düğüm) Fonksiyonu
def analiz_node(state: AgentState):
    """
    State içindeki 'metin' bilgisini alıp task_extractor ile analiz eder,
    sonucu tekrar state'e yazarak döner.
    """
    print(f"[Node: analiz_node] Metin işleniyor...")
    
    metin = state["metin"]
    
    # task_extractor'daki metinden_cikar fonksiyonunu çağırıyoruz
    sonuc = metinden_cikar(metin)
    
    # Güncellenmiş state verisini dönüyoruz
    return {
        "metin": metin,
        "cikarim_sonucu": sonuc,
        "islem_durumu": "ANALİZ_TAMAMLANDI"
    }

# 3. StateGraph Kurulumu ve Akış Bağlantıları
graph_builder = StateGraph(AgentState)

# Düğümü grafiğe ekliyoruz
graph_builder.add_node("analiz_node", analiz_node)

# Akışı (Edges) bağlıyoruz: START -> analiz_node -> END
graph_builder.add_edge(START, "analiz_node")
graph_builder.add_edge("analiz_node", END)

# Grafı derleyerek çalışmaya hazır hale getiriyoruz
graph = graph_builder.compile()

# 4. Test Bloğu (Sistemi test eden kod)
if __name__ == "__main__":
    # Örnek metin
    test_metni = "20 Haziran 2026 tarihinde Trello API entegrasyonu tamamlanacak. Sorumlu: Merve."
    
    # Başlangıç state'i (metin verisi ile)
    baslangic_durumu = {
        "metin": test_metni,
        "cikarim_sonucu": None,
        "islem_durumu": "BAŞLADI"
    }
    
    print("\n🚀 LangGraph Agent çalıştırılıyor...\n")
    print(f"Girdi Metni: '{test_metni}'\n")
    
    # Grafı (Agent'ı) invoke ile çalıştırıyoruz
    tamamlanmis_durum = graph.invoke(baslangic_durumu)
    
    # Sonuçları terminale basıyoruz
    print("\n✅ İşlem Durumu:", tamamlanmis_durum.get("islem_durumu"))
    
    sonuc = tamamlanmis_durum.get("cikarim_sonucu")
    if sonuc:
        print("\n📋 ÇIKARILAN GÖREVLER:")
        for g in sonuc.gorevler:
            print(f"  - {g.baslik} | Sorumlu: {g.sorumlu} | Tarih: {g.son_tarih}")
            
        print("\n📅 ÖNEMLİ TARİHLER:")
        for t in sonuc.onemli_tarihler:
            print(f"  - {t}")
            
        print("\n🏷️ KONULAR:")
        for k in sonuc.konular:
            print(f"  - {k}")
            
    print("\n🏁 Test tamamlandı.")
