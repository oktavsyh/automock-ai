# AutoMock.ai 🤖
**Intelligent JSON Simulator Generator for QA Automation**

AutoMock.ai is a personal QA-centric tool designed to eliminate the tedious manual process of crafting JSON mock files for API testing. It leverages Generative AI (Gemini 3.1 Flash-Lite) to transform master JSON templates into diverse, scenario-specific variations instantly.

## 🚀 Features
- **Dynamic Schema Detection:** Automatically parses any valid JSON master template.
- **Smart Parameter Mapping:** Generate variations for specific keys (e.g., status codes, amounts, timestamps) via an interactive UI.
- **AI-Powered Synthesis:** Uses the latest **Gemini 3.1 Flash-Lite** to ensure schema-compliant and valid JSON outputs.
- **Bulk Generation:** Automatically packages all generated mock files into a downloadable `.zip` archive.
- **Resilient Architecture:** Features multi-API key rotation to prevent rate-limiting issues during bulk generation.
- **Security-First:** Everything is processed in-memory (RAM) without persisting data on the server.

## 🛠️ Tech Stack
- **Frontend/Backend:** Streamlit (Python)
- **AI Model:** Google Gemini 3.1 Flash-Lite
- **Deployment:** Streamlit Community Cloud

## 📋 How It Works
1. **Validate:** Paste your master JSON template, and the app will automatically extract all available keys.
2. **Configure:** Choose the parameters you want to vary and provide the desired values (supports comma-separated inputs for bulk generation).
3. **Generate:** Process and download the results as a ready-to-use `.zip` file for your test environment.

## 🚀 Deployment
This project is built to be deployed on **Streamlit Community Cloud**.
1. Fork/Clone this repository.
2. Deploy to Streamlit Cloud.
3. Configure the `GEMINI_API_KEYS` in the App Secrets settings with the following format:
```toml
   GEMINI_API_KEYS = ["AIza...", "AIza..."]