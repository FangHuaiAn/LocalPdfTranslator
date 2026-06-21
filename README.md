# PDF Markdown 繁體中文翻譯器

## 開發中快速開始

目前專案先以 Python CLI 與核心處理管線為主。第一階段可用下列命令確認 CLI 與測試框架：

```bash
python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m local_pdf_translator --help
```

建立任務輸出目錄的 CLI 形式：

```bash
PYTHONPATH=src python3 -m local_pdf_translator translate path/to/document.pdf --output-dir output --model llama3.1
PYTHONPATH=src python3 -m local_pdf_translator translate path/to/book.epub --output-dir output --model llama3.1
```

未指定 `--model` 時，CLI 只建立任務與英文 raw Markdown。指定 `--model` 時，CLI 會把 `document.en.raw.md` 送入共用 Markdown 管線，切塊後呼叫 Ollama，產生 `chunks/chunk-0001.zh-TW.md` 與 `document.zh-TW.md`。

可指定 Ollama host 與切塊大小：

```bash
PYTHONPATH=src python3 -m local_pdf_translator translate path/to/book.epub \
  --output-dir output \
  --model llama3.1 \
  --ollama-host http://localhost:11434 \
  --chunk-max-chars 3000
```

目前 EPUB 已支援：讀取 EPUB spine 順序，將 XHTML 章節轉成 `document.en.raw.md`，再進入共用 Markdown 翻譯管線。PDF 的 MarkItDown 轉換 adapter 仍按 `Tasks.md` 分階段實作；共用翻譯管線已可重用於任何已產生 `document.en.raw.md` 的來源。

目前 chunker 會依 `--chunk-max-chars` 將相鄰 Markdown block 打包成較大的翻譯單位。以 `War and Peace and War.epub` 為例，`--chunk-max-chars 8000` 會產生約 122 個 chunk，而不是逐段落產生數千個請求。

### EPUB 支援狀態

第一版 EPUB 支援採最小可用範圍：

- 支援 `.epub` 作為輸入格式。
- 解析 `META-INF/container.xml` 與 OPF package。
- 依 EPUB spine 順序讀取 XHTML 章節。
- 將標題、段落、清單、引用、連結、圖片與 inline code 轉成 Markdown。
- 輸出 `document.en.raw.md`。
- 指定 `--model` 時，呼叫 Ollama 產生 `document.zh-TW.md`。

暫不支援：

- DRM 保護 EPUB。
- 輸出翻譯後 EPUB。
- 圖片中文字 OCR。
- 完整 CSS / 排版重建。
- EPUB 目錄與內部連結的完整 QA。

## 1. 專案定位

本專案目標是建立一個本地端文件處理 App，將英文 PDF 轉換為 Markdown，並使用 Ollama 本地大模型翻譯為繁體中文 Markdown。

本專案不是 PDF 版面重建工具，也不是單純的聊天式翻譯工具。它應被設計成一條可恢復、可檢查、可重跑、可維護的本地文件處理管線。

核心流程：

```text
英文 PDF
  → PDF 類型判斷
  → MarkItDown 轉 Markdown
  → Markdown 正規化
  → 結構化切塊
  → Ollama 本地模型逐塊翻譯
  → 格式與完整性檢查
  → 合併
  → 輸出繁體中文 Markdown 與處理報告
```

核心原則：

- 以 Markdown 作為中間格式，而不是直接翻譯 PDF。
- 以本地模型翻譯為預設，不把文件內容送到雲端。
- 先追求「可讀、可檢索、可再編輯」的知識文件，不追求 PDF 原版排版完全還原。
- 第一版先處理英文數位 PDF；掃描 PDF、複雜表格、圖中文字、精準版面分析列為第二階段能力。
- App 外殼不是第一優先；第一優先是穩定的文件處理管線。

---

## 2. 可行性結論

結論：可行，但必須嚴格控制 MVP 範圍。

可行性來自兩點：

1. MarkItDown 可將 PDF 轉為 Markdown，適合作為文件進入 LLM 流程前的中間層。
2. Ollama 可在本地端執行大模型，並提供本地 HTTP API，適合被 App 呼叫來進行翻譯。

但此構想不能採用以下路線：

```text
整份 PDF → 一次丟給模型 → 期待得到完整繁中 Markdown
```

這條路線不可控，主要問題是：

- PDF 本身不是穩定的語義格式。
- 長文件會超過本地模型 context window。
- 模型可能漏譯、摘要、擅自重組內容。
- Markdown 結構可能被破壞。
- 長文件術語容易前後不一致。
- 中斷後無法續跑，失敗成本高。

可靠路線應是：

```text
PDF → Markdown → 正規化 → 切塊 → 逐塊翻譯 → 檢查 → 合併 → 報告
```

---

## 3. 深層設計考量與審慎挑戰

### 3.1 PDF 不是穩定語義格式

PDF 的本質是版面呈現格式，不是語義文件格式。兩份外觀看起來相似的 PDF，內部文字層可能完全不同。

常見差異：

- 文字型 PDF：可直接抽取文字。
- 掃描型 PDF：頁面其實是圖片，需要 OCR。
- 混合型 PDF：部分頁面有文字層，部分頁面是圖片。
- 雙欄 PDF：閱讀順序容易錯亂。
- 含表格 PDF：欄位、列、註腳容易破碎。
- 含頁眉頁腳 PDF：會在 Markdown 中反覆出現干擾內容。
- 含註腳與引用 PDF：正文、註腳、參考文獻的邊界容易混淆。

因此第一版不能宣稱「支援所有 PDF」。比較合理的說法是：

> 第一版支援英文數位文字 PDF，並對掃描 PDF、雙欄 PDF、複雜表格 PDF 產生風險標記與處理報告。

### 3.2 翻譯不是一次 prompt，而是文件工程

長文件翻譯的核心不是 prompt 寫得漂亮，而是建立可控管線。

文件翻譯至少涉及：

- 切塊策略。
- 上下文保留。
- 術語一致性。
- Markdown 結構保留。
- 模型輸出約束。
- 翻譯快取。
- 失敗重試。
- 中斷續跑。
- 完整性檢查。
- 人工審閱標記。

若沒有這些工程機制，本地模型翻譯長文件會不穩定：短文可能效果不錯，長文件會出現漏譯、格式破壞、術語漂移與段落遺失。

### 3.3 不應先做完整 App 外殼

此專案最難的部分不是 UI，而是文件品質控制。

如果一開始投入完整桌面 App、iOS App 或漂亮 UI，會過早承擔不必要成本。更低風險的順序是：

1. 批次處理核心。
2. CLI 或簡單本地服務。
3. 本地 Web UI。
4. 桌面 App 包裝。
5. iOS 作為控制器或閱讀端。

第一階段真正要驗證的是：

- MarkItDown 對目標 PDF 的轉換品質。
- 本地模型翻譯品質是否可接受。
- 分塊後是否仍能維持術語一致。
- Markdown 格式是否可保留。
- 長文件處理速度是否可忍受。
- 中斷後是否能恢復。

### 3.4 產品目標應從「轉換」改為「可用的知識文件」

若目標只是「PDF 轉 Markdown 並翻譯」，容易低估品質問題。

更準確的產品目標是：

> 將英文 PDF 轉換成可閱讀、可檢索、可編輯、可匯入知識庫的繁體中文 Markdown 文件。

這個目標會導出不同設計取捨：

- 可讀性比版面還原更重要。
- Markdown 結構比 PDF 視覺位置更重要。
- 失敗報告比假裝成功更重要。
- 保留原文中間產物比只輸出譯文更重要。
- 可重跑與可追蹤比一次性完成更重要。

---

## 4. MVP 範圍

### 4.1 必做功能

- 匯入單一英文 PDF。
- 使用 MarkItDown 轉出原始英文 Markdown。
- 保留英文 Markdown 中間檔。
- 執行 Markdown 正規化。
- 將 Markdown 按結構切塊。
- 呼叫本地 Ollama 模型逐塊翻譯為繁體中文。
- 保留 Markdown 結構：標題、清單、表格、引用、連結、註腳、程式碼區塊。
- 支援術語表。
- 支援翻譯快取。
- 支援任務中斷後續跑。
- 輸出繁體中文 Markdown。
- 輸出處理報告。
- 對高風險 PDF 類型產生警告。

### 4.2 第一版暫不做

- 不追求 PDF 原始版面完全還原。
- 不做雙欄 PDF 的高精度版面重建。
- 不將 OCR 作為預設能力。
- 不處理圖片中的文字。
- 不做圖表語義解讀。
- 不做多人協作。
- 不做雲端同步。
- 不做引用管理器整合。
- 不做完整人工校對編輯器。
- 不做 iOS 本地大模型推論。

### 4.3 MVP 成功定義

MVP 成功不代表支援所有 PDF，而是代表：

- 對文字型英文 PDF，可穩定完成 PDF → Markdown → 繁中 Markdown。
- 轉換與翻譯過程可追蹤、可中斷、可續跑。
- 輸出可在 Obsidian、VS Code、GitHub Markdown Preview 中閱讀。
- 對失敗或高風險內容能清楚標記，而不是靜默產生錯誤譯文。

---

## 5. 使用者情境

### 5.1 主要使用者

- 研究者。
- 學生。
- 智庫文章閱讀者。
- 政策、軍事、科技、法律文件分析者。
- 希望建立個人知識庫的使用者。

### 5.2 核心使用流程

1. 使用者選擇英文 PDF。
2. App 判斷 PDF 類型與風險。
3. App 將 PDF 轉成英文 Markdown。
4. App 顯示轉換摘要與風險提示。
5. 使用者選擇 Ollama 模型與翻譯 profile。
6. App 將 Markdown 切塊並逐塊翻譯。
7. App 顯示進度、失敗區塊、重試狀態。
8. App 合併翻譯結果。
9. App 執行格式與完整性檢查。
10. App 輸出繁體中文 Markdown 與處理報告。

---

## 6. 建議產品形態

第一版建議做成：

```text
核心處理管線 + CLI / 本地 Web UI
```

優先順序：

1. 核心處理管線：驗證轉檔、切塊、翻譯、合併品質。
2. CLI：最低成本驗證批次處理能力。
3. 本地 Web UI：方便選檔、設定模型、查看進度、下載結果。
4. 桌面 App：流程穩定後再包裝。
5. iOS App：不建議作為 MVP；比較合理的角色是閱讀端或控制器。

iOS 不適合作為第一版主體，原因：

- 本地大模型推論成本高。
- 長 PDF 處理耗時長。
- 檔案處理與續跑機制較麻煩。
- Ollama 通常部署在 Mac、Linux 或桌面環境。

---

## 7. 系統架構總覽

### 7.1 架構分層

```text
Presentation Layer
  - CLI
  - Local Web UI
  - Future Desktop App

Application Layer
  - Job Service
  - Pipeline Orchestrator
  - Progress Reporter
  - Settings Service

Domain Layer
  - Document Model
  - Chunk Model
  - Translation Job Model
  - Glossary Model
  - QA Result Model

Infrastructure Layer
  - MarkItDown Adapter
  - Ollama Adapter
  - File Storage
  - Cache Storage
  - Report Exporter
```

### 7.2 模組職責

| 模組 | 職責 |
|---|---|
| Input Manager | 接收 PDF、建立任務、檢查檔案類型與大小 |
| PDF Classifier | 判斷 PDF 是數位文字、掃描影像、混合型、或疑似複雜版面 |
| Markdown Converter | 呼叫 MarkItDown 將 PDF 轉為英文 Markdown |
| Markdown Normalizer | 清理頁碼、頁眉頁腳、異常換行、破碎標題、重複空白 |
| Markdown Parser | 解析標題、段落、清單、表格、引用、程式碼區塊 |
| Chunker | 依 Markdown 結構切塊，避免切斷表格、清單、註腳與程式碼區塊 |
| Translation Orchestrator | 呼叫 Ollama，管理重試、快取、併發、模型設定 |
| Prompt Builder | 根據區塊類型、術語表、上下文建立翻譯提示 |
| Glossary Manager | 管理術語表、人名、機構名、縮寫、固定譯名 |
| Cache Manager | 依原文 hash、模型、prompt 版本判斷是否可重用翻譯 |
| Stitcher | 將翻譯後區塊合併為完整 Markdown |
| QA Checker | 檢查遺漏、格式破壞、英文殘留、表格列數不一致 |
| Report Generator | 產出轉換、翻譯、警告、失敗與統計報告 |
| Exporter | 輸出 Markdown、JSON metadata、處理報告 |

### 7.3 資料流

```text
PDF
  → Input Manager
  → PDF Classifier
  → Markdown Converter
  → Markdown Normalizer
  → Markdown Parser
  → Chunker
  → Translation Orchestrator
  → QA Checker
  → Stitcher
  → Full Document QA
  → Exporter
```

---

## 8. 系統設計規格

### 8.1 任務模型

每次 PDF 處理應建立一個任務。

任務應包含：

- 任務 ID。
- 來源 PDF 路徑。
- 輸出目錄。
- 建立時間。
- 目前狀態。
- 使用模型。
- 翻譯 profile。
- prompt 版本。
- 是否啟用術語表。
- 是否啟用簡轉繁。
- 總區塊數。
- 已完成區塊數。
- 失敗區塊數。
- 警告清單。

任務狀態：

| 狀態 | 意義 |
|---|---|
| Created | 任務已建立 |
| Classified | PDF 類型已判斷 |
| Converted | 已轉出英文 Markdown |
| Normalized | Markdown 已正規化 |
| Chunked | 已完成切塊 |
| Translating | 翻譯中 |
| Paused | 暫停 |
| Failed | 任務失敗 |
| CompletedWithWarnings | 完成但有警告 |
| Completed | 完成 |

### 8.2 區塊模型

每個區塊應包含：

- 文件 ID。
- 區塊 ID。
- 區塊順序。
- 區塊類型。
- 所屬標題路徑。
- 原始英文內容。
- 原文 hash。
- 翻譯內容。
- 翻譯狀態。
- 使用模型。
- prompt 版本。
- 翻譯時間。
- 重試次數。
- QA 結果。

區塊類型：

- Heading。
- Paragraph。
- List。
- Table。
- Blockquote。
- CodeBlock。
- Footnote。
- Reference。
- MixedSection。

### 8.3 快取鍵設計

翻譯快取不應只看原文內容。至少應納入：

- 原文 hash。
- 模型名稱。
- 模型參數。
- prompt 版本。
- 術語表 hash。
- 目標語言設定。
- 是否保留雙語。

若任一條件改變，快取應標記為可能失效。

### 8.4 設定模型

MVP 應支援下列設定：

- Ollama host。
- 模型名稱。
- context window 目標上限。
- 單塊最大長度。
- 翻譯 profile。
- temperature。
- top_p。
- 重試次數。
- 是否啟用簡轉繁後處理。
- 是否啟用術語表。
- 是否保留英文原文。
- 是否輸出雙語 Markdown。
- 快取目錄。
- 任務輸出目錄。

建議 temperature 預設偏低，以提高翻譯一致性。

---

## 9. PDF 轉 Markdown 規格

### 9.1 輸入限制

第一版建議限制：

- PDF 檔案大小：50 MB 以下。
- 頁數：100 頁以下。
- 語言：英文為主。
- 類型：文字型 PDF 優先。
- 掃描 PDF 顯示警告，不作為 MVP 成功標準。

### 9.2 PDF 類型判斷

PDF Classifier 應判斷：

| 類型 | 判斷依據 | MVP 策略 |
|---|---|---|
| Text PDF | 可抽取大量文字 | 正常處理 |
| Scanned PDF | 文字抽取量極低 | 標記風險，提示需 OCR |
| Mixed PDF | 部分頁面文字量異常 | 處理可抽取部分，報告警告 |
| Complex Layout PDF | 疑似雙欄、表格密集 | 正常嘗試，但報告需人工審查 |

### 9.3 MarkItDown 使用策略

- 預設使用 MarkItDown 的 PDF 支援能力。
- 保留 MarkItDown 原始輸出作為除錯中間產物。
- 若輸出文字量明顯過低，標記為疑似掃描 PDF。
- 若表格破碎嚴重，標記為需要人工檢查。
- 若遇到複雜 PDF，第二階段再評估 OCR、版面分析或其他專門工具。

### 9.4 Markdown 正規化規則

- 移除孤立頁碼。
- 移除重複頁眉頁腳。
- 修復英文斷行造成的破詞。
- 修復異常空白。
- 修復明顯破碎標題。
- 保留標題層級。
- 保留 Markdown 表格。
- 不在表格內任意切塊。
- 保留 URL、DOI、Email、檔名、程式碼內容。
- 將正規化操作記錄在處理報告中。

---

## 10. Markdown 切塊規格

### 10.1 切塊原則

- 優先依標題切塊。
- 次優先依段落切塊。
- 不切斷表格。
- 不切斷清單。
- 不切斷引用區塊。
- 不切斷程式碼區塊。
- 不切斷註腳定義。
- 每一塊都保留前後必要上下文。

### 10.2 切塊目標

- 單塊長度低於模型 context window 的安全範圍。
- 為術語一致性，每一塊可附帶簡短文件上下文。
- 對長表格採用整表處理，不逐列亂切。
- 若單一表格超過安全長度，標記為特殊高風險區塊。

### 10.3 上下文策略

每個翻譯區塊可附帶：

- 文件標題。
- 章節路徑。
- 前一小節標題。
- 術語表。
- 簡短翻譯規則。

但不應附帶過多全文摘要，否則會浪費 context 並增加模型混淆。

---

## 11. 翻譯規格

### 11.1 翻譯目標

將英文 Markdown 翻譯為自然、準確、適合研究閱讀的繁體中文 Markdown。

翻譯不是摘要，不得刪減、擴寫或重組原文論證。

### 11.2 翻譯規則

- 保留 Markdown 結構。
- 保留所有標題層級。
- 保留所有連結 URL。
- 保留表格欄位與列數。
- 保留程式碼區塊原文。
- 保留公式、數字、單位、引用標記。
- 專有名詞第一次出現可採「中文譯名（英文原文）」格式。
- 機構名、人名、地名、武器系統名、法案名、條約名依術語表固定。
- 縮寫第一次出現保留英文縮寫。
- 不加入原文不存在的解釋。
- 不輸出翻譯說明，只輸出譯文。

### 11.3 Prompt 契約

翻譯 prompt 應明確要求模型：

- 只輸出翻譯結果。
- 不加入前言、後記、說明。
- 不摘要。
- 不改變 Markdown 結構。
- 不翻譯 URL。
- 不翻譯程式碼區塊。
- 表格欄位數與列數必須維持一致。
- 不確定的專有名詞保留英文。
- 使用繁體中文。

### 11.4 繁體中文一致性

本地模型可能輸出簡體中文或混合用字，因此需加入後處理：

- 偵測簡體字比例。
- 必要時執行簡轉繁後處理。
- 以台灣繁體中文為預設語體。
- 術語表優先於自動轉換。

### 11.5 術語表

MVP 應支援一份專案層級術語表。

術語表用途：

- 固定 military、geopolitics、law、policy、technology 等領域常見譯名。
- 固定機構名與縮寫。
- 防止同一詞在不同區塊被翻成不同版本。

術語表至少包含：

- 英文詞。
- 繁中譯名。
- 詞性或類型。
- 是否強制使用。
- 備註。

---

## 12. Ollama 整合規格

### 12.1 整合方式

- App 不直接管理模型權重。
- App 呼叫本機 Ollama HTTP API。
- 預設 Ollama 服務位置為 localhost。
- 模型名稱由使用者設定。
- 支援 streaming 與 non-streaming。
- MVP 可先採 non-streaming 降低實作複雜度。

### 12.2 模型 profile

模型不應硬綁在 App 中，應採可替換設定。

建議提供三種 profile：

| Profile | 目的 | 適用情境 |
|---|---|---|
| Fast | 快速粗翻 | 短文、初步閱讀、低硬體規格 |
| Balanced | 品質與速度平衡 | 一般報告、論文、智庫文章 |
| Quality | 高品質翻譯 | 重要文章、長篇研究、需要術語一致性 |

MVP 測試時，至少比較兩類模型：

1. 翻譯特化模型。
2. 通用 instruction model。

評估重點：

- 是否能穩定輸出繁體中文。
- 是否保留 Markdown。
- 是否漏譯。
- 是否擅自摘要。
- 是否能處理專業術語。
- 是否能在可接受時間內完成長文件。

### 12.3 Context window 管理

- 不依賴超長 context 一次處理全文。
- 每一塊保留安全餘裕，避免模型截斷。
- 對長表格與長清單做特殊處理。
- 若模型回覆被截斷，需自動重試或降低區塊長度。

### 12.4 效能策略

- MVP 先支援單任務序列處理。
- 第二階段再加入多區塊併發。
- 併發數需依 RAM / VRAM 控制。
- 翻譯結果需快取。
- 模型預熱可作為效能優化選項。

---

## 13. 品質檢查規格

### 13.1 區塊級檢查

每個區塊翻譯後檢查：

- Markdown 標記是否平衡。
- 表格列數是否一致。
- 表格欄位數是否一致。
- 連結數量是否一致。
- 程式碼區塊是否保留。
- 是否出現明顯英文殘留。
- 譯文長度是否異常過短。
- 是否出現「以下是翻譯」等非正文內容。
- 是否疑似摘要而非翻譯。

### 13.2 全文級檢查

全文合併後檢查：

- 標題階層是否完整。
- 區塊順序是否正確。
- 是否有未完成翻譯區塊。
- 術語是否一致。
- 是否保留主要引用與註腳。
- 是否出現大量簡體中文。
- 是否出現異常重複段落。

### 13.3 人工審閱模式

MVP 不需要完整編輯器，但應輸出處理報告，列出：

- 轉檔警告。
- 翻譯失敗區塊。
- 可能漏譯區塊。
- 表格不一致區塊。
- 疑似掃描 PDF。
- 需要人工檢查的頁面或段落。

---

## 14. 輸出規格

每次任務輸出一個資料夾。

建議輸出：

```text
output/
  document.original.pdf
  document.en.raw.md
  document.en.normalized.md
  document.zh-TW.md
  document.bilingual.md
  report.md
  metadata.json
  chunks/
    chunk-0001.en.md
    chunk-0001.zh-TW.md
  glossary.snapshot.csv
```

繁體中文 Markdown 應可直接被下列工具使用：

- Obsidian。
- VS Code。
- GitHub Markdown Preview。
- 靜態網站產生器。
- 後續 RAG / 知識庫匯入流程。

### 14.1 處理報告內容

處理報告至少包含：

- 來源 PDF 基本資訊。
- PDF 類型判斷。
- MarkItDown 轉換摘要。
- 切塊數量。
- 翻譯模型與設定。
- 總耗時。
- 成功區塊數。
- 失敗區塊數。
- 重試次數。
- 警告。
- 需要人工檢查的區塊。

---

## 15. 安全與隱私

### 15.1 預設安全原則

- 預設只呼叫本機 Ollama。
- 不上傳 PDF 或 Markdown 到雲端。
- 不啟用任何外部翻譯 API。
- 暫存檔與快取位置需可設定。
- 任務完成後可選擇清除暫存檔。

### 15.2 不可信 PDF

PDF 是複雜格式，不應直接信任。

要求：

- App 以最小必要權限執行。
- 匯入檔案需限制路徑存取。
- 不自動跟隨 PDF 中的外部連結。
- 不執行 PDF 內嵌 JavaScript。
- 對未知來源 PDF 顯示安全警告。
- 轉換流程應與重要系統目錄隔離。

---

## 16. 非功能需求

### 16.1 可觀測性

任務需要顯示：

- 目前階段。
- 已處理頁數或區塊數。
- 目前使用模型。
- 已耗時。
- 失敗與重試次數。
- 預估剩餘區塊數。

### 16.2 可恢復性

- 任務中斷後可從最後成功區塊續跑。
- 原文 hash 相同時可重用快取。
- 模型或 prompt 改變時應標記快取失效。
- 任務 metadata 應定期落盤。

### 16.3 可移植性

- 核心處理流程應與 UI 分離。
- 未來可包裝成桌面 App、本地 Web App 或伺服器服務。
- 模型後端應抽象化，未來可替換為其他本地推論服務。

### 16.4 可測試性

- 每個管線階段都應保留輸出中間檔。
- 每個階段都應可單獨重跑。
- 測試集應固定，避免每次只靠主觀閱讀判斷品質。

---

## 17. 驗收標準

MVP 完成需滿足以下標準：

| 類別 | 驗收標準 |
|---|---|
| PDF 轉換 | 對文字型英文 PDF 可穩定產生英文 Markdown |
| 格式保留 | 標題、段落、清單、表格、連結大致保留 |
| 翻譯完整性 | 不摘要、不大幅刪減、不任意新增內容 |
| 繁中輸出 | 主要內容為繁體中文，無大量簡體殘留 |
| Markdown 有效性 | 輸出檔可在一般 Markdown preview 中閱讀 |
| 任務恢復 | 中斷後可續跑，不需重翻已完成區塊 |
| 報告 | 可清楚列出失敗、警告與需人工審查處 |
| 本地性 | 不依賴雲端 LLM API 完成核心流程 |
| 可追蹤性 | 可回溯每個譯文區塊的來源原文與模型設定 |

---

## 18. 測試計畫

### 18.1 測試文件組

至少建立五類測試 PDF：

1. 純文字英文論文。
2. 含註腳與引用的政策報告。
3. 含表格的智庫報告。
4. 雙欄排版 PDF。
5. 掃描 PDF 或混合型 PDF。

### 18.2 測試指標

| 指標 | 說明 |
|---|---|
| 轉換成功率 | PDF 是否成功轉為 Markdown |
| 文字完整率 | Markdown 是否漏掉大量內容 |
| 結構保留率 | 標題、表格、清單是否可用 |
| 翻譯完整率 | 是否完整翻譯而非摘要 |
| 術語一致性 | 同一術語是否保持固定譯法 |
| 格式破壞率 | Markdown 是否被模型破壞 |
| 簡體殘留率 | 是否混入大量簡體中文 |
| 處理時間 | 每頁或每千字耗時 |
| 記憶體使用 | 本地模型是否超出目標硬體能力 |
| 恢復能力 | 中斷後是否能從正確區塊續跑 |

### 18.3 MVP 通過門檻

建議第一階段通過門檻：

- 三份文字型 PDF 可成功完成全流程。
- 輸出 Markdown 可讀。
- 主要段落無明顯漏譯。
- 標題階層保留。
- 表格即使不完美，也能在報告中標記風險。
- 翻譯快取與續跑可用。

---

## 19. 風險與對策

| 風險 | 影響 | 對策 |
|---|---|---|
| PDF 版面複雜 | Markdown 結構破碎 | 第一版限制文件類型；輸出風險報告 |
| 掃描 PDF 無文字層 | MarkItDown 轉出內容不足 | 第二階段加入 OCR 或視覺模型流程 |
| 本地模型漏譯 | 譯文不可靠 | 區塊級完整性檢查與重試 |
| 模型破壞 Markdown | 輸出不可用 | 嚴格 prompt、格式檢查、失敗重試 |
| 翻譯不一致 | 長文件閱讀困難 | 術語表、上下文摘要、快取 |
| 處理速度慢 | 使用體驗差 | 快取、續跑、模型 profile、背景任務 |
| RAM / VRAM 不足 | 無法跑較大模型 | 允許小模型 profile，限制併發 |
| 複雜表格翻譯失真 | 資料錯誤 | 表格整塊處理，列數檢查，必要時標記人工審查 |
| 使用者誤信結果 | 研究判斷受誤導 | 報告中標出高風險區塊與未驗證內容 |
| App 過早產品化 | 工程成本失控 | 先完成核心管線，再做 UI 包裝 |

---

## 20. 開發里程碑

### M0：技術驗證

目標：確認 MarkItDown + Ollama 基本鏈路可跑通。

交付物：

- 一份英文 PDF 成功轉為 Markdown。
- 一份 Markdown 成功翻譯為繁體中文。
- 初步處理報告。

### M1：穩定轉換與切塊

目標：讓不同 PDF 能穩定進入翻譯流程。

交付物：

- Markdown normalizer。
- Markdown parser。
- Chunker。
- 區塊 metadata。
- 原文 hash 快取設計。

### M2：翻譯工作流

目標：建立可恢復、可重試的翻譯管線。

交付物：

- Ollama client 抽象層。
- 模型 profile 設定。
- 翻譯 prompt 規格。
- 區塊翻譯快取。

### M3：品質檢查

目標：降低漏譯與格式破壞。

交付物：

- Markdown 結構檢查。
- 表格一致性檢查。
- 英文殘留檢查。
- 簡體殘留檢查。
- 翻譯報告。

### M4：輕量 UI

目標：讓非命令列使用者能操作。

交付物：

- 選擇 PDF。
- 選擇模型 profile。
- 顯示進度。
- 查看警告。
- 下載輸出檔。

### M5：產品化前評估

目標：決定是否進入桌面 App 或 iOS 延伸。

評估項目：

- 文件處理成功率。
- 翻譯品質。
- 使用者等待時間。
- 硬體需求。
- 錯誤恢復能力。
- 使用者是否願意接受高風險區塊人工審閱。

---

## 21. 建議技術選型

### 21.1 核心處理層

優先建議 Python，原因是 MarkItDown 本身是 Python 工具，整合成本最低。

### 21.2 App 層

| 路線 | 優點 | 缺點 | 建議 |
|---|---|---|---|
| Python CLI | 最快驗證 | 使用者體驗低 | 技術驗證首選 |
| Python + 本地 Web UI | 快速、跨平台 | 需要處理本地服務 | MVP 首選 |
| Tauri / Electron | 桌面體驗好 | 包裝成本增加 | 第二階段 |
| Swift macOS App | 原生體驗好 | Python 與 Ollama 整合要多做封裝 | 流程穩定後再做 |
| iOS App | 行動體驗好 | 本地大模型與批次 PDF 不適合先做 | 不建議作為 MVP |

### 21.3 儲存層

MVP 可先使用檔案系統。

建議儲存：

- 任務 metadata。
- Markdown 中間檔。
- 區塊檔。
- 翻譯快取。
- 報告。

第二階段再考慮 SQLite，用於查詢任務歷史與管理快取。

---

## 22. 未來擴充

可在 MVP 穩定後擴充：

- OCR 流程。
- 雙語對照 Markdown。
- Obsidian vault 匯出。
- Zotero / Readwise / DEVONthink 整合。
- 批次處理多份 PDF。
- 文件摘要與章節摘要。
- 術語庫自動抽取。
- 引用與 footnote 清理。
- 人工校對 UI。
- 本地 RAG 知識庫整合。
- 多模型比較翻譯。
- 翻譯品質評分。

---

## 23. 決策紀錄

### 23.1 為何先用 Markdown 作為中間格式

Markdown 易讀、易 diff、易編輯，也適合匯入 Obsidian、Git、靜態網站與 RAG 流程。若直接從 PDF 翻譯到另一份 PDF，會過早陷入版面與排版問題。

### 23.2 為何先不做 OCR

OCR 會把問題從文件轉換擴大成圖像辨識、版面分析與文字校正。這是另一個高成本子系統，不應混入第一版核心驗證。

### 23.3 為何不先做 iOS App

第一版的核心瓶頸是長文件處理與本地模型翻譯。iOS 不適合作為第一個驗證平台。較合理策略是先在 Mac 或桌面環境建立核心服務，再讓 iOS 成為控制端或閱讀端。

### 23.4 為何要輸出處理報告

翻譯系統最危險的失敗不是明確報錯，而是安靜地漏譯或改寫。處理報告可以讓使用者知道哪些地方可信，哪些地方需要人工檢查。

---

## 24. 參考依據

檢索日期：2026-06-20。

- MarkItDown GitHub：<https://github.com/microsoft/markitdown>
- MarkItDown OCR plugin：<https://github.com/microsoft/markitdown/blob/main/packages/markitdown-ocr/README.md>
- Ollama API introduction：<https://docs.ollama.com/api/introduction>
- Ollama chat API：<https://docs.ollama.com/api/chat>
- Ollama FAQ：<https://docs.ollama.com/faq>
- Ollama translation model search：<https://ollama.com/search?q=translation>
