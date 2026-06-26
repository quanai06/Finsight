# Finsight — Embedding (Dense qua API + Sparse local)

> Tài liệu phần nhúng (embedding) sau đợt chuyển dense embedding sang **API**.
> Cập nhật: 2026-06-26.

## 1. Vì sao đổi sang API

Đo thực tế khi index 1 file BCTC (`2021_...md`, 191.810 ký tự → **284 chunk**, máy 12 core, CPU-only — xem `bugs.md`):

| Pha | Thời gian | % tổng |
| --- | --- | --- |
| đọc .md + chunk | ~0.34s | ~0% |
| **dense embed (e5-large, ONNX CPU)** | **~689s (~11.5 phút)** | **99.8%** |
| sparse embed (BM25) | ~1.0s | 0.1% |

→ **Toàn bộ thời gian index nằm ở dense embedding trên CPU.** Tăng thread/batch *không* giúp (đã đo, oversubscribe còn chậm hơn). Đòn bẩy thật là **đưa dense ra khỏi CPU**.

Vì khâu sinh câu trả lời (LLM) **vốn đã** gọi Groq qua API, thêm một API cho embedding không phá vỡ ràng buộc nào — và còn cho chất lượng tiếng Việt tốt hơn.

## 2. Kiến trúc sau khi đổi

```
Dense (ý nghĩa)   →  HF Inference API   →  AITeamVN/Vietnamese_Embedding (1024-dim)   [REMOTE]
Sparse (chữ/số)   →  FastEmbed local    →  Qdrant/bm25                                 [LOCAL]
                         └──────── fuse bằng RRF trong Qdrant ────────┘
```

- **Dense ra API**: khâu nặng → off-CPU, index 1 file từ ~11.5 phút xuống **vài giây**.
- **Sparse vẫn local**: BM25 rẻ (~1s/file, ~0 RAM), là lớp khớp chính xác số liệu/mã/năm — không có lợi gì khi đưa lên mạng.
- **Không đổi schema Qdrant**: model mới cũng **1024-dim** như e5-large (cosine), vector đã **L2-normalized** sẵn → hợp cosine + MMR.

## 3. Model dùng — `AITeamVN/Vietnamese_Embedding`

- Nền **BGE-M3** fine-tune cho tiếng Việt; đứng đầu bảng **Vietnamese MTEB**, được cộng đồng NLP Việt dùng rộng rãi.
- **1024-dim**, **không cần word-segmentation** (khác các model PhoBERT như `bkai vietnamese-bi-encoder`, `dangvantuan/vietnamese-embedding` — vốn cần tách từ và chỉ 256 token), ngữ cảnh dài → hợp văn bản tài chính nhiều bảng + số.
- **Đối xứng** (symmetric): không cần tiền tố `query:` / `passage:` như e5.
- Đã kiểm chứng chạy được qua HF Inference API (các model PhoBERT bị HF từ chối phục vụ: *"Model not supported by provider hf-inference"*).

## 4. Cách hoạt động trong code

- `src/rag/embeddings.py`
  - `Embedder` — dense **local** (FastEmbed/ONNX) + BM25. Giữ nguyên, là backend mặc định.
  - `ApiEmbedder` — dense qua **HTTP** (mặc định endpoint HF Inference `feature-extraction`) + BM25 local. **Cùng interface** với `Embedder` nên `VectorStore`/`RAGPipeline` không phải sửa.
  - `_BM25Sparse` — phần sparse dùng chung cho cả hai backend.
  - `ApiEmbedder` gom request theo **batch** (mặc định 32 text/lần), **retry có backoff** với lỗi tạm thời (429 rate-limit, 503 cold-start, 5xx, lỗi mạng), gửi `wait_for_model=true` để chờ model nguội; lỗi 4xx (token sai/model không hỗ trợ) thì **raise ngay** (`EmbeddingError`).
- `src/serving/deps.py::get_embedder()` — chọn backend theo `FINSIGHT_EMBED_BACKEND`.
- `src/serving/config.py` — các biến cấu hình + `active_embed_model`.
- `src/serving/app.py` — warm-up lúc boot (gọi 1 lần `embed_query`/`embed_sparse_query`), `/api/health` báo `embed_backend` + model đang dùng.

## 5. Cấu hình (`.env`)

```bash
FINSIGHT_EMBED_BACKEND=api                 # local | api
FINSIGHT_EMBED_DIM=1024                     # phải khớp dim model
HF_API_TOKEN=hf_xxx                         # token HF (quyền Read là đủ)
FINSIGHT_API_EMBED_MODEL=AITeamVN/Vietnamese_Embedding
FINSIGHT_API_EMBED_BATCH=32
# FINSIGHT_API_EMBED_ENDPOINT=             # tùy chọn: trỏ Inference Endpoint riêng / TEI

# Backend local (khi FINSIGHT_EMBED_BACKEND=local):
FINSIGHT_EMBED_MODEL=intfloat/multilingual-e5-large
```

Quay lại local: đặt `FINSIGHT_EMBED_BACKEND=local` (và **re-index**, xem dưới).

## 6. ⚠️ Phải re-index sau khi đổi model

Vector của model mới **không tương thích** vector cũ (e5-large) dù cùng số chiều. Sau khi đổi backend/model:

- App là **session-based** → cách đơn giản nhất: **upload lại tài liệu** trong session mới (Qdrant filter theo `session_id`).
- Hoặc xóa hẳn collection để index sạch: dùng `scripts/migrate_to_postgres.py` / xóa collection `finsight_chunks` rồi nạp lại.
- Collection **không tự** recreate khi đổi model (dim + sparse-schema không đổi) → phải chủ động re-index.

## 7. Chi phí & giới hạn

- 1 file ~191k ký tự ≈ ~50k token → embedding cả 5 năm BCTC chỉ tốn vài cent; **chi phí không đáng kể**.
- HF Inference free tier có **rate-limit** + có thể **cold-start** (đã xử lý bằng retry/backoff + `wait_for_model`). Nếu cần ổn định/throughput cao cho production → trỏ `FINSIGHT_API_EMBED_ENDPOINT` sang **HF Inference Endpoint** riêng hoặc server **TEI** tự host (cùng shape JSON).
- Query thêm ~50–150ms round-trip/lần — nhỏ so với thời gian chờ LLM.

## 8. 🔐 Bảo mật token

- Token HF chỉ nằm trong `.env` (đã **git-ignored**) — **không** commit vào code.
- Quyền **Read** là đủ (chỉ để gọi inference + tải model public). Không cần Write/Fine-grained.
- Nếu token từng bị lộ (ví dụ dán ra ngoài), **revoke và tạo lại** tại https://huggingface.co/settings/tokens.

## 9. Trạng thái

| Hạng mục | Trạng thái |
| --- | --- |
| `ApiEmbedder` + switch backend | ✅ Code + test (`tests/test_rag.py`) |
| Smoke test HF API thật (1024-dim, sparse OK) | ✅ Pass |
| Mặc định `.env` đặt `BACKEND=api` | ✅ |
| Re-index tài liệu cũ | ⏳ Cần bạn upload lại / xóa collection |
