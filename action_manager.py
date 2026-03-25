import os
from datetime import datetime

def takvime_ekle(gorev_listesi):
    """
    Bu fonksiyon task_extractor'dan gelen görevleri alır, 
    terminale yazdırır ve takvim dosyası (.ics) oluşturur.
    """
    print("\n🚀 [ACTION MANAGER] Sisteme Görevler Aktarılıyor...")
    
    if not gorev_listesi:
        print("⚠️ Aktarılacak görev bulunamadı.")
        return False

    # Diğer arkadaşların dosyalarına dokunmamak için yeni bir klasör açıyoruz
    output_folder = "Takvim_Kayitlari"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for i, gorev in enumerate(gorev_listesi):
        tarih = gorev.son_tarih if gorev.son_tarih else "Tarih Belirtilmedi"
        sorumlu = gorev.sorumlu if gorev.sorumlu else "Belirtilmedi"
        
        # --- MEVCUT TERMİNAL ÇIKTISI (Arkadaşlarının sistemi) ---
        print(f"✅ İşlendi: {gorev.baslik}")
        print(f"   📅 Tarih: {tarih}")
        print(f"   👤 Sorumlu: {sorumlu}")
        
        # --- SENİN EKLEDİĞİN OTOMASYON (ICS Dosyası Oluşturma) ---
        # Bu kısım harici araçlara (Google Takvim vb.) aktarımı sağlar.
        ics_icerik = (
            "BEGIN:VCALENDAR\n"
            "VERSION:2.0\n"
            "BEGIN:VEVENT\n"
            f"SUMMARY:{gorev.baslik}\n"
            f"DESCRIPTION:Sorumlu: {sorumlu} (Belgeden otomatik aktarildi)\n"
            f"DTSTART:{datetime.now().strftime('%Y%m%dT090000')}\n"
            "END:VEVENT\n"
            "END:VCALENDAR"
        )

        dosya_adi = f"gorev_{i+1}.ics"
        dosya_yolu = os.path.join(output_folder, dosya_adi)
        
        with open(dosya_yolu, "w", encoding="utf-8") as f:
            f.write(ics_icerik)
            
        print(f"📂 [OTOMASYON] Takvim dosyası oluşturuldu: {dosya_yolu}")
        print("-" * 30)
    
    return True