# Finsight — Nhật ký kiến trúc & stack

Tài liệu này ghi lại **toàn bộ stack** và **kiến trúc** của giai đoạn
*session → upload tài liệu → chat RAG* của Finsight: đã dựng những gì, vì sao
chọn như vậy, cách chạy và cách mở rộng. Đây là bản tiếng Việt; phần hướng dẫn
chạy nhanh bằng tiếng Anh nằm ở `README.md`.

Stack chạy **CPU-only** — model embedding và reranking chạy dưới dạng ONNX qua
FastEmbed (không cần PyTorch, không cần GPU), phần sinh câu trả lời giao cho LLM
host sẵn (Groq). Trạng thái chia cho ba dịch vụ chạy bằng Docker: **Postgres**
(metadata + lịch sử chat), **Qdrant** (vector), **Redis** (bộ nhớ ngắn hạn).

---

## 1. Sản phẩm cuối cùng

Một ứng dụng end-to-end hoàn chỉnh đặt trên nền pipeline OCR sẵn có:

- **Trang chủ** — tạo session, xem tất cả session.
- **Trang session** — upload tài liệu (**PDF / Markdown / JSON**) và chat với
  chúng. Câu trả lời **bám vào** nội dung tài liệu đã upload và hiển thị **trích
  dẫn (citation)**.
- **Lưu trữ bền** — session, tài liệu và toàn bộ lịch sử chat nằm trong Postgres;
  vector của các đoạn (chunk) nằm trong Qdrant; file gốc + Markdown đã chuẩn hoá
  nằm trên đĩa. Khởi động lại không mất gì.

```
                ┌────────────────────────┐         ┌──────────────────────────────┐
                │  Frontend (React/Vite)  │  HTTP   │       Backend (FastAPI)       │
   trình duyệt ▶│  Home → Session page    │ ──────▶ │  src/serving  (REST API)      │
                │  /api/* qua Vite proxy   │        │  src/rag      (RAG engine)    │
                └────────────────────────┘         └───────────────┬──────────────┘
                                                                     │
                       ┌──────────────┬──────────────┬──────────────┼──────────────┐
                       ▼              ▼              ▼              ▼              ▼
                   Postgres        Qdrant         Redis      đĩa (uploads/     Groq LLM
                (session, docs,   (vector của    (các lượt   processed md)    llama-3.3-70b
                 lịch sử chat)     chunk)        chat gần đây)                 -versatile)
```

---

## 2. Công nghệ sử dụng (stack)

| Lớp | Công nghệ | Vai trò |
| --- | --- | --- |
| Frontend | **React + Vite** | Giao diện home / session, gọi `/api/*` qua proxy của Vite |
| Backend | **FastAPI + Uvicorn** | REST API, dependency injection cho các singleton nặng |
| Embedding | **FastEmbed (ONNX, CPU)** | Nhúng vector đa ngôn ngữ, không cần GPU/PyTorch |
| Vector DB | **Qdrant** | Lưu & tìm kiếm vector của chunk, lọc theo `session_id` |
| Rerank | **FastEmbed cross-encoder** | Xếp hạng lại top-N ứng viên (có thể bật/tắt) |
| Sinh văn bản | **Groq** (`llama-3.3-70b-versatile`) | LLM tạo câu trả lời, gọi qua `httpx` thuần |
| CSDL quan hệ | **Postgres + SQLAlchemy 2.0** | Session, tài liệu, lịch sử chat bền vững |
| Bộ nhớ ngắn hạn | **Redis** | Cửa sổ trượt các lượt chat gần đây, có TTL |
| Lưu blob | **Hệ thống file** | File gốc + Markdown đã chuẩn hoá dưới `data/sessions/<id>/` |
| Hạ tầng | **Docker Compose** | Chạy Postgres + Qdrant + Redis bằng named volume |
| OCR (nền sẵn) | **PaddleOCR-VL + PyMuPDF** | Trích text từ PDF; PDF scan fallback sang OCR |

---

## 3. Luồng hoạt động, từng bước

### Tạo session
`POST /api/sessions` → chèn một `SessionRow` vào Postgres. Thư mục trên đĩa và các
point trong Qdrant được tạo lười (lazy) khi có tài liệu.

### Upload tài liệu (xử lý nền — non-blocking)
`POST /api/sessions/{id}/documents` (multipart). Upload được **tách làm hai** để
request không bao giờ bị chặn bởi bước nặng (`src/serving/routes/documents.py`):

**Pha 1 — đồng bộ, trả về ngay (201):**
1. Kiểm tra session, phần mở rộng, giới hạn dung lượng.
2. Lưu file gốc vào `data/sessions/<id>/uploads/` (`src/serving/files.py`).
3. Tạo bản ghi tài liệu với trạng thái **`processing`** và **trả `DocumentInfo`
   ngay lập tức** — client không phải chờ embedding.

**Pha 2 — chạy nền (`_process_document`, trong threadpool của FastAPI):**
4. **Ingest** thành Markdown chuẩn hoá (`src/serving/ingest.py`):
   - `.md` → dùng trực tiếp (đường nhanh).
   - `.json` → render thành Markdown dễ đọc (key lồng nhau + list phẳng thành bảng).
   - `.pdf` → lấy lớp text nhúng bằng PyMuPDF; PDF scan **chỉ** fallback sang OCR
     khi bật `FINSIGHT_ENABLE_API_OCR` (mặc định tắt để tránh nạp VLM nặng vào API).
5. **Chia chunk** Markdown theo cấu trúc (`src/rag/chunking.py`) — bám theo
   trang/heading, bảng được giữ nguyên và lặp lại dòng header cho từng nhóm.
6. **Nhúng** các chunk bằng FastEmbed (ONNX) và **upsert** vào collection chung
   của Qdrant, kèm payload `session_id` (`src/rag/vectorstore.py`). Đây là bước
   ngốn CPU/RAM nhất; đặt ở nền nên upload trả về tức thì và API vẫn phản hồi.
   Nhúng theo **lô nhỏ** (16) + upsert từng lô → RAM giữ thấp và báo được tiến độ.
7. Ghi trạng thái cuối (`ready` / `failed`), số chunk và số ký tự vào Postgres.

**Tiến độ theo %:** tài liệu có cột `progress` (0–100). Trong lúc nhúng,
`vectorstore.add(progress_cb=…)` báo `done/total` sau mỗi vector; worker quy về
thang **5→95%** (parse/chunk = 5%, nhúng xong = 95%, ghi `ready` = 100%) và ghi
vào Postgres mỗi khi tăng ≥5% (tránh ghi DB quá dày).

**Poll trạng thái:** client gọi `GET /api/sessions/{id}/documents/{doc_id}` để
lấy `status` + `progress`. Frontend tự poll mỗi 1.5s khi còn tài liệu
`processing` (`DocumentPanel.jsx`): badge + **thanh % cho từng file** tự cập nhật,
không cần refresh tay.

### Đặt câu hỏi
`POST /api/sessions/{id}/chat`:

1. **Lượt gần đây** lấy từ Redis (cửa sổ ngắn hạn); nếu cache trống thì mồi lại từ
   lịch sử bền trong Postgres.
2. **Truy hồi** — câu hỏi được nhúng, Qdrant trả về top-N ứng viên đã lọc theo
   `session_id`.
3. **Rerank (tuỳ chọn)** — nếu bật, cross-encoder đọc cặp (câu hỏi, chunk) cùng
   lúc và giữ lại top-K tốt nhất. Nếu tắt, dùng luôn điểm tương đồng vector.
4. **Sinh câu trả lời** — các chunk thành ngữ cảnh đánh số `[1]…[K]`; LLM được yêu
   cầu **chỉ** trả lời dựa trên ngữ cảnh đó và trích dẫn số trong ngoặc đã dùng.
5. Lượt người dùng + trợ lý ghi vào **cả** Postgres (bền) lẫn Redis (cửa sổ làm việc).
6. Trả về câu trả lời + citation (tên tài liệu, trang, điểm, đoạn trích).

---

## 4. Các quyết định thiết kế chính

| Quyết định | Vì sao |
| --- | --- |
| **Embedding dày (dense) đa ngôn ngữ** qua FastEmbed/ONNX | Truy hồi theo ngữ nghĩa, chạy **xuyên ngôn ngữ** — câu hỏi tiếng Anh vẫn truy hồi được báo cáo tiếng Việt mà không cần trùng từ khoá. ONNX giữ CPU-only (không PyTorch, không GPU). |
| **Cross-encoder reranker** (tuỳ chọn) | Tìm vector chỉ xếp theo độ tương đồng embedding; reranker đọc cặp câu hỏi–đoạn cùng lúc nên sắc hơn. Lấy dư N ứng viên, rerank, giữ K. Bật/tắt qua `FINSIGHT_USE_RERANKER`. |
| **Qdrant, một collection dùng chung** | Mọi session chung một collection; mỗi point mang payload `session_id` và query lọc theo nó (đã đánh index keyword cho nhanh). Session vẫn cô lập mà index quản lý một chỗ. |
| **Groq để sinh văn bản** | LLM host sẵn = không cần GPU. Gọi qua `httpx` thuần (không thêm SDK). Mặc định `llama-3.3-70b-versatile`. |
| **Postgres cho metadata + chat** | Nguồn sự thật bền, truy vấn được cho session / tài liệu / chat. ORM SQLAlchemy 2.0 với cascade delete; class `Database` phơi các method theo tác vụ để route mỏng. |
| **Redis cho bộ nhớ ngắn hạn** | Cửa sổ trượt có giới hạn + TTL cho các lượt gần đây, nạp lại vào prompt để câu hỏi nối tiếp ("còn năm 2024?") vẫn mạch lạc. Best-effort: Redis chết thì chat fallback về lịch sử Postgres. |
| **Đĩa cho blob** | File nhị phân và Markdown trích ra không nên nằm trong Postgres — để dưới `data/sessions/<id>/`. |
| **Nhận PDF + MD + JSON** | MD/JSON (vd export từ OCR) là đường nhanh; PDF có lớp text chạy tức thì qua PyMuPDF. |

---

## 5. Vì sao chọn truy hồi dense (thắng lợi xuyên ngôn ngữ)

Bản prototype trước dùng **TF-IDF**, vốn thuần từ vựng. Sau khi upload báo cáo
tiếng Việt, câu hỏi tiếng **Anh** (`"revenue"`) trả về *"không tìm thấy gì liên
quan…"* — vì từ "revenue" không xuất hiện trong tài liệu nên không trùng từ nào.
Cách chữa cũ là dùng LLM **mở rộng truy vấn** thành từ khoá đúng ngôn ngữ tài liệu.

Embedding dày đa ngôn ngữ xoá bỏ hẳn mẹo đó: `"revenue"` và `"doanh thu"` ánh xạ
về các vector gần nhau, nên câu hỏi tiếng Anh truy hồi thẳng đoạn tiếng Việt. Phần
mở rộng truy vấn đã bị gỡ khỏi pipeline.

> Mẹo thực tế: trộn nhiều năm trong một session vẫn làm truy hồi khó hơn — nên nêu
> rõ năm trong câu hỏi, hoặc mỗi năm/báo cáo một session.

---

## 6. Lựa chọn model & tinh chỉnh RAM

Vì chạy CPU-only, model nằm hết trong RAM (không phải VRAM). Đo thực tế trên máy:

| Thành phần | RAM nạp thêm |
| --- | --- |
| Embedder `intfloat/multilingual-e5-large` (1024-dim) | ~1.9 GB |
| Embedder `paraphrase-multilingual-mpnet-base-v2` (768-dim) | ~1.9 GB |
| Embedder `paraphrase-multilingual-MiniLM-L12-v2` (384-dim) | ~0.7 GB |
| Reranker `jina-reranker-v2-base-multilingual` | ~1.4 GB |

Lưu ý: FastEmbed **không có** `multilingual-e5-base`; bản 768-dim đa ngôn ngữ thay
thế là `paraphrase-multilingual-mpnet-base-v2`. Do onnxruntime cấp phát vùng nhớ
lớn, đổi e5-large → mpnet gần như không giảm RAM — đòn bẩy thật là **chọn embedder
nhỏ hơn** và/hoặc **tắt reranker**.

**Cấu hình đang dùng trên máy này** (ưu tiên nhẹ RAM): `mpnet-base-v2` (768-dim)
+ **tắt reranker** → backend ~1.5 GB (giảm ~49% so với ~3.0 GB ban đầu). Mọi giá
trị chỉnh qua `.env`:

```
FINSIGHT_EMBED_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2
FINSIGHT_EMBED_DIM=768
FINSIGHT_USE_RERANKER=false
```

> Đổi model embedding là **đổi số chiều vector**, nên phải tạo lại collection
> Qdrant (xoá collection cũ) và nhúng lại tài liệu (`scripts/migrate_to_postgres.py`).

`.env.example` giữ mặc định chất lượng cao (e5-large 1024-dim + bật reranker) cho
người cài mới; ai cần nhẹ RAM thì chỉnh như trên.

---

## 7. Bản đồ file

```
src/rag/
  chunking.py     Markdown → chunk gắn nhãn trang/heading (bảng giữ nguyên)
  embeddings.py   Embedder: nhúng đa ngôn ngữ qua FastEmbed (ONNX, CPU); prefix query/passage cho E5
  vectorstore.py  VectorStore: collection Qdrant, lọc theo session, add/search/delete
  reranker.py     Reranker: cross-encoder qua FastEmbed (ONNX, CPU)
  llm.py          GroqClient: chat-completions tối giản qua httpx
  pipeline.py     RAGPipeline: dense retrieve → rerank → trả lời bám ngữ cảnh + citation

src/serving/
  config.py       cấu hình + loader .env (Groq, URL DB/Qdrant/Redis, embed/rerank, top_k, giới hạn)
  schemas.py      model Pydantic request/response (hợp đồng API)
  db.py           Database + ORM: sessions / documents / chat_messages (Postgres)
  files.py        FileStore: file gốc + Markdown chuẩn hoá trên đĩa
  memory.py       ShortTermMemory: cửa sổ trượt Redis
  ingest.py       pdf/md/json → Markdown chuẩn hoá
  deps.py         singleton dùng chung (db, files, embedder, vectorstore, reranker, memory, pipeline)
  app.py          app FastAPI, CORS, gắn router, /api/health
  routes/         sessions.py · documents.py · chat.py

scripts/
  migrate_to_postgres.py   one-off: dựng lại session file-based cũ sang Postgres + Qdrant

docker-compose.yml         Postgres + Qdrant + Redis (named volume, ở root)

frontend/
  src/api.js              fetch client nhỏ cho /api
  src/App.jsx             khung app (thanh trên)
  src/pages/HomePage.jsx        tạo + liệt kê session
  src/pages/SessionPage.jsx     bố cục upload + chat
  src/components/DocumentPanel.jsx   kéo-thả upload + danh sách tài liệu
  src/components/ChatPanel.jsx       hội thoại + citation mở rộng được
  src/styles.css          theme phẳng, trung tính (không gradient, một màu nhấn)
```

---

## 8. API

| Method | Path | Mục đích |
| --- | --- | --- |
| `POST` | `/api/sessions` | Tạo session |
| `GET` | `/api/sessions` | Liệt kê session |
| `GET` | `/api/sessions/{id}` | Chi tiết session (+ tài liệu) |
| `DELETE` | `/api/sessions/{id}` | Xoá session (Postgres + Qdrant + đĩa + Redis) |
| `POST` | `/api/sessions/{id}/documents` | Upload tài liệu PDF/MD/JSON (trả về ngay, status `processing`) |
| `GET` | `/api/sessions/{id}/documents` | Liệt kê tài liệu |
| `GET` | `/api/sessions/{id}/documents/{doc_id}` | Poll trạng thái một tài liệu (`processing`→`ready`/`failed`) |
| `DELETE` | `/api/sessions/{id}/documents/{doc_id}` | Xoá một tài liệu |
| `POST` | `/api/sessions/{id}/chat` | Đặt câu hỏi (RAG) |
| `GET` | `/api/sessions/{id}/chat` | Lịch sử chat |
| `GET` | `/api/health` | Trạng thái LLM/embed/rerank/Qdrant/Redis |

---

## 9. Cách chạy

```bash
# 1. Hạ tầng — Postgres + Qdrant + Redis
docker compose up -d

# 2. Cấu hình — đặt Groq key vào .env (đã git-ignore)
cp .env.example .env        # rồi set GROQ_API_KEY

# 3. Backend
pip install -r requirements.txt
uvicorn src.serving.app:app --reload --port 8000
# request đầu tiên sẽ tải model embed (+ rerank nếu bật), một lần duy nhất

# 4. Frontend
cd frontend && npm install && npm run dev    # http://localhost:5173
```

Vite dev server proxy `/api` sang `http://localhost:8000`, nên frontend dùng URL
tương đối cùng origin (không vướng CORS lúc dev).

Có prototype file-based cũ? `python scripts/migrate_to_postgres.py` dựng lại các
session đó trong Postgres và nhúng lại file vào Qdrant.

---

## 10. Hướng phát triển tiếp

- **Truy hồi lai (hybrid)** — kết hợp dense với BM25 / sparse vector của Qdrant để
  bắt khớp chính xác mã cổ phiếu, mã số, tên tài khoản.
- **Lọc theo tài liệu / theo năm** trong một session để tránh lẫn năm (payload
  Qdrant đã sẵn `doc_id`).
- **Trả lời theo luồng (SSE)** cho cảm giác chat nhanh hơn.
- ✅ **Ingest nền** — đã làm: upload trả về ngay với status `processing`, embedding
  chạy ở background task, UI poll `GET .../documents/{doc_id}` tới khi `ready`.
  Bước tiếp có thể nâng lên hàng đợi thật (Celery/RQ/Arq) + giới hạn số job song
  song để khống chế đỉnh CPU/RAM khi nhiều người upload cùng lúc.
- **Embedding GPU** — đổi sang model lớn hơn khi có GPU; chỉ `src/rag/embeddings.py`
  đổi, API và frontend giữ nguyên.
```
