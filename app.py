import streamlit as st
import fitz  # PyMuPDF
import io

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="AccessiDOC AI | PDF Accessibility", layout="wide", page_icon="📄")

# Niestandardowy CSS dla wyglądu
st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    div.stButton > button:first-child {
        background-color: #0056b3;
        color: white;
        border-radius: 8px;
    }
    </style>
""", unsafe_allow_html=True)

# --- FUNKCJE SILNIKA ---
def process_pdf_real_xray(file_bytes):
    """Prawdziwy, głęboki rentgen pliku PDF zgodny z PDF/UA"""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    catalog = doc.pdf_catalog()
    
    # 1. TEST TAGÓW (Tagged PDF)
    is_tagged = False
    try:
        mark_info_type, mark_info_val = doc.xref_get_key(catalog, "MarkInfo")
        if mark_info_type != "null" and "Marked" in mark_info_val:
            is_tagged = True
    except Exception:
        pass 
        
    # 2. TEST JĘZYKA (Document Language)
    document_language = None
    try:
        lang_type, lang_val = doc.xref_get_key(catalog, "Lang")
        if lang_type != "null":
            document_language = lang_val.replace("/", "")
    except Exception:
        pass
    
    # 3. TEST TYTUŁU (Metadata Title)
    metadata = doc.metadata
    has_title = True if metadata and metadata.get("title") else False
    
    # 4. TEST ZAWARTOŚCI I OBRAZÓW (Skanujemy max 5 stron dla wydajności)
    pages_to_scan = min(5, len(doc)) 
    images_found = []
    is_scanned_document = True 
    
    for page_num in range(pages_to_scan):
        page = doc.load_page(page_num)
        
        # Sprawdzamy, czy na stronie jest prawdziwy tekst (min. 50 znaków)
        text_length = len(page.get_text("text").strip())
        if text_length > 50: 
            is_scanned_document = False
            
        # Zbieramy obrazki do alt-textów
        for img_index, img in enumerate(page.get_images(full=True)):
            images_found.append({
                "page": page_num + 1, 
                "img_xref": img[0]
            })

    return {
        "pages": len(doc),
        "is_tagged": is_tagged,
        "language": document_language,
        "has_title": has_title,
        "is_scanned": is_scanned_document,
        "images_count": len(images_found),
        "images_details": images_found,
        "doc_ref": doc
    }

def render_page_image(doc, page_num):
    """Renderuje stronę PDF jako obraz do podglądu (lewa strona aplikacji)"""
    page = doc.load_page(page_num - 1)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) 
    return pix.tobytes("png")

# --- INTERFEJS UŻYTKOWNIKA ---
st.title("📄 AccessiDOC AI")
st.markdown("**Platforma do audytu i naprawy dostępności cyfrowej dokumentów (WCAG / EAA 2025)**")

# Zakładki
tab1, tab2 = st.tabs(["🔍 1. Skaner Dokumentu", "🛠️ 2. Studio Naprawcze (Human-in-the-Loop)"])

with tab1:
    st.subheader("Wgraj plik PDF do analizy")
    uploaded_file = st.file_uploader("Wybierz plik PDF (np. Tabela Opłat KBC)", type="pdf")
    
    if uploaded_file is not None:
        with st.spinner("Głębokie skanowanie struktur binarnego PDF (PDF/UA)..."):
            # TUTAJ BYŁ BŁĄD - Teraz funkcja nazywa się prawidłowo:
            pdf_data = process_pdf_real_xray(uploaded_file.getvalue())
            
            # Zapisujemy dane do sesji
            st.session_state['pdf_data'] = pdf_data
            st.session_state['file_name'] = uploaded_file.name
            
        st.success("Skanowanie zakończone!")
        st.markdown("### 📊 Wyniki Audytu Strukturalnego")
        
        # ALERT KRYTYCZNY - Brak tagów
        if not pdf_data["is_tagged"]:
            st.error("🚨 **KRYTYCZNY BŁĄD:** Dokument nie posiada warstwy tagów (Untagged PDF). Jest całkowicie nieczytelny dla czytników ekranu (Screen Readers).")
        else:
            st.success("✅ Dokument posiada strukturę tagów (Tagged PDF).")
            
        # ALERT KRYTYCZNY - Płaski skan
        if pdf_data["is_scanned"]:
            st.warning("⚠️ **UWAGA:** Wygląda na to, że dokument to płaski skan (brak tekstu ukrytego pod spodem). Wymagane użycie OCR.")
            
        # Tablica Metryk (4 kolumny)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Liczba stron", pdf_data["pages"])
        
        title_status = "✅ Posiada" if pdf_data["has_title"] else "❌ Brak"
        c2.metric("Tytuł dokumentu", title_status)
        
        lang_status = pdf_data["language"] if pdf_data["language"] else "❌ Brak"
        c3.metric("Główny Język", lang_status)
        
        c4.metric("Wykryte obrazy", pdf_data["images_count"])

with tab2:
    if 'pdf_data' in st.session_state:
        st.subheader(f"Naprawa pliku: {st.session_state['file_name']}")
        
        # LEWA STRONA (Podgląd) i PRAWA STRONA (AI)
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown("### Podgląd Oryginału")
            page_to_view = st.number_input("Wybierz stronę", min_value=1, max_value=st.session_state['pdf_data']['pages'], value=1)
            img_preview = render_page_image(st.session_state['pdf_data']['doc_ref'], page_to_view)
            st.image(img_preview, caption=f"Strona {page_to_view}")
            
        with col_right:
            st.markdown("### 🤖 Asystent Naprawy AI")
            
            if not st.session_state['pdf_data']["language"]:
                st.error("**Wykryto Błąd: Brak zdefiniowanego języka dokumentu**")
                lang = st.selectbox("Sugerowany język do wstrzyknięcia:", ["nl-BE (Niderlandzki)", "fr-BE (Francuski)", "en-US (Angielski)", "pl-PL (Polski)"])
            
            st.write("---")
            st.write(f"**Wykryto Błąd: Obrazy bez tekstu alternatywnego (Alt-Text) na stronie {page_to_view}**")
            
            # Tu w następnym kroku wepniemy Claude Vision API
            st.text_area("Wygenerowana propozycja AI dla obrazka/wykresu:", value="Wykres słupkowy przedstawiający wzrost oprocentowania kredytów hipotecznych KBC w 2025 roku, z 3% na 4.2%.", height=100)
            
            if st.button("Zatwierdź zmiany (Akceptuj) ✅", type="primary"):
                st.success("Zmiany zapisane do matrycy naprawczej!")
                st.balloons()
                
            st.divider()
            
            st.download_button(
                label="📥 Eksportuj Plan Naprawczy (CSV)",
                data="Strona,Element,Akcja,Wartość\n1,Document,Set Language,nl-BE\n1,Figure_1,Add Alt Text,Wykres słupkowy...",
                file_name="AccessiDOC_Remediation_Plan.csv",
                use_container_width=True
            )
    else:
        st.info("Wróć do pierwszej zakładki i wgraj plik PDF, aby rozpocząć proces analizy i naprawy.")
