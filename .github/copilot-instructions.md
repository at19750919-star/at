# Copilot Instructions for WAA Codebase

## 專案架構總覽
- 本專案為百家樂敏感局產生器，核心邏輯在 `waa.py`，API 層在 `api/app.py`，前端 UI 在 `web/` 資料夾。
- 主要流程：前端透過 API 請求，FastAPI (`api/app.py`) 轉發至 `waa.py` 執行敏感局生成、切牌模擬、資料匯出。
- 產生的 CSV 檔案存放於根目錄，命名規則如 `all_sensitive_B_rounds_*.csv`、`cut_hits_*.csv`。

## 關鍵檔案與目錄
- `waa.py`：敏感局生成主程式，包含所有演算法與資料處理邏輯。
- `api/app.py`：FastAPI 伺服器，提供 `/api/generate_shoe`、`/api/simulate_cut`、`/api/export/*` 等端點，並掛載 `web/` 靜態檔案。
- `web/`：前端介面，含 `index.html`、`script.js`、`style.css`，以 AJAX 方式呼叫 API。

## 主要 API 路徑
- `/api/generate_shoe`：產生敏感局，參數包含牌靴數、訊號花色、和局花色。
- `/api/simulate_cut`：切牌模擬，依目前鞋子資料計算新 rounds。
- `/api/export/{name}`：匯出直式牌序或切牌命中統計，供下載。

## 開發與測試流程
- 執行 FastAPI 伺服器：
  ```powershell
  cd d:\1111\waa\waa
  uvicorn api.app:app --reload
  ```
- 前端可直接於瀏覽器開啟 `web/index.html`，或透過 API 端點測試。
- 產生敏感局時，請確認 `waa.py` 內 CONFIG 區塊設定（如花色、牌靴數、亂數種子等）。

## 專案慣例與注意事項
- 所有敏感局生成、切牌模擬皆由 `waa.py` 處理，API 僅負責資料轉發與格式化。
- FastAPI 啟用 CORS，允許本地網頁直接呼叫 API。
- 靜態檔案掛載於 `/web`，路由順序需在 API 之後。
- 牌靴生成失敗（如剩餘牌無法組成敏感局）會自動重試，最大重試次數由 `MAX_ATTEMPTS` 控制。
- 主要資料結構為 rounds（敏感局清單）、suitCounts（花色統計）、cutSummary（切牌模擬結果）。

## 進階
- 若需自訂尾局順序，請修改 `waa.py` 的 `MANUAL_TAIL` 參數。
- 匯出檔案命名含時間戳，便於追蹤。

---
如有不明確或缺漏之處，請回饋以便補充。
