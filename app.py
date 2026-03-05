import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import glob
import pandas as pd
import streamlit as st
import fitz  # PyMuPDF

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="AccessiDOC AI | PDF Accessibility", layout="wide", page_icon="📄")

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

# --- INICJALIZACJA SILNIKA ---
@st.cache_resource
def check_engine():
    """Sprawdza, czy mamy Javę i nasz plik CLI na serwerze."""
    if not shutil.which("java"):
        st.error("🚨 KRYTYCZNY BŁĄD: Brak Javy! Dodaj plik packages.txt z wpisem default-jre.")
        st.stop()
        
    # Szukamy naszego pliku cli-*.jar (niezależnie od numeru wersji)
    cli_jars = glob.glob("cli-*.jar")
    if not cli_jars:
        st.error("🚨 Brak pliku silnika! Wgraj plik cli-1.31.16.jar na GitHuba.")
        st.stop()
        
    return cli_jars[0] # Zwraca nazwę znalezionego pliku

# Zapisujemy nazwę pliku jar do zmiennej globalnej
CLI_JAR_PATH = check_engine()

# --- FUNKCJE SILNIKA ---
def run_verapdf_audit(file_bytes):
    """Analizuje plik za pomocą pliku JAR VeraPDF (Protokół Matterhorn)"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
        tmp_pdf.write(file_bytes)
        tmp_pdf_path = tmp_pdf.name

    # Odpalamy Javę bezpośrednio z naszego cudownego pliku JAR
    command = [
        "java", "-jar", CLI_JAR_PATH,
        "--flavour", "ua1", 
        "--format", "mrr",  
        tmp_pdf_path
    ]
    
    try:
        process = subprocess.run(command, capture_output=True, text=True, check=True)
        xml_output = process.stdout
    except subprocess.CalledProcessError as e:
        os.remove(tmp_pdf_path)
        # TUTAJ JEST ZMIANA - Łapiemy wszystko jak leci!
        pelny_blad = f"STDOUT: {e.stdout} | STDERR: {e.stderr}"
        return {"is_compliant": False, "errors": [{"rule": "Logi Crashu Javy", "description": pelny_blad, "count": 1}]}
    except Exception as e:
        os.remove(tmp_pdf_path)
        return {"is_compliant": False, "errors": [{"rule": "Inny błąd Pythona", "description": str(e), "count": 1}]}

    errors_found = []
    is_compliant = False
    
    try:
        root = ET.fromstring(xml_output)
        profile_status = root.find(".//validationReport")
        if profile_status is not None:
            is_compliant = profile_status.attrib.get("isCompliant") == "true"
            
        rules = root.findall(".//rule")
        for rule in rules:
            if rule.attrib.get("status") == "failed":
                desc_elem = rule.find("description")
                description = desc_elem.text if desc_elem is not None else "Nieznany błąd"
                specification = rule.attrib.get("specification", "PDF/UA")
                clause = rule.attrib.get("clause", "")
                
                checks = rule.findall(".//check")
                error_count = len([c for c in checks if c.attrib.get("status") == "failed"])
                
                errors_found.append({
                    "rule": f"{specification} - {clause}",
                    "description": description,
                    "count": error_count
                })
    except ET.ParseError:
        pass

    os.remove(tmp_pdf_path)
    return {"is_compliant": is_compliant, "errors": errors_found}

def render_page_image(file_bytes, page_num):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(page_num - 1)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) 
    return pix.tobytes("png"), len(doc)

# --- INTERFEJS UŻYTKOWNIKA ---
st.title("📄 AccessiDOC AI | Oparte na VeraPDF")
st.markdown("**Enterprise PDF Accessibility Studio (Zgodność z EAA 2025 i PDF/UA)**")

tab1, tab2 = st.tabs(["🔍 1. Skaner Dokumentu", "🛠️ 2. Studio Naprawcze (AI)"])

with tab1:
    st.subheader("Wgraj plik PDF do analizy")
    uploaded_file = st.file_uploader("Wybierz plik PDF", type="pdf")
    
    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        
        with st.spinner("Skanowanie binarne przez silnik VeraPDF..."):
            audit_results = run_verapdf_audit(file_bytes)
            
            st.session_state['file_bytes'] = file_bytes
            st.session_state['file_name'] = uploaded_file.name
            st.session_state['audit_results'] = audit_results
            
        st.success("Skanowanie zakończone!")
        
        if audit_results["is_compliant"]:
            st.success("✅ Certyfikat Zgodności! Plik spełnia wszystkie rygorystyczne wymogi PDF/UA.")
        else:
            st.error("🚨 Plik nie spełnia wymogów dostępności strukturalnej (PDF/UA).")
            
            st.markdown("### 📋 Raport Błędów (Protokół Matterhorn)")
            if audit_results["errors"]:
                df_errors = pd.DataFrame(audit_results["errors"])
                df_errors.columns = ["Sygnatura Reguły", "Opis Błędu (Zgodnie z protokołem)", "Liczba Wystąpień"]
                st.dataframe(df_errors, use_container_width=True)
            else:
                st.warning("Plik zawiera błędy, ale nie udało się wyodrębnić detali z raportu XML.")

with tab2:
    if 'file_bytes' in st.session_state:
        st.subheader(f"Naprawa pliku: {st.session_state['file_name']}")
        
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown("### Podgląd Oryginału")
            _, total_pages = render_page_image(st.session_state['file_bytes'], 1)
            
            page_to_view = st.number_input("Wybierz stronę", min_value=1, max_value=total_pages, value=1)
            img_preview, _ = render_page_image(st.session_state['file_bytes'], page_to_view)
            st.image(img_preview, caption=f"Strona {page_to_view}")
            
        with col_right:
            st.markdown("### 🤖 Asystent Naprawy AI")
            st.info("Poniżej znajdą się sugestie wygenerowane przez Claude Vision API (Wkrótce)")
            
            st.text_area("Propozycja AI dla brakującego opisu na tej stronie:", 
                         value="Wykres prezentujący udziały rynkowe...", height=100)
            
            if st.button("Zatwierdź zmiany (Akceptuj) ✅", type="primary"):
                st.success("Zmiany zapisane!")
                st.balloons()
    else:
        st.info("Wgraj plik PDF w pierwszej zakładce, aby odblokować panel naprawczy.")
