import logging
import concurrent.futures
from typing import TypedDict, Optional

from dotenv import load_dotenv, find_dotenv
from langgraph.graph import StateGraph, START, END

from agent.task_extractor import metinden_cikar, CikartmaSonucu

logger = logging.getLogger("GraphBuilder")
load_dotenv(find_dotenv(), override=True)

# Tüm graph invocation'ları için maksimum bekleme süresi (saniye)
GRAPH_TIMEOUT_SANIYE = 30


# ---------------------------------------------------------------------------
# State Tanımı
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    metin: str
    cikarim_sonucu: Optional[CikartmaSonucu]
    islem_durumu: str
    error: Optional[str]


# ---------------------------------------------------------------------------
# Node Fonksiyonu
# ---------------------------------------------------------------------------
def analiz_node(state: AgentState) -> AgentState:
    """
    State içindeki 'metin' bilgisini alıp task_extractor ile analiz eder.
    Hata durumunda 'error' alanı doldurulur, crash edilmez.
    """
    logger.info("[analiz_node] Metin işleniyor...")
    metin = state.get("metin", "")

    if not metin.strip():
        logger.warning("[analiz_node] Boş metin geldi — işlem atlanıyor.")
        return {
            "metin": metin,
            "cikarim_sonucu": None,
            "islem_durumu": "ATLANDI",
            "error": "Boş metin gönderildi."
        }

    try:
        sonuc = metinden_cikar(metin)
        logger.info(f"[analiz_node] Analiz tamamlandı: {len(sonuc.gorevler)} görev bulundu.")
        return {
            "metin": metin,
            "cikarim_sonucu": sonuc,
            "islem_durumu": "ANALİZ_TAMAMLANDI",
            "error": None
        }
    except Exception as e:
        logger.error(f"[analiz_node] Beklenmeyen hata: {e}", exc_info=True)
        return {
            "metin": metin,
            "cikarim_sonucu": None,
            "islem_durumu": "HATA",
            "error": f"Analiz hatası: {str(e)}"
        }


# ---------------------------------------------------------------------------
# Graf Kurulumu
# ---------------------------------------------------------------------------
graph_builder = StateGraph(AgentState)
graph_builder.add_node("analiz_node", analiz_node)
graph_builder.add_edge(START, "analiz_node")
graph_builder.add_edge("analiz_node", END)

_compiled_graph = graph_builder.compile()


# ---------------------------------------------------------------------------
# Timeout Wrapper
# ---------------------------------------------------------------------------
def graph_invoke_with_timeout(state: dict, timeout: int = GRAPH_TIMEOUT_SANIYE) -> dict:
    """
    LangGraph invocation'ını ThreadPoolExecutor ile sarmalar.
    Belirtilen timeout süresini aşarsa TimeoutError fırlatır.
    """
    logger.info(f"Graf çalıştırılıyor (timeout: {timeout}s)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_compiled_graph.invoke, state)
        try:
            result = future.result(timeout=timeout)
            return result
        except concurrent.futures.TimeoutError:
            logger.error(f"Graf {timeout} saniye içinde tamamlanamadı — timeout!")
            raise TimeoutError(f"LangGraph agent {timeout} saniyede tamamlanamadı.")


# Geriye dönük uyumluluk için orijinal `graph` nesnesi de dışa aktarılır
graph = _compiled_graph


# ---------------------------------------------------------------------------
# Test Bloğu
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s — %(message)s')

    test_metni = "20 Haziran 2026 tarihinde Trello API entegrasyonu tamamlanacak. Sorumlu: Merve."

    baslangic_durumu = {
        "metin": test_metni,
        "cikarim_sonucu": None,
        "islem_durumu": "BAŞLADI",
        "error": None
    }

    print("\n🚀 LangGraph Agent çalıştırılıyor (30s timeout)...\n")
    print(f"Girdi Metni: '{test_metni}'\n")

    try:
        tamamlanmis_durum = graph_invoke_with_timeout(baslangic_durumu)

        print("\n✅ İşlem Durumu:", tamamlanmis_durum.get("islem_durumu"))
        if tamamlanmis_durum.get("error"):
            print("⚠️  Hata:", tamamlanmis_durum["error"])

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

    except TimeoutError as e:
        print(f"⏱️ TIMEOUT: {e}")
    except Exception as e:
        print(f"❌ Beklenmeyen hata: {e}")

    print("\n🏁 Test tamamlandı.")
