# -*- coding: utf-8 -*-
"""
PyUpdater UI 组件
提供自动更新界面，包括更新检查、下载进度、重启提示等功能
"""

import customtkinter as ctk
from tkinter import messagebox
import threading
from typing import Optional, Dict, Any
from services.pyupdater_manager import get_updater_manager


class UpdateNotificationWidget(ctk.CTkFrame):
    """更新通知小部件"""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.updater = get_updater_manager()
        
        self.pack_propagate(False)
        self._create_widgets()
        self._bind_events()
        
        # 隐藏小部件，只在有更新时显示
        self.pack_forget()
    
    def _create_widgets(self):
        """创建UI组件"""
        # 通知图标
        self.icon_label = ctk.CTkLabel(
            self,
            text="🔄",
            font=ctk.CTkFont(size=16)
        )
        self.icon_label.pack(side="left", padx=5)
        
        # 通知文本
        self.text_label = ctk.CTkLabel(
            self,
            text="发现新版本",
            font=ctk.CTkFont(size=12)
        )
        self.text_label.pack(side="left", padx=5)
        
        # 操作按钮
        self.update_button = ctk.CTkButton(
            self,
            text="立即更新",
            width=80,
            height=24,
            command=self._start_update
        )
        self.update_button.pack(side="right", padx=5)
        
        self.dismiss_button = ctk.CTkButton(
            self,
            text="稍后",
            width=60,
            height=24,
            command=self._dismiss
        )
        self.dismiss_button.pack(side="right", padx=2)
    
    def _bind_events(self):
        """绑定事件"""
        self.updater.register_status_callback(self._on_status_change)
    
    def _on_status_change(self, status: str, data: Any = None):
        """状态变更回调"""
        if status == "update_available":
            self._show_notification(data)
        elif status == "downloading":
            self._update_downloading_state()
        elif status == "download_complete":
            self._update_ready_state()
    
    def _show_notification(self, update_info: Dict[str, Any]):
        """显示更新通知"""
        version = update_info.get('version', '')
        self.text_label.configure(text=f"发现新版本 {version}")
        self.pack(fill="x", pady=2)
    
    def _update_downloading_state(self):
        """更新下载状态"""
        self.text_label.configure(text="正在下载更新...")
        self.update_button.configure(state="disabled")
    
    def _update_ready_state(self):
        """更新就绪状态"""
        self.text_label.configure(text="更新就绪，需要重启")
        self.update_button.configure(text="重启", state="normal", command=self._restart_app)
    
    def _start_update(self):
        """开始更新"""
        self.updater.download_update(async_download=True)
    
    def _restart_app(self):
        """重启应用"""
        result = messagebox.askyesno(
            "重启应用",
            "应用将重启以完成更新。\n\n确定要现在重启吗？"
        )
        if result:
            self.updater.extract_and_restart()
    
    def _dismiss(self):
        """关闭通知"""
        self.pack_forget()


class UpdateProgressDialog(ctk.CTkToplevel):
    """更新进度对话框"""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.updater = get_updater_manager()
        
        self.title("正在更新")
        self.geometry("400x200")
        self.resizable(False, False)
        
        # 设置为模态对话框
        self.transient(parent)
        self.grab_set()
        
        self._create_widgets()
        self._bind_events()
        
        # 居中显示
        self._center_window()
    
    def _center_window(self):
        """窗口居中"""
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
    
    def _create_widgets(self):
        """创建UI组件"""
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 标题
        title_label = ctk.CTkLabel(
            main_frame,
            text="正在下载更新",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=10)
        
        # 进度条
        self.progress_bar = ctk.CTkProgressBar(main_frame)
        self.progress_bar.pack(fill="x", pady=10)
        self.progress_bar.set(0)
        
        # 进度文本
        self.progress_label = ctk.CTkLabel(
            main_frame,
            text="准备下载...",
            font=ctk.CTkFont(size=12)
        )
        self.progress_label.pack(pady=5)
        
        # 详细信息
        self.detail_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.detail_label.pack(pady=5)
        
        # 取消按钮
        self.cancel_button = ctk.CTkButton(
            main_frame,
            text="后台运行",
            command=self._hide_dialog
        )
        self.cancel_button.pack(pady=10)
    
    def _bind_events(self):
        """绑定事件"""
        self.updater.register_progress_callback(self._on_progress)
        self.updater.register_status_callback(self._on_status_change)
    
    def _on_progress(self, data: Dict[str, Any]):
        """进度更新回调"""
        if 'percent_complete' in data:
            progress = data['percent_complete'] / 100.0
            self.progress_bar.set(progress)
            
            self.progress_label.configure(
                text=f"下载进度: {data['percent_complete']:.1f}%"
            )
        
        if 'total' in data and 'received' in data:
            total_mb = data['total'] / (1024 * 1024)
            received_mb = data['received'] / (1024 * 1024)
            
            self.detail_label.configure(
                text=f"{received_mb:.1f} MB / {total_mb:.1f} MB"
            )
    
    def _on_status_change(self, status: str, data: Any = None):
        """状态变更回调"""
        if status == "download_complete":
            self.progress_bar.set(1.0)
            self.progress_label.configure(text="下载完成！")
            self.detail_label.configure(text="准备安装更新...")
            
            self.cancel_button.configure(text="重启安装", command=self._restart_install)
        
        elif status == "download_error":
            self.progress_label.configure(text="下载失败")
            self.detail_label.configure(text=str(data))
            self.cancel_button.configure(text="关闭", command=self.destroy)
    
    def _restart_install(self):
        """重启安装"""
        self.destroy()
        self.updater.extract_and_restart()
    
    def _hide_dialog(self):
        """隐藏对话框"""
        self.withdraw()


class AutoUpdateWidget(ctk.CTkFrame):
    """自动更新控制小部件"""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.updater = get_updater_manager()
        
        self._create_widgets()
        self._load_settings()
        self._bind_events()
    
    def _create_widgets(self):
        """创建UI组件"""
        # 版本信息区域
        version_frame = ctk.CTkFrame(self)
        version_frame.pack(fill="x", pady=5)
        
        self.version_label = ctk.CTkLabel(
            version_frame,
            text=f"当前版本: {self.updater.current_version}",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.version_label.pack(pady=5)
        
        # 自动更新设置
        settings_frame = ctk.CTkFrame(self)
        settings_frame.pack(fill="x", pady=5)
        
        self.auto_check_var = ctk.BooleanVar()
        self.auto_check_switch = ctk.CTkSwitch(
            settings_frame,
            text="启动时自动检查更新",
            variable=self.auto_check_var,
            command=self._on_auto_check_changed
        )
        self.auto_check_switch.pack(pady=5, anchor="w")
        
        # 更新状态显示
        self.status_label = ctk.CTkLabel(
            settings_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.status_label.pack(pady=2, anchor="w")
        
        # 操作按钮区域
        button_frame = ctk.CTkFrame(self)
        button_frame.pack(fill="x", pady=5)
        
        self.check_button = ctk.CTkButton(
            button_frame,
            text="检查更新",
            command=self._check_update
        )
        self.check_button.pack(side="left", padx=5)
        
        self.settings_button = ctk.CTkButton(
            button_frame,
            text="更新设置",
            command=self._show_settings
        )
        self.settings_button.pack(side="left", padx=5)
        
        # 更新通知区域
        self.notification_widget = UpdateNotificationWidget(self)
    
    def _load_settings(self):
        """加载设置"""
        auto_check = self.updater.get_auto_update_check()
        self.auto_check_var.set(auto_check)
        
        # 如果启用自动检查，启动时检查更新
        if auto_check:
            self.after(2000, self._auto_check_update)  # 延迟2秒后检查
    
    def _bind_events(self):
        """绑定事件"""
        self.updater.register_status_callback(self._on_status_change)
    
    def _on_auto_check_changed(self):
        """自动检查设置变更"""
        enabled = self.auto_check_var.get()
        self.updater.set_auto_update_check(enabled)
        
        if enabled:
            self.status_label.configure(text="启动时将自动检查更新")
        else:
            self.status_label.configure(text="已禁用自动检查更新")
    
    def _on_status_change(self, status: str, data: Any = None):
        """状态变更回调"""
        status_texts = {
            "checking": "正在检查更新...",
            "no_update": "已是最新版本",
            "update_available": "发现新版本",
            "downloading": "正在下载更新...",
            "download_complete": "更新下载完成",
            "check_error": "检查更新失败",
            "download_error": "下载更新失败"
        }
        
        text = status_texts.get(status, "")
        if isinstance(data, str) and status.endswith("_error"):
            text += f": {data}"
        
        self.status_label.configure(text=text)
        
        # 更新按钮状态
        if status == "checking":
            self.check_button.configure(text="检查中...", state="disabled")
        else:
            self.check_button.configure(text="检查更新", state="normal")
    
    def _check_update(self):
        """检查更新"""
        self.updater.check_for_updates(async_check=True)
    
    def _auto_check_update(self):
        """自动检查更新"""
        if self.auto_check_var.get():
            self.status_label.configure(text="正在自动检查更新...")
            self.updater.check_for_updates(async_check=True)
    
    def _show_settings(self):
        """显示更新设置对话框"""
        settings_dialog = UpdateSettingsDialog(self.winfo_toplevel(), self.updater)
        settings_dialog.focus()


class UpdateSettingsDialog(ctk.CTkToplevel):
    """更新设置对话框"""
    
    def __init__(self, parent, updater, **kwargs):
        super().__init__(parent, **kwargs)
        self.updater = updater
        
        self.title("更新设置")
        self.geometry("350x250")
        self.resizable(False, False)
        
        # 设置为模态对话框
        self.transient(parent)
        self.grab_set()
        
        self._create_widgets()
        self._center_window()
    
    def _center_window(self):
        """窗口居中"""
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
    
    def _create_widgets(self):
        """创建UI组件"""
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 标题
        title_label = ctk.CTkLabel(
            main_frame,
            text="更新设置",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=10)
        
        # 设置选项
        self.auto_check_var = ctk.BooleanVar(value=self.updater.get_auto_update_check())
        auto_check_switch = ctk.CTkSwitch(
            main_frame,
            text="启动时自动检查更新",
            variable=self.auto_check_var
        )
        auto_check_switch.pack(pady=10, anchor="w")
        
        # 更新源信息
        info_frame = ctk.CTkFrame(main_frame)
        info_frame.pack(fill="x", pady=10)
        
        source_label = ctk.CTkLabel(info_frame, text="更新源:")
        source_label.pack(anchor="w", pady=2)
        
        source_value = ctk.CTkLabel(
            info_frame,
            text="GitHub Releases",
            text_color="gray"
        )
        source_value.pack(anchor="w", padx=20)
        
        # 按钮区域
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill="x", pady=10)
        
        save_button = ctk.CTkButton(
            button_frame,
            text="保存",
            command=self._save_settings
        )
        save_button.pack(side="right", padx=5)
        
        cancel_button = ctk.CTkButton(
            button_frame,
            text="取消",
            command=self.destroy
        )
        cancel_button.pack(side="right", padx=5)
    
    def _save_settings(self):
        """保存设置"""
        auto_check = self.auto_check_var.get()
        self.updater.set_auto_update_check(auto_check)
        
        messagebox.showinfo("设置保存", "更新设置已保存！")
        self.destroy()