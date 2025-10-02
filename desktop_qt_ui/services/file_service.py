"""
文件服务层
处理文件和文件夹的选择、验证、拖拽等操作
"""
import base64
import json
import logging
import mimetypes
import os
import shutil
import sys
from typing import List, Optional, Set, Tuple

import cv2
import numpy as np

# 添加项目根目录到路径以便导入path_manager
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from manga_translator.utils.path_manager import find_json_path, find_inpainted_path


class FileService:
    """文件操作服务"""
    
    def __init__(self):
        from services import get_config_service
        self.logger = logging.getLogger(__name__)
        self.config_service = get_config_service()
        # 支持的图片格式
        self.supported_image_extensions = {
            '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif'
        }
        # 支持的配置文件格式
        self.supported_config_extensions = {
            '.json', '.yaml', '.yml', '.toml'
        }

    def load_translation_json(self, image_path: str) -> Tuple[List[dict], Optional[np.ndarray], Optional[Tuple[int, int]]]:
        """
        根据给定的图片路径，加载关联的 _translations.json 文件。
        优先从新目录结构加载，支持向后兼容。
        返回 regions, raw_mask, 和 original_size。
        """
        # 使用path_manager查找JSON文件（新位置优先）
        json_path = find_json_path(image_path)
        regions = []
        raw_mask = None
        original_size = None

        if not json_path:
            self.logger.warning(f"JSON file not found for {os.path.basename(image_path)}")
            return regions, raw_mask, original_size

        self.logger.info(f"Loading JSON from: {json_path}")

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            image_key = os.path.abspath(image_path)
            
            if image_key not in data:
                if data:
                    first_key = next(iter(data))
                    self.logger.warning(f"Exact image path '{image_key}' not found in JSON. Using first available key '{first_key}'.")
                    image_data = data[first_key]
                else:
                    image_data = {}
            else:
                image_data = data[image_key]

            regions = image_data.get('regions', [])

            config = self.config_service.get_config()
            default_target_lang = config.translator.target_lang if config else None

            if default_target_lang:
                for region in regions:
                    if not region.get('target_lang'):
                        region['target_lang'] = default_target_lang

            mask_data = image_data.get('mask_raw')
            if isinstance(mask_data, str):
                try:
                    img_bytes = base64.b64decode(mask_data)
                    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
                    raw_mask = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)
                except Exception as e:
                    self.logger.error(f"Failed to decode base64 mask in {os.path.basename(json_path)}: {e}")
                    raw_mask = None
            elif isinstance(mask_data, list):
                raw_mask = np.array(mask_data, dtype=np.uint8)
            
            original_size = (image_data.get('original_width'), image_data.get('original_height'))

            self.logger.info(f"Loaded {len(regions)} regions from {os.path.basename(json_path)}")

        except Exception as e:
            self.logger.error(f"Failed to load or parse JSON file {json_path}: {e}")
            return [], None, None

        return regions, raw_mask, original_size
        
    def validate_image_file(self, file_path: str) -> bool:
        """验证是否为有效的图片文件"""
        try:
            if not os.path.exists(file_path):
                return False
                
            # 检查文件扩展名
            _, ext = os.path.splitext(file_path)
            if ext.lower() not in self.supported_image_extensions:
                return False
                
            # 检查MIME类型
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type and not mime_type.startswith('image/'):
                return False
                
            # 检查文件是否可读
            if not os.access(file_path, os.R_OK):
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"验证图片文件失败 {file_path}: {e}")
            return False
    
    def validate_config_file(self, file_path: str) -> bool:
        """验证是否为有效的配置文件"""
        try:
            if not os.path.exists(file_path):
                return False
                
            _, ext = os.path.splitext(file_path)
            return ext.lower() in self.supported_config_extensions
            
        except Exception as e:
            self.logger.error(f"验证配置文件失败 {file_path}: {e}")
            return False
    
    def get_image_files_from_folder(self, folder_path: str, recursive: bool = False) -> List[str]:
        """从文件夹获取所有图片文件，忽略manga_translator_work目录"""
        image_files = []

        try:
            if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
                return image_files

            if recursive:
                # 递归搜索，忽略manga_translator_work目录
                for root, dirs, files in os.walk(folder_path):
                    # 移除manga_translator_work目录，避免遍历
                    if 'manga_translator_work' in dirs:
                        dirs.remove('manga_translator_work')

                    for file in files:
                        file_path = os.path.join(root, file)
                        if self.validate_image_file(file_path):
                            image_files.append(file_path)
            else:
                # 只搜索当前目录，忽略manga_translator_work目录
                for file in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, file)
                    if os.path.isfile(file_path) and self.validate_image_file(file_path):
                        image_files.append(file_path)

            # 按文件名排序
            image_files.sort(key=lambda x: os.path.basename(x).lower())

        except Exception as e:
            self.logger.error(f"获取文件夹图片失败 {folder_path}: {e}")
            
        return image_files
    
    def filter_valid_image_files(self, file_paths: List[str]) -> List[str]:
        """过滤出有效的图片文件"""
        valid_files = []
        
        for file_path in file_paths:
            if self.validate_image_file(file_path):
                valid_files.append(file_path)
            else:
                self.logger.warning(f"跳过无效文件: {file_path}")
                
        return valid_files
    
    def process_dropped_files(self, dropped_data: str) -> Tuple[List[str], List[str]]:
        """处理拖拽的文件数据
        
        Returns:
            Tuple[List[str], List[str]]: (有效的图片文件列表, 错误信息列表)
        """
        image_files = []
        errors = []
        
        try:
            # 解析拖拽数据
            file_paths = self._parse_drop_data(dropped_data)
            
            for file_path in file_paths:
                if os.path.isfile(file_path):
                    if self.validate_image_file(file_path):
                        image_files.append(file_path)
                    else:
                        errors.append(f"不支持的图片格式: {os.path.basename(file_path)}")
                        
                elif os.path.isdir(file_path):
                    # 处理文件夹
                    folder_images = self.get_image_files_from_folder(file_path)
                    if folder_images:
                        image_files.extend(folder_images)
                    else:
                        errors.append(f"文件夹中没有找到图片: {os.path.basename(file_path)}")
                else:
                    errors.append(f"文件不存在: {os.path.basename(file_path)}")
                    
        except Exception as e:
            self.logger.error(f"处理拖拽文件失败: {e}")
            errors.append(f"处理拖拽文件时出错: {str(e)}")
            
        return image_files, errors
    
    def _parse_drop_data(self, dropped_data: str) -> List[str]:
        """解析拖拽数据，提取文件路径"""
        file_paths = []
        
        # 处理不同操作系统的换行符
        lines = dropped_data.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        
        for line in lines:
            line = line.strip()
            if line:
                # 移除可能的URI前缀
                if line.startswith('file:///'):
                    line = line[8:]  # 移除 'file:///'
                elif line.startswith('file://'):
                    line = line[7:]  # 移除 'file://'
                
                # URL解码
                try:
                    import urllib.parse
                    line = urllib.parse.unquote(line)
                except Exception:
                    pass
                
                if os.path.exists(line):
                    file_paths.append(os.path.abspath(line))
                    
        return file_paths
    
    def get_file_info(self, file_path: str) -> dict:
        """获取文件信息"""
        try:
            if not os.path.exists(file_path):
                return {'error': '文件不存在'}
                
            stat = os.stat(file_path)
            file_info = {
                'name': os.path.basename(file_path),
                'path': os.path.abspath(file_path),
                'size': stat.st_size,
                'size_human': self._format_file_size(stat.st_size),
                'modified': stat.st_mtime,
                'is_readable': os.access(file_path, os.R_OK),
                'is_writable': os.access(file_path, os.W_OK)
            }
            
            if self.validate_image_file(file_path):
                file_info['type'] = 'image'
                # 获取图片尺寸
                try:
                    from PIL import Image
                    with Image.open(file_path) as img:
                        file_info['width'] = img.width
                        file_info['height'] = img.height
                        file_info['format'] = img.format
                except Exception as e:
                    self.logger.warning(f"获取图片信息失败 {file_path}: {e}")
                    
            return file_info
            
        except Exception as e:
            self.logger.error(f"获取文件信息失败 {file_path}: {e}")
            return {'error': str(e)}
    
    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024**2:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024**3:
            return f"{size_bytes/(1024**2):.1f} MB"
        else:
            return f"{size_bytes/(1024**3):.1f} GB"
    
    def create_backup(self, file_path: str, backup_dir: Optional[str] = None) -> str:
        """创建文件备份"""
        try:
            if backup_dir is None:
                backup_dir = os.path.join(os.path.dirname(file_path), 'backups')
                
            os.makedirs(backup_dir, exist_ok=True)
            
            # 生成备份文件名
            import time
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            name, ext = os.path.splitext(os.path.basename(file_path))
            backup_name = f"{name}_{timestamp}{ext}"
            backup_path = os.path.join(backup_dir, backup_name)
            
            # 复制文件
            shutil.copy2(file_path, backup_path)
            self.logger.info(f"创建备份: {backup_path}")
            
            return backup_path
            
        except Exception as e:
            self.logger.error(f"创建备份失败 {file_path}: {e}")
            raise
    
    def cleanup_temp_files(self, temp_dir: str, max_age_hours: int = 24) -> None:
        """清理临时文件"""
        try:
            if not os.path.exists(temp_dir):
                return
                
            import time
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        if current_time - os.path.getmtime(file_path) > max_age_seconds:
                            os.remove(file_path)
                            self.logger.info(f"删除过期临时文件: {file_path}")
                    except Exception as e:
                        self.logger.warning(f"删除临时文件失败 {file_path}: {e}")
                        
        except Exception as e:
            self.logger.error(f"清理临时文件失败: {e}")
    
    def get_supported_image_extensions(self) -> Set[str]:
        """获取支持的图片文件扩展名"""
        return self.supported_image_extensions.copy()
    
    def get_supported_config_extensions(self) -> Set[str]:
        """获取支持的配置文件扩展名"""
        return self.supported_config_extensions.copy()
    
    def normalize_path(self, path: str) -> str:
        """标准化路径"""
        return os.path.normpath(os.path.abspath(path))