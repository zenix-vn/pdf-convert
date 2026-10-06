# Zenix PDF Convert

Ứng dụng desktop chuyển PDF sang Word (DOCX): Python + [pdf2docx](https://github.com/ArtifexSoftware/pdf2docx) (PyMuPDF) + PySide6.

Tài liệu thiết kế: [doc.md](doc.md).

## Chạy từ mã nguồn

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python tools\fetch_tessdata.py   # dữ liệu OCR tiếng Việt (~12 MB), chỉ cần chạy một lần
python main.py
```

## PDF dạng ảnh (scan, ảnh chụp, chữ bị convert sang đường vector)

Trang không có lớp chữ dùng được sẽ tự động được nhận dạng chữ (OCR) trước khi chuyển sang DOCX:
ảnh scan/chụp, file xuất từ CorelDRAW/Illustrator với chữ đã "convert to curves", hoặc bản scan
chỉ có lớp chữ ẩn. Trang được dựng lại thành chữ thật (Times New Roman, giữ màu, chữ đậm),
đường kẻ bảng, dòng chấm "....." và ô "□" nên DOCX vẫn có bảng và sửa được chữ.

- Dùng Tesseract tích hợp trong PyMuPDF, không cần cài Tesseract; model `script/Vietnamese`
  (tessdata_best) đặt ở `zenix_pdf\resources\tessdata` (hoặc biến môi trường `ZENIX_TESSDATA`).
- Khoảng 5–10 giây/trang. Tắt bằng ô "Nhận dạng chữ (OCR)" trên giao diện hoặc `--no-ocr`.
- OCR không hoàn hảo (chữ nghiêng, chữ rất nhỏ, ký hiệu như ☆): nên soát lại sau khi chuyển.
- Gỡ lỗi: đặt `ZENIX_OCR_DEBUG=<thư mục>` để lưu ảnh đã làm sạch và ảnh ghép gửi cho Tesseract.

## Dòng lệnh

```powershell
python main.py --convert a.pdf b.pdf -o D:\Output -p "1-3, 5" --overwrite
python main.py --convert big.pdf --mp          # đa tiến trình (chỉ với khoảng trang liên tục)
python main.py --convert locked.pdf --password 123
python main.py --convert scan.pdf --no-ocr    # không nhận dạng chữ trang dạng ảnh
```

## Test

```powershell
python -m pytest
```

## Đóng gói .exe

```powershell
python tools\make_icon.py                 # tạo zenix_pdf\gui\resources\icon.ico (đã có sẵn)
python tools\fetch_tessdata.py            # bắt buộc: dữ liệu OCR được đóng gói kèm

# Bản thư mục (khởi động nhanh, ~255 MB, phải giữ kèm thư mục _internal)
pyinstaller --noconfirm zenix_pdf.spec
# -> dist\ZenixPdfConvert\ZenixPdfConvert.exe

# Bản 1 file duy nhất (~108 MB, tiện mang đi, khởi động chậm hơn vài giây)
pyinstaller --noconfirm zenix_pdf_onefile.spec
# -> dist\ZenixPdfConvert-portable.exe
```

Log ứng dụng: `%LOCALAPPDATA%\ZenixPdfConvert\logs\app.log`.
