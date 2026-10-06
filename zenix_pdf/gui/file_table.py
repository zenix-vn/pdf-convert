from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor

from ..core.models import ConvertJob, JobStatus

_STATUS_COLORS = {
    JobStatus.RUNNING: QColor("#1565c0"),
    JobStatus.DONE: QColor("#2e7d32"),
    JobStatus.FAILED: QColor("#c62828"),
    JobStatus.CANCELLED: QColor("#757575"),
}


class FileTableModel(QAbstractTableModel):
    HEADERS = ["Tên file", "Số trang", "Trạng thái", "Kết quả"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs: list[ConvertJob] = []

    # --- Qt model API ---
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.jobs)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        job = self.jobs[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return job.pdf_path.name
            if col == 1:
                return job.page_count
            if col == 2:
                return job.status.value
            if col == 3:
                if job.status == JobStatus.DONE and job.output_path:
                    return job.output_path.name
                if job.status == JobStatus.FAILED:
                    return job.error
                if job.is_scanned and job.status == JobStatus.PENDING:
                    return "Cảnh báo: PDF dạng ảnh (scan)"
                return ""
        if role == Qt.ToolTipRole:
            if col == 0:
                return str(job.pdf_path)
            if col == 3:
                if job.output_path and job.status == JobStatus.DONE:
                    return str(job.output_path)
                return job.error or None
        if role == Qt.ForegroundRole and col == 2:
            color = _STATUS_COLORS.get(job.status)
            return QBrush(color) if color else None
        if role == Qt.TextAlignmentRole and col == 1:
            return int(Qt.AlignCenter)
        return None

    # --- helpers ---
    def contains(self, path: Path) -> bool:
        p = Path(path).resolve()
        return any(j.pdf_path.resolve() == p for j in self.jobs)

    def add_job(self, job: ConvertJob):
        row = len(self.jobs)
        self.beginInsertRows(QModelIndex(), row, row)
        self.jobs.append(job)
        self.endInsertRows()

    def remove_rows(self, rows: list[int]):
        for row in sorted(set(rows), reverse=True):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self.jobs[row]
            self.endRemoveRows()

    def clear(self):
        self.beginResetModel()
        self.jobs.clear()
        self.endResetModel()

    def refresh_row(self, row: int):
        self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))

    def reset_statuses(self):
        for job in self.jobs:
            if job.status != JobStatus.PENDING:
                job.status = JobStatus.PENDING
                job.error = ""
                job.output_path = None
        if self.jobs:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self.jobs) - 1, self.columnCount() - 1)
            )
