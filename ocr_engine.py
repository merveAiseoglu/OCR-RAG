import logging
import easyocr
import cv2
import numpy as np

logger = logging.getLogger("OCR_Engine")

print("👀 OCR Motoru (EasyOCR) Yükleniyor... (Bu işlem ilk seferde biraz sürebilir)")
# GPU varsa gpu=True yapabilirsin, yoksa False kalsın
reader = easyocr.Reader(['tr', 'en'], gpu=False)

# Minimum güven eşiği — bu değerin altındaki sonuçlar düşük güvenilir kabul edilir
MIN_CONFIDENCE_THRESHOLD = 0.4


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

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)

    limg = cv2.merge((cl, a, b))
    temiz_img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    return temiz_img


# --- YARDIMCI MODÜL 3: Yüksek Kontrastlı Ön İşleme (Retry için) ---
def yuksek_kontrast_uygula(img):
    """
    EasyOCR boş sonuç döndürdüğünde ikinci deneme için kullanılan
    agresif kontrast artırma yöntemi.
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # Daha agresif CLAHE (clipLimit artırıldı)
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))
    cl = clahe.apply(l)

    limg = cv2.merge((cl, a, b))
    temiz_img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

    # Ek keskinleştirme (Sharpening kernel)
    kernel = np.array([[0, -1, 0],
                       [-1, 5, -1],
                       [0, -1, 0]])
    sharpened = cv2.filter2D(temiz_img, -1, kernel)
    logger.debug("Yüksek kontrast ön işleme uygulandı (retry modu).")
    return sharpened


def _ocr_oku_detayli(img):
    """
    EasyOCR'ı detail=1 modunda çalıştırır.
    Her sonuç: ([[bbox]], metin, güven_skoru) formatındadır.
    Returns: (metin_listesi, ortalama_güven)
    """
    try:
        raw_results = reader.readtext(img, detail=1)
    except Exception as e:
        logger.error(f"EasyOCR okuma hatası: {e}")
        return [], 0.0

    if not raw_results:
        return [], 0.0

    metinler = []
    guvenler = []

    for (_bbox, metin, guven) in raw_results:
        if guven < MIN_CONFIDENCE_THRESHOLD:
            logger.debug(f"Düşük güven skoru ({guven:.2f}) nedeniyle atlandı: '{metin}'")
            continue
        metinler.append(metin)
        guvenler.append(guven)

    ort_guven = float(np.mean(guvenler)) if guvenler else 0.0
    return metinler, ort_guven


def ocr_ile_oku(image_input) -> dict:
    """
    Bu fonksiyon bir resmi alır, görüntü işleme adımlarından geçirir
    ve bulduğu metinleri birleştirip döner.

    Returns:
        dict: {
            "text": str,          — Okunan metin (boş olabilir)
            "confidence": float,  — Ortalama güven skoru (0.0–1.0)
            "warning": str|None   — Düşük güven veya boş sonuç varsa uyarı mesajı
        }
    """
    img = None

    # --- 1. Gelen veriyi Resme Çevir ---
    if isinstance(image_input, str):
        img = cv2.imread(image_input)
        logger.info(f"Dosya yolundan resim okunuyor: {image_input}")
    elif isinstance(image_input, bytes):
        nparr = np.frombuffer(image_input, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        logger.info("Byte verisinden resim decode edildi.")
    elif isinstance(image_input, np.ndarray):
        img = image_input
        logger.info("NumPy array olarak resim alındı.")

    if img is None:
        logger.warning("Görüntü decode edilemedi — boş sonuç dönülüyor.")
        return {"text": "", "confidence": 0.0, "warning": "Görüntü yüklenemedi veya geçersiz format."}

    # --- 2. GÖRÜNTÜ ÖN İŞLEME VE TEMİZLEME ---
    img = belgeyi_duzelt(img)
    img = golgeleri_sil(img)
    logger.debug("Görüntü ön işleme tamamlandı (deskew + shadow removal).")

    # --- 3. Metin Bloklarını Tespit Etme ---
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 2))
    dilate = cv2.dilate(thresh, kernel, iterations=1)

    cnts = cv2.findContours(dilate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts[0] if len(cnts) == 2 else cnts[1]
    cnts = sorted(cnts, key=lambda x: cv2.boundingRect(x)[1])

    bulunan_metinler = []
    tum_guvenler = []

    # --- 4. Kutucukları Temizlenmiş Resim Üzerinden Oku ---
    for c in cnts:
        if cv2.contourArea(c) < 500:
            continue

        x, y, w, h = cv2.boundingRect(c)
        if h > w:
            continue

        roi = img[y:y + h, x:x + w]

        try:
            okunan_liste, guven = _ocr_oku_detayli(roi)
            if okunan_liste:
                satir = " ".join(okunan_liste)
                bulunan_metinler.append(satir)
                tum_guvenler.append(guven)
        except Exception as e:
            logger.warning(f"ROI okuma hatası (atlanıyor): {e}")

    # --- 5. BOŞSA YENİDEN DENE: Yüksek Kontrast ile Retry ---
    if not bulunan_metinler:
        logger.warning("İlk OCR denemesi boş döndü. Yüksek kontrast ile yeniden deneniyor...")
        retry_img = yuksek_kontrast_uygula(img)

        try:
            retry_metinler, retry_guven = _ocr_oku_detayli(retry_img)
            if retry_metinler:
                logger.info(f"Retry başarılı: {len(retry_metinler)} metin bloğu bulundu.")
                ham_metin = " ".join(retry_metinler)
                warning = None
                if retry_guven < MIN_CONFIDENCE_THRESHOLD:
                    warning = f"Düşük güven skoru ({retry_guven:.2f}): Metin doğruluğu düşük olabilir."
                    logger.warning(warning)
                return {"text": ham_metin, "confidence": round(retry_guven, 4), "warning": warning}
            else:
                logger.error("Retry sonrası da metin okunamadı.")
                return {
                    "text": "",
                    "confidence": 0.0,
                    "warning": "Görüntüden hiç metin okunamadı. Daha net bir görüntü gerekli."
                }
        except Exception as e:
            logger.error(f"Retry OCR hatası: {e}")
            return {"text": "", "confidence": 0.0, "warning": f"OCR işlemi başarısız: {str(e)}"}

    # --- 6. Sonuçları Birleştir ve Güven Skoru Hesapla ---
    ham_metin = "\n".join(bulunan_metinler)
    ort_guven = float(np.mean(tum_guvenler)) if tum_guvenler else 0.0
    warning = None

    if ort_guven < MIN_CONFIDENCE_THRESHOLD:
        warning = f"Düşük güven skoru ({ort_guven:.2f}): Metin doğruluğu düşük olabilir."
        logger.warning(f"Düşük ortalama güven skoru: {ort_guven:.2f}")
    else:
        logger.info(f"OCR tamamlandı. {len(bulunan_metinler)} blok, ortalama güven: {ort_guven:.2f}")

    return {
        "text": ham_metin,
        "confidence": round(ort_guven, 4),
        "warning": warning
    }


# --- 7. GELİŞMİŞ TABLO ÇIKARIMI (LlamaParse/Docling Altyapısı) ---
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