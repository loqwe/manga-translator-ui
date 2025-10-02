from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_logic_minimal import AppLogic


class MainWindow(QMainWindow):
    """
    应用主窗口，继承自 QMainWindow。
    最小化版本用于测试基本功能。
    """
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Manga Translator (Qt Refactor) - Minimal")
        self.resize(1280, 800) # 设置默认窗口大小

        self._setup_logic_and_models()
        self._setup_ui()
        self._connect_signals()

    def _setup_logic_and_models(self):
        """实例化所有逻辑和数据模型"""
        self.app_logic = AppLogic()

    def _setup_ui(self):
        """初始化UI组件"""
        # --- 菜单栏 ---
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&文件")
        self.add_files_action = QAction("&添加文件...", self)
        file_menu.addAction(self.add_files_action)

        edit_menu = menu_bar.addMenu("&编辑")
        self.undo_action = QAction("&撤销", self)
        self.redo_action = QAction("&重做", self)
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)

        # --- 中心布局 ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)

        # 临时的简单视图
        self.status_label = QLabel("准备就绪 - 这是最小化测试版本")
        self.layout.addWidget(self.status_label)

        self.test_button = QPushButton("测试按钮")
        self.layout.addWidget(self.test_button)

    def _connect_signals(self):
        """连接信号与槽"""
        self.add_files_action.triggered.connect(self._trigger_add_files)
        self.undo_action.triggered.connect(self._test_action)
        self.redo_action.triggered.connect(self._test_action)
        self.test_button.clicked.connect(self._test_action)
        # Connect AppLogic signals to UI slots
        self.app_logic.files_added.connect(self._on_files_added)

    def _trigger_add_files(self):
        """触发添加文件对话框"""
        file_paths, _ = QFileDialog.getOpenFileNames(self, "添加文件", "", "Image Files (*.png *.jpg *.jpeg *.bmp *.webp)")
        if file_paths:
            self.app_logic.add_files(file_paths)

    def _test_action(self):
        """测试动作"""
        print("Test action triggered")
        self.status_label.setText("测试动作已执行")

    def _on_files_added(self, files):
        """文件添加后的回调"""
        self.status_label.setText(f"已添加 {len(files)} 个文件")

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        print("Shutting down...")
        self.app_logic.shutdown()
        event.accept()