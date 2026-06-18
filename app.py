import streamlit as st
from google import genai
from google.genai import types
import json
import zipfile
import io
import re

# ==========================================
# FUNGSI MANIPULASI NESTED JSON
# ==========================================
def get_all_keys(d, parent_key=''):
    keys = []
    if isinstance(d, dict):
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                keys.extend(get_all_keys(v, new_key))
            else:
                keys.append(new_key)
    return keys

def set_nested_value(d, path, value):
    """Menyisipkan atau mengubah nilai pada struktur path bersarang (deep tree)"""
    parts = path.split('.')
    current = d
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value

def delete_nested_value(d, path):
    """Menghapus parameter tepat pada koordinat path bersarangnya"""
    parts = path.split('.')
    current = d
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            return
        current = current[part]
    if parts[-1] in current:
        current.pop(parts[-1])

# ==========================================
# SETUP APLIKASI & SESSION STATE
# ==========================================
st.set_page_config(page_title="AutoMock.ai | Builder", layout="wide", page_icon="🤖")

st.markdown("""
    <style>
    .header-style { background: linear-gradient(90deg, #4F46E5, #9333EA); padding: 20px; border-radius: 10px; color: white; margin-bottom: 20px; }
    </style>
    <div class="header-style">
        <h1>🤖 AutoMock.ai Builder</h1>
        <p>Enterprise Mock JSON Generator | Crafted by Oktaviansyah and Designed by Albert Shanta 🚀</p>
    </div>
    """, unsafe_allow_html=True)

try:
    api_keys = st.secrets["GEMINI_API_KEYS"]
except KeyError:
    st.error("Konfigurasi API Key tidak ditemukan di secrets.toml.")
    st.stop()

# --- INISIALISASI VARIABEL STATE ---
if 'master_json_input' not in st.session_state: st.session_state.master_json_input = ""
if 'last_parsed_master' not in st.session_state: st.session_state.last_parsed_master = ""
if 'fixed_url' not in st.session_state: st.session_state.fixed_url = "/api/v1/subscription/upgrade"
if 'fixed_method' not in st.session_state: st.session_state.fixed_method = "POST"
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

method_list = ["GET", "POST", "PUT", "DELETE", "PATCH"]
status_list = ["200 OK", "201 Created", "400 Bad Request", "401 Unauthorized", "403 Forbidden", "404 Not Found", "500 Internal Server Error"]

# ==========================================
# DETEKSI AKSI MANUAL (CTRL + ENTER) PADA MASTER JSON
# ==========================================
is_json_valid = True  # Flag global untuk status validitas JSON

if st.session_state.master_json_input != st.session_state.last_parsed_master:
    val = st.session_state.master_json_input
    if val.strip():
        try:
            parsed = json.loads(val)
            req = parsed.get("request", {})
            res = parsed.get("response", {})
            
            if "url" in req: st.session_state.fixed_url = req["url"]
            if "method" in req and req["method"].upper() in method_list: 
                st.session_state.fixed_method = req["method"].upper()
                
            body_patterns = req.get("bodyPatterns", [])
            if body_patterns and isinstance(body_patterns, list) and len(body_patterns) > 0:
                st.session_state.fixed_matched = body_patterns[0].get("matchesJsonPath", "")
                
            if "status" in res:
                status_str = str(res["status"])
                for s in status_list:
                    if s.startswith(status_str):
                        st.session_state.fixed_status = s
                        break
            if "fixedDelayMilliseconds" in res:
                st.session_state.fixed_delay = int(res["fixedDelayMilliseconds"])
                
            st.session_state.last_parsed_master = val
            is_json_valid = True
        except json.JSONDecodeError:
            is_json_valid = False

# ==========================================
# FUNGSI KOMPILASI AKHIR (SMART TEMPLATE PLACEHOLDER & STRICT ORDERING)
# ==========================================
def compile_final_json():
    try:
        base = json.loads(st.session_state.master_json_input) if st.session_state.master_json_input.strip() else {}
    except json.JSONDecodeError:
        # Jika error, kembalikan dict berisi pesan error agar Live Preview tidak ngaco
        return {"error": "⚠️ Format Master JSON tidak valid. Silakan perbaiki sintaks JSON di atas."}

    if base and "request" not in base and "response" not in base:
        base = {"request": {}, "response": {"jsonBody": base}}

    if "request" not in base: base["request"] = {}
    if "response" not in base: base["response"] = {}

    base["request"]["url"] = st.session_state.fixed_url
    base["request"]["method"] = st.session_state.fixed_method
    
    if st.session_state.fixed_matched:
        base["request"]["bodyPatterns"] = [{"matchesJsonPath": st.session_state.fixed_matched}]
    else:
        base["request"].pop("bodyPatterns", None)

    base["response"]["status"] = int(st.session_state.fixed_status.split(" ")[0])
    base["response"]["fixedDelayMilliseconds"] = st.session_state.fixed_delay

    body_key = "body" if ("body" in base["response"] and "jsonBody" not in base["response"]) else "jsonBody"
    if body_key not in base["response"]: base["response"][body_key] = {}

    # Penggabungan Setelan Komponen Variasi dalam bentuk Placeholder "{key}"
    for row in st.session_state.rows:
        act = row.get('action', 'ADD NEW')
        k = row.get('key', '').strip()
        if not k: continue

        leaf_key = k.split('.')[-1]
        placeholder_value = f"{{{leaf_key}}}"

        if act == "REMOVE EXISTING":
            if k.startswith("headers."):
                if "headers" in base["response"]:
                    delete_nested_value(base["response"]["headers"], k[8:])
            else:
                delete_nested_value(base["response"][body_key], k)
        else:
            if k.startswith("headers."):
                if "headers" not in base["response"] or not isinstance(base["response"]["headers"], dict):
                    base["response"]["headers"] = {}
                set_nested_value(base["response"]["headers"], k[8:], placeholder_value)
            else:
                set_nested_value(base["response"][body_key], k, placeholder_value)

    # Membangun Urutan Kaku
    ordered_json = {"request": {}, "response": {}}
    ordered_json["request"]["url"] = base["request"]["url"]
    ordered_json["request"]["method"] = base["request"]["method"]
    if "bodyPatterns" in base["request"]:
        ordered_json["request"]["bodyPatterns"] = base["request"]["bodyPatterns"]
    for k, v in base["request"].items():
        if k not in ["url", "method", "bodyPatterns"]:
            ordered_json["request"][k] = v

    ordered_json["response"]["status"] = base["response"]["status"]
    ordered_json["response"]["fixedDelayMilliseconds"] = base["response"]["fixedDelayMilliseconds"]
    if "headers" in base["response"]:
        ordered_json["response"]["headers"] = base["response"]["headers"]
    ordered_json["response"][body_key] = base["response"][body_key]
    for k, v in base["response"].items():
        if k not in ["status", "fixedDelayMilliseconds", "headers", body_key]:
            ordered_json["response"][k] = v

    return ordered_json

# ==========================================
# BAGIAN 1: FORM UTAMA
# ==========================================
st.subheader("1. Konfigurasi Master")
st.text_area(
    "Template Master JSON (Tekan Ctrl + Enter untuk Menerapkan Perubahan):", 
    height=250, 
    key="master_json_input"
)
filename_template = st.text_input("Pola Nama File:", placeholder="Contoh: mock_response_[code].json", value="mock_response_[code].json")

# EKSTRAKSI SEMUA KUNCI & PENANGANAN ERROR JSON
parsed_root = {}
available_keys = []
if st.session_state.master_json_input.strip():
    try:
        parsed_root = json.loads(st.session_state.master_json_input)
        res_node = parsed_root.get("response", {})
        
        body_node = res_node.get("jsonBody", res_node.get("body", {}))
        if isinstance(body_node, dict):
            available_keys.extend(get_all_keys(body_node))
            
        headers_node = res_node.get("headers", {})
        if isinstance(headers_node, dict):
            headers_keys = get_all_keys(headers_node)
            available_keys.extend([f"headers.{hk}" for hk in headers_keys])
            
        is_json_valid = True
    except json.JSONDecodeError as e:
        is_json_valid = False
        st.error(f"⚠️ Terjadi kesalahan format pada Master JSON. Detail: {e}")

st.divider()

# ==========================================
# BAGIAN 2: PENGATURAN FIXED & PREVIEW
# ==========================================
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("🛠️ Pengaturan Fixed (Req & Res)")
    st.text_input("URL Path / Endpoint:", key="fixed_url")
    
    c_req1, c_req2 = st.columns(2)
    with c_req1: st.selectbox("Request Method:", method_list, key="fixed_method")
    with c_req2: st.selectbox("Response Status:", status_list, key="fixed_status")
        
    c_req3, c_req4 = st.columns(2)
    with c_req3: st.number_input("Fixed Delay (Milliseconds):", min_value=0, step=100, key="fixed_delay")
    with c_req4: st.text_input("Matched JSON Path (Opsional):", key="fixed_matched")

with col_right:
    st.subheader("👁️ Live Preview Hasil")
    compiled_preview = compile_final_json()
    # Jika json tidak valid, tampilkan dengan tema error di preview
    if "error" in compiled_preview:
        st.warning(compiled_preview["error"])
    else:
        st.json(compiled_preview)

# Fungsi Callback Anti StreamlitAPIException
def sync_form_to_master():
    if is_json_valid:
        st.session_state.master_json_input = json.dumps(compile_final_json(), indent=2)
        st.session_state.last_parsed_master = st.session_state.master_json_input
    else:
        pass # Cegah sinkronisasi kalau JSON lagi error

st.button("💾 Sinkronisasikan Form ke Template Master", use_container_width=True, on_click=sync_form_to_master, disabled=not is_json_valid)

# ==========================================
# BAGIAN 3: MANIPULASI PARAMETER VARIASI (FULL WIDTH)
# ==========================================
st.divider()
st.subheader("🔀 Manipulasi Parameter JSON (Variasi)")
st.caption("Gunakan kolom input Key secara bebas hanya pada aksi ADD NEW & REMOVE EXISTING. Parameter bawaan akan otomatis terkunci.")

for i, row in enumerate(st.session_state.rows):
    c1, c2, c3, c4 = st.columns([2, 3, 3, 1])
    action_options = ["ADD NEW", "REMOVE EXISTING"] + available_keys
    
    with c1:
        current_act = row['action'] if row['action'] in action_options else "ADD NEW"
        selected_act = st.selectbox("Aksi / Target", action_options, index=action_options.index(current_act), key=f"act_{row['id']}")
        st.session_state.rows[i]['action'] = selected_act
        
    with c2:
        is_existing_param = selected_act not in ["ADD NEW", "REMOVE EXISTING"]
        
        if is_existing_param:
            st.session_state.rows[i]['key'] = selected_act
            st.text_input("Key (Terkunci)", value=selected_act, disabled=True, key=f"key_disp_{row['id']}")
        else:
            st.session_state.rows[i]['key'] = st.text_input("Nama Key", value=row['key'], key=f"key_input_{row['id']}", placeholder="Masukkan path/nama parameter (e.g. systemData.gatewayNumber)")
            
    with c3:
        if selected_act == "REMOVE EXISTING":
            st.session_state.rows[i]['value'] = ""
            st.text_input("Value", value="- Sifat Penghapusan -", disabled=True, key=f"val_disp_{row['id']}")
        else:
            st.session_state.rows[i]['value'] = st.text_input("Isi Value Variasi", value=row['value'], key=f"val_input_{row['id']}", placeholder="Contoh: ValA, ValB (Gunakan koma untuk multi-variasi)")
            
    with c4:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🗑️ Hapus", key=f"del_{row['id']}", use_container_width=True):
            remove_row(i)
            st.rerun()

if st.button("➕ Tambah Variasi Parameter"):
    add_row()
    st.rerun()

# ==========================================
# BAGIAN 4: PEMBUATAN FILE ZIP DENGAN AI
# ==========================================
st.divider()

if st.button("🚀 GENERATE MULTIPLE FILES (.ZIP)", type="primary", use_container_width=True, disabled=not is_json_valid):
    if not st.session_state.master_json_input.strip():
        st.error("⚠️ Template JSON Utama tidak boleh kosong!")
    elif not is_json_valid:
        st.error("⚠️ Perbaiki dulu format Master JSON Anda sebelum melakukan Generate!")
    else:
        with st.spinner("⏳ AutoMock.ai sedang menyusun struktur variasi file mock..."):
            variations_text = ""
            for r in st.session_state.rows:
                if r['key']:
                    if r['action'] == "REMOVE EXISTING":
                        variations_text += f"- Hapus parameter '{r['key']}' dari response.\n"
                    elif r['action'] == "ADD NEW":
                        variations_text += f"- Tambahkan parameter baru '{r['key']}' ke response body dengan nilai/kombinasi: {r['value']}.\n"
                    else:
                        variations_text += f"- Ubah nilai parameter existing '{r['key']}' menjadi variasi nilai berikut: {r['value']}.\n"

            base_structure = json.dumps(compiled_preview, indent=2)

            full_prompt = (
                f"1) STRUKTUR CETAKAN UTAMA:\n{base_structure}\n\n"
                f"2) POLA NAMA FILE:\n{filename_template}\n\n"
                f"3) INSTRUKSI VARIASI DATA:\n{variations_text}\n"
            )
            
            success = False
            for key in api_keys:
                try:
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(
                        model='gemini-3.1-flash-lite',
                        contents=full_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction="Anda adalah sistem pembuat berkas otomatis untuk QA. Kembalikan data dalam bentuk JSON Array murni. Setiap item wajib memiliki kunci 'filename' dan 'content'. Node 'content' wajib mempertahankan susunan struktural kaku secara mutlak (request: url, method, bodyPatterns; response: status, fixedDelayMilliseconds, headers, jsonBody). Jangan menyertakan penulisan markdown di luar format array.",
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
                    
                    st.success("✅ Seluruh berkas skenario variasi berhasil dibuat!")
                    st.download_button(
                        label="📥 DOWNLOAD HASIL (.ZIP)",
                        data=zip_buffer,
                        file_name="AutoMock_Skenario_QA.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                    success = True
                    break
                except:
                    continue
            
            if not success:
                st.error("❌ Terjadi kendala saat memproses generate berkas. Periksa validitas API Key atau susunan JSON Anda.")