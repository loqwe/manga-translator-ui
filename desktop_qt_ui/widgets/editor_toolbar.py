
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QToolButton,
    QWidget,
)


class EditorToolbar(QWidget):
    """
    编辑器顶部工具栏，包含返回、导出、撤销/重做、缩放、视图模式等全局操作。
    """
    # --- Define signals for all actions ---
    back_requested = pyqtSignal()
    export_requested = pyqtSignal()
    edit_file_requested = pyqtSignal()
    undo_requested = pyqtSignal()
    redo_requested = pyqtSignal()
    edit_geometry_requested = pyqtSignal(bool)
    zoom_in_requested = pyqtSignal()
    zoom_out_requested = pyqtSignal()
    fit_window_requested = pyqtSignal()
    display_mode_changed = pyqtSignal(str)
    original_image_alpha_changed = pyqtSignal(int)
    render_inpaint_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # --- File Actions ---
        self.back_button = QToolButton()
        self.back_button.setText("返回")
        self.back_button.setToolTip("返回主界面")
        layout.addWidget(self.back_button)

        self.export_button = QToolButton()
        self.export_button.setText("导出图片")
        self.export_button.setToolTip("导出当前渲染的图片")
        layout.addWidget(self.export_button)
        
        self.edit_file_button = QToolButton()
        self.edit_file_button.setText("编辑原图")
        self.edit_file_button.setToolTip("切换到当前翻译图的源文件进行编辑")
        layout.addWidget(self.edit_file_button)

        layout.addWidget(self._create_separator())

        # --- Edit Actions ---
        self.undo_button = QToolButton()
        self.undo_button.setText("撤销")
        self.undo_button.setEnabled(False)
        self.undo_button.setToolTip("撤销上一个操作")
        layout.addWidget(self.undo_button)

        self.redo_button = QToolButton()
        self.redo_button.setText("重做")
        self.redo_button.setEnabled(False)
        self.redo_button.setToolTip("重做上一个撤销的操作")
        layout.addWidget(self.redo_button)

        self.edit_geometry_button = QToolButton()
        self.edit_geometry_button.setText("编辑形状")
        self.edit_geometry_button.setToolTip("为选中的文本框增加新的关联形状")
        self.edit_geometry_button.setCheckable(True)
        layout.addWidget(self.edit_geometry_button)

        layout.addWidget(self._create_separator())

        # --- View Actions ---
        self.zoom_out_button = QToolButton()
        self.zoom_out_button.setText("缩小 (-)")
        layout.addWidget(self.zoom_out_button)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(50)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.zoom_label)

        self.zoom_in_button = QToolButton()
        self.zoom_in_button.setText("放大 (+)")
        layout.addWidget(self.zoom_in_button)

        self.fit_window_button = QToolButton()
        self.fit_window_button.setText("适应窗口")
        layout.addWidget(self.fit_window_button)
        
        layout.addWidget(self._create_separator())

        # --- Display Mode ---
        layout.addWidget(QLabel("显示模式:"))
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItems([
            "文字文本框显示",
            "只显示文字",
            "只显示框线",
            "都不显示"
        ])
        layout.addWidget(self.display_mode_combo)

        layout.addWidget(self._create_separator())

        # --- Inpaint Preview ---
        layout.addWidget(QLabel("修复预览:"))
        self.render_inpaint_button = QToolButton()
        self.render_inpaint_button.setText("生成预览")
        layout.addWidget(self.render_inpaint_button)

        layout.addWidget(QLabel("原图不透明度:"))
        self.original_image_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.original_image_alpha_slider.setRange(0, 100)
        self.original_image_alpha_slider.setValue(0) # Default to 0 (fully transparent, show inpainted)
        self.original_image_alpha_slider.setFixedWidth(100)
        layout.addWidget(self.original_image_alpha_slider)

        layout.addStretch() # Pushes everything to the left

    def _create_separator(self):
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        return separator

    def _connect_signals(self):
        self.back_button.clicked.connect(self.back_requested)
        self.export_button.clicked.connect(self.export_requested)
        self.edit_file_button.clicked.connect(self.edit_file_requested)
        self.undo_button.clicked.connect(self.undo_requested)
        self.redo_button.clicked.connect(self.redo_requested)
        self.edit_geometry_button.toggled.connect(self.edit_geometry_requested)
        self.zoom_in_button.clicked.connect(self.zoom_in_requested)
        self.zoom_out_button.clicked.connect(self.zoom_out_requested)
        self.fit_window_button.clicked.connect(self.fit_window_requested)
        self.display_mode_combo.currentTextChanged.connect(self.display_mode_changed)
        self.original_image_alpha_slider.valueChanged.connect(self.original_image_alpha_changed)
        self.render_inpaint_button.clicked.connect(self.render_inpaint_requested)

    # --- Public Slots ---
    def update_undo_redo_state(self, can_undo: bool, can_redo: bool):
        self.undo_button.setEnabled(can_undo)
        self.redo_button.setEnabled(can_redo)

    def set_original_image_alpha_slider(self, alpha: float):
        """同步滑块值（alpha: 0.0-1.0）"""
        # 转换：alpha 0.0 = slider 0（完全透明），alpha 1.0 = slider 100（完全不透明）
        slider_value = int(alpha * 100)
        self.original_image_alpha_slider.blockSignals(True)
        self.original_image_alpha_slider.setValue(slider_value)
        self.original_image_alpha_slider.blockSignals(False)
        # 强制更新UI
        self.undo_button.update()
        self.redo_button.update()

    def update_zoom_level(self, zoom_level: float):
        self.zoom_label.setText(f"{zoom_level:.0%}")
