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

### 1. 建立並啟動虛擬環境 (.venv)
請在專案根目錄中執行：
```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows 系統請輸入 .venv\Scripts\activate
```

### 2. 安裝套件依賴與瀏覽器內核
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. 設定環境變數 (.env)
請在根目錄建立 `.env` 檔案，寫入您的 Google Gemini API 金鑰：
```ini
GEMINI_API_KEY=請在此填入您的API_KEY
```

### 4. 運行系統
* **啟動爬蟲與分析排程器**：`python3 scheduler.py`
* **啟動網頁戰情室 (Dashboard)**：進入 `dashboard` 資料夾並執行 `python3 app.py`，接著在瀏覽器中開啟 `http://127.0.0.1:5000`。

## ⚠️ 免責聲明
本系統僅供國立政治大學校園研究、實習專案與公關趨勢監測使用。所擷取之數據僅作為內部決策輔助，請嚴格遵守相關社群平台（Meta / Threads）之使用規範與隱私條款，嚴禁將爬蟲數據用於非法窺探或商業營利。