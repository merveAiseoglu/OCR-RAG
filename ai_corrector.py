from transformers import pipeline

class AITextCorrector:
    def __init__(self):
        print("🤖 BERTurk Yapay Zeka Modeli Yükleniyor... (İlk seferde indirecektir)")
        # Hocanın istediği Mask-Filling (Boşluk Doldurma) Modeli
        self.fill_mask = pipeline(
            "fill-mask", 
            model="dbmdz/bert-base-turkish-cased", 
            tokenizer="dbmdz/bert-base-turkish-cased"
        )

    def eksik_kelime_tamamla(self, metin):
        """
        İçinde [MASK] olan cümleleri tamamlar.
        Örn: "İş sağlığı ve [MASK] önlemleri" -> "güvenliği"
        """
        try:
            if "[MASK]" not in metin:
                return metin
            
            sonuclar = self.fill_mask(metin)
            
            # Model bazen liste bazen tek obje döner, kontrol edelim:
            if isinstance(sonuclar, list):
                # En yüksek skorlu tahmini al
                tahmin = sonuclar[0]['sequence']
            else:
                tahmin = sonuclar['sequence']
                
            return tahmin
        except Exception as e:
            print(f"AI Düzeltme Hatası: {e}")
            return metin