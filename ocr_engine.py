import easyocr
import cv2
import numpy as np

print("👀 OCR Motoru (EasyOCR) Yükleniyor... (Bu işlem ilk seferde biraz sürebilir)")
# GPU varsa gpu=True yapabilirsin, yoksa False kalsın
reader = easyocr.Reader(['tr', 'en'], gpu=False) 

def ocr_ile_oku(image_input):
    """
    Bu fonksiyon bir resmi alır, arkadaşının görüntü işleme adımlarından geçirir
    ve bulduğu metinleri birleştirip geri döner.
    """
    img = None
    
    # --- 1. Gelen veriyi (Byte veya Dosya Yolu) Resme Çevir ---
    if isinstance(image_input, str):
        # Dosya yolu gelirse
        img = cv2.imread(image_input)
    elif isinstance(image_input, bytes):
        # API'den (Telefondan) gelen veri ise
        nparr = np.frombuffer(image_input, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    elif isinstance(image_input, np.ndarray):
        # Zaten OpenCV formatındaysa
        img = image_input

    if img is None:
        return ""

    # --- 2. Görüntü İşleme (Arkadaşının Mantığı) ---
    # Gri tona çevir
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Gürültü temizle (Blur)
    blur = cv2.GaussianBlur(gray, (7,7), 0)
    
    # Siyah-Beyaz yap (Threshold)
    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    
    # Metin bloklarını genişlet (Dilation - Harfleri birleştirir)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 2))
    dilate = cv2.dilate(thresh, kernel, iterations=1)
    
    # Konturları (Çerçeveleri) bul
    cnts = cv2.findContours(dilate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts[0] if len(cnts) == 2 else cnts[1]
    
    # Satırları yukarıdan aşağıya sırala (Çok önemli, yoksa metin karışır)
    cnts = sorted(cnts, key=lambda x: cv2.boundingRect(x)[1])

    bulunan_metinler = []

    # --- 3. Her Bir Kutucuğu Oku ---
    for c in cnts:
        # Çok küçük lekeleri atla (Gürültü filtresi)
        if cv2.contourArea(c) < 500: continue
        
        x, y, w, h = cv2.boundingRect(c)
        
        # Dikey çizgileri atla (Metinler genelde yataydır)
        if h > w: continue

        # İlgili alanı kes (Region of Interest - ROI)
        roi = img[y:y+h, x:x+w]

        try:
            # EasyOCR ile sadece o parçayı oku
            okunan_liste = reader.readtext(roi, detail=0)
            if len(okunan_liste) > 0:
                satir = " ".join(okunan_liste)
                bulunan_metinler.append(satir)
        except:
            pass

    return "\n".join(bulunan_metinler)