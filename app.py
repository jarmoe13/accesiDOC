import os
import shutil
import requests
import zipfile
import subprocess
import tempfile
import xml.etree.ElementTree as ET
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

# --- AUTOMATYCZNY INSTALATOR VERAPDF ---
@st.cache_resource
def setup_verapdf():
    """Pobiera i instaluje silnik VeraPDF w locie."""
    
    # 1. Zabezpieczenie: Sprawdzamy czy na serwerze jest Java!
    if not shutil.which("java"):
        st.error("🚨 KRYTYCZNY BŁĄD: Brak Javy na serwerze! Upewnij się, że masz na GitHubie plik `packages.txt` z wpisem `default-jre`.")
        st.stop()
        
    engine_dir = os.path.abspath("verapdf-engine")
    
    if not os.path.exists(engine_dir):
        zip_url = "https://software.verapdf.org/releases/1.26/verapdf-greenfield-1.26.5-installer.zip"
        zip_path = "verapdf_installer.zip"
        extract_dir = "verapdf_temp_extract"
        
        with st.spinner("Pobieranie i cicha instalacja silnika VeraPDF... to potrwa około 30 sekund. ☕"):
            try:
                # Pobieranie
                r = requests.get(zip_url, stream=True)
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Rozpakowanie
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # Tworzenie pliku XML dla cichej instalacji
                auto_install_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<AutomatedInstallation langpack="eng">
    <com.izforge.izpack.panels.htmlhello.HTMLHelloPanel id="welcome"/>
    <com.izforge.izpack.panels.target.TargetPanel id="install_dir">
        <installpath>{engine_dir}</installpath>
    </com.izforge.izpack.panels.target.TargetPanel>
    <com.izforge.izpack.panels.packs.PacksPanel id="sdk_pack_select">
        <pack index="0" name="veraPDF GUI" selected="true"/>
        <pack index="1" name="veraPDF Mac and *nix Scripts" selected="true"/>
        <pack index="2" name="veraPDF Validation model" selected="false"/>
        <pack index="3" name="veraPDF Documentation" selected="false"/>
        <pack index="4" name="veraPDF Sample Plugins" selected="false"/>
    </com.izforge.izpack.panels.packs.PacksPanel>
    <com.izforge.izpack.panels.install.InstallPanel id="install"/>
    <com.izforge.izpack.panels.finish.FinishPanel id="finish"/>
</AutomatedInstallation>"""
                
                xml_path = "auto-install.xml"
                with open(xml_path, "w", encoding="utf-8") as f:
                    f.write(auto_install_xml)
                
                # Szukanie pliku .jar instalatora
                installer_jar = None
                for root_dir, dirs, files in os.walk(extract_dir):
                    for file in files:
                        if file.startswith("verapdf-izpack-installer") and file.endswith(".jar"):
                            installer_jar = os.path.join(root_dir, file)
                            break
                
                if not installer_jar:
                    st.error("Nie znaleziono pliku instalatora Java wewnątrz ZIP.")
                    return False
                
                # Uruchomienie instalacji
                subprocess.run(["java", "-jar", installer_jar, xml_path], check=True)
                
                # Sprzątanie
                os.remove(zip_path)
                os.remove(xml_path)
                shutil.rmtree(extract_dir)
                
                # Uprawnienia (Linux/Streamlit)
                if os.name != 'nt':
                    executable_path = os.path.join(engine_dir, "verapdf")
                    if os.path.exists(executable_path):
                        os.chmod(executable_path, 0o755)
                        
            except Exception as e:
                st.error(f"Szczegółowy błąd instalacji: {e}")
                return False
    return True

# --- INICJALIZACJA ---
setup_verapdf()

# --- FUNKCJE SILNIKA ---
def run_verapdf_audit(file_bytes):
    """Analizuje plik za pomocą zainstalowanego VeraPDF (Protokół Matterhorn)"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
        tmp_pdf.write(file_bytes)
        tmp_pdf_path = tmp_pdf.name

    exe_name = "verapdf.bat" if os.name == 'nt' else "verapdf"
    verapdf_executable = os.path.join("verapdf-engine", exe_name) 
    
    command = [
        verapdf_executable, 
        "--flavour", "ua1", 
        "--format", "mrr",  
        tmp_pdf_path
    ]
    
    try:
        process = subprocess.run(command, capture_output=True, text=True, check=True)
        xml_output = process.stdout
    except Exception as e:
        os.remove(tmp_pdf_path)
        return {"is_compliant": False, "errors": [{"rule": "Błąd Silnika", "description": str(e), "count": 1}]}

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
