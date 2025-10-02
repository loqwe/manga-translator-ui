
"""
编辑器历史管理器
支持撤销/重做操作，使用命令模式。
"""
import logging
from typing import Any, List, Optional

# Import the new Command base class
from editor.commands import Command


class EditorHistory:
    """编辑器历史管理器，存储可执行的命令对象。"""
    
    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self.history: List[Command] = []
        self.current_index = -1
        self.logger = logging.getLogger(__name__)

    def add_command(self, command: Command):
        """添加一个新执行的命令到历史记录中。"""
        # 如果当前不在历史记录的末尾（即已经执行过撤销），
        # 则丢弃当前索引之后的所有“可重做”记录。
        if self.current_index < len(self.history) - 1:
            self.history = self.history[:self.current_index + 1]
        
        self.history.append(command)
        self.current_index += 1
        
        # 保持历史记录不超过最大长度
        if len(self.history) > self.max_history:
            self.history.pop(0)
            self.current_index -= 1
        
        self.logger.debug(f"Command executed and added to history: {command.description}")
    
    def can_undo(self) -> bool:
        return self.current_index >= 0
    
    def can_redo(self) -> bool:
        return self.current_index < len(self.history) - 1
    
    def undo(self) -> Optional[Command]:
        """获取用于撤销的命令。"""
        if not self.can_undo():
            return None
        command = self.history[self.current_index]
        self.current_index -= 1
        self.logger.info(f"Preparing to undo command: {command.description} (current_index now: {self.current_index})")
        return command
    
    def redo(self) -> Optional[Command]:
        """获取用于重做的命令。"""
        if not self.can_redo():
            return None
        self.current_index += 1
        action = self.history[self.current_index]
        self.logger.debug(f"Preparing to redo command: {action.description}")
        return action

    def clear(self):
        self.history.clear()
        self.current_index = -1
        self.logger.debug("Cleared command history")

class EditorStateManager:
    """编辑器状态管理器，使用命令模式处理操作。"""
    
    def __init__(self):
        self.history = EditorHistory()
        self.clipboard_data = None
        self.logger = logging.getLogger(__name__)
        
    def execute_command(self, command: Command):
        """执行一个命令，并将其添加到历史记录中。"""
        if command is None:
            return
        command.execute()
        self.history.add_command(command)

    def undo(self):
        """撤销上一个操作。"""
        command = self.history.undo()
        if command:
            command.undo()
            return command # Return for controller to know what was undone
    
    def redo(self):
        """重做上一个被撤销的操作。"""
        command = self.history.redo()
        if command:
            command.execute()
            return command # Return for controller to know what was redone
    
    def can_undo(self) -> bool:
        return self.history.can_undo()
    
    def can_redo(self) -> bool:
        return self.history.can_redo()
    
    def copy_to_clipboard(self, data: Any):
        import copy
        self.clipboard_data = copy.deepcopy(data)
        self.logger.debug("Data copied to internal clipboard")
    
    def paste_from_clipboard(self) -> Any:
        import copy
        if self.clipboard_data is not None:
            return copy.deepcopy(self.clipboard_data)
        return None
    
    def clear(self):
        """清除历史记录。"""
        self.history.clear()
        self.logger.debug("Cleared editor state manager history")
    
    @property
    def undo_stack_size(self) -> int:
        """获取撤销栈的大小，用于检查是否有未保存的修改。"""
        return self.history.current_index + 1

# --- Singleton Pattern ---
_history_service_instance: Optional[EditorStateManager] = None

def get_history_service() -> EditorStateManager:
    """获取历史记录服务的单例。"""
    global _history_service_instance
    if _history_service_instance is None:
        _history_service_instance = EditorStateManager()
    return _history_service_instance

