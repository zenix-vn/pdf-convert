# Zenix PDF Convert

Ứng dụng desktop chuyển PDF sang Word (DOCX): Python + [pdf2docx](https://github.com/ArtifexSoftware/pdf2docx) (PyMuPDF) + PySide6.

Tài liệu thiết kế: [doc.md](doc.md).

## Chạy từ mã nguồn

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python main.py
```

## Dòng lệnh

```powershell
python main.py --convert a.pdf b.pdf -o D:\Output -p "1-3, 5" --overwrite
python main.py --convert big.pdf --mp          # đa tiến trình (chỉ với khoảng trang liên tục)
python main.py --convert locked.pdf --password 123
```

## Test

```powershell
python -m pytest
```

## Đóng gói .exe

```powershell
python tools\make_icon.py                 # tạo zenix_pdf\gui\resources\icon.ico (đã có sẵn)

# Bản thư mục (khởi động nhanh, ~255 MB, phải giữ kèm thư mục _internal)
pyinstaller --noconfirm zenix_pdf.spec
# -> dist\ZenixPdfConvert\ZenixPdfConvert.exe

# Bản 1 file duy nhất (~108 MB, tiện mang đi, khởi động chậm hơn vài giây)
pyinstaller --noconfirm zenix_pdf_onefile.spec
# -> dist\ZenixPdfConvert-portable.exe
```

Log ứng dụng: `%LOCALAPPDATA%\ZenixPdfConvert\logs\app.log`.
