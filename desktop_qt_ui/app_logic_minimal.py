"""
最小化的应用业务逻辑层 - 用于测试UI功能
"""
from PyQt6.QtCore import QObject, pyqtSignal


class AppLogic(QObject):
    """最小化的应用业务逻辑控制器"""
    files_added = pyqtSignal(list)
    files_cleared = pyqtSignal()
    config_loaded = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        print("AppLogic (minimal) initialized")

    def add_files(self, file_paths):
        """添加文件 - 最小实现"""
        print(f"Adding files: {file_paths}")
        self.files_added.emit(file_paths)
        return len(file_paths)

    def shutdown(self):
        """关闭应用 - 最小实现"""
        print("AppLogic shutdown")