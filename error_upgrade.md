# Finsight — Lỗi & Hạng mục nâng cấp

> Tài liệu này liệt kê **toàn bộ lỗi và điểm cần nâng cấp** tìm được khi quét một
> lượt cả project (backend, AI/RAG, OCR, frontend), tập trung vào **tốc độ upload,
> tốc độ xử lý, hiệu năng backend và chất lượng AI**.
>
> **Ngày quét:** 2026-06-21 · **Phạm vi:** `src/ocr`, `src/rag`, `src/serving`, `frontend`, `docker`, `configs`.

## Quy ước độ khó
- **[Khó]** — đụng kiến trúc / nhiều thành phần / cần thiết kế lại.
- **[Trung bình]** — sửa một module, cần cẩn thận và test.
- **[Bình thường]** — sửa cục bộ, nhanh, ít rủi ro.

## ⚠️ Ghi chú nền quan trọng
Cấu hình **runtime thật (`.env`) khác mặc định trong code**: code mặc định
`intfloat/multilingual-e5-large` (1024-dim) + reranker BẬT, nhưng `.env` đang chạy
`paraphrase-multilingual-mpnet-base-v2` (768-dim) + **reranker TẮT**. Nhiều vấn đề
chất lượng bên dưới bắt nguồn từ chính sự lệch này.

---

# A. OCR PIPELINE — chất lượng trích xuất bảng/số liệu (ƯU TIÊN CAO NHẤT)

> Bằng chứng định lượng: **~60–65% bảng** trong 5 file (2021–2025) có
> `len(header) != n_cols` — tức đa số bảng tài chính bị vỡ cấu trúc do parser.

### A1. `_TableParser` bỏ qua `colspan`/`rowspan` → lệch cột toàn bộ bảng — **[Trung bình]**
- **Vị trí:** `src/ocr/postprocess.py:41-57` (`handle_starttag`/`handle_endtag`/`handle_data`), `:60-63`.
- **Mô tả:** Parser chỉ append 1 cell cho mỗi `<td>/<th>`, không đọc `colspan`/`rowspan`. Dữ liệu thật dùng nhiều (file 2021: `colspan="2"`×47, `colspan="3"`×12, `rowspan="2"`×12). Hậu quả: số cột mỗi dòng không khớp → con số trượt sang sai cột.
- **Tác động:** Con số tài chính nằm sai cột (Số cuối năm ↔ Số đầu năm, Giá gốc ↔ Dự phòng). **Lỗi nghiêm trọng nhất** — RAG/LLM đọc số sai.
- **Đề xuất:** Viết lại parser thành lưới 2D có occupancy matrix: `colspan=n` → đặt giá trị vào n ô; `rowspan=n` → giữ ô bị chiếm xuống n dòng; chuẩn hoá mọi dòng về cùng số cột. Cân nhắc `pandas.read_html`/`lxml`.

### A2. `header = grid[0]` ngây thơ — mất header dòng 2 / lấy nhầm dòng dữ liệu — **[Trung bình]**
- **Vị trí:** `src/ocr/postprocess.py:113-114`; cùng giả định ở `:76` (`rows_to_markdown`).
- **Mô tả:** Bảng tài chính thường có header 2 dòng (dòng 1 "Số cuối năm" colspan; dòng 2 "Giá gốc / Giá trị hợp lý / Dự phòng"). Code chỉ lấy dòng đầu → dòng header thứ 2 bị đẩy thành dữ liệu. Bảng không header (danh sách HĐQT) thì lấy nhầm dòng dữ liệu đầu làm header (vd `['Ông Phạm Nhật Vượng','Chủ tịch','']`).
- **Tác động:** Cột "Thuyết minh"/"Năm nay"/"Năm trước" không định vị được; `validate.py` dò header sai.
- **Đề xuất:** Sau khi sửa A1, gộp các dòng header (`<th>` hoặc dòng đầu toàn text) thành multi-row header và phẳng hoá ("Số cuối năm · Giá gốc"). Phân biệt bảng có/không header bằng heuristic.

### A3. `TableRecord` mất tên bảng (caption) và đơn vị tính ("Đơn vị tính: triệu VND") — **[Trung bình]**
- **Vị trí:** `src/ocr/postprocess.py:82-92` (dataclass thiếu field), `:109-114` (không đọc text trước `<table>`).
- **Mô tả:** Tên mục/bảng và dòng "Đơn vị tính" nằm ngay trước `<table>` trong HTML gốc bị rớt khỏi JSON. File 2021 có **49 lần** "Đơn vị tính", lẫn cả "triệu VND" và "VND" (đơn vị KHÁC nhau giữa các bảng).
- **Tác động:** Một con số "5.538.327" không biết là triệu VND hay VND (sai số 10⁶). Mất tên bảng → khó truy hồi/trích dẫn. Đây là gốc rễ việc "hỏi số liệu mà không ra".
- **Đề xuất:** Thêm field `caption` + `unit` vào `TableRecord`; bắt text/heading liền trước mỗi `<table>`, regex `Đơn vị tính:\s*(.+)`; kế thừa đơn vị từ bảng/mục gần nhất nếu thiếu. Gắn unit vào metadata chunk bảng.

### A4. `parse_number` hiểu sai số thập phân/tỷ lệ ("30.1" → 301) — **[Bình thường]**
- **Vị trí:** `src/ocr/validate.py:32` (`_NUM_BODY`), `:49` (`s.replace(".", "")`).
- **Mô tả:** Mọi dấu `.` bị coi là phân tách hàng nghìn (`parse_number('30.1') -> 301.0`); `12,5%` → `None`. BCTC có %, tỷ giá, EPS dạng thập phân.
- **Tác động:** Validate Tier 2/3 và mọi phân tích số trên tỷ lệ/giá đều sai; con số bị nhân 10/100.
- **Đề xuất:** Phân biệt dot-hàng-nghìn (`\d{1,3}(\.\d{3})+`) với dot-thập phân; xử lý `%`; chấp nhận `,` thập phân theo chuẩn VN nhất quán.

### B1. Regex strip HTML xoá luôn page-marker `<!-- page N -->` → mất số trang — **[Bình thường]**
- **Vị trí:** `src/ocr/postprocess.py:28` (`_HTML_TAG`), áp dụng `:118`.
- **Mô tả:** `<[^>]+>` khớp cả HTML comment. Output sạch mất hết page-marker, trong khi `src/rag/chunking.py:23` (`_PAGE_RE`) dựa hoàn toàn vào marker để gán trang cho chunk.
- **Tác động:** Chunk có `page=None` → trích dẫn RAG mất số trang (lỗi liên thông OCR↔RAG).
- **Đề xuất:** Bảo vệ comment (`r"<(?!!--)[^>]+>"`) hoặc chỉ strip whitelist thẻ (`img`, `div`, `span`).

### B2. Strip `<[^>]+>` nuốt văn bản giữa `<` và `>` (bất đẳng thức "< 5%") — **[Bình thường]**
- **Vị trí:** `src/ocr/postprocess.py:28,118`.
- **Mô tả:** `'a < b and c > d' -> 'a  d'`. BCTC có ký tự `<0`, "doanh thu > chi phí".
- **Tác động:** Mất câu/cụm văn bản tài chính âm thầm.
- **Đề xuất:** Strip theo tên thẻ hợp lệ đã biết; escape `<`,`>` không phải tag.

### B3. `n_tables` đếm trùng/sai (`count("<table") + count("|---")`) — **[Bình thường]**
- **Vị trí:** `src/ocr/models.py:38-40`.
- **Mô tả:** Đếm cả `<table` lẫn `|---`; separator multi-header bị đếm nhiều lần.
- **Tác động:** Log/perf report sai số bảng (gây nhiễu khi đánh giá).
- **Đề xuất:** Đếm theo số `TableRecord` thực sau parse.

### B4. `_TABLE_RE` không xử lý bảng lồng / bảng bị cắt qua trang — **[Khó]**
- **Vị trí:** `src/ocr/postprocess.py:27` (`<table.*?</table>`).
- **Mô tả:** Pipeline chạy theo từng trang → bảng dài bị tách 2 mảnh, mảnh sau mất header.
- **Tác động:** Một bảng thành nhiều `TableRecord` rời, mảnh sau mất header → khuếch đại A2.
- **Đề xuất:** Phát hiện và ghép bảng liền kề cùng header/số cột qua ranh giới trang trước khi tạo record.

### C1. OCR chạy tuần tự từng trang, không batch, không overlap render/OCR — **[Trung bình]**
- **Vị trí:** `src/ocr/pipeline.py:48-53`, `src/ocr/pdf_loader.py:56-64`, `src/ocr/batch.py:1-15`.
- **Mô tả:** Render toàn bộ PDF xong mới OCR; `predict` từng ảnh một, không batch. Trên CPU là nút thắt lớn với BCTC 100+ trang.
- **Tác động:** Thời gian OCR rất cao.
- **Đề xuất:** Overlap render & OCR; thử `predict` theo batch; cho cấu hình `cpu_threads`/MKLDNN qua `configs/ocr.yaml`.

### C2. Không giải phóng model OCR sau khi xong (rò RAM/VRAM) — **[Bình thường]**
- **Vị trí:** `src/ocr/engine.py:68-91` (không có `close`/`teardown`), `src/ocr/batch.py:60-86`.
- **Mô tả:** `_pipeline` không bao giờ được free; không `empty_cache()`. Batch dài / nhúng OCR vào API → RAM không trả lại.
- **Tác động:** Chiếm RAM/VRAM kéo dài, nguy cơ OOM.
- **Đề xuất:** Thêm `teardown()`/context-manager, xoá `self._pipeline` + empty cache sau batch.

### C3. Ảnh trang render ra đĩa không dọn; DPI 200 cố định — **[Bình thường]**
- **Vị trí:** `src/ocr/pdf_loader.py:59-60`, `configs/ocr.yaml:8`.
- **Mô tả:** Mỗi trang lưu PNG vĩnh viễn → phình đĩa; DPI 200 có thể yếu cho dấu tiếng Việt (comment đề nghị 300–400).
- **Tác động:** Tốn đĩa; có thể giảm chất lượng nhận dạng dấu.
- **Đề xuất:** Dùng thư mục tạm/xoá ảnh sau OCR; cho thử DPI cao hơn cho trang nhiều bảng.

### D1. Trang OCR lỗi không phân biệt với trang rỗng; không retry — **[Bình thường]**
- **Vị trí:** `src/ocr/engine.py:93-108`, `src/ocr/pipeline.py:48-49`.
- **Mô tả:** `predict` ném lỗi 1 trang → cả tài liệu fail; trang trả "" lặng lẽ thành dữ liệu thiếu, không cảnh báo.
- **Tác động:** Mất nguyên trang số liệu mà không ai biết.
- **Đề xuất:** Try/except từng trang, ghi trạng thái trang (ok/empty/error), retry tuỳ chọn, báo tổng số trang lỗi.

### D2. Postprocess & validate rời rạc, không chạy tự động trong pipeline — **[Trung bình]**
- **Vị trí:** `src/ocr/validate.py` (CLI riêng), `src/ocr/pipeline.py` (không gọi postprocess/validate).
- **Mô tả:** Pipeline kết thúc ở markdown thô; postprocess + validate là bước thủ công tách rời.
- **Tác động:** Dễ bỏ qua kiểm tra; dữ liệu lỗi (A1–A4) lọt vào RAG.
- **Đề xuất:** Nối postprocess (+ validate tuỳ chọn) vào cuối pipeline; có ngưỡng cảnh báo. (Sửa A1/A2 trước thì validate mới đáng tin.)

### D3. Device "auto" im lặng rơi về CPU khi import paddle lỗi — **[Bình thường]**
- **Vị trí:** `src/ocr/engine.py:27-36` (`except Exception: pass` → "cpu").
- **Mô tả:** Cài `paddlepaddle-gpu` mà lỗi CUDA runtime → lặng lẽ chạy CPU (chậm hơn nhiều) không cảnh báo.
- **Tác động:** Hiệu năng tụt bất ngờ, khó chẩn đoán.
- **Đề xuất:** Log WARNING khi auto fallback CPU do exception (phân biệt với "không có GPU").

---

# B. AI / RAG — chất lượng truy hồi & tốc độ

### RAG1. Không có hybrid search (lexical/BM25) — gốc rễ "không kéo được số liệu" — **[Khó]**
- **Vị trí:** `src/rag/vectorstore.py:144-160` (`search` chỉ `query=vector`), `src/rag/pipeline.py:65`.
- **Mô tả:** Truy hồi dense-only. Dense kém với token số ("1.234.567", "2023") và mã chỉ tiêu. Không có sparse/BM25 để khớp từ khoá chính xác.
- **Tác động:** Câu hỏi về SỐ LIỆU cụ thể gần như không lấy đúng chunk. **Nguyên nhân số 1.**
- **Đề xuất:** Bật hybrid của Qdrant: thêm sparse vector (BM25/SPLADE qua FastEmbed `SparseTextEmbedding`), tạo collection có cả dense+sparse, dùng `query_points` + `prefetch` + `FusionQuery(RRF)`. Kết hợp rerank.

### RAG2. Reranker đang TẮT trong runtime — **[Bình thường]**
- **Vị trí:** `.env` (`FINSIGHT_USE_RERANKER=false`), `src/serving/deps.py:45-47`, `src/rag/pipeline.py:69-73`.
- **Mô tả:** Khi tắt, lấy thẳng top_k=6 theo cosine từ 30 candidates → bỏ bước tinh chỉnh quan trọng nhất. Cross-encoder mới phân biệt được "doanh thu thuần" vs "doanh thu tài chính".
- **Tác động:** Mất lớp lọc chính xác → top_k nhiều chunk gần nghĩa nhưng sai chỉ tiêu.
- **Đề xuất:** Bật lại reranker (candidates ~30–50 trên CPU vẫn chấp nhận được). Giữ jina-reranker-v2 (đa ngữ, tốt tiếng Việt).

### RAG3. Lệch model embedding code vs .env — rủi ro lệch dim + chất lượng tiếng Việt — **[Trung bình]**
- **Vị trí:** `src/rag/embeddings.py:18,21,24-26`, `src/serving/config.py:68-69`.
- **Mô tả:** Code mặc định e5-large (1024) nhưng `.env` chạy mpnet (768). Prefix `query:`/`passage:` chỉ áp khi tên model chứa "e5" → mpnet không có (đúng), nhưng mpnet yếu hơn e5-large cho tiếng Việt & số liệu. Không kiểm tra dim model khớp `embed_dim`.
- **Tác động:** Chất lượng truy hồi giảm; rủi ro vỡ collection khi đổi model mà quên đổi dim.
- **Đề xuất:** Thống nhất e5-large (1024) hoặc `bge-m3` (dense+sparse+colbert, hợp hybrid + tiếng Việt). Lấy dim thật từ model lúc khởi tạo, fail-fast nếu lệch.

### RAG4. Không lọc metadata (năm/tài liệu) dù payload đã có — **[Trung bình]**
- **Vị trí:** `src/rag/vectorstore.py:151-157` (chỉ filter `session_id`); payload có `doc_id/page/heading/doc_name` (`:91-99`).
- **Mô tả:** Nhiều năm/công ty trong cùng session → câu hỏi "lợi nhuận 2023" lùa lẫn chunk 2022/2024.
- **Tác động:** Lẫn số liệu giữa các kỳ → trả lời sai số / sai cột năm.
- **Đề xuất:** Cho truyền `doc_ids` vào `search` (UI chọn tài liệu); trích "năm" từ heading/doc_name khi index → payload `year` + lọc; nâng cao: query understanding bóc tách (chỉ tiêu, năm, đơn vị).

### RAG5. `top_k=6` và `candidates=30` quá nhỏ cho tra số liệu — **[Bình thường]**
- **Vị trí:** `src/serving/config.py:82-83`, `.env`.
- **Mô tả:** Báo cáo dài hàng trăm chunk; bảng bị tách nhiều row-group. 30 candidates dense-only thường không chứa đúng chunk số.
- **Tác động:** Chunk chứa số đúng rơi khỏi top 30 → LLM không bao giờ thấy.
- **Đề xuất:** Khi có rerank: nâng candidates 60–100, top_k 8–10. Không tăng top_k khi chưa có rerank (nhiễu). Lý tưởng: hybrid → rerank → top_k.

### RAG6. `_split_table` mất ngữ cảnh đơn vị/cột năm + không trừ prefix heading — **[Trung bình]**
- **Vị trí:** `src/rag/chunking.py:155-183`, `:198-205`.
- **Mô tả:** Lặp header per-chunk (tốt) nhưng tách theo `chunk_size` mà không trừ phần `heading` prepend (`:205`) → chunk vượt ngân sách. Quan trọng hơn: "Đơn vị tính: triệu đồng" nằm ở block text riêng nên chunk bảng mất đơn vị.
- **Tác động:** LLM đọc được số nhưng mất đơn vị/cột năm → sai bậc 1.000 lần hoặc sai năm.
- **Đề xuất:** Gắn caption + "đơn vị tính" vào header block table; trừ `len(heading)` khỏi `size`; giữ nguyên bảng nhỏ không tách.

### RAG7. Heading breadcrumb bị đưa vào LLM 2 lần + phình payload — **[Bình thường]**
- **Vị trí:** `src/rag/chunking.py:204-214` (prepend heading vào text) + `vectorstore.py:96-97` (lưu lại heading riêng) + `pipeline.py:107-113` (in heading lần nữa trong nhãn nguồn).
- **Mô tả:** Breadcrumb xuất hiện 2 lần trong mỗi nguồn gửi LLM → tốn token, nhiễu.
- **Tác động:** Tốn token context (giảm số nguồn), nhiễu nhẹ.
- **Đề xuất:** Chọn 1 nguồn sự thật (giữ heading trong text HOẶC in trong nhãn), bỏ chỗ lặp.

### RAG8. Bug `page 0` bị mất trong nhãn nguồn (truthiness) — **[Bình thường]**
- **Vị trí:** `src/rag/pipeline.py:109` — `(f", page {s.page}" if s.page else "")`.
- **Mô tả:** Dùng `if s.page` thay vì `if s.page is not None` → trang 0 không hiển thị.
- **Tác động:** Trích dẫn thiếu số trang ở edge case (PDF hiện đánh trang từ 1 nên chưa lộ).
- **Đề xuất:** Đổi thành `if s.page is not None`.

### RAG9. Prompt: chống bịa OK nhưng thiếu ép đơn vị/kỳ + xử lý đối chiếu — **[Bình thường]**
- **Vị trí:** `src/rag/pipeline.py:21-28` (`_SYSTEM_PROMPT`).
- **Mô tả:** Đã yêu cầu "use ONLY context", "cite [n]", "report numbers exactly" — tốt. Nhưng không buộc nêu **đơn vị tính + năm** kèm mỗi số; không hướng dẫn chọn đúng cột năm khi context nhiều kỳ; không có few-shot bảng tiếng Việt.
- **Tác động:** Trả lời mơ hồ đơn vị/kỳ, lấy nhầm cột năm.
- **Đề xuất:** Bổ sung chỉ thị "luôn ghi đơn vị + kỳ; nhiều kỳ thì chỉ lấy đúng kỳ hỏi; thiếu đơn vị/kỳ thì nói rõ không xác định". Thêm 1 ví dụ đọc bảng.

### RAG10. Không có query expansion / chuẩn hoá thuật ngữ tài chính — **[Trung bình]**
- **Vị trí:** `src/rag/pipeline.py:64-65`, docstring `:8-10`.
- **Mô tả:** Câu hỏi người dùng ("lãi ròng năm ngoái") khác từ trong báo cáo ("Lợi nhuận sau thuế TNDN"). Dense đa ngữ giúp phần nào nhưng cặp gần-nghĩa vẫn nhầm.
- **Tác động:** Truy hồi sai chỉ tiêu do từ vựng lệch.
- **Đề xuất:** Query expansion bằng LLM rẻ (2–3 biến thể/synonym kế toán VN) → multi-query + hợp nhất; hoặc bảng ánh xạ synonym cố định; hybrid (RAG1) cũng giảm vấn đề.

### RAG11. Không có parent-child / context expansion sau retrieve — **[Khó]**
- **Vị trí:** `src/rag/chunking.py` (toàn bộ), `pipeline.py:96-113`.
- **Mô tả:** Chunk nhỏ tốt cho match nhưng trúng 1 row-group bảng thì LLM mất dòng lân cận (dòng tổng, chỉ tiêu liên quan). Không có "small-to-big".
- **Tác động:** LLM thiếu dòng tổng/đối chiếu → khó trả lời câu tổng hợp.
- **Đề xuất:** Parent-child: lưu `parent_id` (cả bảng) trên mỗi row-group; sau rerank fetch lại parent đầy đủ. `ordinal` đã có để khôi phục lân cận.

### RAG12. `chunk_size=1000` nhỏ và đo bằng ký tự, không phải token — **[Bình thường]**
- **Vị trí:** `src/serving/config.py:86-87`, `chunking.py:191`.
- **Mô tả:** 1000 ký tự ≈ 250–350 token ≈ ~1/3 trang. Với prose thuyết minh dài thì nhỏ; e5-large cho phép 512 token → đang dùng dưới công suất. Overlap 150 ký tự ít.
- **Tác động:** Ngữ cảnh prose phân mảnh.
- **Đề xuất:** Tách config prose vs table. Prose: ~1500–2000 ký tự, overlap ~200–250. Cân nhắc đo bằng token.

### RAG13. Embedding chậm trên CPU: batch_size=16 cứng, không cấu hình luồng ONNX — **[Trung bình]**
- **Vị trí:** `src/rag/embeddings.py:36` (`batch_size=16` hard-code), `:44`.
- **Mô tả:** batch nhỏ tối ưu "progress mượt" chứ không phải throughput. e5-large trên CPU + batch 16 chậm khi index báo cáo lớn. Không thấy cấu hình `OMP_NUM_THREADS`/intra-op.
- **Tác động:** Index chậm, chờ upload lâu.
- **Đề xuất:** Cho `batch_size` cấu hình (32–64 khi không cần progress quá mịn); cân nhắc model nhẹ hơn / ONNX int8; đặt số luồng ONNX theo CPU.

### RAG14. Không khử trùng lặp / không lọc ngưỡng điểm; thang điểm rerank lẫn lộn — **[Trung bình]**
- **Vị trí:** `src/rag/pipeline.py:69-87`.
- **Mô tả:** (1) Không có ngưỡng score → câu ngoài phạm vi vẫn nhồi 6 chunk rác vào LLM (hits hiếm khi rỗng vì luôn có chunk trong session). (2) Score rerank là logit nhưng `round` và hiển thị như cosine. (3) Không dedup chunk cùng bảng → 1 bảng chiếm hết top_k.
- **Tác động:** Bịa khi hỏi ngoài tài liệu; top_k bị 1 nguồn lấn át.
- **Đề xuất:** Ngưỡng score sau rerank (max < ngưỡng → "không tìm thấy"); MMR/dedup theo `doc_id+ordinal`; ghi rõ thang điểm.

### RAG15. Mất số trang cho file .md/.json (bảng — nguồn quan trọng nhất) — **[Trung bình]**
- **Vị trí:** `src/serving/ingest.py:83-103` (`_render_table_export` không chèn page-marker), `:52-68`.
- **Mô tả:** Luồng khuyến nghị là OCR offline → upload JSON/MD, nhưng các render này không phát page-marker → mọi chunk bảng `page=None`.
- **Tác động:** Trích dẫn `[n]` cho số liệu không kèm trang → khó kiểm chứng.
- **Đề xuất:** Nếu JSON OCR có thông tin trang, render kèm `<!-- ===== page N ===== -->` trước mỗi bảng; nếu không, ít nhất giữ `Table index` làm định danh.

---

# C. BACKEND SERVING — tốc độ upload/xử lý & độ ổn định

### BE1. Embedding không giới hạn đồng thời → upload nhiều file = quá tải CPU/RAM — **[Trung bình]**
- **Vị trí:** `src/serving/routes/documents.py:84-94`, `src/serving/deps.py:31-33`, `src/rag/embeddings.py:36`.
- **Mô tả:** Mỗi upload đẩy `_process_document` vào BackgroundTasks (threadpool 40). Upload 10 file → 10 task cùng gọi `_model.embed()` trên cùng ONNX session; FastEmbed nội bộ đa luồng → tranh hết core CPU. Không có Semaphore/hàng đợi.
- **Tác động:** Upload nhiều file làm CPU 100%, chậm cả chat đang chạy, throughput tệ hơn cả chạy tuần tự; nguy cơ RAM tăng đột biến/OOM.
- **Đề xuất:** Hàng đợi ingest (`asyncio.Queue` + N worker, hoặc `ThreadPoolExecutor(max_workers=1..2)` riêng cho embedding; tốt nhất Celery/RQ). Thêm `FINSIGHT_INGEST_CONCURRENCY`. Đặt `OMP_NUM_THREADS`/`ORT` theo core.

### BE2. BackgroundTasks không sống sót khi restart, không retry — **[Khó]**
- **Vị trí:** `src/serving/routes/documents.py:84`.
- **Mô tả:** Chạy cùng process; uvicorn restart/crash giữa chừng → doc kẹt `processing` vĩnh viễn, UI poll vô tận.
- **Tác động:** Tài liệu treo vĩnh viễn.
- **Đề xuất:** Job queue bền (RQ/Celery + Redis sẵn có). Tối thiểu: startup quét doc `processing` quá lâu → đánh dấu `failed`.

### BE3. Đọc toàn bộ file vào RAM (`file.file.read()`), không stream — **[Bình thường]**
- **Vị trí:** `src/serving/routes/documents.py:72`, `src/serving/files.py:32-35`.
- **Mô tả:** Nạp cả file vào RAM TRƯỚC khi kiểm tra dung lượng; 50 MB × nhiều upload đồng thời.
- **Tác động:** Nhiều upload lớn cùng lúc → nguy cơ OOM; client gửi hết file dù sẽ bị 413.
- **Đề xuất:** Stream đọc theo chunk, kiểm ngưỡng trong lúc đọc (dừng sớm + 413), ghi đĩa qua `shutil.copyfileobj`; kiểm `Content-Length` để từ chối sớm.

### BE4. Trích text PDF (PyMuPDF) chạy chung threadpool, không giới hạn — **[Trung bình]**
- **Vị trí:** `src/serving/ingest.py:191-203` (gọi từ `documents.py:116`).
- **Mô tả:** Trích PDF lớn là CPU-bound, chạy chung với embedding & chat.
- **Tác động:** PDF lớn nghẽn threadpool, ảnh hưởng chat.
- **Đề xuất:** Đưa vào cùng hàng đợi ingest giới hạn (BE1) hoặc tách worker.

### BE5. Model nặng nạp lazy ở request đầu → block request đó rất lâu — **[Bình thường]**
- **Vị trí:** `src/serving/deps.py:31-47`, `embeddings.py:20`, `reranker.py:21`, `app.py:36-44`.
- **Mô tả:** Startup cố tình không warm-up; request upload/chat đầu gánh toàn bộ chi phí tải/khởi tạo ONNX (vài giây tới hàng chục giây).
- **Tác động:** Request đầu cực chậm/timeout sau mỗi lần deploy.
- **Đề xuất:** Warm-up trong startup (embed 1 câu ngắn), bật/tắt qua env — đánh đổi thời gian khởi động lấy độ trễ request ổn định.

### BE6. Nhiều uvicorn worker sẽ nhân model trong RAM → OOM — **[Khó]**
- **Vị trí:** `src/serving/deps.py` (singleton per-process), `docker/docker-compose.yml` (không có service API).
- **Mô tả:** Mỗi `--workers N` nạp riêng embedder (~1–2 GB) + reranker → N lần RAM.
- **Tác động:** OOM khi scale; hoặc buộc 1 worker → không tận dụng nhiều core.
- **Đề xuất:** Tách embedding/rerank thành service riêng (1 instance dùng chung) hoặc giữ 1 worker + hàng đợi nội bộ. Thêm service `api` vào compose, ghi rõ trade-off.

### BE7. Reranker rerank 30 candidates đồng bộ trong request chat — **[Trung bình]**
- **Vị trí:** `src/rag/pipeline.py:69-71`, `reranker.py:23-27`, `config.py:82`.
- **Mô tả:** Mỗi câu hỏi: embed + Qdrant search + rerank 30 đoạn (CPU nặng) + gọi Groq — tuần tự, chung threadpool với ingest.
- **Tác động:** Chat chậm; khi đang ingest thì càng chậm.
- **Đề xuất:** Giảm candidates hoặc rerank giới hạn độ dài; tách ingest CPU-bound khỏi đường chat (BE1).

### BE8. Connection pool DB mặc định, không cấu hình — **[Bình thường]**
- **Vị trí:** `src/serving/db.py:110`.
- **Mô tả:** Không set `pool_size/max_overflow/pool_recycle/pool_timeout`. Mặc định 15 kết nối; threadpool 40 + ghi progress liên tục → có thể cạn pool; thiếu `pool_recycle` dễ "server closed connection".
- **Tác động:** Lỗi ngắt kết nối lẻ tẻ dưới tải.
- **Đề xuất:** Cấu hình pool + `pool_recycle=1800`, đưa vào env.

### BE9. Ghi DB quá dày khi index (mỗi +5% là 1 transaction) — **[Bình thường]**
- **Vị trí:** `src/serving/routes/documents.py:129-140`, `db.py:201-209`.
- **Mô tả:** Mỗi cập nhật progress là `SELECT get + UPDATE + COMMIT` riêng; doc lớn ~20 transaction.
- **Tác động:** Tải Postgres, round-trip thừa.
- **Đề xuất:** Throttle theo thời gian (1–2s) thay vì %; hoặc ghi progress vào Redis, chỉ ghi Postgres ở mốc đầu/cuối.

### BE10. N+1 query khi list session (`_summary` 2 query/session) — **[Bình thường]**
- **Vị trí:** `src/serving/db.py:142-165`.
- **Mô tả:** M session → 1 + 2M query (count documents + sum chunk_count).
- **Tác động:** Trang danh sách session chậm khi nhiều session.
- **Đề xuất:** Một query JOIN + GROUP BY trả count/sum cho tất cả session.

### BE11. Thiếu index cho sắp xếp thường dùng — **[Bình thường]**
- **Vị trí:** `db.py:57` (`created_at`), `db.py:181` (`uploaded_at`).
- **Mô tả:** `ORDER BY created_at`/`uploaded_at` không có index riêng.
- **Tác động:** Chậm khi dữ liệu nhiều.
- **Đề xuất:** Index `created_at`; composite `(session_id, uploaded_at)`, `(session_id, id)`.

### BE12. `create_all()` gọi 2 lần + `ALTER TABLE` ad-hoc (thiếu migration) — **[Bình thường]**
- **Vị trí:** `src/serving/deps.py:20-23`, `app.py:40`, `db.py:113-121`.
- **Mô tả:** Gọi 2 lần; migration thủ công bằng `ALTER TABLE IF NOT EXISTS` dễ tích nợ kỹ thuật.
- **Tác động:** Thừa khởi tạo; khó bảo trì schema.
- **Đề xuất:** Dùng Alembic; gọi `create_all` một nơi.

### BE13. Qdrant không timeout, không retry → treo khi Qdrant chậm/chết — **[Bình thường]**
- **Vị trí:** `src/rag/vectorstore.py:44` (không `timeout`), dùng ở `:104,109,148`.
- **Mô tả:** Qdrant treo → request chat/ingest chờ rất lâu; upsert lỗi tạm thời không retry → cả doc fail.
- **Tác động:** Một dependency chậm treo request; mất dữ liệu khi 1 batch upsert lỗi.
- **Đề xuất:** Đặt `timeout`; retry/backoff cho upsert; cân nhắc `wait=False`.

### BE14. Groq timeout 60s đồng bộ, không retry rate-limit (429) — **[Bình thường]**
- **Vị trí:** `src/rag/llm.py:28,56`.
- **Mô tả:** Gọi Groq đồng bộ tối đa 60s; 429/5xx không retry/backoff → 502 cho user.
- **Tác động:** Chat chậm/kém tin cậy khi rate limit.
- **Đề xuất:** Retry backoff cho 429/5xx (đọc `Retry-After`); giảm timeout hợp lý hoặc dùng streaming.

### BE15. Health check Redis/Qdrant đồng bộ mỗi request, không cache — **[Bình thường]**
- **Vị trí:** `src/serving/app.py:47-62`.
- **Mô tả:** `/api/health` đánh thẳng Qdrant + Redis mỗi lần; Qdrant treo thì health treo theo.
- **Tác động:** Có thể thành điểm nghẽn nếu poll dày.
- **Đề xuất:** Cache kết quả vài giây; timeout ngắn cho ping.

### BE16. Chat: `append_message` lỗi sau khi LLM trả lời → 500 / lịch sử lệch — **[Bình thường]**
- **Vị trí:** `src/serving/routes/chat.py:68-75`.
- **Mô tả:** Ghi user + assistant là 2 transaction riêng; nếu Postgres lỗi → 500 dù LLM đã chạy tốn tiền; có thể chỉ ghi được user.
- **Tác động:** Lãng phí lệnh LLM; lịch sử lệch.
- **Đề xuất:** Ghi cả user+assistant trong 1 transaction; bọc try/except để vẫn trả answer kể cả khi lưu lỗi (log lại).

### BE17. Không kiểm tra file rỗng → doc "ready" với 0 chunk — **[Bình thường]**
- **Vị trí:** `src/serving/routes/documents.py:72-83`.
- **Mô tả:** File rỗng vẫn lưu, ingest ra 0 chunk → status `ready` im lặng.
- **Tác động:** Doc "ready" nhưng không có nội dung.
- **Đề xuất:** Từ chối file rỗng (400); nếu chunk_count==0 → `failed` với thông báo rõ.

### BE18. Bẫy lệch `embed_dim` ↔ model (collection không tự tạo lại) — **[Trung bình]**
- **Vị trí:** `config.py:68-69` vs `.env.example:14-15` vs comment "bge-m3" (`vectorstore.py`, `requirements.txt:18`).
- **Mô tả:** Default code e5-large/1024, `.env.example` mpnet/768, comment nói bge-m3. Đổi model mà quên đổi dim → Qdrant collection dim cũ → mọi upsert/search lỗi; `_ensure_collection` chỉ tạo nếu CHƯA tồn tại.
- **Tác động:** Đổi embedding mà không xoá collection → toàn hệ thống fail âm thầm.
- **Đề xuất:** Suy ra `embed_dim` từ model; kiểm dim collection hiện có khớp, lệch thì log lỗi rõ. Đồng bộ default code/.env/comment.

### BE19. Xoá doc/session: xoá Qdrant + đĩa đồng bộ, không xử lý lỗi → vector mồ côi — **[Bình thường]**
- **Vị trí:** `documents.py:159-160`, `sessions.py:49-51`.
- **Mô tả:** Xoá Postgres trước (đã commit) rồi mới xoá Qdrant/đĩa; nếu Qdrant lỗi → rác vector mồ côi.
- **Tác động:** Rò rỉ vector; chậm nếu Qdrant chậm.
- **Đề xuất:** Bọc try/except best-effort cho phần xoá phụ trợ; job dọn dẹp; timeout Qdrant.

### BE20. Không có xác thực/rate-limit — ai biết id đều dùng được, tốn tiền Groq — **[Trung bình]**
- **Vị trí:** Toàn bộ `routes/*.py` (không auth).
- **Mô tả:** Không API key/token; `sid` là `uuid4()[:12]`; không rate limit.
- **Tác động:** Lạm dụng Groq, đầy đĩa/Qdrant.
- **Đề xuất:** Auth tối thiểu (API key) + rate limiting; nếu là demo nội bộ thì ghi rõ.

### BE21. JSON ingest đệ quy không giới hạn độ sâu/kích thước — **[Bình thường]**
- **Vị trí:** `src/serving/ingest.py:52-68,111-131` (`_render_json`).
- **Mô tả:** JSON lồng rất sâu → RecursionError hoặc Markdown khổng lồ (DoS dạng cấu trúc).
- **Tác động:** Ổn định ingest.
- **Đề xuất:** Giới hạn độ sâu + kích thước output; bắt RecursionError → fail gọn.

### BE22. CORS `allow_credentials=True` + `*` methods/headers (thừa, dễ cấu hình sai) — **[Bình thường]**
- **Vị trí:** `src/serving/app.py:23-29`.
- **Mô tả:** Không dùng cookie nên `allow_credentials=True` là thừa; nguy hiểm nếu set `FINSIGHT_CORS_ORIGINS=*`.
- **Tác động:** Bảo mật tiềm ẩn nếu cấu hình sai.
- **Đề xuất:** Tắt `allow_credentials` nếu không dùng cookie; giới hạn methods/headers thực cần.

### BE23. `.env` loader tự viết — mong manh — **[Bình thường]**
- **Vị trí:** `src/serving/config.py:18-37`.
- **Mô tả:** Không hỗ trợ multiline/escape/`export `; dễ lỗi tinh vi.
- **Tác động:** Lỗi cấu hình khó debug.
- **Đề xuất:** Dùng `python-dotenv` / `pydantic-settings`.

### BE24. Validate `sid`/`doc_id` dạng hex ở tầng route — **[Bình thường]**
- **Vị trí:** `documents.py:63-64`, `files.py:32-33` (`glob(f"{doc_id}.*")`).
- **Mô tả:** `doc_id` từ URL chứa ký tự glob/`/` có thể gây hành vi lạ (rủi ro thấp vì match DB).
- **Tác động:** Thấp, nên phòng ngừa.
- **Đề xuất:** Validate khớp `^[0-9a-f]{12}$`.

### BE25. `@app.on_event("startup")` đã deprecated — **[Bình thường]**
- **Vị trí:** `src/serving/app.py:36`.
- **Mô tả:** `on_event` bị deprecated với FastAPI mới (`fastapi>=0.115`).
- **Tác động:** Bảo trì.
- **Đề xuất:** Chuyển sang `lifespan` context manager.

---

# D. FRONTEND — trải nghiệm upload/chat

### FE1. Upload nhiều file chạy tuần tự, một lỗi dừng cả vòng — **[Trung bình]**
- **Vị trí:** `frontend/src/components/DocumentPanel.jsx:22-36`.
- **Mô tả:** `for ... await uploadDocument` — file sau đợi file trước. Backend trả về ngay nên tuần tự là vô ích, chỉ cộng dồn round-trip; list hiện một lượt sau khi tất cả POST xong; 1 file lỗi → các file sau không upload.
- **Tác động:** Tốc độ cảm nhận kém.
- **Đề xuất:** `Promise.allSettled(files.map(...))`, `onChange()` ngay sau mỗi file thành công (hoặc optimistic-add), gom lỗi từng file riêng.

### FE2. Không có % cho giai đoạn UPLOAD (chỉ có % indexing) — **[Trung bình]**
- **Vị trí:** `frontend/src/api.js:34-38` (`fetch` không có upload progress), `DocumentPanel.jsx:99-113`.
- **Mô tả:** Thanh % chỉ phản ánh indexing nền. Bước tải file (PDF 50 MB) không có % — chỉ "Uploading…".
- **Tác động:** Upload file lớn: người dùng tưởng treo.
- **Đề xuất:** Dùng `XMLHttpRequest` + `xhr.upload.onprogress` cho `uploadDocument`; hiện % upload trước, rồi chuyển sang % indexing.

### FE3. Một cờ `uploading` chung cho cả batch — **[Trung bình]**
- **Vị trí:** `DocumentPanel.jsx:8,22-36,77`.
- **Mô tả:** Không biết file nào đang lên; không có trạng thái per-file phía client.
- **Tác động:** UX mơ hồ khi nhiều file.
- **Đề xuất:** Quản lý tiến độ theo từng file (map fileId → progress/status) + optimistic rows.

### FE4. Polling nuốt lỗi + có thể chồng lệnh khi mạng chậm — **[Trung bình]**
- **Vị trí:** `DocumentPanel.jsx:16-20`, `SessionPage.jsx:14-21`.
- **Mô tả:** `setInterval(onChange, 1500)` không `.catch`; mạng chậm > 1.5s → request chồng đống; lỗi poll không hiện.
- **Tác động:** Mất phản hồi khi mạng chập chờn; tải chồng.
- **Đề xuất:** `.catch` trong interval; cờ `inFlight` hoặc `setTimeout` đệ quy; backoff khi lỗi.

### FE5. Poll cả session detail trong khi chỉ cần document status — **[Trung bình]**
- **Vị trí:** `SessionPage.jsx:14-21` (`Promise.all([getSession, listDocuments])`).
- **Mô tả:** Mỗi nhịp poll gọi 2 request dù session gần như không đổi; đã có endpoint `GET /{doc_id}`.
- **Tác động:** Gấp đôi request khi polling.
- **Đề xuất:** Khi poll chỉ gọi `listDocuments` (hoặc `getDocument` cho doc còn processing); `getSession` chỉ khi mount / sau khi có doc ready.

### FE6. Chat không streaming — câu trả lời dài hiện một cục — **[Khó]**
- **Vị trí:** `ChatPanel.jsx:28-33`, `api.js:43`.
- **Mô tả:** Client đợi toàn bộ answer rồi mới render; chỉ "Thinking…".
- **Tác động:** Tốc độ cảm nhận kém ở phần quan trọng nhất.
- **Đề xuất:** Backend SSE/streaming + đọc dần `ReadableStream`, append token. Nâng cấp đáng giá nhất cho cảm nhận tốc độ.

### FE7. Lịch sử chat `key={i}` + gõ phím re-render toàn bộ list — **[Trung bình]**
- **Vị trí:** `ChatPanel.jsx:54-55`.
- **Mô tả:** Key theo index (anti-pattern); input cùng component nên gõ phím re-render cả list messages.
- **Tác động:** Re-render thừa; key index dễ bug khi mở rộng.
- **Đề xuất:** Id ổn định (backend trả message id); tách input ra component con / `React.memo` cho `Message`.

### FE8. Không validate kích thước/loại file ở client — **[Bình thường]**
- **Vị trí:** `DocumentPanel.jsx:22-36`; backend 413/400 ở `documents.py:65-76`.
- **Mô tả:** Drop không lọc `accept`; file 50 MB+/sai loại vẫn round-trip mới báo lỗi.
- **Tác động:** Lãng phí băng thông, báo lỗi chậm.
- **Đề xuất:** Lọc `file.size` + phần mở rộng trong `uploadFiles`/`handleDrop`, báo lỗi tức thì.

### FE9. Dropzone không truy cập được bằng bàn phím (a11y) — **[Bình thường]**
- **Vị trí:** `DocumentPanel.jsx:58-67`.
- **Mô tả:** `div.dropzone` chỉ có `onClick`, thiếu `role/tabIndex/onKeyDown`/`<label>`.
- **Tác động:** Vi phạm a11y; không dùng được bằng keyboard.
- **Đề xuất:** Thêm `role="button"`, `tabIndex={0}`, xử lý Enter/Space, hoặc bọc `<label>`.

### FE10. `d.kind.toUpperCase()` crash nếu thiếu trường — **[Bình thường]**
- **Vị trí:** `DocumentPanel.jsx:91,124-131`.
- **Mô tả:** `kind` null/undefined → throw; không guard.
- **Tác động:** Một bản ghi thiếu trường làm crash cả panel (không có error boundary).
- **Đề xuất:** `(d.kind || "doc").toUpperCase()` + guard status.

### FE11. Chat lỗi: mất câu hỏi đã gõ, không retry — **[Bình thường]**
- **Vị trí:** `ChatPanel.jsx:20-39`.
- **Mô tả:** `api.ask` lỗi: tin user ở lại không có trả lời, input đã bị xoá (`:25`) → phải gõ lại.
- **Tác động:** Khó chịu khi mạng chập chờn.
- **Đề xuất:** Giữ text khi lỗi / nút Retry trên message; đánh dấu tin "gửi lỗi".

### FE12. `getHistory` lỗi bị nuốt im lặng — **[Bình thường]**
- **Vị trí:** `ChatPanel.jsx:12-14` (`.catch(() => {})`).
- **Mô tả:** Tải lịch sử lỗi → không hiện gì, không retry, không log.
- **Tác động:** Mất dữ liệu hiển thị thầm lặng.
- **Đề xuất:** Set error state / thông báo "Không tải được lịch sử".

### FE13. Thanh progress không reset khi `failed` — **[Bình thường]**
- **Vị trí:** `DocumentPanel.jsx:106-116`; backend `documents.py:144` không reset progress.
- **Mô tả:** Lỗi ở 60% thì giữ `progress=60` (hiện không hiển thị lại nên rủi ro thấp).
- **Tác động:** Thấp, vệ sinh dữ liệu.
- **Đề xuất:** Backend set `progress=0` khi failed; frontend không phụ thuộc.

### FE14. Thiếu Error Boundary toàn cục — **[Bình thường]**
- **Vị trí:** `frontend/src/main.jsx:9-20`, `App.jsx`.
- **Mô tả:** Bất kỳ lỗi render nào (vd FE10) làm trắng cả trang.
- **Tác động:** Một lỗi nhỏ → mất toàn bộ UI.
- **Đề xuất:** Bọc `<Outlet/>` bằng ErrorBoundary + fallback + nút reload.

### FE15. `confirm`/`alert` native chặn UI, không nhất quán phong cách — **[Trung bình]**
- **Vị trí:** `HomePage.jsx:44`, `DocumentPanel.jsx:45`.
- **Mô tả:** Dùng `confirm()` trình duyệt — thô, không khớp phong cách "clean".
- **Tác động:** UX kém nhất quán.
- **Đề xuất:** Modal xác nhận trong app.

### FE16. Auto-scroll chat ép cuộn xuống cả khi đang đọc tin cũ — **[Bình thường]**
- **Vị trí:** `ChatPanel.jsx:16-18`.
- **Mô tả:** Mỗi lần `messages`/`sending` đổi đều cuộn xuống đáy bất kể vị trí đọc.
- **Tác động:** Kéo người dùng khỏi chỗ đang đọc.
- **Đề xuất:** Chỉ auto-scroll khi đang ở gần đáy.

### FE17. Answer render plain text — không Markdown/bảng/số đậm — **[Trung bình]**
- **Vị trí:** `ChatPanel.jsx:88` (`{message.content}` + `pre-wrap`).
- **Mô tả:** Q&A tài chính, câu trả lời thường có danh sách/bảng/số liệu/đậm nhưng hiện plain text.
- **Tác động:** Câu trả lời dài/bảng khó đọc.
- **Đề xuất:** Render Markdown an toàn (`react-markdown` + sanitize) — thêm dependency.

### FE18. Không abort request khi unmount — **[Trung bình]**
- **Vị trí:** `SessionPage.jsx:23-27`, `ChatPanel.jsx:12-14`, polling DocumentPanel.
- **Mô tả:** Rời trang khi request đang chạy → `setState` trên component đã unmount; không `AbortController`.
- **Tác động:** Cảnh báo dev, request thừa, race nhỏ.
- **Đề xuất:** `AbortController` + cờ `cancelled` trong cleanup.

### FE19. Layout magic-number + doc-list không cuộn riêng — **[Bình thường]**
- **Vị trí:** `frontend/src/styles.css:271-273`, `.doc-list:216`.
- **Mô tả:** `height: calc(100vh - 200px)` cứng; nhiều document làm panel cao quá màn hình.
- **Tác động:** Bố cục lệch trên màn nhỏ / nhiều file.
- **Đề xuất:** Flex/grid thay magic number; `max-height + overflow:auto` cho `.doc-list`.

### FE20. `vite.config.js` proxy không set timeout cho request LLM lâu — **[Bình thường]**
- **Vị trí:** `frontend/vite.config.js:8-16`, `package.json`.
- **Mô tả:** `api.ask` (LLM) có thể lâu, proxy timeout mặc định có thể cắt; bundle chưa tách vendor chunk.
- **Tác động:** Câu hỏi LLM chậm có nguy cơ bị proxy ngắt.
- **Đề xuất:** Tăng `proxy['/api'].timeout/proxyTimeout`; tách vendor chunk khi build.

---

# E. ĐIỂM ĐÃ LÀM TỐT (không cần sửa)
- Upload tách 2 pha (201 ngay + xử lý nền) — hướng đúng (`documents.py`).
- Embedding stream từng vector + upsert batch 64 → RAM bị giới hạn tốt (`vectorstore.py`, `embeddings.py`).
- Redis memory best-effort, không bao giờ block chat (`memory.py`).
- Payload index `session_id`/`doc_id` trong Qdrant (`vectorstore.py:55-65`).
- Filename chuẩn hoá `.name`, `doc_id` do server sinh → chặn path traversal cơ bản.
- In-API OCR tắt mặc định để tránh nạp VLM 3–5 GB gây OOM (`config.py:75-79`).
- `_split_table` lặp header mỗi row-group — thiết kế đúng (chỉ cần header nguồn đúng, xem A2).

---

# F. THỨ TỰ ƯU TIÊN ĐỀ XUẤT

### Giai đoạn 1 — Nền chất lượng số liệu (làm trước hết)
1. **A1** (colspan/rowspan) — ảnh hưởng ~60–65% bảng.
2. **A2** (multi-row header) + **A3** (caption/đơn vị) — đi cùng A1.
3. **B1/RAG15** (giữ page-marker) — khôi phục trích dẫn trang.
4. **A4** (parse_number thập phân).

### Giai đoạn 2 — Retrieval nâng cao (sau khi nền chắc)
5. **RAG1** (hybrid BM25+dense) + **RAG2** (bật rerank) — đòn bẩy lớn nhất.
6. **RAG4** (lọc năm/tài liệu) + **RAG6** (đơn vị/cột năm trong chunk bảng).
7. **RAG3** (thống nhất model embedding) + **RAG5** (tăng candidates).
8. **RAG9/RAG10** (prompt + query expansion) + **RAG14** (ngưỡng/dedup).

### Giai đoạn 3 — Tốc độ & ổn định backend
9. **BE1** (giới hạn đồng thời ingest) + **BE5** (warm-up model).
10. **BE13/BE14** (timeout/retry Qdrant & Groq) + **BE18** (bẫy embed_dim).
11. **BE8/BE9** (pool DB + giảm ghi progress) + **BE2** (job bền chống doc treo).

### Giai đoạn 4 — Trải nghiệm frontend
12. **FE1** (upload song song) + **FE6** (streaming chat) + **FE2** (% upload thật) + **FE5** (poll thừa).
13. **FE4/FE11/FE12/FE14** (xử lý lỗi + error boundary), rồi các mục hoàn thiện còn lại.

### Dọn nhanh (sửa nhẹ, ít rủi ro)
RAG7, RAG8, BE17, BE25, FE10, FE13.
