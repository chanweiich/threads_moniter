# 政大社群輿情監控系統 (NCCU Threads Crisis Monitor)

## 📌 專案背景
本系統為專門為 **政大秘書處 (NCCU Secretariat)** 開發的實習專案，旨在透過 AI 自動化監控 Threads 平台上的校園動態與學生心聲。系統能即時攔截並評估潛在的公關危機，協助校方在重大爭議（如校園安全、住宿環境、學權問題）發酵前掌握先機並進行妥善處置。

## 🚀 核心功能
* **多維度爬蟲**：支援精準關鍵字與政大專屬黑話（如：`種茶大學`、`自強七舍`、`會研所` 等）的自動巡邏與掃描。
* **AI 危機評分**：無縫整合 Google Gemini API，自動深度判讀貼文情緒走向與潛在公關危機等級（1-10 分），並針對高風險議題給予加權預警。
* **人工通報入口**：提供友善的互動介面，支援管理員手動輸入特定單篇貼文網址，系統將強制破除反爬蟲機制，即時將其強制作為重點追蹤對象。
* **動態 Dashboard**：即時視覺化排行榜、數據統計圖表與輿情溫度的動態警報標籤（如 `🔥 持續監控中`、`炎上預警`）。

## 🛠️ 技術棧 (Tech Stack)
* **後端架構**：`Python`, `Flask`
* **自動化爬蟲**：`Playwright` (搭配 Stealth 隱蔽模組)
* **AI 分析決策**：`Google Gemini 2.5 Pro / Flash` (透過 `google-genai` 與 Pydantic 結構解析)
* **前端與數據視覺化**：原生 HTML/JS 搭配 `Chart.js` 及 Bootstrap

## 📦 安裝指南
本專案依賴嚴格的 Python 隔離環境運行，請按照以下步驟部署：

請在終端機執行以下指令

請選擇您想放置檔案的位置，如至於桌面 `C:\Users\user>Desktop`
### 1. 下載本專案
```bash
git clone https://github.com/chanweiich/threads_moniter.git
cd threads_moniter
```

### 2. 建立並啟動虛擬環境 (.venv)
請在專案根目錄中執行：

`Mac`
```bash
python3 -m venv .venv
source .venv/bin/activate
```

`Windows`
```bash
py -m venv .venv
.venv\Scripts\activate
# 確保名稱一致(複製一份python.exe，命名為 python3.exe)
copy .venv\Scripts\python.exe .venv\Scripts\python3.exe
```

### 3. 安裝套件依賴與瀏覽器內核
```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. 設定環境變數 (.env)
本系統目前優先採用 **Groq API (Llama 3)** 以確保極速分析與穩定性。請在專案根目錄建立 `.env` 檔案，寫入以下內容：

```ini
GROQ_API_KEY=您的_Groq_API_金鑰
GEMINI_API_KEY=您的_Gemini_API_金鑰 (備援用)
```

> **🔑 取得 API Key**：您可以前往 [Groq Console](https://console.groq.com/keys) 免費註冊並取得金鑰。

**🚨 【安全性警語】：請務必確保 `.env` 檔案保留在本地，絕對不可推送到 GitHub。**

### 5. 運行系統
請按照以下順序輸入指令
```bash
cd hourly_crawler
python hourly_scheduler.py
cd ..
python analyze_crisis.py
cd dashboard
python app.py
```
接著在瀏覽器中開啟 `http://127.0.0.1:5000`。

#### 以下代修改=============
* **啟動爬蟲與分析排程器**
```bash
python3 analyze_crisis.py
python3 track_trends.py
python3 scheduler.py
```
若未曾於電腦登入threads：

彈出瀏覽視窗時，請在該視窗另開一分頁輸入threads.net，輸入帳號登入threads。

* **啟動網頁戰情室 (Dashboard)**
另外開啟一個terminal
```bash
cd dashboard
python3 app.py
```
接著在瀏覽器中開啟 `http://127.0.0.1:5000`。
#### =============

## ⚠️ 免責聲明
本系統僅供國立政治大學校園研究、實習專案與公關趨勢監測使用。所擷取之數據僅作為內部決策輔助，請嚴格遵守相關社群平台（Meta / Threads）之使用規範與隱私條款，嚴禁將爬蟲數據用於非法窺探或商業營利。
