# Translate Service — thiết kế chức năng

> **Phạm vi tài liệu này:** CHỈ `translate-service` (workbench dịch + biến thể
> thích ứng cho audio/video). Không mô tả crawl/TTS/video chi tiết.
>
> **Đối tượng đọc:** agent / người implement khi mất context chat.
> Cập nhật khi đổi quyết định sản phẩm — đây là nguồn sự thật chức năng.
>
> **Liên quan:** crawl handoff mô tả ở [crawl-service.md](./crawl-service.md);
> toàn cảnh microservice (nếu có) xem `microservices-architecture.md`.

**Trạng thái:** Phase 0 + Phase 1 MVP + **P1+** (glossary, review, estimate/budget, resume, FE tab) + **fork-from-full** (P3 cost rule) + **multi-AI pool + fallback chain** + **rolling context + auto-glossary** + **gate chất lượng handoff (B2)** **đã code**. Ngày cập nhật: 2026-09-23.

Quyết định vận hành hiện tại:
- **`Job.ai_provider_id`**: lưu AI provider (registry) job được tạo từ, nếu có. Resume/retry **không kèm override** sẽ re-resolve credential mới nhất từ registry (không kẹt ở snapshot lúc tạo job) — tránh trường hợp user sửa key sai trong Settings rồi bấm "Dịch lại" vẫn dùng key cũ. Override tay (PATCH/resume kèm field cụ thể) sẽ gỡ liên kết này (`ai_provider_id=None`) — từ đó job không tự refresh theo registry nữa, đúng ý định ghi đè thủ công.
- `lang_tgt` mặc định: **vi**
- Provider mặc định: **mock** (dev/test); production: OpenAI-compatible 1 endpoint
- **Gate chất lượng handoff (B2)**: `Work.missing_cleaned`/`Work.unreviewed_chapters` lưu số liệu crawl-service gửi kèm mỗi lần `POST /works/from-crawl` (payload đã có sẵn 2 field `missing_cleaned`/`unreviewed`, trước đây bị router bỏ qua). **Chỉ cảnh báo trên UI** (Work overview + badge trong thư viện), **không tự chặn dịch** — crawl-service đã có `require_cleaned` riêng của nó trước khi gọi handoff, translate-service chặn thêm lần nữa sẽ vô hiệu hoá lựa chọn "gửi cả chương chưa mượt" của user bên crawl.
- **AI local đã verify chạy thật (bug đã fix)**: `OpenAICompatTranslator` từng luôn gửi header `Authorization: Bearer ` (rỗng) kể cả khi không có api_key — httpx từ chối gửi (`Illegal header value`, trailing whitespace) nên **mọi request tới AI local từng fail 100%** dù logic registry đã đúng. Giờ chỉ gắn header khi có api_key thật; có bộ test dựng HTTP server thật (`tests/test_local_ai_real_http.py`, không mock) xác nhận 1 AI local và pool 2 AI local chạy đúng.
- **Giới hạn tổng số request đồng thời toàn hệ thống**: `MAX_CONCURRENT_TRANSLATE_CALLS` (semaphore toàn cục, mặc định 8) chặn cả khi nhiều job dùng **khác** AI — bổ sung cho giãn cách theo từng key ở dưới (2 lớp: theo key, rồi theo tổng toàn hệ thống). Bỏ qua khi mock.
- **Estimate phân biệt theo mode**: `audio_cut` chạy thêm 1 pass `must_keep_beats` (spec 4.3) nên tốn hơn `full`/`pov`/`style_clone` — `estimate_tokens` cũ dùng chung 1 công thức cho mọi mode, giờ cộng thêm `estimate_beats_pass_tokens` khi mode là `audio_cut`. `GET /works/{id}/estimate` nhận query `?mode=` (modal "Bắt đầu dịch" tự refetch estimate mỗi khi đổi mode).
- **Nhiều AI chia nhau dịch 1 job (pool)**: modal "Bắt đầu dịch" cho tick nhiều AI (không chỉ 1) — `ai_provider_ids` (>=2) thay `ai_provider_id`. Segment chia round-robin theo thứ tự chương cho từng AI (bảng `job_provider_slots`, snapshot như Job — không FK registry). `run_job()` spawn 1 thread/AI (mỗi thread tự mở Session riêng, không share giữa các thread), join xong mới tổng kết chung; cancel/pause dùng chung cờ `job.status` nên áp dụng "miễn phí" cho mọi thread. Pool job **không hỗ trợ** đổi AI giữa chừng (PATCH/resume kèm override provider bị từ chối — xóa job, tạo lại nếu muốn đổi).
- **(Đã gỡ) "1 AI nhiều model"**: từng thêm `AiProvider.models: list[str]` cho phép 1 tài khoản/key mang nhiều model nhỏ — đã xác nhận thật qua debug Gemini rằng đổi TÊN model trên CÙNG 1 key vẫn dính chung 1 hạn mức tài khoản (không giải quyết được rate-limit), và không phải pattern các tool tương tự (AiNiee/Glossarion) dùng, nên gỡ bỏ hoàn toàn trước khi release — xem mục "Nhiều API key/1 AI" bên dưới, đây mới là hướng đúng.
- **Tự động chia nhỏ chương quá to (`_translate_chunk`/`_translate_once` trong `OpenAICompatTranslator`)**: phát hiện qua debug thật — 1 chương 12k+ ký tự vượt hạn mức token/phút CỨNG theo từng request (vd Groq free tier OTPM/TPM) — lỗi này KHÔNG transient, đổi model nào trong fallback cũng fail y hệt vì bản thân request đã quá to, không phải model hỏng. Tham khảo AiNiee (đã tra kỹ trước khi làm): họ thử gửi cả cụm trước, chỉ chia nhỏ khi lỗi ("auto-shrink on failure", không phải ngưỡng tĩnh đặt sẵn), và luôn tôn trọng ranh giới file/chương (xác nhận qua kiến trúc reader theo từng file + output 1:1 theo file, dù không tìm thấy dòng doc nào nói thẳng). Áp dụng đúng kiểu đó: `translate()` giờ là wrapper gọi `_translate_chunk(depth=0)` — thử `_translate_once(text)` (logic gốc, đổi tên) nguyên cụm trước; bắt lỗi qua `_looks_too_large()` (nhận diện các cụm từ chuẩn: "request too large", "reduce your message size", "reduce max_tokens", "context_length_exceeded" — khác hẳn 429/5xx tạm thời `_chat()` đã tự retry sẵn); nếu khớp và còn đủ dài (`_MIN_SPLITTABLE_CHARS=500`) và chưa quá sâu (`_MAX_SPLIT_DEPTH=4`, tối đa 16 mảnh) thì `_split_in_half()` theo ranh giới đoạn văn (`\n\n`, sa xuống `\n`), đệ quy dịch từng nửa (nửa sau nhận đuôi nửa trước làm `prior_context` cục bộ), ghép lại bằng `\n\n`. Không bao giờ cắt/gộp qua CHƯƠNG KHÁC — toàn bộ nằm trong 1 lần gọi `translate()` của đúng 1 segment, vô hình với segment/cache/export/pool/fallback phía trên (vẫn nhận đúng 1 kết quả dịch cho chương đó, không cần đổi gì ở `run_job.py`). Test: `tests/test_chunk_oversized_chapter.py` (auto-split + ghép đúng thứ tự, đệ quy khi 1 nửa vẫn quá to, và xác nhận lỗi KHÁC — vd model không tồn tại — không kích hoạt chia nhỏ).
- **Nhiều API key/1 AI, xoay vòng CÙNG model đã chọn trên job (`AiProvider.api_keys` + `AiSelectionIn.model`)**: Settings lưu keys + model *mặc định*; lúc start job FE gửi `ai_selections: [{ai_provider_id, model?, use_all_keys?}]` — `model` override chỉ snapshot vào job/slot (không ghi Settings). Resume trơn giữ `job.model`, chỉ refresh key/url từ registry.
- **Fix `_call_with_shared_pacing` giữ khoá suốt lúc AI tự retry, triệt tiêu song song thật của pool**: khoá theo `(base_url, api_key)` trước đây giữ SUỐT thời gian `call()` chạy (kể cả internal retry ~vài phút khi gặp lỗi tạm thời, vd Gemini 503 "high demand") — nếu nhiều slot chia sẻ CÙNG 1 identity (vd nhiều key của 1 AI, tính năng multi-key), 1 slot đang retry khoá đứng toàn bộ slot khác, biến pool thành tuần tự trên thực tế (phát hiện trực tiếp qua debug job Gemini thật của user — đứng im 0/39 nhiều phút dù mạng thông). Giờ khoá chỉ giữ đủ lâu để giãn cách ĐIỂM BẮT ĐẦU (ghi `_identity_last_call` rồi nhả ngay), không giữ suốt lúc gọi thật — các slot cùng identity vẫn có thể chạy CHỒNG LẤN nhau (chỉ điểm bắt đầu cách nhau `MIN_CALL_INTERVAL`). Test: `test_slow_call_does_not_block_next_same_identity_call_from_starting` trong `test_shared_pacing.py` (verify 2 chiều — tắt fix đi thấy fail).
- **Fix `_run_fallback_chain_segments` kẹt vĩnh viễn ở slot chết sau khi 1 chương exhaust hết cả dãy**: trước đây `current_idx` KHÔNG reset sau khi 1 segment fail hết mọi slot (best-effort exhaustion) — biến này persist qua vòng lặp `for seg in segments`, nên chương kế bắt đầu ngay ở slot vừa fail (thường là model chết hẳn cuối danh sách), không bao giờ quay lại slot đầu dãy dù chúng vẫn hoạt động tốt (verify bằng cách gọi trực tiếp API thật của user). Giờ chỉ "định cư" (giữ `current_idx`) khi có 1 slot dịch THÀNH CÔNG thật; exhaust hoàn toàn thì reset `current_idx = 0` cho chương kế — cho cả dãy 1 cơ hội công bằng lại từ đầu. Test: `tests/test_fallback_resets_after_full_exhaustion.py` (verify cả 2 chiều — tắt fix đi thì test phải fail).
- **Tóm tắt "trạng thái truyện" xuyên suốt cả sách (`Segment.story_state`, tuỳ chọn qua `mode_params.track_story_state`)**: lớp trí nhớ DÀI HẠN, khác `prior_context`/rolling context (chỉ đuôi chương ngay trước) — sau mỗi chương dịch xong, `translator.summarize_state(previous_state, new_chapter_text)` (lệnh gọi phụ, chỉ khi bật cờ) tóm tắt lại quan hệ nhân vật/tình tiết chưa giải quyết, gộp với `story_state` của chương ngay trước (đọc qua `_story_state_tail()`, tương tự `_prior_context_tail()`), lưu vào chính segment đó. Chương kế đọc lại field này của chương trước (bất kể slot/model nào dịch chương đó) — best-effort giống rolling context: pool chạy song song không đảm bảo chương trước đã xong, khi đó coi như state rỗng, không chặn job. Mặc định TẮT (tốn thêm 1 lệnh gọi AI/chương); `normalize_mode_params()` giờ cho cờ này sống sót qua MỌI mode kể cả `full` (trước đây `full` luôn trả `{}` cứng). Test: `tests/test_story_state.py`.
- **Glossary tự động giờ "trộn vào" (merge), không còn "tất cả hoặc không gì"**: `_auto_seed_glossary_pre_translate`/`_auto_extract_glossary_if_empty` trước đây `if glossary_repo.list_by_work(...): return` — chỉ cần Work có ≥1 mục (kể cả tự tay thêm) là bỏ qua trích hoàn toàn. Giờ luôn thử trích, dùng tập `existing_lower` (source_term đã có, không phân biệt hoa/thường) để chỉ bỏ qua đúng mục trùng, không huỷ toàn bộ.
- **Glossary trích TRƯỚC khi dịch (`_auto_seed_glossary_pre_translate`)**: khác `_auto_extract_glossary_if_empty` (chạy SAU khi job full xong, cần cặp nguồn+bản dịch mẫu) — hàm này chạy NGAY trước khi `run_job()` spawn pool/fallback/single (chỉ variant `full`, Work chưa có glossary nào, job dùng AI thật), lấy mẫu vài chương nguồn (chưa cần bản dịch), yêu cầu model đề xuất `{source_term, target_term}` nhất quán rồi lưu thẳng. Sửa đúng gap: trước đây job full đầu tiên của 1 Work dịch SUỐT với glossary rỗng (pool nhiều model chia chương thì mỗi model tự đặt tên nhân vật khác nhau ngay từ đầu) — giờ mọi chương của CHÍNH job đang chạy đều thấy chung 1 glossary từ chương 1, bất kể slot/model nào xử lý.
- **Chuẩn hoá format giữa nhiều model + fix segment "done" rỗng**: `OpenAICompatTranslator._chat()` giờ coi `content` rỗng từ model (hay gặp ở reasoning model như qwen3, deepseek-r1-distill — cắt cụt giữa lúc "suy nghĩ") là lỗi tạm thời, tự retry — không bao giờ trả rỗng để tránh segment bị đánh dấu DONE mà không có bản dịch thật. `translate()` không còn nhét `"Title: X"` vào USER message (từng khiến vài model echo lại thành `"Tiêu đề: X"` hoặc tự bọc markdown khác nhau) — tên chương giờ chỉ nằm trong system prompt làm ngữ cảnh, kèm chỉ dẫn rõ "output chỉ có nội dung dịch, không markdown, không tự đặt heading".
- **Rolling context (giữ mạch truyện qua nhiều AI)**: `pov`/`audio_cut` (mode "nâng cao", đã fork-from-full) giờ nhận thêm `prior_context` — đuôi ~700 ký tự (`_CONTEXT_TAIL_CHARS`, `run_job.py`) của chương NGAY TRƯỚC (đã adapt xong, cùng job) — `_prior_context_tail()` đọc segment chương trước qua `SegmentRepository.get_by_job_and_chapter()`, best-effort (chương trước FAILED/chưa DONE, hoặc do AI khác xử lý trong fallback/pool → trả rỗng, không chặn). Đưa vào `OpenAICompatTranslator.translate()` qua `build_prior_context_block()` (`modes.py`), chèn vào system prompt trước glossary. Không áp dụng cho `full`/`style_clone` (rủi ro thấp hơn, giữ chi phí thấp). Tham khảo: AiNiee (previous_text_list) và Glossarion (rolling history window) đều dùng đúng kiểu context này, và đều VẪN cho chạy song song nhiều AI/key (không coi lệch style giữa model là vấn đề phải khoá cứng tuần tự) — nên translate-service cũng không cấm pool/fallback dùng rolling context, chỉ chấp nhận thiếu context khi race (giống 2 repo trên).
- **Auto-glossary (không bắt user gõ tay)**: sau khi 1 job `full` COMPLETED sạch (0 lỗi) và `Work` **chưa có glossary nào** (không đè lựa chọn tay), `_auto_extract_glossary_if_empty()` lấy tối đa 3 chương đầu (cả nguồn lẫn bản dịch, ≤6000 ký tự) làm mẫu, gọi 1 lệnh LLM phụ (`build_glossary_extraction_prompt()`) yêu cầu xuất JSON `[{source_term, target_term}]`, parse rồi lưu thẳng vào glossary (`notes="Tự động trích xuất"`, không `protected`, user vẫn sửa/xoá được sau). Chỉ chạy khi `job.provider == "openai"` (mock không trích được gì thật); mọi lỗi (parse JSON hỏng, request lỗi...) bị nuốt lặng lẽ — không làm fail job. Tham khảo Glossarion (tự trích glossary từ bản dịch đã xong).
- **AI dự phòng tuần tự (fallback chain)**: cùng chọn ≥2 AI như pool, nhưng modal "Bắt đầu dịch" cho chọn `ai_mode: "fallback"` thay vì `"pool"` (mặc định vẫn là `"pool"` khi không gửi `ai_mode`, giữ backward-compat). Khác pool ở chỗ **không chạy song song** — mọi segment bắt đầu ở slot 0 (AI ưu tiên cao nhất); AI hiện tại lỗi (bất kỳ exception nào, không riêng 429) thì `_run_fallback_chain_segments()` (`run_job.py`) tự thử lại **ngay** đúng segment đó bằng AI kế tiếp trong danh sách (rebuild translator + cache_key theo model mới), rồi **"định cư"** ở AI đó cho mọi segment còn lại (không quay lại AI đã lỗi). Chỉ khi thử hết cả danh sách cho 1 segment mới đánh dấu FAILED thật (áp dụng backoff 15s nếu lỗi giống rate-limit). `JobOut.current_slot_index` cho biết đang chạy AI nào (Job Detail bôi xanh AI đang active); fallback job cũng **không hỗ trợ** đổi AI giữa chừng, giống pool. Test: `tests/test_fallback_chain.py` (dựng 2 HTTP server thật — 1 luôn lỗi 400, 1 luôn OK — xác nhận job tự chuyển AI và "định cư" đúng AI dự phòng).
- **Giãn cách dùng chung theo (base_url, api_key)** (`_call_with_shared_pacing` trong `run_job.py`): 2 job/thread bất kỳ (khác Work, khác Variant, kể cả job thường lẫn slot trong pool) trỏ tới **cùng 1 AI thật** sẽ tự khoá + cách nhau tối thiểu `MIN_CALL_INTERVAL` (3s) thay vì bắn song song không kiểm soát và cùng vượt rate-limit thật của nhà cung cấp. Bỏ qua hoàn toàn khi `provider == "mock"`. Khoá là in-process (`threading.Lock` theo dict toàn cục, key = `(base_url, api_key)`) — chỉ hiệu lực trong 1 tiến trình translate-service, không phối hợp giữa nhiều instance/replica nếu scale-out sau này.
- **Fork-from-full** (mục 4.3): `pov`/`audio_cut`/`style_clone` luôn dịch từ output của variant `full` (không đụng ChapterSource) — `source_variant_id` tự gắn khi tạo variant; start job trên variant con khi `full` chưa xong sẽ bị từ chối (400) và tự kích hoạt `full`, rồi tự chạy tiếp (auto-chain) khi `full` hoàn tất. `audio_cut` chạy 2 pass thật (must_keep_beats rồi mới condense).
- **AI provider registry** (`/api/translate/ai-providers`, bảng `ai_providers`): user lưu **nhiều** kết nối AI (kể cả AI local như Ollama/LM Studio — `requires_api_key=false`, không cần key), chọn theo từng job qua `ai_provider_id`; thay cho model "1 provider active" cũ. `Job`/`JobModel` snapshot lại provider/model/base_url/api_key/`requires_api_key` tại thời điểm start/resume/patch — registry không phải FK, sửa/xóa registry không ảnh hưởng job cũ.
- FE Translate: **có** (`/translate`) — library, modal "Bắt đầu dịch" (chọn AI + full/tóm tắt, tạo variant+job trong 1 bước), Work overview (variant+job list: xóa/tạm dừng/dịch lại), Job Detail riêng (`/translate/:workId/jobs/:jobId`, review + đổi AI giữa job), glossary, settings (registry AI + budget)
- Job pause: **không phải status mới** — `pause_job()`/`POST /jobs/{id}/pause` dùng lại đúng cơ chế `cancel_job` (CANCELLED, resumable qua `resume_job`), chỉ đổi message hiển thị. Xem mục 4.4.
- Crawl CTA **Gửi sang dịch** + callback `translating` / `ready_for_video`: **có** — FE crawl gọi handoff với `start_job: false` (mặc định mới), **không** tự chạy job; landing trên `/translate/:workId` sẽ tự mở modal "Bắt đầu dịch" để user chọn AI/mode trước. Backend `send_to_translate(start_job=True)` vẫn giữ để tương thích, chỉ không còn là default phía FE.
- EPUB import và export bản dịch: **có**. Polish opt-in (`mode_params.polish`, mặc định tắt): **có**. TTS là service riêng (`tts-service`). Video: chưa.

---

## 0. Một câu định vị

**Translate-service là owner của “sách cần dịch / biến thể nội dung”.**  
Đứng **một mình** (user import file) **và** nhận **handoff** từ crawl.  
Crawl **không** chứa bản dịch; TTS/video **không** gọi LLM dịch — chỉ nhận
export từ đây.

Hai lớp sản phẩm trong **cùng một service**:

| Lớp | Tên | Vai trò |
|---|---|---|
| **A** | Workbench | Parity desk dịch EPUB/TXT hiện có trên thị trường |
| **B** | Pipeline / Variants | USP: chế độ full / đổi ngôi / rút audio / clone văn phong + nối crawl |

---

## 1. Mục tiêu sản phẩm

1. User **không cần crawl** vẫn import TXT/EPUB/ZIP (và Excel nếu cần) → dịch → review → export.
2. User **có crawl** bấm “Gửi sang dịch” (hoặc rule auto) → Work tạo từ cleaned chapters.
3. Trên **một Work nguồn**, tạo được **nhiều Variant** (bản con) với mode khác nhau — phục vụ A/B audio-video, không chỉ “một bản dịch”.
4. Chi phí kiểm soát được: cache segment, budget, estimate trước chạy, model rẻ mặc định, polish/QA **opt-in**.

**Không thuộc phạm vi translate-service:** quét site, anti-bot, TTS, ghép video, auth multi-tenant SaaS (phase sau).

---

## 2. Tham khảo hệ có sẵn — lấy gì / không lấy gì

Đã đối chiếu (2026-09): BookForge, BookLLM, epublate, wenyi, trans-epub,
Jade Scroll / epub-translator, Paperford, AI-Book-Translator, audiobook-revamper,
Manuscripts.ai (POV), AI_epub_edits.

| Pattern thị trường | Quyết định của mình |
|---|---|
| Import file → Project/Work → queue → segment → provider → cache → export | **Bắt buộc** (lớp A) |
| OpenAI-compatible 1 adapter (DeepSeek/Qwen/OpenRouter/Ollama) | **Bắt buộc** |
| Checkpoint/resume theo segment + SQLite (hoặc tương đương) | **Bắt buộc** |
| Glossary + term protected | **Bắt buộc** |
| Style / tone preset trên **một** lần chạy | Có (lớp A); **mở rộng** thành clone Variant (lớp B) |
| Review/polish multi-pass mặc định | **Opt-in** (BookLLM cảnh báo cost) |
| POV rewrite / abridge-for-audio như **mode sản phẩm** | Thị trường làm **rời**; mình gói thành **Adaptation Mode** (USP) |
| Share DB với crawler | **Cấm** — chỉ API/event + payload |
| RAG/HNSW tái dùng câu (NovelTrans) | **Không** phase 1–2 |
| OCR PDF | **Không** phase đầu (crawl đã có text) |

---

## 3. Sơ đồ chức năng tổng thể

```
                    ┌──────────────────────────────────────────┐
                    │           translate-service              │
                    │                                          │
  Upload TXT/EPUB/  │   Work (nguồn sạch, 1 lần)               │
  ZIP/XLSX ────────►│      │                                   │
                    │      ├── Variant: full                   │
  Crawl handoff ───►│      ├── Variant: pov                    │
  (chapters+fp)     │      ├── Variant: audio_cut              │
                    │      └── Variant: style_clone            │
                    │             │                            │
                    │             ▼                            │
                    │   Job → Segments → LLM provider          │
                    │   Cache / Glossary / Budget               │
                    │             │                            │
                    │             ▼                            │
                    │   Review UI → Export TXT/EPUB/JSON        │
                    │             │                            │
                    └─────────────┼────────────────────────────┘
                                  │
                    callback (opt) ┼──► crawl lifecycle hint
                                  └──► TTS/video (sau)
```

**Luồng A — Import độc lập**

```
User upload → parse → Work(source=upload)
  → (optional) tạo Variant ngay với mode chọn
  → Job chạy → Review → Export
```

**Luồng B — Pipeline crawl**

```
Crawl: fully_crawled + cleaned (+ ideally reviewed)
  → POST /works/from-crawl
  → Work(source=crawl_handoff, external_id=crawl:novel:{id})
  → User chọn mode(s) qua modal "Bắt đầu dịch"
  → Job(s) → callback translating / ready_for_video
```

---

## 4. Domain model (chức năng)

### 4.1 Thực thể

| Entity | Ý nghĩa |
|---|---|
| **Work** | 1 cuốn nguồn đã chuẩn hóa (title, author, lang_src, chapters nguồn). Không phải “bản dịch”. |
| **ChapterSource** | 1 chương nguồn: `index`, `title`, `text`, `content_fingerprint` (sha256). |
| **Variant** | 1 bản xuất phát từ Work: mode + params (POV, style, target_minutes…). Có lifecycle riêng. |
| **TranslateJob** | 1 lần chạy trên 1 Variant (provider, model, prompt_version, cost, status). |
| **Segment** | Đơn vị dịch/cache/retry trong Job (không bắt LLM sửa EPUB). |
| **GlossaryTerm** | Term gắn Work (và optionally series); `protected=true` thì không bị auto ghi đè. |
| **StyleProfile** | JSON preset văn phong (tái dùng cho `style_clone` và refine). |
| **ExportArtifact** | File/blob kết quả (txt/epub/json) gắn Variant. |

### 4.2 Nguồn Work (`source_type`)

- `upload` — user import
- `crawl_handoff` — từ crawl-service
- `api` — push từ tool khác (cùng schema handoff)

### 4.3 Adaptation Mode (USP — lớp B)

Mỗi **Variant** có đúng 1 `mode`:

| Mode | Mục tiêu | Input thực tế | Pass LLM |
|---|---|---|---|
| `full` | Dịch trung thành đủ chương | ChapterSource | 1-pass dịch (+ polish opt-in) |
| `pov` | Đổi ngôi kể (1 ↔ 3 limited / omniscient…) | Output của variant `full` cùng Work/lang_tgt | 1-pass rewrite POV — input đã là bản dịch nên tự động **tách pass** khỏi "dịch", không cần đặc cách |
| `audio_cut` | Rút ngắn giữ beat — cho TTS/shorts | Output của variant `full` cùng Work/lang_tgt | **2 pass**: (1) trích `must_keep_beats` (outline) (2) condense theo phút/ký tự mục tiêu, bắt buộc giữ đủ beats |
| `style_clone` | Clone văn phong khác (web-novel VN, cinematic…) | Output của variant `full` cùng Work/lang_tgt | 1-pass rewrite style theo StyleProfile |

**Quy tắc chi phí (đã code):** `pov`/`audio_cut`/`style_clone` **bắt buộc** fork từ output `full` — `Variant.source_variant_id` gắn tự động khi tạo (`create_variant`/`clone_variant` tự tìm-hoặc-tạo variant `full` cùng lang_tgt). Nếu `full` chưa dịch xong sạch (0 segment lỗi): `enqueue_job` trên variant con **từ chối** (400) và tự khởi động job `full` thay vì dịch lại từ nguồn; khi `full` hoàn tất, `run_job()` tự start mọi variant con đang chờ (`_start_pending_forks`) — không cần user bấm lại. Không còn fallback "nguồn nếu cùng ngôn ngữ đích" — luôn fork, kể cả lang_src==lang_tgt, để logic đơn giản và nhất quán.

**Quy tắc chất lượng POV:** chỉ đổi narration; giữ nguyên lời thoại; input đã là bản dịch nên không có nguy cơ gộp "dịch+đổi ngôi" nữa (đã tách pass tự nhiên bằng kiến trúc fork).

**Quy tắc audio_cut (đã code):** `OpenAICompatTranslator` chạy 2 lệnh gọi thật — pass 1 trích outline `MUST-KEEP BEATS` (twist, reveal, chi tiết chương sau cần), pass 2 condense với outline đó chèn vào prompt, yêu cầu giữ đủ beat kể cả khi phải hy sinh độ ngắn.

### 4.4 Lifecycle

**Work**

`draft → ready → archived`  
(`ready` = đã có ChapterSource hợp lệ để tạo Variant)

**Variant**

`pending → queued → running → needs_review → ready → failed / cancelled`

**Segment / Job**

Job: `queued → running → cancelled → completed | failed | cancelled`
Segment: `pending → done | failed | skipped_cache`

Không có status `paused` riêng trong `JobStatus` — "Tạm dừng" (`pause_job`) và "Dừng"
(`cancel_job`) cùng chuyển job về `cancelled` (cơ chế worker-loop dừng giữa segment giống
hệt nhau, cùng resumable qua `resume_job` — vốn đã không phân biệt lý do dừng, chỉ chặn
khi job đang `running`). Hai verb chỉ khác `job.error` message hiển thị cho user; tách
thành 2 status thật sẽ chỉ thêm thuật ngữ chứ không thêm hành vi mới.

### 4.5 Cache key (bắt buộc đủ chặt)

```
hash(
  source_text,
  mode,
  mode_params,          # pov target, style_profile_id, target_minutes…
  lang_src, lang_tgt,
  model,
  prompt_version,
  glossary_hash
)
```

Đổi glossary protected / prompt_version → cache miss có chủ đích.

`lang_src` trong hash là **lang_src hiệu lực** (`_effective_lang_src()`), không
phải luôn `work.lang_src`: variant fork từ `full` dùng `lang_tgt` làm lang_src
hiệu lực (input đã là bản dịch) — tách cache khỏi các lần chạy `full` gốc.

---

## 5. Chức năng lớp A — Workbench (parity)

Checklist sản phẩm tối thiểu để “không thua desk hiện có”:

| # | Chức năng | Ghi chú |
|---|---|---|
| A1 | Library Works | List, search, filter status/source, cost tổng |
| A2 | Import | TXT, EPUB, ZIP thư mục chương; (XLSX optional) |
| A3 | Parse & segment | Prose-only; EPUB structure do app giữ |
| A4 | Job control | Start / pause / resume / retry fail / concurrency |
| A5 | Estimate & budget | Ước token/$ trước chạy; cap theo Work/Variant; dừng hoặc hỏi |
| A6 | Provider settings | Registry nhiều AI đã lưu (`/ai-providers`, gồm AI local không cần key), chọn theo job qua `ai_provider_id` |
| A7 | Glossary | Auto-scan đề xuất; CRUD; protected lock |
| A8 | Review | So sánh nguồn ↔ output theo chương; sửa tay; duyệt |
| A9 | Stages opt-in | Polish / QA pass — **tắt mặc định** |
| A10 | Export | TXT, EPUB, JSON segments (TTS-ready shape) |
| A11 | Cost meter | Token/cost theo Job và Variant |

---

## 6. Chức năng lớp B — Pipeline & Variants (USP)

| # | Chức năng | Ghi chú |
|---|---|---|
| B1 | Handoff từ crawl | `POST /works/from-crawl` — idempotent theo `external_id` |
| B2 | Gate chất lượng | Đã code — chỉ cảnh báo (`missing_cleaned`/`unreviewed_chapters` trên Work), không block; block đã có sẵn phía crawl-service (`require_cleaned`) trước khi gọi handoff |
| B3 | Fingerprint sync | Crawl gửi lại chapter đổi → chỉ re-run segment đổi |
| B4 | Tạo Variant | UI: chọn mode + params; “Clone từ Variant X” |
| B5 | Multi-variant song song | Nhiều Job cùng Work; cost tách |
| B6 | Callback | Webhook/status cho crawl: `translating` / `ready_for_video` / `failed` |
| B7 | Hàng đợi vận hành | Inbox: đang chạy / cần review / sẵn export (tương tự “Hôm nay” crawl) |

*(Đã bỏ "Preset farm" — tạo sẵn bộ Variant (vd full+audio_cut) theo kịch bản cố định. Modal "Bắt đầu dịch" đã cho chọn AI + mode/params trực tiếp mỗi lần tạo, khiến preset chỉ còn tiết kiệm đúng 1 thao tác tạo thêm variant thứ 2 — không đủ giá trị để giữ code riêng.)*

### 6.1 Handoff payload (tối thiểu)

```json
{
  "external_id": "crawl:novel:123",
  "title": "...",
  "author": "...",
  "lang_src": "zh",
  "lang_tgt_hint": "vi",
  "chapters": [
    {
      "index": 1,
      "title": "...",
      "text": "...",
      "fingerprint": "sha256:...",
      "has_cleaned": true,
      "reviewed": true
    }
  ],
  "callback_url": "http://crawl-service/.../optional"
}
```

Idempotent: cùng `external_id` + fingerprints không đổi → không tạo Work trùng; chapter fingerprint đổi → cập nhật ChapterSource + invalidate segment liên quan.

### 6.2 Params mode (gợi ý)

**pov**

```json
{ "target_pov": "first_person", "viewpoint_character": "optional name" }
```

**audio_cut**

```json
{ "target_minutes": 10, "max_chars": 12000, "keep_dialogue_ratio": 0.7 }
```

**style_clone**

```json
{ "style_profile_id": "web_novel_vn_shorts" }
```

---

## 7. API bề mặt (chức năng — chưa chốt path chi tiết)

| Nhóm | Ví dụ |
|---|---|
| Works | `POST /works/import`, `POST /works/from-crawl`, `GET /works`, `GET /works/{id}` |
| Glossary | `GET/POST /works/{id}/glossary`, lock term |
| Variants | `POST /works/{id}/variants`, `GET ...`, `POST .../clone` |
| Jobs | `POST /variants/{id}/jobs`, pause/resume/retry, `GET` progress |
| Review | `GET/PUT` chapter output |
| Export | `POST /variants/{id}/export?format=txt\|epub\|json` |
| Settings | AI provider registry, budget defaults |
| Ops | `GET /inbox/today` |

Worker: **không** chạy LLM trong request HTTP dài — enqueue job, poll/SSE progress.

---

## 8. UI chức năng (màn hình)

1. **Inbox / Hôm nay** — jobs chạy, cần review, sẵn export
2. **Library Works** — mọi nguồn (upload + crawl)
3. **Work overview** (`/translate/:workId`) — chapters nguồn, glossary, danh sách
   Variant + job mới nhất của từng variant (xóa / tạm dừng / dịch lại / clone), nút
   “Dịch mới” mở modal Bắt đầu dịch
4. **Modal “Bắt đầu dịch”** — tick 1 **hoặc nhiều** AI đã lưu (registry; ≥2 = pool
   chia nhau dịch) + Dịch đầy đủ / Dịch tóm tắt (mode `audio_cut` gắn nhãn lại; mục
   Nâng cao mở full/pov/audio_cut/style_clone) → tạo Variant (nếu chưa có) + start
   Job trong 1 bước; tự mở lần đầu khi Work chưa có job nào, sau đó luôn mở lại
   được qua nút “Dịch mới”
5. **Job Detail** (`/translate/:workId/jobs/:jobId`) — progress, review từng segment,
   export, tạm dừng/tiếp tục/xóa, “Đổi AI” (thủ công — user chọn AI khác trong registry
   khi AI hiện tại hết quota, áp dụng ngay nếu job đang chạy hoặc khi bấm Tiếp tục)
6. **Import wizard** — kéo thả file
7. **Settings** — registry AI (nhiều kết nối, kể cả AI local), budget
8. (Crawl FE) — CTA “Gửi sang dịch” gọi handoff; không embed DB dịch

---

## 9. Chi phí & vận hành

- Default model: rẻ (DeepSeek / Qwen-MT / Gemini Flash… — cấu hình được).  
- Escalation model chỉ khi QA fail hoặc user chọn “chất lượng cao”.  
- Concurrency bounded + rate limit (học trans-epub) — **đã code**: giãn cách theo từng `(base_url, api_key)` + semaphore toàn cục `MAX_CONCURRENT_TRANSLATE_CALLS` (mục "Quyết định vận hành" ở đầu tài liệu).  
- Estimate trước Start; budget hard-cap.  
- Cache hit hiện rõ trên UI (tiết kiệm cảm nhận được).  
- Không bật polish/QA hàng loạt cho các variant tóm tắt/shorts trừ khi user chọn.

---

## 10. Ranh giới với crawl / TTS

| | Crawl | Translate | TTS (sau) |
|---|---|---|---|
| Sở hữu | Novel raw/cleaned | Work / Variant / bản dịch | Audio files |
| Gọi LLM dịch | Không | Có | Không |
| Giao tiếp | Handoff + callback | Export JSON/TXT | Đọc artifact |

Crawl lifecycle gợi ý (không bắt translate phụ thuộc enum crawl): sau handoff có thể nhận callback để FE crawl hiện `translating` / `ready_for_video`.

---

## 11. Phase triển khai (chức năng)

| Phase | Deliverable | Xong khi | Status |
|---|---|---|---|
| **P0** | Crawl `GET .../translate-handoff` + Work import TXT + Job `full` + mock/openai + export TXT | Dịch được 1 cuốn upload E2E | **done** (2026-09-22) |
| **P1** | Glossary + review UI + budget/estimate + resume + FE tab | Parity desk cơ bản | **done** (2026-09-22) |
| **P2** | Handoff crawl UI + gate + callback lifecycle | Nối pipeline farm | **done** (2026-09-22) |
| **P3** | Variants: `pov`, `audio_cut`, `style_clone` + clone UI | USP audio/video | **done** (2026-09-22) |
| **P4** | Fingerprint sync, export JSON TTS-ready, Inbox | Vận hành hàng ngày | **done** (2026-09-22) |
| **P5** | Polish opt-in, EPUB import/export, EPUB song ngữ đã có | Parity cao cấp | một phần |

---

## 12. Non-goals (giai đoạn hiện tại)

- Share SQLite/Postgres với crawl-service  
- Multi-tenant billing / auth phức tạp  
- OCR PDF / scan sách giấy  
- Agent 3 lớp Orchestrator–Translator–Reviewer mặc định (đắt)  
- Tự đăng Shorts/TikTok  
- Dịch “ngầm” trong crawl-service

---

## 13. Quyết định đã chốt (để agent sau khỏi hỏi lại)

1. **Một service** chứa cả workbench (A) và variants pipeline (B).  
2. **Work = nguồn; Variant = bản sản phẩm** — không ghi đè nguồn khi đổi mode.  
3. **Mode tách pass; bắt buộc fork từ `full`** (đã code) — variant con không có
   đường nào dịch thẳng từ nguồn nữa; `enqueue_job` chặn cứng nếu `full` chưa xong.  
4. **Import độc lập bắt buộc** — không khóa user vào crawl.  
5. **Handoff contract** là biên giới duy nhất với crawl.
6. Tài liệu này là spec chức năng; schema SQL / OpenAPI viết khi scaffold.
7. **AI provider registry thay cho "1 provider active"** — user lưu nhiều kết nối
   (kể cả AI local, `requires_api_key=false`), chọn theo `ai_provider_id` mỗi lần
   start/resume/patch job; Job vẫn tự snapshot config của nó, không FK vào registry.
8. **"Tạm dừng" không phải status job mới** — dùng lại máy trạng thái `cancelled`/
   `resume_job` sẵn có, chỉ khác message hiển thị. "Dịch tóm tắt" ở FE cũng không phải
   mode mới — là nhãn khác của `audio_cut` đã có.

---

## 14. Cấu trúc thư mục (đã code)

Job chạy trong thread của process API (`run_job`), không có worker queue riêng.

```
translate-service/
  src/translate/
    domain/
    application/     # import, from-crawl, run_job, export, variants
    infrastructure/  # sqlite, openai-compatible, parser txt
    api/
  tests/
  README.md
```

Stack: FastAPI + SQLite + OpenAI-compatible client. Deploy độc lập như `crawl-service/`.

---

*Hết tài liệu chức năng translate-service. Khi implement, cập nhật mục 11/13 và link OpenAPI thật.*
