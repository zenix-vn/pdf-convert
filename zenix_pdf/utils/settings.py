"""Ghi nhớ tuỳ chọn người dùng giữa các lần mở app (QSettings)."""

from PySide6.QtCore import QSettings

from .. import APP_NAME, ORG_NAME


class AppSettings:
    def __init__(self):
        self._s = QSettings(ORG_NAME, APP_NAME)

    def _bool(self, key: str, default: bool) -> bool:
        v = self._s.value(key, default)
        return v in (True, "true", "1", 1)

    @property
    def use_custom_output(self) -> bool:
        return self._bool("output/custom", False)

    @use_custom_output.setter
    def use_custom_output(self, v: bool):
        self._s.setValue("output/custom", v)

    @property
    def output_dir(self) -> str:
        return str(self._s.value("output/dir", ""))

    @output_dir.setter
    def output_dir(self, v: str):
        self._s.setValue("output/dir", v)

    @property
    def last_open_dir(self) -> str:
        return str(self._s.value("input/last_dir", ""))

    @last_open_dir.setter
    def last_open_dir(self, v: str):
        self._s.setValue("input/last_dir", v)

    @property
    def overwrite(self) -> bool:
        return self._bool("options/overwrite", False)

    @overwrite.setter
    def overwrite(self, v: bool):
        self._s.setValue("options/overwrite", v)

    @property
    def multi_processing(self) -> bool:
        return self._bool("options/multi_processing", False)

    @multi_processing.setter
    def multi_processing(self, v: bool):
        self._s.setValue("options/multi_processing", v)

    @property
    def ocr(self) -> bool:
        return self._bool("options/ocr", True)

    @ocr.setter
    def ocr(self, v: bool):
        self._s.setValue("options/ocr", v)

    @property
    def geometry(self):
        return self._s.value("window/geometry")

    @geometry.setter
    def geometry(self, v):
        self._s.setValue("window/geometry", v)
