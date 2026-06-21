# PDF Markdown 繁體中文翻譯器執行計劃

> 來源規格：`README.md`

## 目標

建立一條本地端、可恢復、可檢查、可重跑的文件處理管線，將英文數位 PDF 轉為英文 Markdown，再透過本機 Ollama 模型逐塊翻譯為繁體中文 Markdown，並輸出處理報告。

## 執行原則

- 先完成核心處理管線，再做 UI。
- 第一版只把英文數位文字 PDF 作為成功標準。
- 所有階段都保留中間產物，方便檢查、重跑與除錯。
- 翻譯採逐塊處理，不把整份文件一次丟給模型。
- 預設只呼叫本機 Ollama，不使用雲端 LLM API。
- 每個任務完成時都要有可驗證輸出或測試。

## 建議技術基線

- 語言：Python
- 第一階段介面：CLI
- 後續介面：本地 Web UI
- PDF 轉換：MarkItDown
- EPUB 轉換：內建 EPUB spine / XHTML 解析，先輸出 Markdown
- 本地模型：Ollama HTTP API
- MVP 儲存：檔案系統
- 後續儲存：必要時加入 SQLite

## 里程碑總覽

| 里程碑 | 目標 | 主要交付物 |
|---|---|---|
| M0 | 技術驗證 | MarkItDown + Ollama 基本鏈路 |
| M1 | 穩定轉換與切塊 | normalizer、parser、chunker、metadata |
| M2 | 翻譯工作流 | Ollama client、prompt、cache、resume |
| M3 | 品質檢查 | Markdown、表格、英文殘留、簡體殘留檢查 |
| M4 | 輕量 UI | 本地 Web UI、進度、警告、下載 |
| M5 | 產品化評估 | 成功率、品質、效能、下一階段決策 |

---

## Phase 0：專案骨架與基礎規範

### Task 0.1：建立 Python 專案骨架

- [x] 建立 `pyproject.toml`
- [x] 建立 `src/local_pdf_translator/`
- [x] 建立 `tests/`
- [x] 建立 CLI 入口點，例如 `local-pdf-translator`
- [x] 建立 `.gitignore`
- [x] 建立基本 README 使用方式區塊

驗收：

- [x] 可執行 CLI 並顯示 help
- [x] 測試框架可執行
- [x] 專案可被乾淨安裝到本地虛擬環境

### Task 0.2：定義核心資料模型

- [x] 定義 `Job`
- [x] 定義 `Document`
- [x] 定義 `Chunk`
- [x] 定義 `GlossaryEntry`
- [x] 定義 `QAResult`
- [x] 定義任務狀態 enum
- [x] 定義區塊類型 enum

驗收：

- [x] 任務模型可序列化為 JSON
- [x] 任務 metadata 可寫入與讀回
- [x] 單元測試涵蓋狀態轉換與必要欄位

### Task 0.3：建立輸出目錄結構

- [x] 為每次任務建立獨立 output folder
- [x] 複製來源 PDF 為 `document.original.pdf`
- [x] 預留 `chunks/`
- [x] 預留 `metadata.json`
- [x] 預留 `report.md`

驗收：

- [x] 建立任務時會產生穩定、可重跑的輸出目錄
- [x] 重新執行同一任務不會覆蓋未完成資料，除非使用者明確指定

---

## Phase 1：PDF 輸入、分類與 Markdown 轉換

### Task 1.0：EPUB 最小 Markdown 轉換

- [x] 支援 `.epub` 作為輸入格式
- [x] 解析 `META-INF/container.xml`
- [x] 解析 OPF manifest 與 spine
- [x] 依 spine 順序讀取 XHTML 章節
- [x] 將基本 XHTML 內容轉成 Markdown
- [x] 由 CLI 輸出 `document.en.raw.md`

驗收：

- [x] 測試用 EPUB 可依章節順序產生 Markdown
- [x] 標題、段落、清單與連結可轉成 Markdown
- [x] 任務 metadata 會記錄 `source_format = epub`

### Task 1.1：實作輸入管理

- [x] 驗證來源檔案路徑存在
- [x] 驗證副檔名
- [ ] 驗證檔案大小
- [ ] 檢查 MVP 限制：建議 50 MB 以下
- [ ] 記錄來源檔案 metadata

驗收：

- [ ] 無效路徑會產生清楚錯誤
- [ ] 非 PDF 檔會被拒絕
- [ ] 超出限制的 PDF 會產生警告或阻擋

### Task 1.2：實作 PDF 類型初步判斷

- [ ] 判斷是否可抽取文字
- [ ] 判斷疑似掃描 PDF
- [ ] 判斷疑似 mixed PDF
- [ ] 判斷疑似 complex layout PDF
- [ ] 將分類結果寫入 `metadata.json`

驗收：

- [ ] 文字型 PDF 被標記為 `Text PDF`
- [ ] 文字量過低時標記為疑似掃描 PDF
- [ ] 高風險分類會寫入報告警告

### Task 1.3：整合 MarkItDown

- [ ] 建立 MarkItDown adapter
- [ ] 將 PDF 轉成 `document.en.raw.md`
- [ ] 捕捉轉換錯誤
- [ ] 記錄轉換耗時與輸出文字量

驗收：

- [ ] 一份文字型英文 PDF 可成功轉出 raw Markdown
- [ ] 轉換失敗時任務狀態變為 `Failed`
- [ ] raw Markdown 永遠作為中間檔保留

---

## Phase 2：Markdown 正規化、解析與切塊

### Task 2.0：共用 Markdown 翻譯最小閉環

- [x] 從 `document.en.raw.md` 進入共用管線
- [x] 輸出 `document.en.normalized.md`
- [x] 依 Markdown block 建立穩定 chunk
- [x] 寫出 `chunks/chunk-0001.en.md`
- [x] 呼叫 Ollama-compatible `/api/chat`
- [x] 寫出 `chunks/chunk-0001.zh-TW.md`
- [x] 依 chunk 順序合併 `document.zh-TW.md`
- [x] 更新 `metadata.json` 狀態與 chunk 統計

驗收：

- [x] 測試以 mock Ollama 驗證 EPUB 可產生 `document.zh-TW.md`
- [x] 已存在的 chunk 譯文可重用，不會重送 Ollama
- [x] 共用管線不依賴來源格式，只依賴 `document.en.raw.md`

### Task 2.1：實作 Markdown normalizer

- [ ] 移除孤立頁碼
- [ ] 偵測並移除重複頁眉頁腳
- [ ] 修復英文斷行造成的破詞
- [ ] 修復異常空白
- [ ] 保留 URL、DOI、Email、檔名、程式碼區塊
- [ ] 輸出 `document.en.normalized.md`

驗收：

- [ ] 正規化不破壞 Markdown 標題層級
- [ ] URL 與程式碼區塊不被誤改
- [ ] 正規化操作記錄到 report

### Task 2.2：實作 Markdown parser

- [ ] 解析 heading
- [ ] 解析 paragraph
- [ ] 解析 list
- [ ] 解析 table
- [ ] 解析 blockquote
- [ ] 解析 code block
- [ ] 解析 footnote
- [ ] 保留每個區塊的 heading path

驗收：

- [ ] parser 能保留文件順序
- [ ] code block 不被切碎
- [ ] table 不被切碎

### Task 2.3：實作 chunker

- [x] 優先依標題切塊
- [x] 次優先依段落切塊
- [x] 依 `chunk-max-chars` 將相鄰 Markdown block 打包成較大 chunk
- [ ] 不切斷表格、清單、引用、程式碼、註腳
- [x] 為每個 chunk 產生原文 hash
- [x] 將 chunk 輸出到 `chunks/chunk-0001.en.md`

驗收：

- [x] 每個 chunk 有穩定 ID 與順序
- [ ] chunk metadata 可回溯原文內容
- [x] 對大型 EPUB 測試輸入，`--chunk-max-chars 8000` 可將 2,770 個細碎 block 打包為約 122 個 chunk
- [ ] 超長表格會標為高風險，而不是強行切開

---

## Phase 3：Ollama 翻譯工作流

### Task 3.1：建立設定模型

- [x] 支援 Ollama host
- [x] 支援模型名稱
- [ ] 支援 context window 目標上限
- [x] 支援單塊最大長度
- [x] 支援 temperature、top_p
- [ ] 支援重試次數
- [ ] 支援是否啟用術語表
- [ ] 支援是否輸出雙語 Markdown

驗收：

- [ ] CLI 可讀取設定檔
- [ ] CLI 參數可覆蓋設定檔
- [ ] 設定會寫入 `metadata.json`

### Task 3.2：實作 Ollama client

- [x] 實作 non-streaming chat request
- [x] 支援 timeout
- [ ] 支援重試
- [ ] 捕捉 API 錯誤
- [ ] 記錄模型名稱與參數

驗收：

- [ ] 可對本機 Ollama 發送測試 prompt
- [ ] Ollama 不可用時產生清楚錯誤
- [ ] API 失敗不會造成已完成 chunk 遺失

### Task 3.3：實作 prompt builder

- [x] 加入繁體中文翻譯規則
- [x] 要求只輸出譯文
- [x] 要求不摘要、不刪減、不重組
- [x] 要求保留 Markdown 結構
- [x] 要求不翻譯 URL 與程式碼區塊
- [x] 加入章節路徑
- [ ] 加入術語表

驗收：

- [ ] prompt 對不同 chunk 類型可產生穩定輸入
- [ ] prompt 版本納入 cache key

### Task 3.4：實作翻譯 cache

- [ ] cache key 包含原文 hash
- [ ] cache key 包含模型名稱與參數
- [ ] cache key 包含 prompt 版本
- [ ] cache key 包含術語表 hash
- [ ] cache key 包含目標語言設定
- [ ] cache 可讀寫到檔案系統

驗收：

- [ ] 相同 chunk 重跑時可命中 cache
- [ ] 模型或 prompt 改變時 cache 不會誤用
- [ ] cache 命中狀態寫入報告

### Task 3.5：實作翻譯 orchestrator

- [x] 逐塊翻譯
- [x] 更新任務狀態為 `Translating`
- [x] 每完成一塊就落盤
- [ ] 失敗 chunk 可重試
- [x] 中斷後可從最後成功 chunk 續跑
- [x] 輸出 `chunks/chunk-0001.zh-TW.md`

驗收：

- [ ] 中斷後重跑不會重翻已完成 chunk
- [ ] 失敗 chunk 記錄重試次數
- [ ] 所有完成 chunk 都可追溯模型與 prompt 版本

---

## Phase 4：品質檢查與合併輸出

### Task 4.1：實作 chunk 級 QA

- [ ] 檢查 Markdown 標記平衡
- [ ] 檢查連結數量一致
- [ ] 檢查程式碼區塊是否保留
- [ ] 檢查表格列數與欄位數
- [ ] 檢查譯文長度是否異常過短
- [ ] 檢查是否出現「以下是翻譯」等非正文內容
- [ ] 檢查明顯英文殘留

驗收：

- [ ] QA warning 會寫入 chunk metadata
- [ ] 高風險 chunk 會出現在 report
- [ ] QA 不通過時可依策略重試或標記人工審查

### Task 4.2：實作簡體殘留檢查與後處理

- [ ] 偵測簡體字比例
- [ ] 支援可選簡轉繁後處理
- [ ] 術語表優先於自動轉換
- [ ] 記錄後處理結果

驗收：

- [ ] 大量簡體輸出會被警告
- [ ] 啟用後處理時可產生台灣繁體中文輸出

### Task 4.3：實作 stitcher

- [x] 依 chunk 順序合併譯文
- [x] 輸出 `document.zh-TW.md`
- [ ] 可選輸出 `document.bilingual.md`
- [x] 保留章節順序

驗收：

- [ ] 合併後 Markdown 可被一般 preview 開啟
- [ ] chunk 順序與原文一致
- [ ] 缺失 chunk 會阻擋完成或標記為警告完成

### Task 4.4：實作全文級 QA

- [ ] 檢查標題階層完整
- [ ] 檢查是否有未完成 chunk
- [ ] 檢查大量簡體殘留
- [ ] 檢查異常重複段落
- [ ] 檢查術語一致性

驗收：

- [ ] 任務可正確落在 `Completed`、`CompletedWithWarnings` 或 `Failed`
- [ ] 全文 QA 結果寫入 `report.md`

### Task 4.5：實作 report generator

- [ ] 輸出來源 PDF 基本資訊
- [ ] 輸出 PDF 類型判斷
- [ ] 輸出 MarkItDown 轉換摘要
- [ ] 輸出 chunk 數量
- [ ] 輸出模型與設定
- [ ] 輸出總耗時
- [ ] 輸出成功、失敗、重試數
- [ ] 輸出警告與人工檢查區塊

驗收：

- [ ] `report.md` 能清楚說明哪些地方可信、哪些需要人工檢查
- [ ] 報告足以支援重新處理與除錯

---

## Phase 5：CLI MVP

### Task 5.1：實作 CLI 主流程

- [ ] `translate <pdf-path>` 建立任務並跑完整流程
- [ ] `resume <job-dir>` 從既有任務續跑
- [ ] `inspect <job-dir>` 顯示任務狀態與警告
- [ ] `models` 檢查 Ollama 可用模型

驗收：

- [ ] 單一命令可完成 PDF 到繁中 Markdown
- [ ] resume 不會破壞已完成輸出
- [ ] inspect 可顯示目前階段、已完成 chunk、失敗 chunk

### Task 5.2：加入進度與可觀測性

- [ ] 顯示目前階段
- [ ] 顯示已處理 chunk 數
- [ ] 顯示目前模型
- [ ] 顯示耗時
- [ ] 顯示失敗與重試次數

驗收：

- [ ] 長文件處理時使用者能判斷系統仍在工作
- [ ] 發生錯誤時能定位到具體階段與 chunk

---

## Phase 6：測試資料與驗收

### Task 6.1：建立測試 PDF 組

- [ ] 純文字英文論文
- [ ] 含註腳與引用的政策報告
- [ ] 含表格的智庫報告
- [ ] 雙欄排版 PDF
- [ ] 掃描或混合型 PDF

驗收：

- [ ] 測試資料來源、版權與用途記錄清楚
- [ ] 測試文件覆蓋 README 定義的主要風險類型

### Task 6.2：建立自動化測試

- [ ] 單元測試：資料模型
- [ ] 單元測試：normalizer
- [ ] 單元測試：parser
- [ ] 單元測試：chunker
- [ ] 單元測試：cache key
- [ ] 單元測試：QA checker
- [ ] 整合測試：PDF 到 raw Markdown
- [ ] 整合測試：Markdown 到 chunks
- [ ] 整合測試：mock Ollama 翻譯流程

驗收：

- [ ] 測試可在無 Ollama 的環境跑過 mock 流程
- [ ] 有 Ollama 時可跑端到端 smoke test

### Task 6.3：MVP 驗收

- [ ] 三份文字型 PDF 可完成全流程
- [ ] 輸出 Markdown 可讀
- [ ] 主要段落無明顯漏譯
- [ ] 標題階層保留
- [ ] 表格風險能被報告標記
- [ ] 翻譯 cache 可用
- [ ] 任務中斷後可續跑

驗收：

- [ ] 符合 README 的 MVP 通過門檻
- [ ] 不支援或高風險文件有清楚警告，而非靜默成功

---

## Phase 7：本地 Web UI

### Task 7.1：建立本地服務

- [ ] 暴露建立任務 API
- [ ] 暴露查詢任務狀態 API
- [ ] 暴露重試失敗 chunk API
- [ ] 暴露下載輸出 API

驗收：

- [ ] UI 與核心管線分離
- [ ] CLI 與 Web UI 可共用同一套 application service

### Task 7.2：建立輕量 UI

- [ ] 選擇 PDF
- [ ] 選擇模型 profile
- [ ] 顯示處理進度
- [ ] 顯示警告與失敗 chunk
- [ ] 下載 `document.zh-TW.md`
- [ ] 下載 `report.md`

驗收：

- [ ] 非命令列使用者可完成單份 PDF 處理
- [ ] UI 不隱藏高風險警告

---

## Phase 8：產品化前評估

### Task 8.1：效能與品質評估

- [ ] 量測每頁或每千字處理時間
- [ ] 量測記憶體使用
- [ ] 比較至少兩類 Ollama 模型
- [ ] 評估繁體中文穩定性
- [ ] 評估術語一致性

驗收：

- [ ] 可判斷預設模型 profile
- [ ] 可判斷 MVP 的合理硬體需求

### Task 8.2：下一階段決策

- [ ] 評估是否加入 OCR
- [ ] 評估是否加入批次處理
- [ ] 評估是否加入人工校對 UI
- [ ] 評估是否包裝為桌面 App
- [ ] 評估 iOS 作為控制端或閱讀端的必要性

驗收：

- [ ] 有明確 Go / No-Go 決策
- [ ] 下一階段範圍不混入未驗證的大型子系統

---

## 第一個可執行切入點

建議從下列最小閉環開始：

1. 建立 Python 專案骨架與 CLI。
2. 實作 MarkItDown adapter，輸出 `document.en.raw.md`。
3. 實作最小 chunker，把 Markdown 依段落切成穩定 chunk。
4. 實作 Ollama non-streaming client。
5. 翻譯一個 chunk 並輸出 `chunk-0001.zh-TW.md`。
6. 合併 chunk，產生 `document.zh-TW.md`。
7. 產生最小 `report.md`。

這條路徑完成後，即可驗證 README 中最重要的假設：`PDF → Markdown → 分塊 → Ollama → 繁中 Markdown → 報告` 是否在本機可穩定跑通。
