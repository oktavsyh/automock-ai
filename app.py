import streamlit as st
from google import genai
from google.genai import types
import json
import zipfile
import io

# ==========================================
# FUNGSI PEMBANTU
# ==========================================
def get_all_keys(d, parent_key=''):
    keys = []
    if isinstance(d, dict):
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, (dict, list)):
                keys.extend(get_all_keys(v, new_key))
            else:
                keys.append(new_key)
    elif isinstance(d, list):
        for i, v in enumerate(d):
            new_key = f"{parent_key}[{i}]"
            if isinstance(v, (dict, list)):
                keys.extend(get_all_keys(v, new_key))
            else:
                keys.append(new_key)
    return keys

# ==========================================
# SETUP APLIKASI
# ==========================================
st.set_page_config(page_title="AutoMock.ai", layout="wide", page_icon="🤖")

st.markdown("""
    <style>
    .header-style {
        background: linear-gradient(90deg, #4F46E5, #9333EA);
        padding: 20px;
        border-radius: 10px;
        color: white;
        margin-bottom: 20px;
    }
    </style>
    <div class="header-style">
        <h1>🤖 AutoMock.ai</h1>
        <p>Intelligent JSON Simulator Generator | Crafted by Oktaviansyah 🚀</p>
    </div>
    """, unsafe_allow_html=True)

try:
    api_keys = st.secrets["GEMINI_API_KEYS"]
except KeyError:
    st.error("Konfigurasi API Key tidak ditemukan di secrets.toml.")
    st.stop()

# ==========================================
# STEP 1: VALIDASI
# ==========================================
st.subheader("1. Template Master JSON")
base_template = st.text_area("Tempelkan JSON master di sini:", height=200)

if st.button("🔍 Validasi & Muat Template"):
    if base_template:
        try:
            st.session_state['parsed_json'] = json.loads(base_template)
            st.session_state['available_keys'] = get_all_keys(st.session_state['parsed_json'])
            st.success("Template berhasil dimuat!")
        except:
            st.error("JSON tidak valid!")
    else:
        st.warning("Masukkan JSON terlebih dahulu.")

# ==========================================
# STEP 2: KONFIGURASI
# ==========================================
st.divider()
st.subheader("2. Konfigurasi Variasi")
col1, col2 = st.columns(2)

with col1:
    filename_template = st.text_area("Pola Nama File:", placeholder="Contoh: sub_upgrade_[code].json")

with col2:
    available_keys = st.session_state.get('available_keys', [])
    selected_keys = st.multiselect("Pilih parameter dari JSON:", options=available_keys)
    
    modifications = {}
    for k in selected_keys:
        modifications[k] = st.text_input(
            f"Variasi untuk '{k}':", 
            help="Gunakan koma (,) sebagai pemisah. Contoh: 00, 51, 99"
        )

# ==========================================
# STEP 3: GENERATE
# ==========================================
st.divider()
if st.button("🚀 PROSES & GENERATE FILE (.ZIP)", type="primary", use_container_width=True):
    if 'parsed_json' not in st.session_state:
        st.warning("Harap validasi JSON template di Step 1 terlebih dahulu.")
    elif not filename_template or not modifications:
        st.warning("Lengkapi konfigurasi di Step 2.")
    else:
        with st.spinner("⏳ AutoMock.ai sedang merakit variasi data..."):
            user_prompt = "\n".join([f"- '{k}': {v}" for k, v in modifications.items()])
            full_prompt = f"JSON:\n{base_template}\n\nPOLA: {filename_template}\n\nATURAN:\n{user_prompt}"
            
            success = False
            for key in api_keys:
                try:
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(
                        model='gemini-3.1-flash-lite',
                        contents=full_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction="Berikan array JSON murni berisi key 'filename' dan 'content'.",
                            response_mime_type="application/json",
                            temperature=0.2
                        )
                    )
                    data = json.loads(response.text)
                    
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                        for item in data:
                            zf.writestr(item['filename'], json.dumps(item['content'], indent=2))
                    zip_buffer.seek(0)
                    
                    st.download_button("📥 DOWNLOAD HASIL (.ZIP)", zip_buffer, "AutoMock_results.zip", "application/zip", use_container_width=True)
                    
                    st.success("Generate sukses!")
                    with st.expander("👁️ Lihat Preview Struktur File"):
                        for item in data:
                            st.markdown(f"**📄 {item.get('filename')}**")
                            st.json(item.get('content'))
                    
                    success = True
                    break
                except Exception as e:
                    continue
            if not success:
                st.error("Gagal melakukan generate. Periksa koneksi atau API Key.")