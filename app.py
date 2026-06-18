import streamlit as st
from google import genai
from google.genai import types
import json
import zipfile
import io
import re

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
# SETUP APLIKASI & STATE
# ==========================================
st.set_page_config(page_title="AutoMock.ai | Builder", layout="wide", page_icon="🤖")

st.markdown("""
    <style>
    .header-style { background: linear-gradient(90deg, #4F46E5, #9333EA); padding: 20px; border-radius: 10px; color: white; margin-bottom: 20px; }
    .st-emotion-cache-1v0mbdj { margin-top: 25px; } /* Adjusting remove button alignment */
    </style>
    <div class="header-style">
        <h1>🤖 AutoMock.ai Builder</h1>
        <p>Enterprise Mock JSON Generator | Crafted by Oktaviansyah 🚀</p>
    </div>
    """, unsafe_allow_html=True)

try:
    api_keys = st.secrets["GEMINI_API_KEYS"]
except KeyError:
    st.error("Konfigurasi API Key tidak ditemukan di secrets.toml.")
    st.stop()

# Inisialisasi State untuk baris parameter dinamis
if 'rows' not in st.session_state:
    st.session_state.rows = [{'id': 0, 'action': 'ADD', 'key': '', 'value': ''}]
if 'row_counter' not in st.session_state:
    st.session_state.row_counter = 1

def add_row():
    st.session_state.rows.append({'id': st.session_state.row_counter, 'action': 'ADD', 'key': '', 'value': ''})
    st.session_state.row_counter += 1

def remove_row(index):
    st.session_state.rows.pop(index)

# ==========================================
# BAGIAN ATAS: TEMPLATE & POLA NAMA
# ==========================================
st.subheader("1. Konfigurasi Master")
base_template = st.text_area("Template Master JSON (Body):", height=150, placeholder='{"data": "sample"}')
filename_template = st.text_input("Pola Nama File:", placeholder="Contoh: mock_response_[code].json")

parsed_json = {}
available_keys = []
if base_template:
    try:
        parsed_json = json.loads(base_template)
        available_keys = get_all_keys(parsed_json)
    except json.JSONDecodeError:
        st.error("⚠️ Format JSON master tidak valid!")

st.divider()

# ==========================================
# KOTAK GEDE 2 (KIRI: BUILDER | KANAN: PREVIEW)
# ==========================================
col_left, col_right = st.columns([1.2, 1])

with col_left:
    st.subheader("🛠️ Konfigurasi Mock")
    
    # --- FIXED PARAMETERS ---
    st.markdown("**A. Pengaturan Request & Response (Fixed)**")
    
    url_input = st.text_input("URL Path / Endpoint:")
    if url_input and not re.match(r'^(http|/|\\w)', url_input):
         st.warning("⚠️ Pastikan URL formatnya benar (diawali '/', 'http', dll)")
            
    c_req1, c_req2 = st.columns(2)
    with c_req1:
        method_input = st.selectbox("Request Method:", ["GET", "POST", "PUT", "DELETE", "PATCH"])
    with c_req2:
        status_input = st.selectbox("Response Status:", [
            "200 OK", "201 Created", "400 Bad Request", "401 Unauthorized", 
            "403 Forbidden", "404 Not Found", "500 Internal Server Error"
        ])
        status_code = int(status_input.split(" ")[0]) # Hanya ambil angkanya saja
        
    c_req3, c_req4 = st.columns(2)
    with c_req3:
        delay_input = st.number_input("Fixed Delay (Milliseconds):", min_value=0, value=0, step=100)
    with c_req4:
        matched_path = st.text_input("Matched JSON Path (Opsional):", placeholder="$.data.id")
        
    st.markdown("---")
    
    # --- DYNAMIC PARAMETERS ---
    st.markdown("**B. Manipulasi Parameter JSON (Variasi)**")
    st.caption("Pilih ADD untuk parameter baru, REMOVE untuk menghapus, atau Pilih Parameter yang sudah ada untuk memodifikasi nilainya.")
    
    for i, row in enumerate(st.session_state.rows):
        c1, c2, c3, c4 = st.columns([2, 3, 3, 1])
        
        # Opsi Dropdown: Gabungan Action & Available Keys
        action_options = ["ADD NEW", "REMOVE EXISTING"] + available_keys
        
        with c1:
            # Jika current action tidak ada di list, set default ke ADD NEW
            current_action = row['action'] if row['action'] in action_options else "ADD NEW"
            selected_action = st.selectbox("Aksi / Target", options=action_options, index=action_options.index(current_action), key=f"act_{row['id']}")
            st.session_state.rows[i]['action'] = selected_action
            
        with c2:
            if selected_action == "ADD NEW":
                st.session_state.rows[i]['key'] = st.text_input("Key Baru", value=row['key'], placeholder="nama_key", key=f"key_{row['id']}")
            else:
                st.session_state.rows[i]['key'] = selected_action # Key otomatis mengikuti target
                st.text_input("Key (Locked)", value=selected_action, disabled=True, key=f"lock_{row['id']}")
                
        with c3:
            if selected_action == "REMOVE EXISTING":
                st.session_state.rows[i]['value'] = ""
                st.text_input("Value", value="-akan dihapus-", disabled=True, key=f"val_{row['id']}")
            else:
                st.session_state.rows[i]['value'] = st.text_input("Isi Value", value=row['value'], placeholder="Contoh: 00, 51 (koma untuk banyak)", key=f"val_{row['id']}")
                
        with c4:
            if st.button("🗑️", key=f"del_{row['id']}"):
                remove_row(i)
                st.rerun()

    if st.button("➕ Tambah Variasi Parameter"):
        add_row()
        st.rerun()


with col_right:
    st.subheader("👁️ Live Preview Hasil")
    
    # Merakit struktur MOCK JSON secara real-time
    preview_body = parsed_json.copy() if parsed_json else {}
    
    # Terapkan modifikasi dasar untuk preview (hanya mengambil value pertama sebelum koma untuk preview)
    for r in st.session_state.rows:
        if not r['action'] or not r['key']: continue
        
        first_val = r['value'].split(",")[0].strip() if r['value'] else ""
        
        if r['action'] == "REMOVE EXISTING":
            if r['key'] in preview_body:
                del preview_body[r['key']]
        else:
            # Mengubah/menambah value. (Catatan: modifikasi nested json lebih kompleks, 
            # untuk preview kita taruh di root level atau modif root level)
            if r['key']:
                preview_body[r['key']] = first_val
                
    preview_json = {
        "request": {
            "method": method_input,
            "url": url_input if url_input else "/"
        },
        "response": {
            "status": status_code,
            "fixedDelayMilliseconds": delay_input,
            "body": preview_body
        }
    }
    
    if matched_path:
        preview_json["request"]["matchedJsonPath"] = matched_path

    st.json(preview_json)

# ==========================================
# BAGIAN BAWAH: GENERATE AI
# ==========================================
st.divider()

if st.button("🚀 GENERATE MULTIPLE FILES (.ZIP)", type="primary", use_container_width=True):
    if not base_template or not filename_template:
        st.error("⚠️ Template JSON dan Pola Nama File harus diisi!")
    elif not url_input:
        st.error("⚠️ URL / Endpoint tidak boleh kosong!")
    else:
        with st.spinner("⏳ AutoMock.ai sedang merakit data dengan AI..."):
            
            # Merakit instruksi variasi untuk Gemini
            variations_text = ""
            for r in st.session_state.rows:
                if r['key']:
                    if r['action'] == "REMOVE EXISTING":
                        variations_text += f"- Hapus parameter '{r['key']}' dari dalam response body.\n"
                    else:
                        variations_text += f"- Ubah/tambah parameter '{r['key']}' di dalam response body dengan nilai: {r['value']} (buatkan kombinasinya jika ada koma)\n"

            # Blueprint dasar yang dikirim ke AI berdasarkan Live Preview
            base_structure = json.dumps(preview_json, indent=2)

            full_prompt = (
                f"1) STRUKTUR DASAR MOCK (WAJIB DIPERTAHANKAN):\n{base_structure}\n\n"
                f"2) POLA NAMA FILE:\n{filename_template}\n\n"
                f"3) ATURAN VARIASI (Terapkan variasi ini PADA BAGIAN 'body' di dalam response):\n{variations_text}\n"
            )
            
            success = False
            for key in api_keys:
                try:
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(
                        model='gemini-3.1-flash-lite',
                        contents=full_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction="Anda adalah AI pembuat file Mock untuk QA. Output WAJIB berupa JSON Array murni di mana setiap item memiliki key 'filename' dan 'content'. 'content' harus mengikuti struktur dasar yang diberikan (ada request & response). JANGAN beri teks apa pun di luar JSON Array.",
                            response_mime_type="application/json",
                            temperature=0.2
                        )
                    )
                    
                    generated_data = json.loads(response.text)
                    
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                        for item in generated_data:
                            fname = item.get('filename', 'mock.json')
                            fcontent = json.dumps(item.get('content', {}), indent=2)
                            zf.writestr(fname, fcontent)
                    zip_buffer.seek(0)
                    
                    st.success("✅ File berhasil di-generate!")
                    st.download_button(
                        label="📥 DOWNLOAD HASIL (.ZIP)",
                        data=zip_buffer,
                        file_name="AutoMock_results.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                    success = True
                    break
                except Exception as e:
                    continue
            
            if not success:
                st.error("❌ Gagal melakukan generate. Periksa format JSON master atau API Key Anda.")