#!/usr/bin/env python3
"""
简单测试撤回功能
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget

from editor.commands import UpdateRegionCommand
from services.history_service import get_history_service


class MockModel:
    def __init__(self):
        self._regions = [{"text": "原始文本", "lines": [[0, 0], [100, 0], [100, 50], [0, 50]]}]
        
    def get_region_by_index(self, index):
        if 0 <= index < len(self._regions):
            return self._regions[index].copy()
        return None

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("撤回功能测试")
        self.setGeometry(100, 100, 400, 300)
        
        # 创建模拟模型
        self.model = MockModel()
        # 创建一个简单的信号模拟
        class MockSignal:
            def emit(self, *args):
                print(f"Signal emitted with args: {args}")
        self.model.region_style_updated = MockSignal()
        
        # 获取历史服务
        self.history_service = get_history_service()
        
        # 创建UI
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建按钮
        self.add_command_btn = QPushButton("添加命令到历史")
        self.undo_btn = QPushButton("撤回")
        self.redo_btn = QPushButton("重做")
        self.check_history_btn = QPushButton("检查历史")
        
        layout.addWidget(self.add_command_btn)
        layout.addWidget(self.undo_btn)
        layout.addWidget(self.redo_btn)
        layout.addWidget(self.check_history_btn)
        
        # 连接信号
        self.add_command_btn.clicked.connect(self.add_test_command)
        self.undo_btn.clicked.connect(self.test_undo)
        self.redo_btn.clicked.connect(self.test_redo)
        self.check_history_btn.clicked.connect(self.check_history)
        
        self.update_buttons()
    
    def add_test_command(self):
        print("添加测试命令...")
        old_data = {"text": "原始文本", "lines": [[0, 0], [100, 0], [100, 50], [0, 50]]}
        new_data = {"text": "修改后文本", "lines": [[0, 0], [100, 0], [100, 50], [0, 50]]}
        
        command = UpdateRegionCommand(
            model=self.model,
            region_index=0,
            old_data=old_data,
            new_data=new_data,
            description="测试命令"
        )
        
        self.history_service.execute_command(command)
        print(f"命令已添加，历史大小: {len(self.history_service.history.history)}")
        self.update_buttons()
    
    def test_undo(self):
        print("测试撤回...")
        command = self.history_service.undo()
        if command:
            print(f"撤回命令: {command.description}")
            command.undo()
        else:
            print("没有可撤回的命令")
        self.update_buttons()
    
    def test_redo(self):
        print("测试重做...")
        command = self.history_service.redo()
        if command:
            print(f"重做命令: {command.description}")
            command.execute()
        else:
            print("没有可重做的命令")
        self.update_buttons()
    
    def check_history(self):
        history = self.history_service.history
        print("历史记录状态:")
        print(f"  总数: {len(history.history)}")
        print(f"  当前索引: {history.current_index}")
        print(f"  可撤回: {self.history_service.can_undo()}")
        print(f"  可重做: {self.history_service.can_redo()}")
        for i, cmd in enumerate(history.history):
            marker = " <-- 当前" if i == history.current_index else ""
            print(f"  [{i}] {cmd.description}{marker}")
    
    def update_buttons(self):
        self.undo_btn.setEnabled(self.history_service.can_undo())
        self.redo_btn.setEnabled(self.history_service.can_redo())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())