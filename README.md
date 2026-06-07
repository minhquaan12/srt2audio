# srt2audio — SRT → Audio qua CapCut TTS

Công cụ Python có giao diện (PySide6) đọc file phụ đề `.srt`, gọi **CapCut TTS**
(qua wrapper API [`kuwacom/CapCut-TTS`](https://github.com/kuwacom/CapCut-TTS))
để đọc từng đoạn, sau đó **ghép audio khớp đúng timeline** của file SRT. Đoạn nào
audio dài hơn thời lượng cho phép sẽ được **tăng tốc (giữ nguyên cao độ)** vừa đủ
khớp, nên khi ghép vào video sẽ trùng khớp thời gian.

## Tính năng

- Parse SRT mạnh mẽ (BOM, CRLF, nhiều dòng, encoding khác nhau).
- Client gọi CapCut TTS wrapper (`GET /v1/synthesize`), có retry.
- Khớp thời lượng: tăng tốc bằng `ffmpeg atempo`, có giới hạn tốc độ tối đa.
- Ghép theo timeline tuyệt đối (đặt mỗi đoạn đúng `start time`, chèn khoảng lặng).
- **Đa luồng 1–500** xử lý đồng thời, **luôn giữ đúng thứ tự** đoạn.
- Tiến trình, log, nút Hủy.
- Xuất `wav` / `mp3` / `m4a`.

## Kiến trúc

Tool này là **client**. Bạn cần tự chạy server [`kuwacom/CapCut-TTS`](https://github.com/kuwacom/CapCut-TTS)
(cấu hình `DEVICE_TIME` và `SIGN` lấy từ CapCut) rồi trỏ **Base URL** trong app tới
server đó (mặc định `http://localhost:8080`).

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
python -m srt2audio --cli samples/sample.srt out.wav --base-url http://localhost:8080 --workers 32
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
| Giọng | `type` của CapCut (xem danh sách trong app) |
| Pitch / Speed / Volume | tham số gửi thẳng cho API (0–20, mặc định 10) |
| Số luồng | số request đồng thời (1–500) |
| Tăng tốc tối đa | trần hệ số `atempo` để giọng không bị méo |
