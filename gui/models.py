from PyQt6.QtCore import QAbstractListModel, QSize, QThreadPool, QModelIndex, Qt
from PyQt6.QtGui import QColor

from core import ImageLoader

class PhotoModel(QAbstractListModel):
    def __init__(self, db_manager, icon_size=None):
        super().__init__()
        self.db = db_manager
        self.file_list = []
        self.image_cache = {}
        self.icon_size = icon_size if icon_size else QSize(180, 180)
        self.thread_pool = QThreadPool()

    def reload(self):
        self.beginResetModel()
        self.file_list = self.db.get_all_files()
        self.image_cache.clear()
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self.file_list = []
        self.image_cache = {}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.file_list)

    def data(self, index, role):
        if not index.isValid(): return None
        row = index.row()
        if role == Qt.ItemDataRole.DecorationRole:
            if row in self.image_cache:
                return self.image_cache[row]
            else:
                self.load_image_async(row)
                return QColor("#2b2b2b")
        if role == Qt.ItemDataRole.ToolTipRole: return self.file_list[row]
        return None

    def load_image_async(self, row):
        if row in self.image_cache: return
        loader = ImageLoader(row, self.file_list[row], self.icon_size)
        loader.signals.finished.connect(self.on_loaded)
        self.thread_pool.start(loader)

    def on_loaded(self, row, image):
        if row >= len(self.file_list): return
        self.image_cache[row] = image
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])
