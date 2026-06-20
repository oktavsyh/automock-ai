import streamlit as st
from google import genai
from google.genai import types
import json
import zipfile
import io
import re

# ==========================================
# NESTED JSON MANIPULATION FUNCTIONS
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
    """Insert or update value in a deep nested path"""
    parts = path.split('.')
    current = d
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value

def delete_nested_value(d, path):
    """Delete a parameter at its exact nested coordinate"""
    parts = path.split('.')
    current = d
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            return
        current = current[part]
    if parts[-1] in current:
        current.pop(parts[-1])

# ==========================================
# APP SETUP & SESSION STATE
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
    st.error("API Key configuration not found in secrets.toml.")
    st.stop()

# --- INITIALIZE STATE VARIABLES ---
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
# MANUAL ACTION DETECTION ON MASTER JSON
# ==========================================
is_json_valid = True

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
# FINAL COMPILATION & BLUEPRINT FUNCTION
# ==========================================
def compile_final_json():
    try:
        base = json.loads(st.session_state.master_json_input) if st.session_state.master_json_input.strip() else {}
    except json.JSONDecodeError:
        return {"error": "⚠️ Invalid Master JSON format. Please fix the JSON syntax above."}

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
# AUTO-SYNC & DELETE CALLBACK
# ==========================================
def auto_sync():
    for row in st.session_state.rows:
        rid = row['id']
        if f"act_{rid}" in st.session_state: row['action'] = st.session_state[f"act_{rid}"]
        if row['action'] not in ["ADD NEW", "REMOVE EXISTING"]:
            row['key'] = row['action']
        else:
            if f"key_input_{rid}" in st.session_state: row['key'] = st.session_state[f"key_input_{rid}"]
        if f"val_input_{rid}" in st.session_state: row['value'] = st.session_state[f"val_input_{rid}"]

    if is_json_valid:
        compiled = compile_final_json()
        if "error" not in compiled:
            st.session_state.master_json_input = json.dumps(compiled, indent=2)
            st.session_state.last_parsed_master = st.session_state.master_json_input

def handle_delete_row(index, row_data):
    """Callback to delete a row and revert the ADD NEW value from Master JSON"""
    try:
        if is_json_valid and st.session_state.master_json_input.strip():
            base = json.loads(st.session_state.master_json_input)
            act = row_data.get('action')
            k = row_data.get('key', '').strip()
            
            # Revert operation if the parameter is ADD NEW
            if k and act == "ADD NEW":
                body_key = "body" if ("body" in base.get("response", {}) and "jsonBody" not in base.get("response", {})) else "jsonBody"
                if k.startswith("headers."):
                    delete_nested_value(base.get("response", {}).get("headers", {}), k[8:])
                else:
                    delete_nested_value(base.get("response", {}).get(body_key, {}), k)
                    
                st.session_state.master_json_input = json.dumps(base, indent=2)
                st.session_state.last_parsed_master = st.session_state.master_json_input
    except:
        pass
    
    # Remove the row from UI and re-sync
    remove_row(index)
    auto_sync()

# ==========================================
# PART 1: MAIN FORM
# ==========================================
st.subheader("1. Master Configuration")
st.text_area(
    "Master JSON Template (Edit directly here, or use the form below for automation):", 
    height=250, 
    key="master_json_input"
)
filename_template = st.text_input("Filename Pattern:", placeholder="Example: mock_response_[code].json", value="mock_response_[code].json")

parsed_root = {}
available_keys = []
if st.session_state.master_json_input.strip():
    try:
        parsed_root = json.loads(st.session_state.master_json_input)
        res_node = parsed_root.get("response", {})
        
        body_node = res_node.get("jsonBody", res_node.get("body", {}))
        if isinstance(body_node, dict): available_keys.extend(get_all_keys(body_node))
            
        headers_node = res_node.get("headers", {})
        if isinstance(headers_node, dict):
            headers_keys = get_all_keys(headers_node)
            available_keys.extend([f"headers.{hk}" for hk in headers_keys])
            
        is_json_valid = True
    except json.JSONDecodeError:
        is_json_valid = False
        st.toast("⚠️ Invalid Master JSON format. Please check your JSON syntax.", icon="❌")

st.divider()

# ==========================================
# PART 2: FIXED SETTINGS & PREVIEW
# ==========================================
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("🛠️ Fixed Settings (Req & Res)")
    st.text_input("URL Path / Endpoint:", key="fixed_url", on_change=auto_sync)
    
    c_req1, c_req2 = st.columns(2)
    with c_req1: st.selectbox("Request Method:", method_list, key="fixed_method", on_change=auto_sync)
    with c_req2: st.selectbox("Response Status:", status_list, key="fixed_status", on_change=auto_sync)
        
    c_req3, c_req4 = st.columns(2)
    with c_req3: st.number_input("Fixed Delay (Milliseconds):", min_value=0, step=100, key="fixed_delay", on_change=auto_sync)
    with c_req4: st.text_input("Matched JSON Path (Optional):", key="fixed_matched", on_change=auto_sync)

with col_right:
    st.subheader("👁️ Live Preview")
    compiled_preview = compile_final_json()
    if "error" in compiled_preview:
        st.warning(compiled_preview["error"])
    else:
        st.json(compiled_preview)

# ==========================================
# PART 3: JSON PARAMETER MANIPULATION
# ==========================================
st.divider()
st.subheader("🔀 JSON Parameter Manipulation (Variations)")
st.caption("All changes in this form will be AUTOMATICALLY synchronized as a '{key}' Placeholder in the Master JSON.")

for i, row in enumerate(st.session_state.rows):
    c1, c2, c3, c4 = st.columns([2, 3, 3, 1])
    
    action_options = ["ADD NEW", "REMOVE EXISTING"] + available_keys
    current_act = row['action']
    if current_act not in action_options and current_act not in ["", None]:
        action_options.append(current_act)

    with c1:
        st.session_state.rows[i]['action'] = st.selectbox("Action / Target", action_options, index=action_options.index(current_act) if current_act in action_options else 0, key=f"act_{row['id']}", on_change=auto_sync)
        
    with c2:
        is_existing_param = st.session_state.rows[i]['action'] not in ["ADD NEW", "REMOVE EXISTING"]
        
        if is_existing_param:
            st.text_input("Key (Locked)", value=st.session_state.rows[i]['action'], disabled=True, key=f"key_disp_{row['id']}")
        else:
            st.text_input("Key Name", value=row['key'], key=f"key_input_{row['id']}", placeholder="e.g. systemData.gatewayNumber", on_change=auto_sync)
            
    with c3:
        if st.session_state.rows[i]['action'] == "REMOVE EXISTING":
            st.text_input("Value", value="- Will Be Completely Removed -", disabled=True, key=f"val_disp_{row['id']}")
        else:
            st.text_input("Variation Value(s)", value=row['value'], key=f"val_input_{row['id']}", placeholder="Example: ValA, ValB", on_change=auto_sync)
            
    with c4:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        st.button("🗑️ Delete", key=f"del_{row['id']}", use_container_width=True, on_click=handle_delete_row, args=(i, row))

if st.button("➕ Add Parameter Variation"):
    add_row()
    st.rerun()

# ==========================================
# PART 4: AI GENERATION & ZIP DOWNLOAD
# ==========================================
st.divider()

if st.button("🚀 GENERATE MULTIPLE FILES (.ZIP)", type="primary", use_container_width=True, disabled=not is_json_valid):
    if not st.session_state.master_json_input.strip():
        st.error("⚠️ Master JSON Template cannot be empty!")
    elif not is_json_valid:
        st.error("⚠️ Please fix your Master JSON format before generating!")
    else:
        with st.spinner("⏳ AutoMock.ai is assembling the mock file variations structure..."):
            variations_text = ""
            for r in st.session_state.rows:
                if r['key']:
                    leaf_key = r['key'].split('.')[-1]
                    if r['action'] == "REMOVE EXISTING":
                        variations_text += f"- Ensure the parameter '{r['key']}' is removed from the blueprint.\n"
                    elif r['action'] == "ADD NEW":
                        variations_text += f"- Replace the placeholder {{{leaf_key}}} in '{r['key']}' with the value: {r['value']}.\n"
                    else:
                        variations_text += f"- Replace the placeholder {{{leaf_key}}} in '{r['key']}' with the variation value: {r['value']}. (ABSOLUTE INSTRUCTION: If the value is a random/generation instruction, follow it exactly and DO NOT leave the previous original text!).\n"

            base_structure = json.dumps(compiled_preview, indent=2)

            full_prompt = (
                f"1) MAIN BLUEPRINT FORMAT (MAINTAIN THIS STRUCTURE):\n{base_structure}\n\n"
                f"2) FILENAME PATTERN:\n{filename_template}\n\n"
                f"3) DATA VARIATION INSTRUCTIONS FOR EACH FILE:\n{variations_text}\n"
            )
            
            success = False
            for key in api_keys:
                try:
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(
                        model='gemini-3.1-flash-lite',
                        contents=full_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction="You are an automated Mock API file generator system. Return the data as a pure JSON Array. Each item MUST have a 'filename' and 'content' key. The 'content' node MUST strictly follow the MAIN BLUEPRINT FORMAT. Do not leave curly braces (placeholders) in the final result. Do not add any text outside the JSON Array.",
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
                    
                    st.success("✅ All variation scenario files generated successfully!")
                    st.download_button(
                        label="📥 DOWNLOAD RESULTS (.ZIP)",
                        data=zip_buffer,
                        file_name="AutoMock_QA_Scenarios.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                    success = True
                    break
                except:
                    continue
            
            if not success:
                st.error("❌ An error occurred while generating files. Please check your API Key validity or AI instructions.")