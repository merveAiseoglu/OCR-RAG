import fitz  # PyMuPDF
import re

class PDFProcessor:
    def __init__(self):
        pass

    def clean_text(self, text):
        """Metin temizliği"""
        if not text: return ""
        text = text.replace("-\n", "") 
        text = text.replace("\n", " ") 
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def extract_text_with_metadata(self, pdf_path):
        try:
            doc = fitz.open(pdf_path)
            results = []
            
            print(f"--- Dosya Analizi: {pdf_path} ---") # Hata ayıklama için
            
            for page_num, page in enumerate(doc):
                # GÜNCELLEME 1: sort=True ekledik. 
                # Bu, metni sayfadaki fiziksel konumuna (yukarıdan aşağıya) göre sıralar.
                text = page.get_text("text", sort=True)
                
                # GÜNCELLEME 2: Sayfada ne okunduğunu görmek için ham metnin ilk 100 karakterini bas.
                print(f"[Sayfa {page_num+1}] Okunan ham veri uzunluğu: {len(text)}")
                if len(text) < 50:
                    print(f"⚠️ UYARI: Sayfa {page_num+1} çok az veri içeriyor! Okunan: {text.strip()}")

                cleaned = self.clean_text(text)
                if cleaned:
                    results.append({
                        "text": cleaned,
                        "page": page_num + 1 
                    })
            
            return results
            
        except Exception as e:
            print(f"Hata oluştu ({pdf_path}): {e}")
            return []