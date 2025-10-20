# Copilot Instructions for WAA Codebase

## 架構與資料流
- 本專案為「百家樂敏感鞋」生成與分析工具，分三層：
  - **核心演算法**：`waa.py`，負責敏感局生成、花色規則、切牌模擬與 CSV 匯出。
  - **API 層**：`api/app.py`（FastAPI），將 REST API 請求轉發至 `waa.py`，並管理全域狀態。
  - **前端**：`web/`（`index.html`, `script.js`, `style.css`），以 AJAX 呼叫 API，呈現資料與匯出功能。
- 主要資料流：前端操作 → API 請求 `/api/generate_shoe`/`/api/simulate_cut` → `waa.py` 執行 → 回傳 JSON/CSV → 前端渲染或下載。
- 所有狀態皆保存在後端記憶體（無資料庫），多工作者部署時需注意狀態一致性。

## 關鍵檔案與目錄
- `waa.py`：敏感鞋生成主程式，含所有演算法、資料結構與規則。
- `api/app.py`：FastAPI 伺服器，提供 `/api/generate_shoe`、`/api/simulate_cut`、`/api/export/*` 等端點，並掛載 `web/` 靜態檔案。
- `web/`：前端 UI，含 `index.html`（主頁）、`script.js`（互動邏輯）、`style.css`（深色主題）。
- `app.py`：專案啟動入口，匯出 FastAPI 物件，支援 `uvicorn app:app`。
- `Dockerfile`：容器化建置，CMD 啟動 `uvicorn app:app`。
- `requirements.txt`：依賴 FastAPI、Uvicorn。
- `docs/PROJECT_OVERVIEW.md`、`folder_overview.txt`：詳細架構、API、開發流程說明。

## 主要 API 路徑
- `POST /api/generate_shoe`：產生敏感鞋，參數含牌靴數、訊號花色、和局花色，回傳 rounds、suit_counts、vertical、meta。
- `POST /api/simulate_cut`：切牌模擬，依目前鞋子資料計算新 rounds。
- `GET /api/export/vertical`、`/api/export/cut_hits.csv`：匯出直式牌序或切牌命中統計。
- `POST /api/scan`：預留掃描 API，尚未實作。

## 開發與啟動流程
1. 安裝依賴：`pip install -r requirements.txt`（建議用虛擬環境）。
2. 啟動後端：`uvicorn app:app --reload --host 127.0.0.1 --port 7860`。
3. 前端於瀏覽器開啟 `web/index.html`，即可操作與測試。
4. 產生敏感鞋時，請確認 `waa.py` 內 CONFIG 區塊（如花色、牌靴數、亂數種子等）設定正確。
5. Docker 部署：`docker build -t waa .`、`docker run --rm -p 7860:7860 waa`。

## 專案慣例與注意事項
- 敏感鞋生成、切牌模擬皆由 `waa.py` 處理，API 層僅負責資料轉發與格式化。
- FastAPI 啟用 CORS，允許本地網頁直接呼叫 API。
- 靜態檔案掛載於 `/web`，路由順序需在 API 之後。
- 牌靴生成失敗（如剩餘牌無法組成敏感局）會自動重試，最大重試次數由 `MAX_ATTEMPTS` 控制。
- 主要資料結構為 rounds（敏感局清單）、suitCounts（花色統計）、cutSummary（切牌模擬結果）。
- 匯出檔案命名含時間戳，便於追蹤。
- 若需自訂尾局順序，請修改 `waa.py` 的 `MANUAL_TAIL` 參數。

## 測試與技術債
- 專案目前無自動化測試，建議以 pytest 撰寫單元測試（如 `waa.generate_all_sensitive_shoe_or_retry`）。
- API 可用 fastapi.testclient 撰寫整合測試。
- 前端無自動測試，建議以 Playwright/Cypress 撰寫端對端測試。
- `POST /api/scan` 尚未實作，僅回傳零命中。
- `waa.py` 中文註解部分顯示亂碼，建議統一轉 UTF-8。
- 後端全域 STATE 僅適用單進程，需注意多工作者部署。
- 無授權/驗證，API 對外開放，若部署於公網需加強存取控制。
- Dockerfile 未設健康檢查與非 root 使用者。

---

# --- 前端與 CSS 開發指南 ---

## 1. 回答原則 (非常重要)
- 當我詢問關於 `style.css` 的問題時，**請務必根據檔案內的實際內容回答**。
- **不要自行創造或假設不存在的 CSS 變數或 class 名稱**。你的回答應該是**引用和分析**，而不是創作。
- 在回答佈局問題時，請務必使用瀏覽器的「開發者工具」來確認**真正生效的 CSS 選擇器及其權重**，而不是猜測。

## 2. 佈局與結構 (Layout)
- **主要佈局方式**：頁面採用 **CSS Grid** 進行宏觀佈局，並使用 **Flexbox** 處理元件內部的微觀佈局。
- **頂部三欄卡片佈局 (`.grid-top`)**：
  - 這個佈局由 `.grid-top` 選擇器控制，它的權重高於通用的 `.grid`。
  - 欄寬設定為 `auto auto 1fr`，其目的是：
    - **前兩欄 (`auto`)**: 寬度自動收縮，以剛好容納其內容。
    - **第三欄 (`1fr`)**: 自動填滿所有剩餘的可用空間。
- **網格項目壓縮問題**：
  - 為了讓 `auto` 欄寬能正確收縮，必須為網格的直接子項目（卡片）設定 `min-width: 0;`。
  - 正確的選擇器是 `.grid-top > .card`，因為卡片是 `.grid-top` 的直接子元素。

## 3. 關鍵檔案與選擇器 (Key Selectors)
- **主要樣式檔案**：`web/style.css`。
- **全域變數**: 定義在 `:root` 中，用於管理主題色彩、圓角、間距等，應優先使用。
- **頂部三欄網格容器**: `.grid-top` (這是控制頂部卡片寬度的主要選擇器)。
- **通用卡片容器**: `.card` (定義所有卡片的基礎外觀，如背景、邊框、陰影)。
- **卡片標題列**: `.card .head` (使用 `display: flex` 和 `justify-content: space-between` 讓標題分居左右)。
- **卡片內容操作區**: `.actions` (使用 `display: flex` 讓內部元件橫向排列)。
- **表單標籤**: `label`。
- **數字輸入框**: `input[type=number]`。
- **下拉選單**: `select`。
- **主要按鈕**: `button.primary` (用於需要強調的操作)。

## 4. HTML 結構慣例
- **卡片結構**: 卡片使用 `<section class="card">` 標籤。
- **佈局層級**: 卡片 (`<section class="card">`) 是網格容器 (`<div class="grid-top">`) 的**直接子元素**。在編寫 CSS 選擇器時，可以使用子選擇器 `>` 來精準選取，例如 `.grid-top > .card`。

