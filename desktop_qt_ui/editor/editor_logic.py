import json
import os
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFileDialog

from services import get_config_service


class EditorLogic(QObject):
    """
    Handles the business logic for the editor view, including file list management.
    """
    file_list_changed = pyqtSignal(list)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.source_files: List[str] = []
        self.translated_files: List[str] = []
        self.translation_map_cache = {}
        self.config_service = get_config_service()

    # --- File Management Methods ---

    @pyqtSlot()
    def open_and_add_files(self):
        """Opens a file dialog to add files to the editor's list."""
        last_dir = self.config_service.get_config().app.last_open_dir
        file_paths, _ = QFileDialog.getOpenFileNames(
            None, 
            "添加文件到编辑器", 
            last_dir, 
            "Image Files (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if file_paths:
            self.add_files(file_paths)
            os.path.dirname(file_paths[0])
            # TODO: Find a way to save last_open_dir back to config service

    @pyqtSlot()
    def open_and_add_folder(self):
        """Opens a folder dialog to add all containing images to the list."""
        last_dir = self.config_service.get_config().app.last_open_dir
        folder_path = QFileDialog.getExistingDirectory(
            None,
            "添加文件夹到编辑器",
            last_dir
        )
        if folder_path:
            self.add_folder(folder_path)

    def add_files(self, files: List[str]):
        if not files:
            return
        new_files = [f for f in files if f not in self.source_files]
        if new_files:
            # 检查是否是第一次添加文件（列表为空）
            is_first_add = len(self.source_files) == 0

            self.source_files.extend(new_files)
            self.file_list_changed.emit(self.source_files)

            # 如果是第一次添加文件，自动加载第一个
            if is_first_add and len(new_files) > 0:
                self.load_image_into_editor(new_files[0])

    def add_folder(self, folder_path: str):
        if not folder_path or not os.path.isdir(folder_path):
            return
        
        image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
        try:
            files_in_folder = [
                os.path.join(folder_path, f) 
                for f in os.listdir(folder_path) 
                if os.path.splitext(f)[1].lower() in image_extensions
            ]
            self.add_files(files_in_folder)
        except OSError as e:
            print(f"Error reading folder {folder_path}: {e}")

    @pyqtSlot(str)
    def remove_file(self, file_path: str):
        """移除文件（可能是源文件或翻译后的文件）"""
        removed = False

        # 查找文件对（源文件和翻译文件）
        source_path, translated_path = self._find_file_pair(file_path)

        # 移除源文件
        if source_path and source_path in self.source_files:
            self.source_files.remove(source_path)
            removed = True

        # 移除翻译文件
        if translated_path and translated_path in self.translated_files:
            self.translated_files.remove(translated_path)
            removed = True

        # 如果没有找到文件对，尝试直接移除
        if not removed:
            if file_path in self.source_files:
                self.source_files.remove(file_path)
                removed = True
            if file_path in self.translated_files:
                self.translated_files.remove(file_path)
                removed = True

        if removed:
            # 重新发射文件列表（优先发射翻译文件列表）
            self.file_list_changed.emit(self.translated_files if self.translated_files else self.source_files)

            # 检查当前加载的图片是否是被移除的文件
            current_image_path = self.controller.model.get_source_image_path()
            if current_image_path and (current_image_path == file_path or current_image_path == source_path):
                # 清空编辑器
                self.controller._clear_editor_state()
                self.controller.model.set_image(None)

    @pyqtSlot()
    def clear_list(self):
        self.source_files.clear()
        self.translated_files.clear()
        # 清空列表时发射空列表
        self.file_list_changed.emit([])

    # --- Image Loading Methods ---

    def load_file_lists(self, source_files: List[str], translated_files: List[str]):
        """
        Receives the file lists from the coordinator to populate the editor.
        """
        self.source_files = source_files
        self.translated_files = translated_files
        self.translation_map_cache.clear() # Clear cache when lists change
        # 发射翻译后的文件列表，而不是源文件列表
        self.file_list_changed.emit(self.translated_files if self.translated_files else self.source_files)

    @pyqtSlot(str)
    def load_image_into_editor(self, file_path: str):
        """
        Loads a specific image into the editor view by finding its pair and calling the controller.
        如果是翻译后的图片，直接加载翻译后的图片（查看器模式）
        如果是源文件，加载源文件（编辑模式）
        """
        source_path, translated_path = self._find_file_pair(file_path)

        # 如果传入的是翻译后的文件（translated_path == file_path），直接加载翻译后的文件
        if translated_path and os.path.normpath(file_path) == os.path.normpath(translated_path):
            self.controller.load_image_and_regions(translated_path)
        elif source_path:
            self.controller.load_image_and_regions(source_path)
        else:
            # Fallback for safety
            self.controller.load_image_and_regions(file_path)

    def _find_file_pair(self, file_path: str) -> (str, Optional[str]):
        """Given a file path, find its source/translated pair using translation_map.json."""
        norm_path = os.path.normpath(file_path)

        # Case 1: The given file is a translated file (a key in a map)
        try:
            output_dir = os.path.dirname(norm_path)
            map_path = os.path.join(output_dir, 'translation_map.json')
            if os.path.exists(map_path):
                t_map = self.translation_map_cache.get(map_path)
                if t_map is None:
                    with open(map_path, 'r', encoding='utf-8') as f:
                        t_map = json.load(f)
                    self.translation_map_cache[map_path] = t_map
                
                if norm_path in t_map:
                    source = t_map[norm_path]
                    if os.path.exists(source):
                        return source, file_path
        except Exception: pass
        
        # Case 2: The given file is a source file (a value in a map)
        try:
            for trans_file in self.translated_files:
                if not trans_file: continue
                norm_trans = os.path.normpath(trans_file)
                output_dir = os.path.dirname(norm_trans)
                map_path = os.path.join(output_dir, 'translation_map.json')
                if os.path.exists(map_path):
                    t_map = self.translation_map_cache.get(map_path)
                    if t_map is None:
                        with open(map_path, 'r', encoding='utf-8') as f:
                            t_map = json.load(f)
                        self.translation_map_cache[map_path] = t_map

                    if t_map.get(norm_trans) == norm_path:
                        return file_path, trans_file
        except Exception: pass

        # Case 3: No pair found, it's a source file with no known translation.
        return file_path, None

    @pyqtSlot()
    def on_global_render_setting_changed(self):
        """Slot to handle changes in global render settings."""
        self.controller.handle_global_render_setting_change()