import os

from PIL import Image
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QWidget,
)


class FileListItemWidget(QWidget):
    """自定义列表项，用于显示缩略图、文件名和移除按钮"""
    remove_requested = pyqtSignal(str)

    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(10)

        # Thumbnail
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(40, 40)
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.thumbnail_label)

        if os.path.isdir(self.file_path):
            style = QApplication.style()
            icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
            self.thumbnail_label.setPixmap(icon.pixmap(QSize(40,40)))
        else:
            self._load_thumbnail()

        # File Name
        self.name_label = QLabel(os.path.basename(file_path))
        self.name_label.setWordWrap(True)
        self.layout.addWidget(self.name_label, 1) # Stretch factor

        # Remove Button
        self.remove_button = QPushButton("✕")
        self.remove_button.setFixedSize(20, 20)
        self.remove_button.clicked.connect(self._emit_remove_request)
        self.layout.addWidget(self.remove_button)

    def _load_thumbnail(self):
        try:
            img = Image.open(self.file_path)
            img.thumbnail((40, 40))
            
            # Convert PIL image to QPixmap
            if img.mode == 'RGB':
                q_img = QImage(img.tobytes(), img.width, img.height, img.width * 3, QImage.Format.Format_RGB888)
            elif img.mode == 'RGBA':
                q_img = QImage(img.tobytes(), img.width, img.height, img.width * 4, QImage.Format.Format_RGBA8888)
            else: # Fallback for other modes like L, P, etc.
                img = img.convert('RGBA')
                q_img = QImage(img.tobytes(), img.width, img.height, img.width * 4, QImage.Format.Format_RGBA8888)

            pixmap = QPixmap.fromImage(q_img)
            self.thumbnail_label.setPixmap(pixmap)
        except Exception as e:
            self.thumbnail_label.setText("ERR")
            print(f"Error loading thumbnail for {self.file_path}: {e}")

    def _emit_remove_request(self):
        self.remove_requested.emit(self.file_path)

    def get_path(self):
        return self.file_path

class FileListView(QListWidget):
    """显示文件列表的自定义控件"""
    file_remove_requested = pyqtSignal(str)
    file_selected = pyqtSignal(str)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model # Although not used yet, good for future state management
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self):
        selected_items = self.selectedItems()
        if not selected_items:
            return
        
        list_item = selected_items[0]
        file_path = list_item.data(Qt.ItemDataRole.UserRole)
        if file_path:
            self.file_selected.emit(file_path)

    def add_files(self, file_paths):
        """Slot to add multiple files to the list."""
        for path in file_paths:
            item = QListWidgetItem(self)
            item_widget = FileListItemWidget(path)
            
            # Store path in the item itself for easy access
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setSizeHint(item_widget.sizeHint())
            
            self.addItem(item)
            self.setItemWidget(item, item_widget)
            item_widget.remove_requested.connect(self.file_remove_requested.emit)

    def remove_file(self, file_path):
        """Slot to remove a file from the list."""
        for i in range(self.count()):
            item = self.item(i)
            path_in_item = item.data(Qt.ItemDataRole.UserRole)
            if path_in_item == file_path:
                self.takeItem(i)
                break

    def clear(self):
        """Slot to clear all items from the list."""
        super().clear()