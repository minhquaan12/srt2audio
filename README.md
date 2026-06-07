# srt2audio — SRT → Audio qua CapCut TTS

Công cụ Python có giao diện (PySide6) đọc file phụ đề `.srt`, gọi **CapCut TTS**
(qua wrapper API [`kuwacom/CapCut-TTS`](https://github.com/kuwacom/CapCut-TTS))
để đọc từng đoạn, sau đó **ghép audio khớp đúng timeline** của file SRT. Đoạn nào
audio dài hơn thời lượng cho phép sẽ được **tăng tốc (giữ nguyên cao độ)** vừa đủ
khớp, nên khi ghép vào video sẽ trùng khớp thời gian.

## Tính năng

- Parse SRT mạnh mẽ (BOM, CRLF, nhiều dòng, encoding khác nhau).
- Client gọi CapCut TTS wrapper: **`/v2/synthesize`** (đăng nhập tài khoản, có
  danh sách giọng thật) mặc định, hoặc **`/v1/synthesize`** (legacy) — đều có retry.
- Khớp thời lượng: tăng tốc bằng `ffmpeg atempo`, có giới hạn tốc độ tối đa.
- Ghép theo timeline tuyệt đối (đặt mỗi đoạn đúng `start time`, chèn khoảng lặng).
- **Đa luồng 1–500** xử lý đồng thời, **luôn giữ đúng thứ tự** đoạn.
- Tiến trình, log, nút Hủy.
- Xuất `wav` / `mp3` / `m4a`.

## Kiến trúc

Tool này là **client**. Bạn cần tự chạy server [`kuwacom/CapCut-TTS`](https://github.com/kuwacom/CapCut-TTS)
rồi trỏ **Base URL** trong app tới server đó (mặc định `http://localhost:8080`).

Server hỗ trợ 2 luồng:

- **v2 (mặc định)** — đăng nhập bằng `CAPCUT_EMAIL` / `CAPCUT_PASSWORD`; app lấy
  được **danh sách giọng thật** qua `GET /v2/speakers` (bấm "Tải giọng từ server"
  hoặc "Kiểm tra kết nối" trong app). Audio trả về là MP3.
- **v1 (legacy)** — cần cấu hình `LEGACY_DEVICE_TIME` / `LEGACY_SIGN` trên server;
  chọn giọng theo `type`. Audio trả về là WAV.

```
SRT  ──parse──▶  [đoạn]  ──TTS (đa luồng)──▶  WAV/đoạn
                                   │
                          tăng tốc nếu quá dài (atempo)
                                   │
                     overlay theo start time  ──▶  audio khớp timeline  ──▶  xuất file
```

## Cài đặt

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Cần ffmpeg trong PATH (pydub dùng để xử lý audio).
#   Ubuntu: sudo apt-get install ffmpeg
```

## Chạy GUI

```bash
python -m srt2audio
```

## Chạy headless (CLI)

```bash
# v2 (giọng thật, chọn speaker id từ /v2/speakers)
python -m srt2audio --cli samples/sample.srt out.mp3 \
  --base-url http://localhost:8080 --api-version v2 \
  --speaker ICL_en_male_henry1 --workers 32 --format mp3

# v1 (legacy, theo type)
python -m srt2audio --cli samples/sample.srt out.wav \
  --base-url http://localhost:8080 --api-version v1 --voice 0 --workers 32
```

## Thử nhanh không cần CapCut (mock server)

```bash
python tools/mock_tts_server.py --port 8080      # cửa sổ 1
python -m srt2audio --cli samples/sample.srt out.wav --base-url http://localhost:8080  # cửa sổ 2
```

Mock server chỉ tạo tiếng tone có độ dài tỉ lệ với số ký tự để kiểm thử logic
khớp thời gian; **không** phải giọng đọc thật.

## Tham số chính

| Tham số | Ý nghĩa |
| --- | --- |
| API | `v2` (đăng nhập tài khoản, giọng thật) hoặc `v1` (legacy theo `type`) |
| Giọng | v2: speaker id thật (tải từ server); v1: `type` của CapCut |
| Pitch / Speed / Volume | tham số gửi thẳng cho API (0–20, mặc định 10) |
| Số luồng | số request đồng thời (1–500) |
| Tăng tốc tối đa | trần hệ số `atempo` để giọng không bị méo |
