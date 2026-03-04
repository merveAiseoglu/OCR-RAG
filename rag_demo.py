import streamlit as st
import chromadb
from sentence_transformers import SentenceTransformer
import google.generativeai as genai
import os
from dotenv import load_dotenv

# --- AYARLAR ---
st.set_page_config(page_title="RAG Asistanı (Final)", layout="wide")
load_dotenv() 
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY: st.stop()
genai.configure(api_key=GOOGLE_API_KEY)

# --- SİSTEM ---
@st.cache_resource
def sistemi_yukle():
    embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    client = chromadb.PersistentClient(path="chroma_db")
    collection = client.get_or_create_collection(name="rag_koleksiyonu", metadata={"hnsw:space": "cosine"})
    return embedder, collection

# --- ARAYÜZ ---
st.title("🤖 Yapay Zeka Doküman Asistanı")
st.caption("Google Gemini 2.5 + Sayfa Referanslı RAG")

with st.sidebar:
    st.header("⚙️ Ayarlar")
    esik_degeri = st.slider("Benzerlik Eşiği", 0.0, 1.0, 0.40)
    sonuc_sayisi = st.slider("Kaynak Sayısı", 1, 10, 3)

embedder, collection = sistemi_yukle()
st.success("Sistem Hazır! ✅")

soru = st.text_input("Sorunuzu Yazın:")
if st.button("🔍 Yanıtla") and soru:
    with st.spinner("Araştırılıyor..."):
        soru_vektoru = embedder.encode(soru).tolist()
        sonuclar = collection.query(query_embeddings=[soru_vektoru], n_results=sonuc_sayisi)
        
        gecerli_dokumanlar = []
        referanslar = [] # Metadata için yeni liste
        
        if sonuclar['documents']:
            documents = sonuclar['documents'][0]
            distances = sonuclar['distances'][0]
            metadatas = sonuclar['metadatas'][0] # Metadata (Sayfa No) burada
            
            for i, doc in enumerate(documents):
                skor = 1 - distances[i]
                if skor >= esik_degeri:
                    gecerli_dokumanlar.append(doc)
                    # Sayfa bilgisini alalım
                    sayfa = metadatas[i].get("page", "?")
                    dosya = metadatas[i].get("source", "Bilinmiyor")
                    referanslar.append(f"📄 **{dosya}** (Sayfa: {sayfa})")

        if not gecerli_dokumanlar:
            st.warning("Bilgi bulunamadı.")
        else:
            baglam = "\n".join(gecerli_dokumanlar)
            prompt = f"Bağlamı kullanarak cevapla:\nBAĞLAM:{baglam}\nSORU: {soru}"
            
            try:
                model = genai.GenerativeModel('gemini-2.5-flash') 
                response = model.generate_content(prompt)
                
                st.markdown("### 💡 Cevap:")
                st.write(response.text)
                
                st.markdown("---")
                st.markdown("### 📚 Kaynaklar")
                for i, ref in enumerate(referanslar):
                    st.success(f"{ref}\n\n> {gecerli_dokumanlar[i]}")
                    
            except Exception as e:
                st.error(f"Hata: {e}")