import os
import chromadb
from sentence_transformers import SentenceTransformer
from pdf_reader import PDFProcessor
import uuid
import json
import re
import hashlib

class DocumentProcessor:
    def __init__(self, persist_directory="chroma_db"):
        print("⚙️ İşlemci Başlatılıyor...")
        
        self.log_file = "processed_files_log.json"
        self.processed_files = self.gecmisi_yukle()
        
        # Embedding Modeli
        self.embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        
        # Veritabanı
        self.chroma_client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.chroma_client.get_or_create_collection(
            name="rag_koleksiyonu",
            metadata={"hnsw:space": "cosine"}
        )
        
        self.pdf_reader = PDFProcessor()
        print("✅ İşlemci Hazır.")

    def gecmisi_yukle(self):
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return []
        return []

    def gecmisi_kaydet(self):
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(self.processed_files, f, ensure_ascii=False, indent=4)

    # ========================================
    # 1️⃣ MADDELİ CHUNKING (UPGRADED)
    # ========================================
    def madde_bazli_chunk(self, text, file_name, page_num=None):
        """
        Sözleşme metnini madde numarasına göre böler.
        Her chunk = 1 madde + metadata
        """
        chunks = []
        
        # Madde pattern: "Madde 6", "MADDE 6", "6.", "Madde 6:", vb.
        # Daha esnek pattern (sayfa başında rakam da olabilir)
        pattern = r'(?:MADDE|Madde|BÖLÜM|Bölüm)\s*(\d+)\s*[:\-.]?\s*([^\n]*)'
        
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        
        if matches:
            # Maddeler bulundu
            for i, match in enumerate(matches):
                madde_no = int(match.group(1))
                madde_basligi = (match.group(2) or "").strip()
                
                baslangic = match.end()
                bitis = matches[i+1].start() if i+1 < len(matches) else len(text)
                
                madde_metni = text[baslangic:bitis].strip()
                
                # Boş maddeleri atla
                if len(madde_metni) < 20:
                    continue
                
                # Chunk oluştur
                chunk = {
                    "text": f"MADDE {madde_no}: {madde_basligi}\n\n{madde_metni}",
                    "metadata": {
                        "source": file_name,
                        "page": page_num,
                        "section_number": madde_no,
                        "section_title": madde_basligi,
                        "chunk_type": "madde",
                        "type": "text"
                    }
                }
                chunks.append(chunk)
            
            print(f"   📌 {len(chunks)} madde tespit edildi (Sayfa {page_num})")
        else:
            # Madde bulunamadı → Geleneksel chunking
            print(f"   ⚠️ Madde bulunamadı, geleneksel chunking yapılıyor (Sayfa {page_num})")
            traditional_chunks = self.chunk_text(text)
            
            for idx, chunk_text in enumerate(traditional_chunks):
                chunk = {
                    "text": chunk_text,
                    "metadata": {
                        "source": file_name,
                        "page": page_num,
                        "section_number": None,
                        "section_title": "Genel",
                        "chunk_type": "genel",
                        "chunk_index": idx,
                        "type": "text"
                    }
                }
                chunks.append(chunk)
        
        return chunks

    def chunk_text(self, text, chunk_size=800, overlap=100):
        """Metni parçalara böler (Eski yöntem - fallback)"""
        chunks = []
        start = 0
        text_len = len(text)
        while start < text_len:
            end = start + chunk_size
            if end < text_len:
                # Kelime ortasından bölmemek için boşluk ara
                while end > start and text[end] != " ": 
                    end -= 1
            if end == start: 
                end = start + chunk_size
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end - overlap
        return chunks

    # ========================================
    # 2️⃣ TEKİL DOSYA İŞLEME (UPGRADED)
    # ========================================
    def process_single_file(self, file_path):
        """API'den gelen tek bir dosyayı işler (Maddeli Chunking ile)"""
        file_name = os.path.basename(file_path)
        print(f"\n🚀 Tekil Dosya İşleniyor: {file_name}")

        # PDF'i Oku
        pages_data = self.pdf_reader.extract_text_with_metadata(file_path)
        
        if not pages_data:
            print("❌ HATA: Dosyadan hiç metin okunamadı! PDF resim formatında olabilir.")
            return False

        dosya_icin_chunk_sayisi = 0
        tum_chunks = []
        
        # Her sayfayı işle
        for page_data in pages_data:
            raw_text = page_data["text"]
            page_num = page_data["page"]
            
            # Çok kısa sayfaları uyar
            if len(raw_text) < 50:
                print(f"⚠️ UYARI: Sayfa {page_num} çok az veri içeriyor ({len(raw_text)} karakter). Taranmış resim olabilir.")
                continue

            # Maddeli chunking yap
            chunks = self.madde_bazli_chunk(raw_text, file_name, page_num)
            tum_chunks.extend(chunks)

        # ChromaDB'ye toplu ekle
        if tum_chunks:
            ids = []
            embeddings = []
            documents = []
            metadatas = []
            
            for chunk in tum_chunks:
                # Unique ID oluştur (madde numarasına göre)
                if chunk["metadata"]["section_number"]:
                    id_string = f"{file_name}_madde_{chunk['metadata']['section_number']}"
                else:
                    id_string = f"{file_name}_chunk_{uuid.uuid4()}"
                
                doc_id = hashlib.md5(id_string.encode()).hexdigest()
                
                ids.append(doc_id)
                documents.append(chunk["text"])
                metadatas.append(chunk["metadata"])
                
                # Embedding oluştur
                embedding = self.embedder.encode(chunk["text"]).tolist()
                embeddings.append(embedding)
            
            # ChromaDB'ye ekle (upsert = varsa güncelle, yoksa ekle)
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            
            dosya_icin_chunk_sayisi = len(tum_chunks)
            print(f"🎉 '{file_name}' başarıyla veritabanına eklendi ({dosya_icin_chunk_sayisi} chunk).")
        
        if dosya_icin_chunk_sayisi > 0:
            if file_name not in self.processed_files:
                self.processed_files.append(file_name)
                self.gecmisi_kaydet()
            return True
        else:
            print("⚠️ Dosya işlendi ama veritabanına eklenecek veri çıkmadı.")
            return False

    # ========================================
    # 3️⃣ KLASÖR İŞLEME
    # ========================================
    def process_folder(self, folder_path="documents"):
        """Klasördeki tüm dosyaları tarar"""
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            
        files = [f for f in os.listdir(folder_path) if f.endswith(".pdf")]
        
        if not files:
            print("⚠️ Klasörde PDF dosyası bulunamadı.")
            return
        
        print(f"\n📂 {len(files)} PDF dosyası bulundu.")
        
        for file in files:
            if file in self.processed_files:
                print(f"⏭️ '{file}' daha önce işlenmiş, atlanıyor.")
                continue
            
            file_path = os.path.join(folder_path, file)
            self.process_single_file(file_path)

    # ========================================
    # 4️⃣ API İÇİN ÖZEL FONKSİYON
    # ========================================
    def process_single_file_with_madde_chunking(self, file_path):
        """
        API endpoint'i için özel fonksiyon
        Chunks listesi döner (ChromaDB'ye ekleme API'de yapılır)
        """
        file_name = os.path.basename(file_path)
        print(f"\n🚀 Maddeli Chunking ile İşleniyor: {file_name}")

        # PDF'i Oku
        pages_data = self.pdf_reader.extract_text_with_metadata(file_path)
        
        if not pages_data:
            print("❌ HATA: Dosyadan hiç metin okunamadı!")
            return []

        tum_chunks = []
        
        # Her sayfayı işle
        for page_data in pages_data:
            raw_text = page_data["text"]
            page_num = page_data["page"]
            
            if len(raw_text) < 50:
                print(f"⚠️ Sayfa {page_num} atlandı (çok az veri)")
                continue

            # Maddeli chunking
            chunks = self.madde_bazli_chunk(raw_text, file_name, page_num)
            tum_chunks.extend(chunks)

        print(f"✅ Toplam {len(tum_chunks)} chunk oluşturuldu")
        return tum_chunks