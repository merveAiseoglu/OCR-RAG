import os
import fitz

documents_folder = "documents"
files = [f for f in os.listdir(documents_folder) if f.endswith(".pdf") and f != "whatsapp security.pdf"]

for f_name in files:
    pdf_path = os.path.join(documents_folder, f_name)
    print(f"\n==========================================")
    print(f"Document: {f_name}")
    doc = fitz.open(pdf_path)
    for sayfa_no in range(len(doc)):
        sayfa = doc[sayfa_no]
        text = sayfa.get_text()
        print(f"--- Page {sayfa_no+1} (Length: {len(text)}) ---")
        print(text[:1000])
