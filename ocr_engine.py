import easyocr
import cv2
import numpy as np

print("👀 OCR Motoru (EasyOCR) Yükleniyor... (Bu işlem ilk seferde biraz sürebilir)")
# GPU varsa gpu=True yapabilirsin, yoksa False kalsın
reader = easyocr.Reader(['tr', 'en'], gpu=False) 

# --- YARDIMCI MODÜL 1: Yamukluk Düzeltme (Deskew) ---
def belgeyi_duzelt(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    
    if len(coords) == 0:
        return img
        
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    
    # Sadece belli bir dereceden fazla yamukluk varsa döndür
    if abs(angle) < 0.5:
        return img
        
    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated

# --- YARDIMCI MODÜL 2: Gölge Silme ve Netleştirme (CLAHE) ---
def golgeleri_sil(img):
    # Renk dengesini bozmamak için LAB uzayına geçip sadece L (Aydınlık) kanalını işliyoruz
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    cl = clahe.apply(l)
    
    limg = cv2.merge((cl, a, b))
    temiz_img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    return temiz_img


def ocr_ile_oku(image_input):
    """
    Bu fonksiyon bir resmi alır, görüntü işleme adımlarından geçirir
    ve bulduğu metinleri birleştirip geri döner.
    """
    img = None
    
    # --- 1. Gelen veriyi Resme Çevir ---
    if isinstance(image_input, str):
        img = cv2.imread(image_input)
    elif isinstance(image_input, bytes):
        nparr = np.frombuffer(image_input, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    elif isinstance(image_input, np.ndarray):
        img = image_input

    if img is None:
        return ""

    # --- 2. GÖRÜNTÜ ÖN İŞLEME VE TEMİZLEME ---
    img = belgeyi_duzelt(img) # Kamera açısından kaynaklı yamukluğu düzelt
    img = golgeleri_sil(img)  # Kötü ışık ve gölgeleri silerek kontrastı artır

    # --- 3. Metin Bloklarını Tespit Etme ---
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7,7), 0)
    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 2))
    dilate = cv2.dilate(thresh, kernel, iterations=1)
    
    cnts = cv2.findContours(dilate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts[0] if len(cnts) == 2 else cnts[1]
    
    cnts = sorted(cnts, key=lambda x: cv2.boundingRect(x)[1])

    bulunan_metinler = []

    # --- 4. Kutucukları Temizlenmiş Resim Üzerinden Oku ---
    for c in cnts:
        if cv2.contourArea(c) < 500: continue
        
        x, y, w, h = cv2.boundingRect(c)
        if h > w: continue

        # EasyOCR'a artık karanlık olanı değil, filtrelerden geçmiş 'img'yi veriyoruz
        roi = img[y:y+h, x:x+w]

        try:
            okunan_liste = reader.readtext(roi, detail=0)
            if len(okunan_liste) > 0:
                satir = " ".join(okunan_liste)
                bulunan_metinler.append(satir)
        except:
            pass

    # --- 5. METİN PARÇALAMA (CHUNKING) OPTİMİZASYONU ---
    # Paragrafları ayırmak için satırları anlamlı bloklar haline getiriyoruz
    ham_metin = "\n".join(bulunan_metinler)
    
    # İleride LLM için ekstra maddeleme veya chunking eklenecekse bu blokta yapılacak
    llm_icin_hazir_metin = ham_metin 

    return llm_icin_hazir_metin

# --- 6. GELİŞMİŞ TABLO ÇIKARIMI (LlamaParse/Docling Altyapısı) ---
def gelismis_tablo_cikarimi(belge_yolu):
    """
    EasyOCR'ın yetersiz kaldığı sözleşme ve faturalar için rezerve edilmiştir.
    API Key entegrasyonu sağlandığında Docling veya LlamaParse boru hattı 
    buradan tetiklenecektir.
    """
    pass
    # TODO: Akşam LlamaParse API Key alındığında burası doldurulacak.
    # Örnek kullanım:
    # parsed_data = llama_parse_api.read(belge_yolu)
    # return parsed_data