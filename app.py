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
    </style>
    <div class="header-style">
        <h1>🤖 AutoMock.ai Builder</h1>
        <p>Enterprise Mock JSON Generator | Crafted by Oktaviansyah & Designed by Albert Shanta 🚀</p>
    </div>
    """, unsafe_allow_html=True)

try:
    api_keys = st.secrets["GEMINI_API_KEYS"]
except KeyError:
    st.error("Konfigurasi API Key tidak ditemukan di secrets.toml.")
    st.stop()

# --- DAFTAR PILIHAN FIXED ---
method_list = ["GET", "POST", "PUT", "DELETE", "PATCH"]
status_list = ["200 OK", "201 Created", "400 Bad Request", "401 Unauthorized", "403 Forbidden", "404 Not Found", "500 Internal Server Error"]

# --- INISIALISASI SESSION STATE ---
if 'master_json_input' not in st.session_state: st.session_state.master_json_input = ""
if 'fixed_url' not in st.session_state: st.session_state.fixed_url = "/api/v1/test"
if 'fixed_method' not in st.session_state: st.session_state.fixed_method = "GET"
if 'fixed_status' not in st.session_state: st.session_state.fixed_status = "200 OK"
if 'fixed_delay' not in st.session_state: st.session_state.fixed_delay = 0
if 'fixed_matched' not in st.session_state: st.session_state.fixed_matched = ""

if 'rows' not in st.session_state: st.session_state.rows = [{'id': 0, 'action': 'ADD NEW', 'key': '', 'value': ''}]
if 'row_counter' not in st.session_state: st.session_state.row_counter = 1

def add_row():
    st.session_state.rows.append({'id': st.session_state.row_counter, 'action': 'ADD NEW', 'key': '', 'value': ''})
    st.session_state.row_counter += 1

def remove_row(index):
    st.session_state.rows.pop(index)

# ==========================================
# FUNGSI PENGATUR URUTAN KETAT (STRICT ORDERING)
# ==========================================
def build_ordered_wiremock(parsed):
    """Membongkar dan merakit ulang JSON dengan urutan ketat sesuai instruksi."""
    if "request" not in parsed and "response" not in parsed:
        parsed = {"request": {}, "response": {"jsonBody": parsed}}

    old_req = parsed.get("request", {})
    old_res = parsed.get("response", {})

    ordered_json = {"request": {}, "response": {}}

    # --- 1. REQUEST ORDERING (STRICT) ---
    ordered_json["request"]["url"] = st.session_state.fixed_url
    ordered_json["request"]["method"] = st.session_state.fixed_method
    
    if st.session_state.fixed_matched:
        ordered_json["request"]["bodyPatterns"] = [{"matchesJsonPath": st.session_state.fixed_matched}]
        
    for k, v in old_req.items():
        if k not in ["url", "urlPath", "urlPattern", "method", "bodyPatterns"]:
            ordered_json["request"][k] = v

    # --- 2. RESPONSE ORDERING (STRICT) ---
    ordered_json["response"]["status"] = int(st.session_state.fixed_status.split(" ")[0])
    ordered_json["response"]["fixedDelayMilliseconds"] = st.session_state.fixed_delay
    
    if "headers" in old_res:
        ordered_json["response"]["headers"] = old_res["headers"]
    
    if "jsonBody" in old_res:
        ordered_json["response"]["jsonBody"] = old_res["jsonBody"]
    elif "body" in old_res:
        ordered_json["response"]["body"] = old_res["body"]
        
    for k, v in old_res.items():
        if k not in ["status", "fixedDelayMilliseconds", "headers", "jsonBody", "body"]:
            ordered_json["response"][k] = v

    return ordered_json

# ==========================================
# FUNGSI SINKRONISASI BARU
# ==========================================
def update_master_json_from_variations():
    try:
        current_data = json.loads(st.session_state.master_json_input)
        if "response" not in current_data: current_data["response"] = {}
        if "jsonBody" not in current_data["response"]: current_data["response"]["jsonBody"] = {}
            
        body = current_data["response"]["jsonBody"]
        
        for row in st.session_state.rows:
            if not row['key']: continue
            
            # Jika ADD NEW, tambahkan key baru
            if row['action'] == "ADD NEW":
                body[row['key']] = row['value']
            # Jika Modify (yaitu key yang sudah ada), update nilainya
            elif row['action'] not in ["ADD NEW", "REMOVE EXISTING"]:
                body[row['key']] = row['value']
            # Jika REMOVE
            elif row['action'] == "REMOVE EXISTING":
                body.pop(row['key'], None)
                
        st.session_state.master_json_input = json.dumps(build_ordered_wiremock(current_data), indent=2)
    except:
        pass

# ==========================================
# CALLBACKS: 2-WAY DATA BINDING AJAIB
# ==========================================
def sync_from_master():
    """Membaca teks dari Master JSON dan mengupdate input di bawahnya"""
    val = st.session_state.master_json_input
    if not val.strip(): return
    try:
        parsed = json.loads(val)
        
        if "request" not in parsed and "response" not in parsed:
            parsed = {"request": {}, "response": {"jsonBody": parsed}}
            
        req = parsed.get("request", {})
        res = parsed.get("response", {})
        
        # Ekstrak data dari teks ke UI Variable
        if "url" in req: st.session_state.fixed_url = req["url"]
        elif "urlPath" in req: st.session_state.fixed_url = req["urlPath"]
        elif "urlPattern" in req: st.session_state.fixed_url = req["urlPattern"]
        
        if "method" in req and req["method"].upper() in method_list:
            st.session_state.fixed_method = req["method"].upper()
            
        body_patterns = req.get("bodyPatterns", [])
        if body_patterns and isinstance(body_patterns, list) and len(body_patterns) > 0 and "matchesJsonPath" in body_patterns[0]:
            st.session_state.fixed_matched = body_patterns[0]["matchesJsonPath"]
            
        if "status" in res:
            status_str = str(res["status"])
            for s in status_list:
                if s.startswith(status_str):
                    st.session_state.fixed_status = s
                    break
                    
        if "fixedDelayMilliseconds" in res:
            st.session_state.fixed_delay = int(res["fixedDelayMilliseconds"])

        # Rakit ulang agar urutannya paten sesuai instruksi bos
        ordered = build_ordered_wiremock(parsed)
        st.session_state.master_json_input = json.dumps(ordered, indent=2)
        
    except Exception:
        pass

def sync_from_inputs():
    """Membaca perubahan dari form input dan mengupdate Master JSON di atas"""
    val = st.session_state.master_json_input
    try:
        parsed = json.loads(val) if val.strip() else {}
    except:
        parsed = {}
        
    # Selalu rakit ulang dengan format baku setiap kali ada perubahan UI
    ordered = build_ordered_wiremock(parsed)
    st.session_state.master_json_input = json.dumps(ordered, indent=2)


# ==========================================
# BAGIAN 1: TEMPLATE & POLA NAMA
# ==========================================
st.subheader("1. Konfigurasi Master")
st.text_area(
    "Template Master JSON (WireMock Format / Body):", 
    height=300, 
    placeholder='{"request": {...}, "response": {...}} atau sekadar {"data": "sample"}', 
    key="master_json_input", 
    on_change=sync_from_master
)

filename_template = st.text_input("Pola Nama File:", placeholder="Contoh: mock_response_[code].json")

parsed_json = {}
available_keys = []
if st.session_state.master_json_input.strip():
    try:
        parsed_json = json.loads(st.session_state.master_json_input)
        available_keys = get_all_keys(parsed_json)
    except json.JSONDecodeError:
        st.error("⚠️ Format JSON master tidak valid!")

st.divider()

# ==========================================
# BAGIAN 2: BUILDER FIXED KIRI & PREVIEW KANAN
# ==========================================
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("🛠️ Pengaturan Fixed (Req & Res)")
    
    url_input = st.text_input("URL Path / Endpoint:", key="fixed_url", on_change=sync_from_inputs)
    if url_input and not re.match(r'^(http|/|\\w)', url_input):
         st.warning("⚠️ Pastikan URL formatnya benar (diawali '/', 'http', dll)")
            
    c_req1, c_req2 = st.columns(2)
    with c_req1:
        st.selectbox("Request Method:", method_list, key="fixed_method", on_change=sync_from_inputs)
    with c_req2:
        st.selectbox("Response Status:", status_list, key="fixed_status", on_change=sync_from_inputs)
        
    c_req3, c_req4 = st.columns(2)
    with c_req3:
        st.number_input("Fixed Delay (Milliseconds):", min_value=0, step=100, key="fixed_delay", on_change=sync_from_inputs)
    with c_req4:
        st.text_input("Matched JSON Path (Opsional):", placeholder="$.data.id", key="fixed_matched", on_change=sync_from_inputs)

with col_right:
    st.subheader("👁️ Live Preview Hasil")
    preview_container = st.empty()

# ==========================================
# BAGIAN 3: PARAMETER DINAMIS (FULL WIDTH)
# ==========================================
st.divider()
st.subheader("🔀 Manipulasi Parameter JSON (Variasi)")
st.caption("Pilih ADD untuk parameter baru, REMOVE untuk menghapus, atau Pilih Parameter yang sudah ada untuk memodifikasi nilainya.")

for i, row in enumerate(st.session_state.rows):
    c1, c2, c3, c4 = st.columns([2, 3, 3, 1])
    action_options = ["ADD NEW", "REMOVE EXISTING"] + available_keys
    
    with c1:
        st.session_state.rows[i]['action'] = st.selectbox("Action", action_options, key=f"a{row['id']}", on_change=update_master_json_from_variations)
    
    with c2:
        # LOGIKA: Jika action adalah ADD NEW, baru input box aktif. 
        # Jika action adalah salah satu dari available_keys, maka dia kunci (disabled).
        is_locked = st.session_state.rows[i]['action'] not in ["ADD NEW", "REMOVE EXISTING"]
        
        if not is_locked:
            st.session_state.rows[i]['key'] = st.text_input("Key", value=row['key'], key=f"k{row['id']}", on_change=update_master_json_from_variations)
        else:
            # Mengunci input dengan nilai dari dropdown
            st.session_state.rows[i]['key'] = st.session_state.rows[i]['action']
            st.text_input("Key", value=st.session_state.rows[i]['action'], disabled=True, key=f"k{row['id']}")
            
    with c3:
        st.session_state.rows[i]['value'] = st.text_input("Value", value=row['value'], key=f"v{row['id']}", on_change=update_master_json_from_variations)
            
    with c4:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        if st.button("🗑️", key=f"del{row['id']}", use_container_width=True):
            remove_row(i)
            update_master_json_from_variations()
            st.rerun()

if st.button("➕ Tambah Variasi Parameter"):
    add_row()
    st.rerun()

# --- INJECT PREVIEW KANAN ---
# Preview akan persis menampilkan apa yang ada di kotak Master JSON, karena Master JSON 
# sekarang secara konstan sudah dirapikan posisinya oleh fungsi build_ordered_wiremock()
preview_json = parsed_json.copy() if parsed_json else {
    "request": { "url": st.session_state.fixed_url, "method": st.session_state.fixed_method },
    "response": { "status": int(st.session_state.fixed_status.split(" ")[0]), "fixedDelayMilliseconds": st.session_state.fixed_delay }
}
preview_container.json(preview_json)

# ==========================================
# BAGIAN 4: GENERATE AI
# ==========================================
st.divider()

if st.button("🚀 GENERATE MULTIPLE FILES (.ZIP)", type="primary", use_container_width=True):
    if not st.session_state.master_json_input.strip() or not filename_template:
        st.error("⚠️ Template JSON dan Pola Nama File harus diisi!")
    elif not st.session_state.fixed_url:
        st.error("⚠️ URL / Endpoint tidak boleh kosong!")
    else:
        with st.spinner("⏳ AutoMock.ai sedang merakit data dengan AI..."):
            
            variations_text = ""
            for r in st.session_state.rows:
                if r['key']:
                    if r['action'] == "REMOVE EXISTING":
                        variations_text += f"- Hapus parameter '{r['key']}' dari struktur JSON.\n"
                    else:
                        variations_text += f"- Ubah/tambah parameter '{r['key']}' dengan nilai: {r['value']} (buatkan kombinasinya jika ada pemisah koma)\n"

            base_structure = json.dumps(preview_json, indent=2)

            full_prompt = (
                f"1) STRUKTUR DASAR MOCK (JADIKAN CETAKAN UTAMA):\n{base_structure}\n\n"
                f"2) POLA NAMA FILE:\n{filename_template}\n\n"
                f"3) ATURAN VARIASI:\n{variations_text}\n"
            )
            
            success = False
            for key in api_keys:
                try:
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(
                        model='gemini-3.1-flash-lite',
                        contents=full_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction="Anda adalah AI pembuat file Mock untuk QA. Output WAJIB berupa JSON Array murni di mana setiap item memiliki key 'filename' dan 'content'. 'content' harus mematuhi urutan struktur dasar secara persis, yaitu request (url, method, bodyPatterns) dan response (status, headers, fixedDelayMilliseconds, jsonBody/body). Lakukan variasi data HANYA pada bagian body sesuai aturan. JANGAN beri teks apa pun di luar JSON Array.",
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