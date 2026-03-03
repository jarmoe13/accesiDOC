import streamlit as st
import fitz  # PyMuPDF
import io

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="AccessiDOC AI | PDF Accessibility Studio", layout="wide", page_icon="📄")

# Niestandardowy CSS dla czystego wyglądu (White-label)
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

# --- FUNKCJE POMOCNICZE ---
def process_pdf(file_bytes):
    """Prosty rentgen PDF-a przy użyciu PyMuPDF"""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    metadata = doc.metadata
    
    # Symulacja znalezienia obrazków (do Alt-textów)
    images_found = []
    for page_num in range(min(3, len(doc))): # Skanujemy tylko max 3 strony dla dema
        page = doc.load_page(page_num)
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            images_found.append({"page": page_num + 1, "img_index": img_index, "rect": "Symulacja_wymiarów"})
            
    return {"pages": len(doc), "metadata": metadata, "images": images_found, "doc_ref": doc}

def render_page_image(doc, page_num):
    """Renderuje stronę PDF jako obraz do podglądu"""
    page = doc.load_page(page_num - 1)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) # Wyższa rozdzielczość
    img_bytes = pix.tobytes("png")
    return img_bytes

# --- INTERFEJS UŻYTKOWNIKA ---
st.title("📄 AccessiDOC AI")
st.markdown("**Platforma do audytu i naprawy dostępności cyfrowej dokumentów (WCAG / EAA 2025)**")

# Zakładki aplikacji
tab1, tab2 = st.tabs(["🔍 1. Skaner Dokumentu", "🛠️ 2. Studio Naprawcze (Human-in-the-Loop)"])

with tab1:
    st.subheader("Wgraj plik PDF do analizy")
    st.info("💡 Wersja MVP obsługuje na razie wgrywanie plików z dysku (idealne dla poufnych dokumentów bankowych).")
    
    uploaded_file = st.file_uploader("Wybierz plik PDF (np. Tabela Opłat KBC)", type="pdf")
    
    if uploaded_file is not None:
        with st.spinner("Skanowanie struktur PDF i analizowanie obrazów..."):
            pdf_data = process_pdf(uploaded_file.getvalue())
            st.session_state['pdf_data'] = pdf_data
            st.session_state['file_name'] = uploaded_file.name
            st.session_state['raw_bytes'] = uploaded_file.getvalue()
            
        st.success("Skanowanie zakończone!")
        
        # Metryki
        c1, c2, c3 = st.columns(3)
        c1.metric("Liczba stron", pdf_data["pages"])
        
        title_status = "✅ Posiada" if pdf_data["metadata"].get("title") else "❌ Brak tytułu"
        c2.metric("Tytuł dokumentu", title_status)
        c3.metric("Wykryte obrazy (potencjalny brak Alt)", len(pdf_data["images"]))

with tab2:
    if 'pdf_data' in st.session_state:
        st.subheader(f"Naprawa pliku: {st.session_state['file_name']}")
        
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown("### Podgląd Oryginału")
            page_to_view = st.number_input("Wybierz stronę", min_value=1, max_value=st.session_state['pdf_data']['pages'], value=1)
            img_preview = render_page_image(st.session_state['pdf_data']['doc_ref'], page_to_view)
            st.image(img_preview, caption=f"Strona {page_to_view}")
            
        with col_right:
            st.markdown("### 🤖 Asystent Naprawy AI")
            st.warning("Symulacja analizy Claude AI...")
            
            # Formularz Human-in-the-Loop
            st.write("**Błąd: Brak zdefiniowanego języka dokumentu**")
            lang = st.selectbox("Wybierz język", ["nl-BE (Niderlandzki)", "fr-BE (Francuski)", "en-US (Angielski)", "pl-PL (Polski)"])
            
            st.write("---")
            st.write(f"**Błąd: Obrazy bez tekstu alternatywnego (Alt-Text) na stronie {page_to_view}**")
            
            # Symulacja propozycji AI
            st.text_area("Propozycja AI dla Wykresu 1:", value="Wykres słupkowy przedstawiający wzrost oprocentowania kredytów hipotecznych KBC w 2025 roku, z 3% na 4.2%.", height=100)
            
            if st.button("Zatwierdź zmiany (Akceptuj) ✅", type="primary"):
                st.success("Zmiany zapisane w buforze! (W pełnej wersji zaktualizujemy tu strukturę dokumentu).")
                st.balloons()
                
            st.divider()
            st.download_button(
                label="📥 Eksportuj Raport Napraw (CSV/HTML)",
                data="Symulowany plik z tagami",
                file_name="AccessiDOC_Raport.txt",
                use_container_width=True
            )
    else:
        st.info("Wróć do pierwszej zakładki i wgraj plik, aby rozpocząć proces naprawy.")
