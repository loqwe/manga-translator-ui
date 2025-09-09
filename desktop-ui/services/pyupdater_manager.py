# -*- coding: utf-8 -*-
"""
PyUpdater 更新管理器
集成PyUpdater实现自动更新功能
"""

import os
import sys
import threading
import json
from typing import Callable, Optional, Dict, Any
from pyupdater.client import Client
# 添加desktop-ui目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入统一配置
from client_config import ClientConfig


class PyUpdaterManager:
    """PyUpdater 更新管理器"""
    
    def __init__(self, update_callback: Optional[Callable] = None, 
                 progress_callback: Optional[Callable] = None):
        self.update_callback = update_callback
        self.progress_callback = progress_callback
        
        # 初始化 PyUpdater 客户端
        self.client = Client(ClientConfig(), refresh=True, progress_hooks=[self._progress_hook])
        
        # 当前版本 (从 VERSION 文件动态读取)
        self.current_version = self._get_version_from_file()
        self.app_name = "MangaTranslatorUI"
        
        # 状态变量
        self.checking_update = False
        self.downloading_update = False
        self.restart_required = False
        
        # 更新信息
        self.update_available = False
        self.update_info = None
        
        # 回调函数列表
        self.update_callbacks = []
        self.progress_callbacks = []
        self.status_callbacks = []

    def _get_version_from_file(self):
        try:
            version_file = os.path.join(os.path.dirname(__file__), '..', '..', 'VERSION')
            with open(version_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            print(f"Error reading VERSION file: {e}")
            return "unknown"
    
    def register_update_callback(self, callback: Callable):
        """注册更新检查回调"""
        self.update_callbacks.append(callback)
    
    def register_progress_callback(self, callback: Callable):
        """注册下载进度回调"""
        self.progress_callbacks.append(callback)
    
    def register_status_callback(self, callback: Callable):
        """注册状态变更回调"""
        self.status_callbacks.append(callback)
    
    def _progress_hook(self, data):
        """PyUpdater 进度钩子"""
        if self.progress_callback:
            self.progress_callback(data)
        
        for callback in self.progress_callbacks:
            try:
                callback(data)
            except Exception as e:
                print(f"进度回调错误: {e}")
    
    def _notify_status(self, status: str, data: Any = None):
        """通知状态变更"""
        for callback in self.status_callbacks:
            try:
                callback(status, data)
            except Exception as e:
                print(f"状态回调错误: {e}")
    
    def check_for_updates(self, async_check: bool = True):
        """检查更新"""
        if self.checking_update:
            return
        
        if async_check:
            thread = threading.Thread(target=self._check_for_updates_sync, daemon=True)
            thread.start()
        else:
            self._check_for_updates_sync()
    
    def _check_for_updates_sync(self):
        """同步检查更新"""
        self.checking_update = True
        self._notify_status("checking", "正在检查更新...")
        
        try:
            # 刷新更新仓库
            self.client.refresh()
            
            # 检查是否有更新
            app_update = self.client.update_check(self.app_name, self.current_version)
            
            if app_update:
                self.update_available = True
                self.update_info = {
                    'version': app_update.version,
                    'filename': app_update.filename,
                    'file_size': getattr(app_update, 'file_size', 0),
                    'download_url': getattr(app_update, 'download_url', ''),
                    'release_notes': self._get_release_notes(app_update.version)
                }
                
                self._notify_status("update_available", self.update_info)
                
                # 调用更新回调
                for callback in self.update_callbacks:
                    try:
                        callback(True, self.update_info)
                    except Exception as e:
                        print(f"更新回调错误: {e}")
                
            else:
                self.update_available = False
                self.update_info = None
                
                self._notify_status("no_update", "已是最新版本")
                
                # 调用更新回调
                for callback in self.update_callbacks:
                    try:
                        callback(False, None)
                    except Exception as e:
                        print(f"更新回调错误: {e}")
        
        except Exception as e:
            print(f"检查更新失败: {e}")
            self._notify_status("check_error", str(e))
            
            # 调用更新回调
            for callback in self.update_callbacks:
                try:
                    callback(False, None, str(e))
                except Exception as e:
                    print(f"更新回调错误: {e}")
        
        finally:
            self.checking_update = False
    
    def download_update(self, async_download: bool = True):
        """下载更新"""
        if not self.update_available or self.downloading_update:
            return False
        
        if async_download:
            thread = threading.Thread(target=self._download_update_sync, daemon=True)
            thread.start()
            return True
        else:
            return self._download_update_sync()
    
    def _download_update_sync(self):
        """同步下载更新"""
        if not self.update_available:
            return False
        
        self.downloading_update = True
        self._notify_status("downloading", "正在下载更新...")
        
        try:
            # 开始下载更新
            app_update = self.client.update_check(self.app_name, self.current_version)
            if app_update:
                success = app_update.download()
                
                if success:
                    self._notify_status("download_complete", "下载完成")
                    self.restart_required = True
                    return True
                else:
                    self._notify_status("download_error", "下载失败")
                    return False
        
        except Exception as e:
            print(f"下载更新失败: {e}")
            self._notify_status("download_error", str(e))
            return False
        
        finally:
            self.downloading_update = False
    
    def extract_and_restart(self):
        """解压并重启应用"""
        if not self.restart_required:
            return False
        
        try:
            app_update = self.client.update_check(self.app_name, self.current_version)
            if app_update:
                # 解压更新
                success = app_update.extract_restart()
                return success
        
        except Exception as e:
            print(f"解压重启失败: {e}")
            return False
        
        return False
    
    def _get_release_notes(self, version: str) -> str:
        """获取发布说明"""
        # 这里可以从远程服务器获取发布说明
        # 暂时返回默认内容
        return f"版本 {version} 更新说明:\n• 性能优化\n• Bug 修复\n• 新功能添加"
    
    def get_update_status(self) -> Dict[str, Any]:
        """获取更新状态"""
        return {
            'checking': self.checking_update,
            'downloading': self.downloading_update,
            'update_available': self.update_available,
            'restart_required': self.restart_required,
            'current_version': self.current_version,
            'update_info': self.update_info
        }
    
    def set_auto_update_check(self, enabled: bool):
        """设置自动检查更新"""
        # 这里可以保存到配置文件
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'update_settings.json')
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, 'w') as f:
                json.dump({'auto_check': enabled}, f)
        except Exception as e:
            print(f"保存自动更新设置失败: {e}")
    
    def get_auto_update_check(self) -> bool:
        """获取自动检查更新设置"""
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'update_settings.json')
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    return config.get('auto_check', True)
        except Exception as e:
            print(f"读取自动更新设置失败: {e}")
        
        return True  # 默认启用
    
    def cleanup_old_updates(self):
        """清理旧的更新文件"""
        try:
            # PyUpdater 会自动处理清理工作
            pass
        except Exception as e:
            print(f"清理旧更新文件失败: {e}")


# 全局更新管理器实例
_updater_manager = None


def get_updater_manager() -> PyUpdaterManager:
    """获取更新管理器实例"""
    global _updater_manager
    if _updater_manager is None:
        _updater_manager = PyUpdaterManager()
    return _updater_manager