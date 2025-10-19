import customtkinter as ctk
from tkinter import scrolledtext
import subprocess
import threading
import json
import os
import shutil
import zipfile
import requests
from datetime import datetime, timedelta
from pathlib import Path
import time
import schedule
import sys

# Windows 平台的常數，用於隱藏子進程視窗
if sys.platform == 'win32':
    import ctypes
    CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0


class CustomDialog(ctk.CTkToplevel):
    """自定義對話框,符合主題配色"""
    def __init__(self, parent, title, message, dialog_type="info", buttons=("確定",)):
        super().__init__(parent)
        
        self.result = None
        self.title(title)
        
        # 根據按鈕數量調整高度
        height = 280 if len(buttons) > 1 else 220
        self.geometry(f"450x{height}")
        self.resizable(False, False)
        
        # 設置為模態窗口
        self.transient(parent)
        self.grab_set()
        
        # 處理關閉事件 - 返回None表示取消
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 置中顯示
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 450) // 2
        y = parent.winfo_y() + (parent.winfo_height() - height) // 2
        self.geometry(f"+{x}+{y}")
        
        # 主框架
        main_frame = ctk.CTkFrame(self, corner_radius=0)
        main_frame.pack(fill="both", expand=True, padx=0, pady=0)
        
        # 圖標和標題
        icon_map = {
            "info": "[ i ]",
            "warning": "[ ! ]",
            "error": "[ X ]",
            "question": "[ ? ]",
            "success": "[ ✓ ]"
        }
        icon = icon_map.get(dialog_type, "[ i ]")
        
        title_frame = ctk.CTkFrame(main_frame, fg_color=("#17A2B8", "#1A8299"))
        title_frame.pack(fill="x", padx=0, pady=0)
        
        ctk.CTkLabel(
            title_frame, 
            text=f"{icon} {title}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="white"
        ).pack(pady=15)
        
        # 訊息內容
        message_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        message_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(
            message_frame,
            text=message,
            font=ctk.CTkFont(size=13),
            wraplength=350,
            justify="left"
        ).pack(expand=True)
        
        # 按鈕區域
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(10, 20))
        
        # 根據按鈕數量調整佈局
        if len(buttons) == 1:
            btn = ctk.CTkButton(
                button_frame,
                text=buttons[0],
                command=lambda: self.on_button_click(buttons[0]),
                width=120,
                height=40,
                font=ctk.CTkFont(size=14, weight="bold"),
                fg_color="#17A2B8",
                hover_color="#138496"
            )
            btn.pack(pady=5)
        else:
            # 創建內部框架以更好控制按鈕佈局
            inner_frame = ctk.CTkFrame(button_frame, fg_color="transparent")
            inner_frame.pack(expand=True)
            
            for i, btn_text in enumerate(buttons):
                if btn_text in ["是", "確定", "保存"]:
                    fg_color = "#17A2B8"
                    hover_color = "#138496"
                else:
                    fg_color = "#6C757D"
                    hover_color = "#5A6268"
                
                btn = ctk.CTkButton(
                    inner_frame,
                    text=btn_text,
                    command=lambda t=btn_text: self.on_button_click(t),
                    width=120,
                    height=40,
                    font=ctk.CTkFont(size=14, weight="bold"),
                    fg_color=fg_color,
                    hover_color=hover_color
                )
                btn.pack(side="left", padx=8, pady=5)
    
    def on_button_click(self, button_text):
        """按鈕點擊事件"""
        self.result = button_text
        self.grab_release()
        self.destroy()
    
    def on_close(self):
        """窗口關閉事件 - 對於多按鈕對話框，關閉等同於取消"""
        self.result = None
        self.grab_release()
        self.destroy()
    
    def get_result(self):
        """等待並返回結果"""
        self.wait_window()
        return self.result


class BDSConsole(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # 基礎設定
        self.title("BDS Console")
        self.geometry("1200x700")
        
        # 路徑設定 - 處理 PyInstaller 打包後的路徑
        # 當打包成 exe 時,使用 sys.executable 的路徑
        # 當以 .py 執行時,使用 __file__ 的路徑
        if getattr(sys, 'frozen', False):
            # 打包後的 exe 執行環境
            self.base_dir = Path(sys.executable).parent
        else:
            # 開發環境(.py 檔案)
            self.base_dir = Path(__file__).parent
            
        self.app_dir = self.base_dir / "data"
        self.server_dir = self.base_dir / "server_files"
        self.backup_dir = self.base_dir / "backup"
        self.temp_dir = self.app_dir / "temp"
        
        # 設定視窗圖示
        self._set_window_icon()
        
        # 建立必要資料夾
        self.create_directories()
        
        # 伺服器相關
        self.server_process = None
        self.server_status = "停止"
        self.online_players = 0
        self.max_players = 10
        self.server_version = "未知"
        self.output_queue = []
        
        # 玩家列表
        self.player_list_file = self.app_dir / "player_list.json"
        self.player_list = self.load_player_list()
        self.online_players_names = []  # 在線玩家名稱列表
        self.player_ui_vars = {}  # 存儲玩家的 UI 變數 (xuid -> {allowlist_var, perm_var})
        self.update_pending = False  # 防止重複更新的標誌
        
        # 更新通知狀態
        self.update_notification_active = False  # 是否正在進行更新通知
        self.update_remaining_seconds = 0  # 更新剩餘秒數
        self.update_next_broadcast_seconds = 0  # 下次預定廣播的剩餘秒數
        self.update_cancel_requested = False  # 是否請求取消更新
        self.update_in_progress = False  # 是否正在執行更新（下載完成後）
        self.update_download_thread = None  # 下載線程引用
        
        # 伺服器操作狀態
        self.server_operation_in_progress = False  # 伺服器操作進行中（啟動/停止/重啟）
        self.is_restarting = False  # 是否正在重啟過程中
        
        # 備份時間追蹤
        self.last_manual_backup_time = None  # 上次手動備份時間
        self.last_auto_backup_time = None    # 上次自動備份時間
        self.backup_time_file = self.app_dir / "backup_time.json"
        self.load_backup_times()
        
        # 設定變更追蹤
        self.backup_settings_changed = False  # 備份設定是否已變更
        self.update_settings_changed = False  # 更新設定是否已變更
        self.saved_backup_settings = {}  # 已儲存的備份設定
        self.saved_update_settings = {}  # 已儲存的更新設定
        
        # 自動任務設定
        self.config_file = self.app_dir / "config.json"
        self.load_config()
        
        # 主題設定（從配置文件加載）
        theme = self.config.get("theme", "dark")
        ctk.set_appearance_mode(theme)
        ctk.set_default_color_theme("blue")
        
        # 建立介面
        self.create_ui()
        
        # 初始化命令輸入框狀態（伺服器未運行時應禁用）
        self._update_command_entry_state()
        
        # 設置排程任務
        self.setup_schedules()
        
        # 啟動排程檢查執行緒
        self.schedule_thread = threading.Thread(target=self.run_schedule, daemon=True)
        self.schedule_thread.start()
        
        # 自動啟動伺服器
        self.after(1000, self.start_server)
        
        # 啟動時自動檢查更新
        self.after(2000, self.auto_check_update_on_startup)
        
        # 關閉視窗處理
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def _set_window_icon(self):
        """設定視窗圖示"""
        try:
            # 處理打包後的資源路徑
            if getattr(sys, 'frozen', False):
                # 打包後,資源會被解壓到 sys._MEIPASS 臨時目錄
                icon_path = Path(sys._MEIPASS) / "logo.ico"
            else:
                # 開發環境
                icon_path = self.base_dir / "logo.ico"
            
            if icon_path.exists():
                # 設定視窗圖示
                self.iconbitmap(str(icon_path))
            else:
                # 如果找不到圖示檔案,記錄但不中斷程式
                print(f"警告: 找不到圖示檔案 {icon_path}")
        except Exception as e:
            # 如果設定圖示失敗,記錄但不中斷程式
            print(f"設定圖示時發生錯誤: {e}")
        
    def create_directories(self):
        """建立必要的資料夾結構"""
        dirs = [
            self.app_dir,
            self.server_dir,
            self.backup_dir,
            self.temp_dir,
            self.backup_dir / "server_settings",
            self.backup_dir / "worlds_manual",  # 手動備份資料夾
            self.backup_dir / "worlds_auto"     # 自動備份資料夾
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
    
    def load_config(self):
        """載入設定"""
        default_config = {
            "auto_backup_enabled": False,  # 默認停用自動備份
            "backup_frequency_type": "hours",
            "backup_frequency_value": 6,
            "backup_time_hour": 3,
            "backup_time_minute": 0,
            "backup_weekday": 0,
            "backup_day": 1,
            "backup_notify_seconds": 5,
            "auto_update_enabled": False,  # 默認停用自動更新
            "update_frequency_type": "daily",
            "update_frequency_value": 1,
            "update_time_hour": 4,
            "update_time_minute": 0,
            "update_weekday": 0,
            "update_day": 1,
            "update_notify_minutes": 10,
            "backup_max_size_gb": 10,
            "theme": "system"  # 默認使用系統主題
        }
        
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
                self.config = {**default_config, **loaded_config}
                # 確保備份容量不小於0.5
                if self.config["backup_max_size_gb"] < 0.5:
                    self.config["backup_max_size_gb"] = 0.5
        else:
            self.config = default_config
            self.save_config()
    
    def save_config(self):
        """儲存設定"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)
    
    def load_backup_times(self):
        """載入備份時間記錄"""
        from datetime import datetime
        
        # 先從檔案載入記錄
        if self.backup_time_file.exists():
            try:
                with open(self.backup_time_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get("last_manual_backup"):
                        self.last_manual_backup_time = datetime.fromisoformat(data["last_manual_backup"])
                    if data.get("last_auto_backup"):
                        self.last_auto_backup_time = datetime.fromisoformat(data["last_auto_backup"])
            except Exception as e:
                print(f"載入備份時間記錄失敗: {str(e)}")
        
        # 從備份資料夾掃描最新的備份檔案並更新時間
        self.scan_latest_backups()
    
    def scan_latest_backups(self):
        """掃描備份資料夾並從檔名獲取最新的備份時間"""
        from datetime import datetime
        import re
        
        try:
            # 掃描手動備份資料夾
            manual_backup_dir = self.backup_dir / "worlds_manual"
            if manual_backup_dir.exists():
                manual_backups = list(manual_backup_dir.glob("world_backup_*.zip"))
                if manual_backups:
                    # 從檔名提取時間戳並排序
                    manual_times = []
                    for backup_file in manual_backups:
                        # 檔名格式: world_backup_YYYYMMDD_HHMMSS.zip
                        match = re.search(r'world_backup_(\d{8}_\d{6})\.zip', backup_file.name)
                        if match:
                            timestamp_str = match.group(1)
                            try:
                                backup_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                                manual_times.append(backup_time)
                            except ValueError:
                                continue
                    
                    if manual_times:
                        latest_manual = max(manual_times)
                        # 如果從檔案掃描到的時間比記錄的時間新，則更新
                        if not self.last_manual_backup_time or latest_manual > self.last_manual_backup_time:
                            self.last_manual_backup_time = latest_manual
                            self.log_message(f"從檔案掃描到最新手動備份時間: {latest_manual.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 掃描自動備份資料夾
            auto_backup_dir = self.backup_dir / "worlds_auto"
            if auto_backup_dir.exists():
                auto_backups = list(auto_backup_dir.glob("world_backup_*.zip"))
                if auto_backups:
                    # 從檔名提取時間戳並排序
                    auto_times = []
                    for backup_file in auto_backups:
                        # 檔名格式: world_backup_YYYYMMDD_HHMMSS.zip
                        match = re.search(r'world_backup_(\d{8}_\d{6})\.zip', backup_file.name)
                        if match:
                            timestamp_str = match.group(1)
                            try:
                                backup_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                                auto_times.append(backup_time)
                            except ValueError:
                                continue
                    
                    if auto_times:
                        latest_auto = max(auto_times)
                        # 如果從檔案掃描到的時間比記錄的時間新，則更新
                        if not self.last_auto_backup_time or latest_auto > self.last_auto_backup_time:
                            self.last_auto_backup_time = latest_auto
                            self.log_message(f"從檔案掃描到最新自動備份時間: {latest_auto.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 如果有更新，保存到檔案
            if self.last_manual_backup_time or self.last_auto_backup_time:
                self.save_backup_times()
                
        except Exception as e:
            self.log_message(f"掃描備份檔案時發生錯誤: {str(e)}")
    
    def save_backup_times(self):
        """儲存備份時間記錄"""
        try:
            data = {}
            if self.last_manual_backup_time:
                data["last_manual_backup"] = self.last_manual_backup_time.isoformat()
            if self.last_auto_backup_time:
                data["last_auto_backup"] = self.last_auto_backup_time.isoformat()
            
            with open(self.backup_time_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"儲存備份時間記錄失敗: {str(e)}")
    
    def run_schedule(self):
        """運行排程檢查"""
        while True:
            schedule.run_pending()
            time.sleep(1)
    
    def setup_schedules(self):
        """設置排程任務"""
        schedule.clear()
        
        # 設置自動備份
        if self.config["auto_backup_enabled"]:
            freq_type = self.config["backup_frequency_type"]
            if freq_type == "hours":
                hours = self.config["backup_frequency_value"]
                schedule.every(hours).hours.do(lambda: threading.Thread(
                    target=self.scheduled_backup, daemon=True).start())
            elif freq_type == "daily":
                time_str = f"{self.config['backup_time_hour']:02d}:{self.config['backup_time_minute']:02d}"
                schedule.every().day.at(time_str).do(lambda: threading.Thread(
                    target=self.scheduled_backup, daemon=True).start())
            elif freq_type == "weekly":
                weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                time_str = f"{self.config['backup_time_hour']:02d}:{self.config['backup_time_minute']:02d}"
                getattr(schedule.every(), weekdays[self.config["backup_weekday"]]).at(time_str).do(
                    lambda: threading.Thread(target=self.scheduled_backup, daemon=True).start())
            elif freq_type == "monthly":
                # 每天檢查是否是指定日期
                schedule.every().day.at("00:01").do(self.check_monthly_backup)
        
        # 設置自動更新
        if self.config["auto_update_enabled"]:
            freq_type = self.config["update_frequency_type"]
            if freq_type == "hours":
                hours = self.config["update_frequency_value"]
                schedule.every(hours).hours.do(lambda: threading.Thread(
                    target=self.scheduled_update_check, daemon=True).start())
            elif freq_type == "daily":
                time_str = f"{self.config['update_time_hour']:02d}:{self.config['update_time_minute']:02d}"
                schedule.every().day.at(time_str).do(lambda: threading.Thread(
                    target=self.scheduled_update_check, daemon=True).start())
            elif freq_type == "weekly":
                weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                time_str = f"{self.config['update_time_hour']:02d}:{self.config['update_time_minute']:02d}"
                getattr(schedule.every(), weekdays[self.config["update_weekday"]]).at(time_str).do(
                    lambda: threading.Thread(target=self.scheduled_update_check, daemon=True).start())
            elif freq_type == "monthly":
                schedule.every().day.at("00:01").do(self.check_monthly_update)
    
    def check_monthly_backup(self):
        """檢查是否執行月度備份"""
        if datetime.now().day == self.config["backup_day"]:
            hour = self.config["backup_time_hour"]
            minute = self.config["backup_time_minute"]
            now = datetime.now()
            if now.hour == hour and now.minute == minute:
                threading.Thread(target=self.scheduled_backup, daemon=True).start()
    
    def check_monthly_update(self):
        """檢查是否執行月度更新"""
        if datetime.now().day == self.config["update_day"]:
            hour = self.config["update_time_hour"]
            minute = self.config["update_time_minute"]
            now = datetime.now()
            if now.hour == hour and now.minute == minute:
                threading.Thread(target=self.scheduled_update_check, daemon=True).start()
    
    def scheduled_backup(self):
        """排程備份（帶通知）"""
        self.log_message("排程備份即將執行...")
        self.perform_backup_with_notification(
            self.config["backup_notify_minutes"], 
            is_auto=True
        )
    
    def _compare_versions(self, version1, version2):
        """比較兩個版本號
        
        Args:
            version1: 第一個版本號（如 "1.21.113.1"）
            version2: 第二個版本號（如 "1.21.114.0"）
        
        Returns:
            1: version1 > version2
            0: version1 == version2
            -1: version1 < version2
        """
        try:
            # 分割版本號並轉換為整數列表
            v1_parts = [int(x) for x in version1.split('.')]
            v2_parts = [int(x) for x in version2.split('.')]
            
            # 補齊較短的版本號（用0填充）
            max_len = max(len(v1_parts), len(v2_parts))
            v1_parts.extend([0] * (max_len - len(v1_parts)))
            v2_parts.extend([0] * (max_len - len(v2_parts)))
            
            # 逐段比較
            for v1, v2 in zip(v1_parts, v2_parts):
                if v1 > v2:
                    return 1
                elif v1 < v2:
                    return -1
            
            return 0
        except Exception as e:
            self.log_message(f"版本比較錯誤: {str(e)}")
            return 0
    
    def scheduled_update_check(self):
        """排程更新檢查"""
        self.log_message("正在檢查更新...")
        # 先檢查更新（自動模式不顯示彈窗）
        self._check_update(is_auto=True)
        # 如果有更新可用且版本較新，執行更新
        if hasattr(self, 'download_url') and self.download_url and hasattr(self, 'has_new_version') and self.has_new_version:
            self.log_message("開始自動更新...")
            self.perform_update_with_notification(
                self.config["update_notify_minutes"],
                is_auto=True
            )
    
    def broadcast_message(self, message, log_prefix=None):
        """發送廣播訊息到遊戲中
        
        Args:
            message: 廣播訊息內容
            log_prefix: 日誌前綴（如 "備份通知"、"更新通知"、"重啟通知"），None則使用預設格式
        """
        if self.server_process:
            try:
                command = f'say {message}'
                self.server_process.stdin.write(command + "\n")
                self.server_process.stdin.flush()
                
                # 根據前綴決定日誌格式
                if log_prefix:
                    self.log_message(f"已發送{log_prefix}: {message}")
                else:
                    self.log_message(f"廣播: {message}")
            except Exception as e:
                self.log_message(f"廣播失敗: {str(e)}")
    
    def _format_time_unit(self, value, unit="second"):
        """格式化時間單位（自動判斷單複數）"""
        if value == 1:
            return f"{value} {unit}"
        else:
            return f"{value} {unit}s"
    
    def perform_backup_with_notification(self, notify_seconds, is_auto=False):
        """執行備份（帶通知，單位秒）"""
        try:
            # 自動備份時需要禁用按鈕（手動備份已在調用前處理）
            if is_auto:
                self.after(0, self._disable_operation_buttons)
            
            if notify_seconds > 0 and self.server_process:
                time_str = self._format_time_unit(notify_seconds, "second")
                message = f"Backup will begin in {time_str}"
                self.broadcast_message(message, "備份通知")
                time.sleep(notify_seconds)
            
            # 記錄實際備份開始時間（排除等待時間）
            backup_start_time = time.time()
            
            # 執行備份（移除進行中通知）
            # 注意：_perform_backup 內部也會調用 _disable_operation_buttons，
            # 但這裡先調用是為了在通知期間就禁用按鈕
            self._perform_backup(is_auto=is_auto)
            
            # 計算實際備份耗時（不包含提前通知等待時間）
            if self.server_process:
                elapsed = int(time.time() - backup_start_time)
                if elapsed < 60:
                    time_str = self._format_time_unit(elapsed, "second")
                else:
                    minutes = elapsed // 60
                    seconds = elapsed % 60
                    if seconds == 0:
                        time_str = self._format_time_unit(minutes, "minute")
                    else:
                        time_str = f"{self._format_time_unit(minutes, 'minute')} {self._format_time_unit(seconds, 'second')}"
                message = f"Backup completed, took {time_str}"
                self.broadcast_message(message, "備份通知")
        except Exception as e:
            self.log_message(f"備份通知流程錯誤: {str(e)}")

    
    def perform_update_with_notification(self, notify_minutes, is_auto=False):
        """執行更新（帶通知）- 優化版本，並行下載，精確倒數"""
        try:
            # 自動更新時需要禁用按鈕（手動更新已在調用前處理）
            if is_auto:
                self.after(0, self._disable_operation_buttons)
            
            download_thread = None
            
            # 如果有通知時間，在通知期間並行下載檔案
            if notify_minutes > 0:
                self.update_notification_active = True  # 開始更新通知
                self.update_remaining_seconds = notify_minutes * 60
                
                self.log_message("開始並行下載更新檔...")
                # 啟動下載執行緒並保存引用
                download_thread = threading.Thread(target=self._download_and_store, daemon=True)
                self.update_download_thread = download_thread
                download_thread.start()
                
                # 同時進行通知倒數
                if self.server_process:
                    total_seconds = notify_minutes * 60
                    
                    # 大於 30 分鐘時，每 10 分鐘廣播一次
                    while total_seconds > 30 * 60:
                        # 檢查是否請求取消
                        if self.update_cancel_requested:
                            self.log_message("更新已取消（通知階段）")
                            return
                        
                        remaining_minutes = total_seconds // 60
                        time_str = self._format_time_unit(remaining_minutes, "minute")
                        message = f"Update in {time_str}"
                        self.broadcast_message(message, "更新通知")
                        self.update_remaining_seconds = total_seconds
                        self.update_next_broadcast_seconds = total_seconds - 10 * 60
                        
                        # 以1秒為單位更新剩餘時間
                        for _ in range(10 * 60):
                            if self.update_cancel_requested:
                                self.log_message("更新已取消（通知階段）")
                                return
                            time.sleep(1)
                            total_seconds -= 1
                            self.update_remaining_seconds = total_seconds
                    
                    # 30 分鐘內每 5 分鐘一次
                    while total_seconds > 5 * 60:
                        # 檢查是否請求取消
                        if self.update_cancel_requested:
                            self.log_message("更新已取消（通知階段）")
                            return
                        
                        remaining_minutes = total_seconds // 60
                        time_str = self._format_time_unit(remaining_minutes, "minute")
                        message = f"Update in {time_str}"
                        self.broadcast_message(message, "更新通知")
                        self.update_remaining_seconds = total_seconds
                        self.update_next_broadcast_seconds = total_seconds - 5 * 60
                        
                        # 以1秒為單位更新剩餘時間
                        for _ in range(5 * 60):
                            if self.update_cancel_requested:
                                self.log_message("更新已取消（通知階段）")
                                return
                            time.sleep(1)
                            total_seconds -= 1
                            self.update_remaining_seconds = total_seconds
                    
                    # 5 分鐘到 1 分鐘之間（2-5分鐘）
                    if total_seconds > 60:
                        # 檢查是否請求取消
                        if self.update_cancel_requested:
                            self.log_message("更新已取消（通知階段）")
                            return
                        
                        remaining_minutes = total_seconds // 60
                        time_str = self._format_time_unit(remaining_minutes, "minute")
                        message = f"Update in {time_str}"
                        self.broadcast_message(message, "更新通知")
                        self.update_remaining_seconds = total_seconds
                        self.update_next_broadcast_seconds = 60
                        
                        # 以1秒為單位更新剩餘時間，直到剩下1分鐘
                        while total_seconds > 60:
                            if self.update_cancel_requested:
                                self.log_message("更新已取消（通知階段）")
                                return
                            time.sleep(1)
                            total_seconds -= 1
                            self.update_remaining_seconds = total_seconds
                    
                    # 剩餘 1 分鐘
                    if total_seconds >= 60:
                        # 檢查是否請求取消
                        if self.update_cancel_requested:
                            self.log_message("更新已取消（通知階段）")
                            return
                        
                        message = "Update in 1 minute"
                        self.broadcast_message(message, "更新通知")
                        self.update_remaining_seconds = total_seconds
                        self.update_next_broadcast_seconds = 30
                        
                        # 以1秒為單位更新剩餘時間，直到剩下30秒
                        while total_seconds > 30:
                            if self.update_cancel_requested:
                                self.log_message("更新已取消（通知階段）")
                                return
                            time.sleep(1)
                            total_seconds -= 1
                            self.update_remaining_seconds = total_seconds
                    
                    # 剩餘 30 秒，每 5 秒倒數
                    while total_seconds > 10:
                        # 檢查是否請求取消
                        if self.update_cancel_requested:
                            self.log_message("更新已取消（通知階段）")
                            return
                        
                        time_str = self._format_time_unit(total_seconds, "second")
                        message = f"Update in {time_str}"
                        self.broadcast_message(message, "更新通知")
                        self.update_remaining_seconds = total_seconds
                        self.update_next_broadcast_seconds = total_seconds - 5
                        
                        # 以1秒為單位更新剩餘時間
                        for _ in range(5):
                            if self.update_cancel_requested:
                                self.log_message("更新已取消（通知階段）")
                                return
                            time.sleep(1)
                            total_seconds -= 1
                            self.update_remaining_seconds = total_seconds
                            if total_seconds <= 10:
                                break
                    
                    # 剩餘 10 秒，每秒倒數
                    while total_seconds > 0:
                        # 檢查是否請求取消
                        if self.update_cancel_requested:
                            self.log_message("更新已取消（通知階段）")
                            return
                        
                        time_str = self._format_time_unit(total_seconds, "second")
                        message = f"Update in {time_str}"
                        self.broadcast_message(message, "更新通知")
                        self.update_remaining_seconds = total_seconds
                        self.update_next_broadcast_seconds = total_seconds - 1
                        time.sleep(1)
                        total_seconds -= 1
                        self.update_remaining_seconds = total_seconds
                
                # 等待下載完成
                if download_thread:
                    self.log_message("等待下載完成...")
                    download_thread.join()
                
                # 檢查最後一次是否請求取消
                if self.update_cancel_requested:
                    self.log_message("更新已取消（下載後）")
                    return
                
                # 清除更新通知狀態
                self.update_notification_active = False
                self.update_remaining_seconds = 0
                self.update_next_broadcast_seconds = 0
            
            # 標記進入更新階段（無法取消）
            self.update_in_progress = True
            
            # 將按鈕改為無效化的反灰狀態
            if not is_auto:
                self.after(0, lambda: self.force_update_btn.configure(
                    text="手動更新",
                    state="disabled",
                    fg_color="#6C757D",
                    hover_color="#6C757D"
                ))
            
            # 執行更新
            self._perform_update()
            
        except Exception as e:
            self.log_message(f"更新通知流程錯誤: {str(e)}")
            # 確保清除狀態
            self.update_notification_active = False
            self.update_remaining_seconds = 0
            self.update_next_broadcast_seconds = 0
    
    def send_immediate_update_notification(self, player_name):
        """立即發送更新通知給新上線的玩家（spawned時）"""
        try:
            # 檢查是否在更新通知期間
            if self.update_notification_active and self.update_remaining_seconds > 0:
                # 計算與下次預定廣播的時間差
                time_until_next_broadcast = self.update_next_broadcast_seconds
                
                # 如果與下次預定廣播相距超過60秒，則發送額外通知
                if time_until_next_broadcast > 60:
                    # 計算完整的分秒格式
                    remaining_seconds = int(self.update_remaining_seconds)
                    minutes = remaining_seconds // 60
                    seconds = remaining_seconds % 60
                    
                    # 構建訊息
                    if minutes > 0 and seconds > 0:
                        message = f"Update in {minutes} minute{'' if minutes == 1 else 's'} {seconds} second{'' if seconds == 1 else 's'}"
                    elif minutes > 0:
                        message = f"Update in {minutes} minute{'' if minutes == 1 else 's'}"
                    else:
                        message = f"Update in {seconds} second{'' if seconds == 1 else 's'}"
                    
                    self.broadcast_message(message, f"更新通知 (for {player_name})")
                    self.log_message(f"為新上線玩家 {player_name} 發送更新通知 (剩餘 {minutes}分{seconds}秒)")
        except Exception as e:
            self.log_message(f"即時通知錯誤: {str(e)}")
    
    def _download_and_store(self):
        """下載並儲存檔案路徑（供並行下載使用）"""
        temp_zip = self._download_update_file()
        if temp_zip:
            self._downloaded_zip = temp_zip
            self.log_message("並行下載已完成，等待伺服器關閉...")
        else:
            # 檢查是否為取消操作
            if not self.update_cancel_requested:
                # 只有在非取消情況下才記錄為失敗
                self.log_message("並行下載失敗！")
            
    def load_player_list(self):
        """載入玩家列表"""
        if self.player_list_file.exists():
            with open(self.player_list_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_player_list(self):
        """儲存玩家列表"""
        with open(self.player_list_file, 'w', encoding='utf-8') as f:
            json.dump(self.player_list, f, indent=4, ensure_ascii=False)
    
    def create_ui(self):
        """建立主介面"""
        # 主容器
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # 左側導航欄 - 使用漸層色
        self.nav_frame = ctk.CTkFrame(self, width=220, corner_radius=0, 
                                     fg_color=("#2B5278", "#1A1A2E"))
        self.nav_frame.grid(row=0, column=0, sticky="nsew")
        self.nav_frame.grid_rowconfigure(6, weight=1)
        
        # 標題區域
        title_frame = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        title_frame.grid(row=0, column=0, padx=15, pady=25, sticky="ew")
        
        title_label = ctk.CTkLabel(title_frame, text="BDS Console", 
                                   font=ctk.CTkFont(size=24, weight="bold"),
                                   text_color=("#FFFFFF", "#FFFFFF"))
        title_label.pack()
        
        subtitle_label = ctk.CTkLabel(title_frame, text="Minecraft 伺服器管理", 
                                      font=ctk.CTkFont(size=12),
                                      text_color=("#E0E0E0", "#B0B0B0"))
        subtitle_label.pack(pady=(5,0))
        
        # 分隔線
        separator = ctk.CTkFrame(self.nav_frame, height=2, 
                                fg_color=("#FFFFFF", "#FFFFFF"))
        separator.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        
        # 導航按鈕
        self.nav_buttons = []
        pages = [
            ("伺服器狀態", "伺服器狀態"),
            ("伺服器設定", "伺服器設定"),
            ("備份與更新", "備份與更新"),
            ("控制面板設定", "控制面板設定")
        ]
        
        for i, (display_name, page_name) in enumerate(pages):
            btn = ctk.CTkButton(
                self.nav_frame, 
                text=display_name, 
                command=lambda p=page_name: self.show_page(p),
                corner_radius=10, 
                height=45, 
                anchor="w",
                font=ctk.CTkFont(size=14, weight="bold"),
                fg_color="transparent",
                hover_color=("#3A6EA5", "#2D2D44"),
                text_color=("#FFFFFF", "#FFFFFF")
            )
            btn.grid(row=i+2, column=0, sticky="ew", padx=12, pady=6)
            self.nav_buttons.append(btn)
        
        # 底部版本資訊
        version_label = ctk.CTkLabel(
            self.nav_frame, 
            text="v1.0.0", 
            font=ctk.CTkFont(size=10),
            text_color=("#B0B0B0", "#808080")
        )
        version_label.grid(row=7, column=0, pady=(0,15))
        
        # 右側內容區
        self.content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)
        
        # 先載入 server.properties
        self.load_server_properties()
        
        # 建立所有頁面
        self.pages = {}
        self.create_status_page()
        self.create_settings_page()
        self.create_backup_page()
        self.create_console_settings_page()
        
        # 顯示第一個頁面
        self.show_page("伺服器狀態")

        
    def show_page(self, page_name):
        """切換頁面"""
        # 檢查當前頁面是否有未保存的設定
        current_page = None
        for name, page in self.pages.items():
            if page.winfo_ismapped():
                current_page = name
                break
        
        # 如果是從備份與更新頁面切換,檢查是否有未保存的設定
        if current_page == "備份與更新" and page_name != "備份與更新":
            has_unsaved = self.backup_settings_changed or self.update_settings_changed
            
            if has_unsaved:
                dialog = CustomDialog(
                    self,
                    "未保存的設定",
                    "您有未保存的設定,是否要保存?\n\n• 是: 保存設定並切換頁面\n• 否: 捨棄變更並切換頁面\n• 取消: 留在當前頁面",
                    dialog_type="question",
                    buttons=("是", "否", "取消")
                )
                result = dialog.get_result()
                
                if result == "取消" or result is None:
                    return  # 不切換頁面(包含點擊X關閉窗口)
                elif result == "是":
                    # 保存所有變更（不顯示對話框）
                    if self.backup_settings_changed:
                        self.save_backup_settings(show_dialog=False)
                    if self.update_settings_changed:
                        self.save_update_settings(show_dialog=False)
                elif result == "否":
                    # 捨棄變更,重新載入設定
                    self.reload_backup_update_settings()
        
        # 切換頁面
        for page in self.pages.values():
            page.grid_remove()
        self.pages[page_name].grid()
        
        # 更新按鈕狀態 - 使用更醒目的選中效果
        page_display_names = {
            "伺服器狀態": "伺服器狀態",
            "伺服器設定": "伺服器設定",
            "備份與更新": "備份與更新",
            "控制面板設定": "控制面板設定"
        }
        
        for btn in self.nav_buttons:
            btn_text = btn.cget("text")
            is_active = btn_text == page_display_names.get(page_name, page_name)
            
            if is_active:
                btn.configure(
                    fg_color=("#FFFFFF", "#3D3D5C"),
                    text_color=("#2B5278", "#FFFFFF"),
                    hover_color=("#F0F0F0", "#35354E")
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=("#FFFFFF", "#FFFFFF"),
                    hover_color=("#3A6EA5", "#2D2D44")
                )

    
    def create_status_page(self):
        """建立伺服器狀態頁面"""
        page = ctk.CTkScrollableFrame(self.content_frame, corner_radius=0, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        page.grid_columnconfigure(0, weight=1)
        self.pages["伺服器狀態"] = page
        
        # 控制台輸出卡片（包含標題右側的狀態資訊）
        console_card = ctk.CTkFrame(page, corner_radius=15, fg_color=("#E8E8E8", "#2B2B2B"))
        console_card.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        console_card.grid_rowconfigure(1, weight=1)  # 控制台輸出佔主要空間
        console_card.grid_columnconfigure(0, weight=1)
        
        # 設定最小高度以顯示更多內容
        console_card.configure(height=380)
        
        # 標題列（包含狀態燈號、難度和按鈕）
        header_frame = ctk.CTkFrame(console_card, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15,5))
        header_frame.grid_columnconfigure(2, weight=1)
        
        # 左側：狀態燈號 + 標題
        left_title_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        left_title_frame.grid(row=0, column=0, sticky="w")
        
        # 狀態燈號（圓圈）
        self.status_indicator = ctk.CTkLabel(
            left_title_frame,
            text="●",
            font=ctk.CTkFont(size=18),
            text_color="#DC3545"  # 紅色 = 停止
        )
        self.status_indicator.pack(side="left", padx=(0,8))
        
        # 標題
        ctk.CTkLabel(left_title_frame, text="控制台", 
                    font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        
        # 中間：難度選擇
        difficulty_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        difficulty_frame.grid(row=0, column=1, sticky="w", padx=(20,0))
        
        ctk.CTkLabel(difficulty_frame, text="難度:", 
                    font=ctk.CTkFont(size=12)).pack(side="left", padx=(0,5))
        
        current_difficulty = self.server_properties.get("difficulty", "normal")
        self.difficulty_var = ctk.StringVar(value=current_difficulty)
        
        difficulties = ["peaceful", "easy", "normal", "hard"]
        self.difficulty_menu = ctk.CTkOptionMenu(difficulty_frame, values=difficulties, 
                                                 variable=self.difficulty_var,
                                                 command=self.change_difficulty,
                                                 height=30, width=120)
        self.difficulty_menu.pack(side="left")
        
        # 右側：伺服器控制按鈕 + 版本
        right_controls_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        right_controls_frame.grid(row=0, column=3, sticky="e")
        
        # 按鈕組
        button_frame = ctk.CTkFrame(right_controls_frame, fg_color="transparent")
        button_frame.pack(side="left", padx=(0,15))
        
        # 啟動/停止切換按鈕
        self.toggle_server_btn = ctk.CTkButton(
            button_frame, 
            text="啟動", 
            command=self.toggle_server, 
            width=90, 
            height=32,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#28A745", 
            hover_color="#218838"
        )
        self.toggle_server_btn.pack(side="left", padx=2)
        
        # 重啟按鈕
        self.restart_btn = ctk.CTkButton(
            button_frame, 
            text="重新啟動", 
            command=self.restart_server, 
            width=120, 
            height=32,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#17A2B8", 
            hover_color="#138496"
        )
        self.restart_btn.pack(side="left", padx=2)
        
        # 版本資訊
        version_frame = ctk.CTkFrame(right_controls_frame, fg_color="transparent")
        version_frame.pack(side="left")
        
        version_label_title = ctk.CTkLabel(
            version_frame,
            text="版本:",
            font=ctk.CTkFont(size=11)
        )
        version_label_title.pack(side="left", padx=(0,3))
        
        self.version_label = ctk.CTkLabel(
            version_frame,
            text="未知",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.version_label.pack(side="left")
        
        # 控制台輸出區
        self.console_output = ctk.CTkTextbox(console_card, font=("Consolas", 11),
                                            fg_color=("#F5F5F5", "#1E1E1E"),
                                            height=330)
        self.console_output.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0,10))
        
        # 命令輸入區（合併到控制台底部）
        command_frame = ctk.CTkFrame(console_card, fg_color="transparent")
        command_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(0,15))
        command_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(command_frame, text="", 
                    font=ctk.CTkFont(size=14)).grid(row=0, column=0, padx=(0,8))
        
        self.command_entry = ctk.CTkEntry(command_frame, height=35, 
                                         font=ctk.CTkFont(size=13),
                                         placeholder_text="輸入伺服器命令...")
        self.command_entry.grid(row=0, column=1, sticky="ew")
        self.command_entry.bind("<Return>", lambda e: self.send_command())
        
        self.send_command_btn = ctk.CTkButton(command_frame, text="發送", command=self.send_command, 
                     width=80, height=35,
                     font=ctk.CTkFont(size=13, weight="bold"))
        self.send_command_btn.grid(row=0, column=2, padx=(10,0))

        
        # 玩家管理卡片（整合在線和離線玩家）
        players_management_card = ctk.CTkFrame(page, corner_radius=15, fg_color=("#E8E8E8", "#2B2B2B"))
        players_management_card.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        players_management_card.grid_rowconfigure(1, weight=1)
        players_management_card.grid_columnconfigure(0, weight=1)
        
        # 設定最小高度以顯示更多內容
        players_management_card.configure(height=400)
        
        # 標題列（包含在線人數和保存按鈕）
        players_header_frame = ctk.CTkFrame(players_management_card, fg_color="transparent")
        players_header_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15,5))
        players_header_frame.grid_columnconfigure(1, weight=1)
        
        # 左側：燈號 + 標題
        left_title_frame = ctk.CTkFrame(players_header_frame, fg_color="transparent")
        left_title_frame.grid(row=0, column=0, sticky="w")
        
        # 在線狀態燈號（圓圈）
        self.players_online_indicator = ctk.CTkLabel(
            left_title_frame,
            text="●",
            font=ctk.CTkFont(size=18),
            text_color="#6C757D"  # 灰色 = 無人在線（與玩家離線狀態一致）
        )
        self.players_online_indicator.pack(side="left", padx=(0,8))
        
        # 標題
        ctk.CTkLabel(left_title_frame, text="玩家管理", 
                    font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        
        # 右側：在線人數 + 保存按鈕
        right_controls = ctk.CTkFrame(players_header_frame, fg_color="transparent")
        right_controls.grid(row=0, column=2, sticky="e")
        
        # 在線人數
        ctk.CTkLabel(right_controls, text="在線:", 
                    font=ctk.CTkFont(size=12)).pack(side="left", padx=(0,3))
        
        self.players_label = ctk.CTkLabel(
            right_controls,
            text="0/10",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.players_label.pack(side="left", padx=(0,15))
        
        # 保存按鈕
        ctk.CTkButton(
            right_controls,
            text="儲存",
            command=self.save_players_permissions,
            width=90,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#007BFF",
            hover_color="#0056b3"
        ).pack(side="left")
        
        # 玩家列表框（包含在線和離線玩家）
        self.players_management_frame = ctk.CTkScrollableFrame(
            players_management_card, 
            fg_color=("#F5F5F5", "#1E1E1E"),
            corner_radius=10,
            height=300
        )
        self.players_management_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0,15))
        self.players_management_frame.grid_columnconfigure(0, weight=1)
        
        self.players_management_widgets = []
        
        self.update_players_management_display()

    
    def create_settings_page(self):
        """建立伺服器設定頁面（統一風格）"""
        page = ctk.CTkFrame(self.content_frame, corner_radius=0, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        self.pages["伺服器設定"] = page

        # 標題列（包含儲存按鈕）
        header_frame = ctk.CTkFrame(page, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20,10))
        header_frame.grid_columnconfigure(0, weight=1)
        
        # 左側標題
        ctk.CTkLabel(header_frame, text="伺服器設定", 
                    font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        
        # 右側儲存按鈕
        ctk.CTkButton(
            header_frame, 
            text="儲存設定",
            command=self.save_server_settings,
            width=120,
            height=38,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#007BFF",
            hover_color="#0056b3"
        ).pack(side="right")

        settings_card = ctk.CTkFrame(page, corner_radius=15, fg_color=("#E8E8E8", "#2B2B2B"))
        settings_card.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0,20))
        settings_card.grid_columnconfigure(0, weight=1)
        settings_card.grid_rowconfigure(0, weight=1)
        
        left_frame = ctk.CTkScrollableFrame(settings_card, corner_radius=10, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        left_frame.grid_columnconfigure(1, weight=1)
        left_frame.grid_rowconfigure(999, weight=1)

        ctk.CTkLabel(left_frame, text="屬性設定", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=10, pady=(10,10)
        )
        self.load_server_properties()
        self.settings_vars = {}
        
        # 檢查 server.properties 是否存在
        if not self.server_properties:
            # 顯示提示訊息
            info_label = ctk.CTkLabel(
                left_frame, 
                text="未找到 server.properties 檔案\n\n請先啟動伺服器以生成配置文件，\n或下載安裝 Bedrock Server。",
                font=ctk.CTkFont(size=14),
                text_color="gray"
            )
            info_label.grid(row=1, column=0, columnspan=2, padx=20, pady=50)
            return
        
        row = 1

        # 依 server.properties 逐項添加
        properties_items = [
            # key, label, widget_type, 中文說明
            ("server-name", "伺服器名稱", "entry", "用作伺服器名稱，任意字串（不可含分號）"),
            ("gamemode", "遊戲模式", ["survival", "creative", "adventure"], "新玩家的遊戲模式"),
            ("force-gamemode", "強制遊戲模式", ["true", "false"], "強制所有玩家使用 server.properties 設定的遊戲模式"),
            ("difficulty", "難度", ["peaceful", "easy", "normal", "hard"], "世界難度"),
            ("allow-cheats", "允許作弊", ["true", "false"], "允許使用作弊指令"),
            ("max-players", "最大玩家數", "entry", "最大同時在線玩家數"),
            ("online-mode", "線上模式", ["true", "false"], "是否需 Xbox Live 驗證"),
            ("allow-list", "白名單啟用", ["true", "false"], "是否啟用白名單（allowlist.json）"),
            ("server-port", "伺服器端口", "entry", "IPv4 監聽端口"),
            ("server-portv6", "伺服器端口IPv6", "entry", "IPv6 監聽端口"),
            ("enable-lan-visibility", "啟用LAN可見", ["true", "false"], "是否回應 LAN 伺服器搜尋"),
            ("view-distance", "視距", "entry", "最大視距（區塊）"),
            ("tick-distance", "更新距離", "entry", "世界更新距離（區塊）"),
            ("player-idle-timeout", "閒置踢出時間", "entry", "玩家閒置多久後踢出（分鐘，0為不踢）"),
            ("max-threads", "最大執行緒數", "entry", "伺服器可用最大執行緒數"),
            ("level-name", "世界名稱", "entry", "世界名稱（檔案夾名）"),
            ("level-seed", "世界種子", "entry", "世界種子（隨機生成用）"),
            ("default-player-permission-level", "預設權限", ["visitor", "member", "operator"], "新玩家預設權限"),
            ("texturepack-required", "強制材質包", ["true", "false"], "是否強制玩家使用世界材質包"),
            ("content-log-file-enabled", "啟用內容日誌", ["true", "false"], "啟用內容錯誤日誌"),
            ("compression-threshold", "壓縮閾值", "entry", "網路封包壓縮最小大小"),
            ("compression-algorithm", "壓縮演算法", ["zlib", "snappy"], "網路壓縮演算法"),
            ("server-authoritative-movement-strict", "嚴格移動校正", ["true", "false"], "更嚴格校正玩家位置"),
            ("server-authoritative-dismount-strict", "嚴格下坐騎校正", ["true", "false"], "更嚴格校正下坐騎位置"),
            ("server-authoritative-entity-interactions-strict", "嚴格實體互動校正", ["true", "false"], "更嚴格校正實體互動"),
            ("player-position-acceptance-threshold", "玩家位置容忍度", "entry", "伺服器與玩家位置差異容忍度"),
            ("player-movement-action-direction-threshold", "玩家攻擊方向容忍度", "entry", "玩家攻擊與視角方向容忍度"),
            ("server-authoritative-block-breaking-pick-range-scalar", "方塊破壞距離比例", "entry", "方塊破壞距離比例"),
            ("chat-restriction", "聊天限制", ["None", "Dropped", "Disabled"], "聊天限制等級"),
            ("disable-player-interaction", "禁用玩家互動", ["true", "false"], "是否禁用玩家間互動"),
            ("client-side-chunk-generation-enabled", "客戶端生成區塊", ["true", "false"], "允許客戶端生成視覺區塊"),
            ("block-network-ids-are-hashes", "方塊ID使用雜湊", ["true", "false"], "方塊網路ID是否使用雜湊"),
            ("disable-persona", "禁用個人化", ["true", "false"], "僅內部使用"),
            ("disable-custom-skins", "禁用自訂皮膚", ["true", "false"], "禁用自訂皮膚"),
            ("server-build-radius-ratio", "伺服器生成半徑比例", ["Disabled"], "伺服器生成區塊比例"),
            ("allow-outbound-script-debugging", "允許外部腳本除錯", ["true", "false"], "允許外部腳本除錯"),
            ("allow-inbound-script-debugging", "允許內部腳本除錯", ["true", "false"], "允許內部腳本除錯"),
            ("script-debugger-auto-attach", "腳本除錯自動連接", ["disabled", "connect", "listen"], "腳本除錯自動連接模式"),
            ("disable-client-vibrant-visuals", "禁用Vibrant Visuals", ["true", "false"], "禁用客戶端高畫質特效"),
        ]
        for key, label, widget_type, desc in properties_items:
            ctk.CTkLabel(left_frame, text=label + "：", font=ctk.CTkFont(size=14)).grid(
                row=row, column=0, padx=10, pady=5, sticky="w")
            if isinstance(widget_type, list):
                var = ctk.StringVar(value=self.server_properties.get(key, widget_type[0]))
                widget = ctk.CTkOptionMenu(left_frame, values=widget_type, variable=var, width=220)
            else:
                var = ctk.StringVar(value=self.server_properties.get(key, ""))
                widget = ctk.CTkEntry(left_frame, textvariable=var, width=220)
            widget.grid(row=row, column=1, padx=10, pady=5, sticky="w")
            self.settings_vars[key] = var
            row += 1
            # 中文說明
            ctk.CTkLabel(left_frame, text=desc, font=ctk.CTkFont(size=12), text_color="gray70").grid(
                row=row, column=0, columnspan=2, padx=20, pady=(0,8), sticky="w")
            row += 1
    
    

    def create_backup_page(self):
        """建立備份與更新頁面"""
        page = ctk.CTkScrollableFrame(self.content_frame, corner_radius=0, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        self.pages["備份與更新"] = page

        # ========== 備份區域 ========== 
        backup_card = ctk.CTkFrame(page, corner_radius=15, fg_color=("#E8E8E8", "#2B2B2B"))
        backup_card.grid(row=0, column=0, sticky="ew", padx=20, pady=15)
        backup_card.grid_columnconfigure(1, weight=1)
        
        # 標題列（包含手動備份按鈕和提前通知滑條）
        backup_header_frame = ctk.CTkFrame(backup_card, fg_color="transparent")
        backup_header_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=20, pady=(20,10))
        backup_header_frame.grid_columnconfigure(1, weight=1)
        
        # 左側標題
        ctk.CTkLabel(backup_header_frame, text="世界備份", 
                    font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, sticky="w")
        
        # 中間提前通知滑條
        notify_container = ctk.CTkFrame(backup_header_frame, fg_color="transparent")
        notify_container.grid(row=0, column=1, padx=20, sticky="e")
        
        ctk.CTkLabel(notify_container, text="提前通知:", 
                    font=ctk.CTkFont(size=12)).pack(side="left", padx=(0,5))
        
        self.backup_notify_var = ctk.IntVar(value=self.config.get("backup_notify_seconds", 5))
        self.backup_notify_slider = ctk.CTkSlider(
            notify_container, 
            from_=0, 
            to=60, 
            number_of_steps=60,
            variable=self.backup_notify_var,
            width=120,
            command=self.on_backup_notify_change
        )
        self.backup_notify_slider.pack(side="left", padx=5)
        
        self.backup_notify_label = ctk.CTkLabel(
            notify_container, 
            text=f"{self.backup_notify_var.get()}秒",
            font=ctk.CTkFont(size=12),
            width=40
        )
        self.backup_notify_label.pack(side="left")
        
        # 右側手動備份按鈕
        self.manual_backup_btn = ctk.CTkButton(
            backup_header_frame, 
            text="手動備份",
            command=self.manual_backup_with_prompt,
            width=110,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#17A2B8",
            hover_color="#138496"
        )
        self.manual_backup_btn.grid(row=0, column=2, sticky="e")
        
        # 自動備份開關
        self.auto_backup_var = ctk.BooleanVar(value=self.config["auto_backup_enabled"])
        auto_backup_switch = ctk.CTkSwitch(backup_card, text="啟用自動備份", 
                                          variable=self.auto_backup_var,
                                          command=self.toggle_auto_backup,
                                          font=ctk.CTkFont(size=13))
        auto_backup_switch.grid(row=1, column=0, columnspan=3, padx=20, pady=8, sticky="w")
        
        # 備份頻率類型
        ctk.CTkLabel(backup_card, text="備份頻率:", 
                    font=ctk.CTkFont(size=13)).grid(
            row=2, column=0, padx=20, pady=8, sticky="w")
        self.backup_freq_type_var = ctk.StringVar(value=self.config["backup_frequency_type"])
        self.backup_freq_menu = ctk.CTkOptionMenu(backup_card, 
                                            values=["hours", "daily", "weekly", "monthly"],
                                            variable=self.backup_freq_type_var,
                                            command=self.on_backup_frequency_type_change,
                                            width=150, height=32)
        self.backup_freq_menu.grid(row=2, column=1, padx=10, pady=8, sticky="w")
        
        # 動態頻率設定區域
        self.backup_freq_frame = ctk.CTkFrame(backup_card, fg_color="transparent")
        self.backup_freq_frame.grid(row=3, column=0, columnspan=3, padx=20, pady=8, sticky="ew")
        self.update_backup_frequency_ui(self.config["backup_frequency_type"])
        
        # 最大容量設定（僅針對自動備份）
        size_frame = ctk.CTkFrame(backup_card, fg_color="transparent")
        size_frame.grid(row=4, column=0, columnspan=3, padx=20, pady=8, sticky="w")
        
        ctk.CTkLabel(size_frame, text="最大容量 (GB):", 
                    font=ctk.CTkFont(size=13)).pack(side="left", padx=(0,10))
        
        # 儲存當前設定值用於比較
        self.saved_backup_size = self.config["backup_max_size_gb"]
        self.backup_size_var = ctk.DoubleVar(value=self.saved_backup_size)
        
        self.backup_size_slider = ctk.CTkSlider(
            size_frame, 
            from_=0.5, 
            to=100, 
            number_of_steps=199,
            variable=self.backup_size_var,
            width=200,
            command=self.on_backup_size_slider_change
        )
        self.backup_size_slider.pack(side="left", padx=10)
        
        self.backup_size_label = ctk.CTkLabel(
            size_frame, 
            text=f"{self.backup_size_var.get():.1f} GB",
            font=ctk.CTkFont(size=13),
            width=70
        )
        self.backup_size_label.pack(side="left", padx=5)
        
        # 容量使用百分比（移到最大容量下方）
        capacity_frame = ctk.CTkFrame(backup_card, fg_color="transparent")
        capacity_frame.grid(row=5, column=0, columnspan=3, padx=20, pady=(0,8), sticky="ew")
        
        ctk.CTkLabel(capacity_frame, text="容量使用:", 
                    font=ctk.CTkFont(size=13)).pack(side="left", padx=(0,10))
        
        self.backup_capacity_bar = ctk.CTkProgressBar(capacity_frame, width=200, height=15)
        self.backup_capacity_bar.pack(side="left", padx=5)
        self.backup_capacity_bar.set(0)
        
        self.backup_capacity_label = ctk.CTkLabel(
            capacity_frame, 
            text="0.0%",
            font=ctk.CTkFont(size=13),
            width=120
        )
        self.backup_capacity_label.pack(side="left", padx=(5,0))
        
        # 初始化容量進度條
        self.update_backup_capacity_bar()
        
        # 儲存設定按鈕（放在所有設定項目下方）
        save_backup_settings_frame = ctk.CTkFrame(backup_card, fg_color="transparent")
        save_backup_settings_frame.grid(row=6, column=0, columnspan=3, padx=20, pady=(10,8), sticky="ew")
        
        self.backup_save_settings_btn = ctk.CTkButton(
            save_backup_settings_frame,
            text="儲存備份設定",
            command=self.save_backup_settings,
            width=150,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#6C757D",
            hover_color="#5A6268",
            state="disabled"  # 初始為禁用
        )
        self.backup_save_settings_btn.pack(side="left")
        
        # 備份時間資訊
        backup_time_info_frame = ctk.CTkFrame(backup_card, corner_radius=10, 
                                             fg_color=("#D0D0D0", "#1E1E1E"))
        backup_time_info_frame.grid(row=7, column=0, columnspan=3, padx=20, pady=10, sticky="ew")
        backup_time_info_frame.grid_columnconfigure(1, weight=1)
        
        # 上次手動備份
        ctk.CTkLabel(backup_time_info_frame, text="上次手動備份:", 
                    font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, padx=15, pady=8, sticky="w")
        self.last_manual_backup_label = ctk.CTkLabel(backup_time_info_frame, text="尚未備份",
                                                     font=ctk.CTkFont(size=13))
        self.last_manual_backup_label.grid(row=0, column=1, padx=10, pady=8, sticky="w")
        
        # 上次自動備份
        ctk.CTkLabel(backup_time_info_frame, text="上次自動備份:", 
                    font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=1, column=0, padx=15, pady=8, sticky="w")
        self.last_auto_backup_label = ctk.CTkLabel(backup_time_info_frame, text="尚未備份",
                                                   font=ctk.CTkFont(size=13))
        self.last_auto_backup_label.grid(row=1, column=1, padx=10, pady=8, sticky="w")
        
        # 下次自動備份
        ctk.CTkLabel(backup_time_info_frame, text="下次自動備份:", 
                    font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=2, column=0, padx=15, pady=8, sticky="w")
        self.next_backup_label = ctk.CTkLabel(backup_time_info_frame, text="未啟用",
                                             font=ctk.CTkFont(size=13))
        self.next_backup_label.grid(row=2, column=1, padx=10, pady=8, sticky="w")
        
        # 初始更新備份時間顯示
        self.update_last_manual_backup_label()
        self.update_last_auto_backup_label()
        self.update_next_backup_time()
        
        # ========== 更新區域 ========== 
        update_card = ctk.CTkFrame(page, corner_radius=15, fg_color=("#E8E8E8", "#2B2B2B"))
        update_card.grid(row=1, column=0, sticky="ew", padx=20, pady=15)
        update_card.grid_columnconfigure(1, weight=1)
        
        # 標題列（包含更新按鈕和提前通知滑條）
        update_header_frame = ctk.CTkFrame(update_card, fg_color="transparent")
        update_header_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=20, pady=(20,10))
        update_header_frame.grid_columnconfigure(1, weight=1)
        
        # 左側標題
        ctk.CTkLabel(update_header_frame, text="伺服器更新", 
                    font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, sticky="w")
        
        # 中間提前通知滑條
        update_notify_container = ctk.CTkFrame(update_header_frame, fg_color="transparent")
        update_notify_container.grid(row=0, column=1, padx=20, sticky="e")
        
        ctk.CTkLabel(update_notify_container, text="提前通知:", 
                    font=ctk.CTkFont(size=12)).pack(side="left", padx=(0,5))
        
        self.update_notify_var = ctk.IntVar(value=self.config["update_notify_minutes"])
        self.update_notify_slider = ctk.CTkSlider(
            update_notify_container, 
            from_=0, 
            to=60, 
            number_of_steps=60,
            variable=self.update_notify_var,
            width=120,
            command=self.on_update_notify_change
        )
        self.update_notify_slider.pack(side="left", padx=5)
        
        self.update_notify_label = ctk.CTkLabel(
            update_notify_container, 
            text=f"{self.update_notify_var.get()}分",
            font=ctk.CTkFont(size=12),
            width=40
        )
        self.update_notify_label.pack(side="left")
        
        # 右側按鈕組
        update_buttons_frame = ctk.CTkFrame(update_header_frame, fg_color="transparent")
        update_buttons_frame.grid(row=0, column=2, sticky="e")
        
        self.check_update_btn = ctk.CTkButton(
            update_buttons_frame, 
            text="檢查更新",
            command=self.check_update,
            width=100,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#17A2B8",
            hover_color="#138496"
        )
        self.check_update_btn.pack(side="left", padx=(0,8))
        
        self.force_update_btn = ctk.CTkButton(
            update_buttons_frame, 
            text="手動更新",
            command=self.toggle_force_update,
            width=100,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#17A2B8",
            hover_color="#138496"
        )
        self.force_update_btn.pack(side="left")
        
        # 自動更新開關
        self.auto_update_var = ctk.BooleanVar(value=self.config["auto_update_enabled"])
        auto_update_switch = ctk.CTkSwitch(update_card, text="啟用自動更新檢查", 
                                          variable=self.auto_update_var,
                                          command=self.toggle_auto_update,
                                          font=ctk.CTkFont(size=13))
        auto_update_switch.grid(row=1, column=0, columnspan=3, padx=20, pady=8, sticky="w")
        
        # 更新頻率類型
        ctk.CTkLabel(update_card, text="檢查頻率:", 
                    font=ctk.CTkFont(size=13)).grid(
            row=2, column=0, padx=20, pady=8, sticky="w")
        self.update_freq_type_var = ctk.StringVar(value=self.config["update_frequency_type"])
        self.update_freq_menu = ctk.CTkOptionMenu(update_card, 
                                            values=["hours", "daily", "weekly", "monthly"],
                                            variable=self.update_freq_type_var,
                                            command=self.on_update_frequency_type_change,
                                            width=150, height=32)
        self.update_freq_menu.grid(row=2, column=1, padx=10, pady=8, sticky="w")
        
        # 動態頻率設定區域
        self.update_freq_frame = ctk.CTkFrame(update_card, fg_color="transparent")
        self.update_freq_frame.grid(row=3, column=0, columnspan=3, padx=20, pady=8, sticky="ew")
        self.update_update_frequency_ui(self.config["update_frequency_type"])
        
        # 儲存設定按鈕（放在所有設定項目下方）
        save_update_settings_frame = ctk.CTkFrame(update_card, fg_color="transparent")
        save_update_settings_frame.grid(row=4, column=0, columnspan=3, padx=20, pady=(10,8), sticky="ew")
        
        self.update_save_settings_btn = ctk.CTkButton(
            save_update_settings_frame,
            text="儲存更新設定",
            command=self.save_update_settings,
            width=150,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#6C757D",
            hover_color="#5A6268",
            state="disabled"  # 初始為禁用
        )
        self.update_save_settings_btn.pack(side="left")
        
        # 版本資訊
        version_info_frame = ctk.CTkFrame(update_card, corner_radius=10, 
                                         fg_color=("#D0D0D0", "#1E1E1E"))
        version_info_frame.grid(row=5, column=0, columnspan=3, padx=20, pady=10, sticky="ew")
        version_info_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(version_info_frame, text="目前版本:", 
                    font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, padx=15, pady=8, sticky="w")
        self.current_version_label = ctk.CTkLabel(version_info_frame, text="未知",
                                                  font=ctk.CTkFont(size=13))
        self.current_version_label.grid(row=0, column=1, padx=10, pady=8, sticky="w")

        ctk.CTkLabel(version_info_frame, text="最新版本:", 
                    font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=1, column=0, padx=15, pady=8, sticky="w")
        self.latest_version_label = ctk.CTkLabel(version_info_frame, text="未檢查",
                                                font=ctk.CTkFont(size=13))
        self.latest_version_label.grid(row=1, column=1, padx=10, pady=8, sticky="w")
        
        # 初始化控件啟用/禁用狀態
        self.after(100, lambda: self.toggle_auto_backup())
        self.after(100, lambda: self.toggle_auto_update())




    def create_console_settings_page(self):
        """建立控制面板設定頁面"""
        page = ctk.CTkFrame(self.content_frame, corner_radius=0, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        page.grid_rowconfigure(2, weight=1)
        page.grid_columnconfigure(0, weight=1)
        self.pages["控制面板設定"] = page

        # 主卡片
        main_card = ctk.CTkFrame(page, corner_radius=15, fg_color=("#E8E8E8", "#2B2B2B"))
        main_card.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=10, pady=10)
        main_card.grid_rowconfigure(2, weight=1)
        main_card.grid_columnconfigure(0, weight=1)

        # 標題
        ctk.CTkLabel(main_card, text="控制面板設定", 
                    font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, padx=20, pady=(20,15), sticky="ew"
        )

        # 主題設定卡片
        theme_card = ctk.CTkFrame(main_card, corner_radius=12, 
                                 fg_color=("#D8D8D8", "#1E1E1E"))
        theme_card.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        theme_card.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(theme_card, text="外觀主題", 
                    font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=20, pady=15, sticky="w"
        )
        # 從配置文件加載主題設定
        self.theme_var = ctk.StringVar(value=self.config.get("theme", "dark"))
        theme_menu = ctk.CTkOptionMenu(
            theme_card,
            values=["light", "dark", "system"],
            variable=self.theme_var,
            command=self.change_theme,
            width=150,
            height=35,
            font=ctk.CTkFont(size=13)
        )
        theme_menu.grid(row=0, column=1, padx=20, pady=15, sticky="w")

        # 控制面板記錄卡片
        log_card = ctk.CTkFrame(main_card, corner_radius=12, 
                               fg_color=("#D8D8D8", "#1E1E1E"))
        log_card.grid(row=2, column=0, sticky="nsew", padx=20, pady=10)
        log_card.grid_rowconfigure(1, weight=1)
        log_card.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(log_card, text="控制面板記錄", 
                    font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=20, pady=(15,10), sticky="w")
        
        self.log_text = ctk.CTkTextbox(log_card, height=250, 
                                       font=("Consolas", 11),
                                       fg_color=("#F5F5F5", "#0F0F0F"))
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0,15))

        # 資訊卡片
        info_card = ctk.CTkFrame(main_card, corner_radius=12, 
                                fg_color=("#D8D8D8", "#1E1E1E"))
        info_card.grid(row=3, column=0, sticky="ew", padx=20, pady=(10,20))
        info_card.grid_columnconfigure(0, weight=1)
        
        info_text = (
            "BDS Console - Minecraft Bedrock Server 管理面板 v1.0\n\n"
            "功能特點:\n"
            "  • 即時監控伺服器狀態\n"
            "  • 圖形化設定編輯器\n"
            "  • 玩家許可權管理\n"
            "  • 自動/手動備份\n"
            "  • 一鍵更新伺服器"
        )
        ctk.CTkLabel(info_card, text=info_text, justify="left",
                    font=ctk.CTkFont(size=13)).grid(
            row=0, column=0, padx=20, pady=15, sticky="w")

    
    def load_server_properties(self):
        """載入 server.properties"""
        properties_file = self.server_dir / "server.properties"
        self.server_properties = {}
        
        if properties_file.exists():
            with open(properties_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        self.server_properties[key] = value
        else:
            # 檢查伺服器是否存在
            server_exe = self.server_dir / "bedrock_server.exe"
            if server_exe.exists():
                # 伺服器存在但缺少 server.properties，這是錯誤
                self.log_message("錯誤：找不到 server.properties 檔案")
            # 如果伺服器不存在，將在啟動時處理
    
    def save_server_settings(self):
        """儲存伺服器設定"""
        try:
            # 備份舊設定
            self.backup_server_settings()
            
            # 更新設定
            for key, var in self.settings_vars.items():
                self.server_properties[key] = var.get()
            
            # 寫入檔案
            properties_file = self.server_dir / "server.properties"
            with open(properties_file, 'w', encoding='utf-8') as f:
                f.write("# Minecraft Bedrock Server Properties\n")
                for key, value in self.server_properties.items():
                    f.write(f"{key}={value}\n")
            
            self.show_info("成功", "設定已儲存,伺服器將重新啟動")
            self.restart_server()
            
        except Exception as e:
            self.show_error("錯誤", f"儲存設定失敗: {str(e)}")
    
    def backup_server_settings(self):
        """備份伺服器設定檔"""
        backup_folder = self.backup_dir / "server_settings"
        
        # 刪除舊備份
        for file in backup_folder.glob("*"):
            file.unlink()
        
        # 建立新備份
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        files_to_backup = ["server.properties", "allowlist.json", "permissions.json"]
        
        for filename in files_to_backup:
            src = self.server_dir / filename
            if src.exists():
                dst = backup_folder / f"{timestamp}_{filename}"
                shutil.copy2(src, dst)
    
    
    def load_json_file(self, filepath, default=None):
        """載入JSON檔案"""
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return default if default is not None else {}
        return default if default is not None else {}
    
    def save_json_file(self, filepath, data):
        """儲存JSON檔案"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    
    def _disable_server_operation_buttons(self):
        """禁用伺服器操作按鈕（啟動/停止/重啟）"""
        if hasattr(self, 'toggle_server_btn'):
            self.toggle_server_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
        if hasattr(self, 'restart_btn'):
            self.restart_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
    
    def _enable_server_operation_buttons(self):
        """啟用伺服器操作按鈕（啟動/停止/重啟）"""
        if hasattr(self, 'toggle_server_btn'):
            # 根據伺服器狀態設置正確的顏色
            if self.server_process is None:
                self.toggle_server_btn.configure(state="normal", fg_color="#28A745", hover_color="#218838")
            else:
                self.toggle_server_btn.configure(state="normal", fg_color="#DC3545", hover_color="#C82333")
        if hasattr(self, 'restart_btn'):
            self.restart_btn.configure(state="normal", fg_color="#17A2B8", hover_color="#138496")
    
    def _update_command_entry_state(self):
        """更新命令輸入框和發送按鈕狀態（根據伺服器運行狀態）"""
        if hasattr(self, 'command_entry'):
            if self.server_process is None:
                # 伺服器停止時禁用
                self.command_entry.configure(state="disabled")
            else:
                # 伺服器運行時啟用
                self.command_entry.configure(state="normal")
        
        if hasattr(self, 'send_command_btn'):
            if self.server_process is None:
                # 伺服器停止時禁用並反灰
                self.send_command_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
            else:
                # 伺服器運行時啟用並恢復顏色
                self.send_command_btn.configure(state="normal", fg_color=["#3B8ED0", "#1F6AA5"], hover_color=["#36719F", "#144870"])
    
    def toggle_server(self):
        """切換伺服器狀態（啟動/停止）"""
        if self.server_process is None:
            self.start_server()
        else:
            self.stop_server()
    
    def update_toggle_button(self):
        """更新切換按鈕的外觀"""
        if self.server_process is None:
            # 伺服器已停止，顯示啟動按鈕
            self.toggle_server_btn.configure(
                text="啟動",
                fg_color="#28A745",
                hover_color="#218838"
            )
        else:
            # 伺服器運行中，顯示停止按鈕
            self.toggle_server_btn.configure(
                text="停止",
                fg_color="#DC3545",
                hover_color="#C82333"
            )
    
    def start_server(self):
        """啟動伺服器"""
        if self.server_process is not None:
            self.show_warning("警告", "伺服器已在運行中")
            return
        
        try:
            # 設置操作進行中狀態
            self.server_operation_in_progress = True
            self._disable_server_operation_buttons()
            
            self.update_status("啟動", "yellow")
            self.log_message("正在啟動伺服器...")
            
            server_exe = self.server_dir / "bedrock_server.exe"
            if not server_exe.exists():
                # 詢問是否自動下載
                result = self.ask_yes_no(
                    "找不到伺服器檔案",
                    "找不到 bedrock_server.exe\n\n是否自動下載最新版本的 Bedrock Server？\n\n點擊「是」將自動下載並安裝\n點擊「否」將退出程式"
                )
                
                if result:
                    # 使用者選擇下載
                    self.log_message("自動下載伺服器...")
                    threading.Thread(target=self._auto_download_and_install_server, daemon=True).start()
                else:
                    # 使用者選擇不下載，退出程式
                    self.log_message("找不到伺服器檔案，程式即將退出...")
                    self.show_info("提示", "程式將退出")
                    self.destroy()
                
                self.update_status("停止", "red")
                return
            
            # 檢查是否需要執行啟動前備份
            if self._check_and_perform_startup_backup():
                self.log_message("啟動前備份已完成，繼續啟動伺服器...")
            
            # 啟動伺服器進程
            # 在 Windows 上設定 CREATE_NO_WINDOW 來隱藏命令提示字元視窗
            creation_flags = CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            
            self.server_process = subprocess.Popen(
                [str(server_exe)],
                cwd=str(self.server_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creation_flags
            )
            
            # 啟動輸出讀取執行緒
            threading.Thread(target=self.read_server_output, daemon=True).start()
            
            self.update_toggle_button()
            self._update_command_entry_state()
            self.log_message("伺服器進程已啟動，等待伺服器初始化...")
            
            # 啟動後同步難度顯示（延遲執行，確保伺服器已初始化）
            self.after(5000, self.sync_difficulty_after_restart)
            
            # 注意：狀態將由 parse_server_output 檢測到 "Server started" 時更新
            
        except Exception as e:
            self.show_error("錯誤", f"啟動失敗: {str(e)}")
            self.server_operation_in_progress = False
            self._enable_server_operation_buttons()
            self.update_status("停止", "red")
            self.update_toggle_button()
    
    def _check_and_perform_startup_backup(self):
        """檢查是否需要在啟動前執行備份
        如果上次備份時間已超過設定週期，則立即執行備份（忽略提前通知）
        
        Returns:
            bool: 是否執行了備份
        """
        if not self.config["auto_backup_enabled"]:
            return False
        
        if not self.last_auto_backup_time:
            # 如果從未執行過自動備份，執行一次
            self.log_message("檢測到從未執行自動備份，啟動前執行首次備份...")
            self._perform_backup(is_auto=True)
            return True
        
        from datetime import datetime, timedelta
        
        now = datetime.now()
        freq_type = self.config["backup_frequency_type"]
        time_since_last = now - self.last_auto_backup_time
        
        needs_backup = False
        
        if freq_type == "hours":
            hours = self.config["backup_frequency_value"]
            if time_since_last >= timedelta(hours=hours):
                self.log_message(f"上次備份距今已超過 {hours} 小時，啟動前執行備份...")
                needs_backup = True
        
        elif freq_type == "daily":
            if time_since_last >= timedelta(days=1):
                self.log_message("上次備份距今已超過 1 天，啟動前執行備份...")
                needs_backup = True
        
        elif freq_type == "weekly":
            if time_since_last >= timedelta(weeks=1):
                self.log_message("上次備份距今已超過 1 週，啟動前執行備份...")
                needs_backup = True
        
        elif freq_type == "monthly":
            # 粗略計算，30天為一個月
            if time_since_last >= timedelta(days=30):
                self.log_message("上次備份距今已超過 1 個月，啟動前執行備份...")
                needs_backup = True
        
        if needs_backup:
            self._perform_backup(is_auto=True)
            return True
        
        return False
    
    def _disable_operation_buttons(self):
        """禁用操作按鈕（執行期間）"""
        if hasattr(self, 'manual_backup_btn'):
            self.manual_backup_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
        if hasattr(self, 'check_update_btn'):
            self.check_update_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
        if hasattr(self, 'force_update_btn'):
            self.force_update_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
    
    def _enable_operation_buttons(self):
        """啟用操作按鈕（執行完成後）"""
        if hasattr(self, 'manual_backup_btn'):
            self.manual_backup_btn.configure(state="normal", fg_color="#17A2B8", hover_color="#138496")
        if hasattr(self, 'check_update_btn'):
            self.check_update_btn.configure(state="normal", fg_color="#17A2B8", hover_color="#138496")
        if hasattr(self, 'force_update_btn'):
            self.force_update_btn.configure(state="normal", fg_color="#17A2B8", hover_color="#138496")
    
    def stop_server(self):
        """關閉伺服器（UI調用，帶確認）"""
        if self.server_process is None:
            return
        
        # 顯示確認對話框
        result = self.ask_yes_no("確認停止", "確定要停止伺服器嗎？")
        if not result:
            return
        
        # 使用線程執行停止操作，避免UI阻塞
        threading.Thread(target=self._do_stop_server, daemon=True).start()
    
    def _do_stop_server(self):
        """實際執行關閉伺服器的操作"""
        if self.server_process is None:
            return
        
        try:
            # 設置操作進行中狀態
            self.server_operation_in_progress = True
            self.after(0, self._disable_server_operation_buttons)
            
            self.after(0, lambda: self.update_status("關閉", "yellow"))
            self.log_message("正在關閉伺服器...")
            
            # 發送stop命令
            self.server_process.stdin.write("stop\n")
            self.server_process.stdin.flush()
            
            # 等待進程結束
            self.server_process.wait(timeout=30)
            self.server_process = None
            
            # 清空在線玩家列表
            self.online_players_names.clear()
            self.after(0, self.update_players_management_display)
            self.after(0, self.update_player_count)
            
            self.after(0, self.update_toggle_button)
            self.after(0, self._update_command_entry_state)
            self.log_message("伺服器已關閉")
            # 注意：狀態和按鈕將由 parse_server_output 檢測到 "Quit correctly" 時更新
            
        except Exception as e:
            # 強制終止
            if self.server_process:
                self.server_process.kill()
                self.server_process = None
            
            # 清空在線玩家列表
            self.online_players_names.clear()
            self.after(0, self.update_players_management_display)
            self.after(0, self.update_player_count)
            
            self.server_operation_in_progress = False
            self.after(0, self._enable_server_operation_buttons)
            self.after(0, lambda: self.update_status("停止", "red"))
            self.after(0, self.update_toggle_button)
            self.after(0, self._update_command_entry_state)
            self.log_message(f"伺服器已強制關閉: {str(e)}")

    
    def restart_server(self):
        """重新啟動伺服器（帶通知）"""
        if self.server_process is None:
            self.show_warning("警告", "伺服器未運行")
            return
        
        # 顯示確認對話框
        result = self.ask_yes_no("確認重啟", "確定要重新啟動伺服器嗎？")
        if not result:
            return
        
        # 設置重啟標誌
        self.is_restarting = True
        
        # 使用線程執行重啟操作，避免UI阻塞
        threading.Thread(target=self._do_restart_server, daemon=True).start()
    
    def _do_restart_server(self):
        """實際執行重啟操作"""
        try:
            self.log_message("重新啟動伺服器...")
            # 調用內部停止方法（不帶確認框）
            self._do_stop_server()
            time.sleep(2)
            self.start_server()
            # start_server() 會自動同步難度顯示
            # 啟動完成後清除重啟標誌（延遲執行，確保 Server started 已處理）
            self.after(10000, self._clear_restarting_flag)
        except Exception as e:
            self.log_message(f"重啟過程出錯: {str(e)}")
            self.after(0, self._clear_restarting_flag)
    
    def _restart_with_notification(self):
        """重新啟動伺服器（帶提前通知）"""
        try:
            self.log_message("重新啟動伺服器（提前通知玩家）...")
            
            # 30秒倒數
            message = "Server restart in 30 seconds"
            self.broadcast_message(message, "重啟通知")
            time.sleep(10)
            message = "Server restart in 20 seconds"
            self.broadcast_message(message, "重啟通知")
            time.sleep(10)
            message = "Server restart in 10 seconds"
            self.broadcast_message(message, "重啟通知")
            time.sleep(5)
            message = "Server restart in 5 seconds"
            self.broadcast_message(message, "重啟通知")
            time.sleep(1)
            
            # 最後倒數
            for i in range(4, 0, -1):
                time_str = self._format_time_unit(i, "second")
                message = f"Server restart in {time_str}"
                self.broadcast_message(message, "重啟通知")
                time.sleep(1)
            
            # 執行重啟
            self.stop_server()
            time.sleep(2)
            self.start_server()
            # start_server() 會自動同步難度顯示
            # 啟動完成後清除重啟標誌（延遲執行，確保 Server started 已處理）
            self.after(10000, self._clear_restarting_flag)
            
        except Exception as e:
            self.log_message(f"重啟通知流程錯誤: {str(e)}")
            # 如果出錯，直接重啟
            self.stop_server()
            time.sleep(2)
            self.start_server()
            # 出錯時也要清除重啟標誌
            self.after(10000, self._clear_restarting_flag)
    
    def _clear_restarting_flag(self):
        """清除重啟標誌"""
        self.is_restarting = False
        self.log_message("重啟流程結束")
    
    def sync_difficulty_after_restart(self):
        """啟動/重啟後同步難度顯示（不發送命令）"""
        # 重新讀取 server.properties 的難度，並同步到介面顯示
        self.load_server_properties()
        difficulty = self.server_properties.get("difficulty", "normal")
        self.difficulty_var.set(difficulty)
        self.log_message(f"已同步介面難度顯示: {difficulty}")
    
    def read_server_output(self):
        """讀取伺服器輸出"""
        try:
            for line in iter(self.server_process.stdout.readline, ''):
                if not line:
                    break
                
                line = line.strip()
                self.console_output.insert("end", line + "\n")
                self.console_output.see("end")
                
                # 解析輸出
                self.parse_server_output(line)
                
        except Exception as e:
            self.log_message(f"讀取輸出錯誤: {str(e)}")
    
    def parse_server_output(self, line):
        """解析伺服器輸出"""
        # 檢測伺服器狀態變化
        if "Starting Server" in line:
            # 伺服器開始啟動
            self.server_operation_in_progress = True
            self.after(0, self._disable_server_operation_buttons)
            self.after(0, lambda: self.update_status("啟動", "yellow"))
            self.log_message("檢測到：伺服器開始啟動...")
        
        elif "Server started" in line or "Server running" in line:
            # 伺服器啟動完成
            self.server_operation_in_progress = False
            self.is_restarting = False  # 清除重啟標誌
            self.after(0, self._enable_server_operation_buttons)
            self.after(0, self._update_command_entry_state)
            self.after(0, lambda: self.update_status("運行", "green"))
            self.log_message("伺服器啟動完成")
        
        elif "Stopping server" in line or "Stopping Server" in line:
            # 伺服器開始停止
            self.server_operation_in_progress = True
            self.after(0, self._disable_server_operation_buttons)
            self.after(0, lambda: self.update_status("關閉", "yellow"))
            self.log_message("檢測到：伺服器開始關閉...")
        
        elif "Quit correctly" in line:
            # 伺服器正確退出
            if not self.is_restarting:
                # 如果不是重啟過程，則結束操作狀態
                self.server_operation_in_progress = False
                self.after(0, self._enable_server_operation_buttons)
                self.after(0, self._update_command_entry_state)
                self.after(0, lambda: self.update_status("停止", "red"))
                self.log_message("伺服器已正確關閉")
            else:
                # 重啟過程中，保持操作狀態，保持黃色燈號
                self.after(0, lambda: self.update_status("重啟", "yellow"))
                self.log_message("伺服器已關閉，準備重新啟動...")
        
        # 檢測版本 - 格式: [2025-10-12 21:48:08:511 INFO] Version: 1.21.113.1
        if "Version:" in line or "Version :" in line:
            import re
            # 匹配版本號格式 (例如: 1.21.113.1)
            version_pattern = r'Version[:\s]+(\d+\.\d+\.\d+\.\d+)'
            match = re.search(version_pattern, line)
            if match:
                self.server_version = match.group(1)
                self.version_label.configure(text=self.server_version)
                self.current_version_label.configure(text=self.server_version)
                self.log_message(f"檢測到伺服器版本: {self.server_version}")
        
        # 檢測玩家加入/離開
        if "Player connected" in line or "Player disconnected" in line:
            
            # 提取玩家資訊 - 格式: Player connected: PlayerName, xuid: 1234567890
            if "Player connected" in line:
                try:
                    import re
                    # 提取玩家名稱
                    name_match = re.search(r'Player connected:\s*([^,]+)', line)
                    # 提取 XUID
                    xuid_match = re.search(r'xuid:\s*(\d+)', line, re.IGNORECASE)
                    
                    if name_match and xuid_match:
                        name = name_match.group(1).strip()
                        xuid = xuid_match.group(1).strip()
                        
                        # 獲取當前時間
                        from datetime import datetime
                        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        # 添加到在線玩家列表（確保添加成功）
                        if name not in self.online_players_names:
                            self.online_players_names.append(name)
                        
                        player_exists = False
                        for player in self.player_list:
                            if player.get("xuid") == xuid:
                                player["last_online"] = current_time
                                player_exists = True
                                break
                        
                        if not player_exists:
                            self.player_list.append({
                                "name": name,
                                "xuid": xuid,
                                "last_online": current_time
                            })
                            self.log_message(f"新玩家加入: {name} (XUID: {xuid})")
                            self.auto_add_to_allowlist(name, xuid)
                        
                        self.save_player_list()
                        self.update_player_count()
                        self.update_players_management_display()
                except Exception as e:
                    self.log_message(f"解析玩家資訊失敗: {str(e)}")
            
            # 玩家離開
            if "Player disconnected" in line:
                try:
                    import re
                    name_match = re.search(r'Player disconnected:\s*([^,]+)', line)
                    if name_match:
                        name = name_match.group(1).strip()
                        self.log_message(f"玩家離開: {name}")
                        
                        if name in self.online_players_names:
                            self.online_players_names.remove(name)
                            self.update_player_count()
                            self.update_players_management_display()
                except:
                    pass
            
            self.update_player_count()
        
        # 檢測玩家 spawned（完全進入遊戲）
        if "Player Spawned" in line or "spawned" in line.lower():
            try:
                import re
                # 嘗試多種格式匹配玩家名稱
                # 格式可能是: "Player Spawned: PlayerName" 或 "PlayerName spawned"
                name_match = re.search(r'(?:Player Spawned:\s*|spawned:\s*)([^,\s]+)', line, re.IGNORECASE)
                if not name_match:
                    # 嘗試另一種格式: "PlayerName spawned"
                    name_match = re.search(r'([^\s]+)\s+spawned', line, re.IGNORECASE)
                
                if name_match:
                    name = name_match.group(1).strip()
                    
                    # 檢查是否在更新通知期間，如果是則立即發送通知
                    if self.update_notification_active and self.update_remaining_seconds > 0:
                        threading.Thread(
                            target=self.send_immediate_update_notification,
                            args=(name,),
                            daemon=True
                        ).start()
            except Exception as e:
                self.log_message(f"解析 spawned 訊息失敗: {str(e)}")

    
    def auto_add_to_allowlist(self, name, xuid):
        """自動添加玩家到白名單"""
        try:
            allowlist_file = self.server_dir / "allowlist.json"
            allowlist = self.load_json_file(allowlist_file, [])
            
            if not any(p.get("xuid") == xuid for p in allowlist):
                allowlist.append({
                    "ignoresPlayerLimit": False,
                    "name": name,
                    "xuid": xuid
                })
                self.save_json_file(allowlist_file, allowlist)
            
            permissions_file = self.server_dir / "permissions.json"
            permissions = self.load_json_file(permissions_file, [])
            
            if not any(p.get("xuid") == xuid for p in permissions):
                permissions.append({
                    "permission": "member",
                    "xuid": xuid
                })
                self.save_json_file(permissions_file, permissions)
                
        except Exception as e:
            self.log_message(f"自動添加白名單失敗: {str(e)}")
    
    def update_player_count(self):
        """更新玩家數量"""
        online_count = len(self.online_players_names)
        max_players = self.server_properties.get("max-players", "10")
        self.players_label.configure(text=f"{online_count}/{max_players}")
        
        # 更新玩家在線燈號
        if hasattr(self, 'players_online_indicator'):
            if online_count > 0:
                # 有玩家在線 - 綠燈（與玩家列表在線狀態一致）
                self.players_online_indicator.configure(text_color="#28A745")
            else:
                # 無人在線 - 灰燈（與玩家列表離線狀態一致）
                self.players_online_indicator.configure(text_color="#6C757D")
    
    def update_players_management_display(self):
        """更新玩家管理列表顯示（只從 player_list 讀取玩家）"""
        # 防止重複更新
        if self.update_pending:
            return
        
        self.update_pending = True
        
        # 延遲執行實際更新
        self.after(100, self._do_update_players_management_display)
    
    def _do_update_players_management_display(self):
        """實際執行玩家管理列表更新"""
        try:
            for widget in self.players_management_widgets:
                try:
                    if widget.winfo_exists():
                        widget.destroy()
                except:
                    pass
            self.players_management_widgets.clear()
            self.player_ui_vars.clear()
            
            allowlist = self.load_json_file(self.server_dir / "allowlist.json", [])
            permissions = self.load_json_file(self.server_dir / "permissions.json", [])
            
            header_frame = ctk.CTkFrame(self.players_management_frame, fg_color="transparent")
            header_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
            header_frame.grid_columnconfigure(0, weight=2, minsize=150)
            header_frame.grid_columnconfigure(1, weight=2, minsize=150)
            header_frame.grid_columnconfigure(2, weight=2, minsize=150)
            header_frame.grid_columnconfigure(3, weight=1, minsize=80)
            header_frame.grid_columnconfigure(4, weight=1, minsize=120)
            
            headers = ["狀態 / 玩家", "XUID", "上線時間", "白名單", "權限等級"]
            for i, header in enumerate(headers):
                header_label = ctk.CTkLabel(
                    header_frame,
                    text=header,
                    font=ctk.CTkFont(size=13, weight="bold")
                )
                header_label.grid(row=0, column=i, padx=10, pady=5, sticky="w")
                self.players_management_widgets.append(header_label)
            
            self.players_management_widgets.append(header_frame)
            
            if not self.player_list:
                # 如果沒有玩家，顯示提示
                no_player_label = ctk.CTkLabel(
                    self.players_management_frame, 
                    text="暫無玩家記錄\n\n玩家首次連線後將自動顯示在此處",
                    font=ctk.CTkFont(size=12),
                    text_color="gray"
                )
                no_player_label.grid(row=1, column=0, columnspan=5, pady=20)
                self.players_management_widgets.append(no_player_label)
            else:
                for row_idx, player in enumerate(self.player_list, start=1):
                    name = player.get("name", "Unknown")
                    xuid = player.get("xuid", "")
                    last_online = player.get("last_online", "尚未記錄")
                    
                    is_online = name in self.online_players_names
                    
                    # 玩家框架 - 使用與表頭相同的列配置
                    player_frame = ctk.CTkFrame(
                        self.players_management_frame,
                        fg_color=("#D4EDDA", "#1E3A1E") if is_online else ("#F8F9FA", "#2A2A2A"),
                        corner_radius=8
                    )
                    player_frame.grid(row=row_idx, column=0, sticky="ew", padx=5, pady=3)
                    player_frame.grid_columnconfigure(0, weight=2, minsize=150)
                    player_frame.grid_columnconfigure(1, weight=2, minsize=150)
                    player_frame.grid_columnconfigure(2, weight=2, minsize=150)
                    player_frame.grid_columnconfigure(3, weight=1, minsize=80)
                    player_frame.grid_columnconfigure(4, weight=1, minsize=120)
                    
                    status_frame = ctk.CTkFrame(player_frame, fg_color="transparent")
                    status_frame.grid(row=0, column=0, padx=(10,0), pady=8, sticky="w")
                    
                    status_indicator = ctk.CTkLabel(
                        status_frame,
                        text="●",
                        font=ctk.CTkFont(size=20),
                        text_color=("#28A745", "#28A745") if is_online else ("#6C757D", "#6C757D"),
                        width=20
                    )
                    status_indicator.pack(side="left", padx=(0,5))
                    
                    name_label = ctk.CTkLabel(
                        status_frame,
                        text=name,
                        font=ctk.CTkFont(size=13, weight="bold" if is_online else "normal"),
                        anchor="w"
                    )
                    name_label.pack(side="left")
                    
                    xuid_label = ctk.CTkLabel(
                        player_frame,
                        text=xuid,
                        font=ctk.CTkFont(size=11),
                        anchor="w"
                    )
                    xuid_label.grid(row=0, column=1, padx=10, pady=8, sticky="w")
                    
                    last_online_label = ctk.CTkLabel(
                        player_frame,
                        text=last_online if not is_online else "線上",
                        font=ctk.CTkFont(size=11),
                        anchor="w",
                        text_color=("#28A745", "#28A745") if is_online else "gray"
                    )
                    last_online_label.grid(row=0, column=2, padx=10, pady=8, sticky="w")
                    
                    in_allowlist = any(p.get("xuid") == xuid for p in allowlist)
                    allowlist_var = ctk.BooleanVar(value=in_allowlist)
                    allowlist_check = ctk.CTkCheckBox(
                        player_frame,
                        text="",
                        variable=allowlist_var,
                        width=30
                    )
                    allowlist_check.grid(row=0, column=3, padx=10, pady=8)
                    
                    perm_level = "member"
                    for p in permissions:
                        if p.get("xuid") == xuid:
                            perm_level = p.get("permission", "member")
                            break
                    
                    perm_var = ctk.StringVar(value=perm_level)
                    perm_menu = ctk.CTkOptionMenu(
                        player_frame,
                        values=["visitor", "member", "operator"],
                        variable=perm_var,
                        width=110,
                        height=28
                    )
                    perm_menu.grid(row=0, column=4, padx=10, pady=8)
                    
                    self.player_ui_vars[xuid] = {
                        "allowlist_var": allowlist_var,
                        "perm_var": perm_var
                    }
                    
                    self.players_management_widgets.extend([
                        player_frame, status_frame, status_indicator, name_label, 
                        xuid_label, last_online_label, allowlist_check, perm_menu
                    ])
            
        except Exception as e:
            self.log_message(f"更新玩家管理列表失敗: {str(e)}")
        finally:
            self.update_pending = False
    
    def save_players_permissions(self):
        """儲存玩家權限設定（只使用 self.player_list）"""
        try:
            # 備份
            self.backup_server_settings()
            
            # 建立 allowlist 和 permissions
            allowlist = []
            permissions = []
            
            # 遍歷 self.player_list 並使用 self.player_ui_vars 獲取 UI 狀態
            for player in self.player_list:
                xuid = player.get("xuid", "")
                name = player.get("name", "")
                
                # 🔧 從單獨的 UI 變數字典中獲取值
                if xuid in self.player_ui_vars:
                    ui_vars = self.player_ui_vars[xuid]
                    
                    # 檢查白名單
                    if ui_vars["allowlist_var"].get():
                        allowlist.append({
                            "ignoresPlayerLimit": False,
                            "name": name,
                            "xuid": xuid
                        })
                    
                    # 添加權限
                    permissions.append({
                        "permission": ui_vars["perm_var"].get(),
                        "xuid": xuid
                    })
            
            # 儲存檔案
            self.save_json_file(self.server_dir / "allowlist.json", allowlist)
            self.save_json_file(self.server_dir / "permissions.json", permissions)
            
            self.show_info("成功", "玩家權限已儲存")
            self.log_message("已儲存玩家權限設定")
            
        except Exception as e:
            self.show_error("錯誤", f"儲存權限失敗: {str(e)}")

    
    def send_command(self):
        """發送命令到伺服器"""
        if self.server_process is None:
            self.show_warning("警告", "伺服器未運行")
            return
        
        command = self.command_entry.get().strip()
        if not command:
            return
        
        try:
            self.server_process.stdin.write(command + "\n")
            self.server_process.stdin.flush()
            self.command_entry.delete(0, "end")
            self.log_message(f"已發送命令: {command}")
        except Exception as e:
            self.show_error("錯誤", f"發送命令失敗: {str(e)}")
    
    def change_difficulty(self, difficulty):
        """修改遊戲難度"""
        if self.server_process is not None:
            command = f"difficulty {difficulty}"
            try:
                self.server_process.stdin.write(command + "\n")
                self.server_process.stdin.flush()
                self.log_message(f"難度已更改為: {difficulty}")
            except Exception as e:
                self.log_message(f"更改難度失敗: {str(e)}")
        else:
            self.log_message(f"伺服器未運行，難度選擇僅顯示，不會生效")
    
    def save_server_properties_file(self):
        """單獨儲存 server.properties 檔案（不重啟伺服器）"""
        try:
            properties_file = self.server_dir / "server.properties"
            with open(properties_file, 'w', encoding='utf-8') as f:
                f.write("# Minecraft Bedrock Server Properties\n")
                for key, value in self.server_properties.items():
                    f.write(f"{key}={value}\n")
        except Exception as e:
            self.log_message(f"儲存設定檔失敗: {str(e)}")
    
    def update_status(self, status, color):
        """更新伺服器狀態顯示（圓圈燈號）"""
        self.server_status = status
        color_map = {
            "green": "#28A745",   # 綠色 = 運行中
            "yellow": "#FFC107",  # 黃色 = 啟動中
            "red": "#DC3545"      # 紅色 = 停止
        }
        indicator_color = color_map.get(color, "#808080")  # 預設灰色
        self.status_indicator.configure(text_color=indicator_color)

    
    
    def update_backup_frequency_ui(self, freq_type):
        """更新備份頻率設定介面"""
        # 清除舊的 widget
        for widget in self.backup_freq_frame.winfo_children():
            widget.destroy()
        
        if freq_type == "hours":
            ctk.CTkLabel(self.backup_freq_frame, text="每").grid(row=0, column=0, padx=5)
            self.backup_hours_var = ctk.StringVar(value=str(self.config.get("backup_frequency_value", 6)))
            hours_options = ["1", "2", "3", "4", "6", "8", "12", "24"]
            ctk.CTkOptionMenu(self.backup_freq_frame, variable=self.backup_hours_var,
                            values=hours_options, width=80,
                            command=lambda x: self.check_backup_settings_changed()).grid(row=0, column=1, padx=5)
            ctk.CTkLabel(self.backup_freq_frame, text="小時").grid(row=0, column=2, padx=5)
            
        elif freq_type == "daily":
            ctk.CTkLabel(self.backup_freq_frame, text="每天").grid(row=0, column=0, padx=5)
            self.backup_hour_var = ctk.StringVar(value=str(self.config.get("backup_time_hour", 3)))
            self.backup_minute_var = ctk.StringVar(value=str(self.config.get("backup_time_minute", 0)))
            hour_options = [str(i) for i in range(24)]
            minute_options = ["0", "15", "30", "45"]
            ctk.CTkOptionMenu(self.backup_freq_frame, variable=self.backup_hour_var,
                            values=hour_options, width=70,
                            command=lambda x: self.check_backup_settings_changed()).grid(row=0, column=1, padx=5)
            ctk.CTkLabel(self.backup_freq_frame, text="時").grid(row=0, column=2, padx=5)
            ctk.CTkOptionMenu(self.backup_freq_frame, variable=self.backup_minute_var,
                            values=minute_options, width=70,
                            command=lambda x: self.check_backup_settings_changed()).grid(row=0, column=3, padx=5)
            ctk.CTkLabel(self.backup_freq_frame, text="分").grid(row=0, column=4, padx=5)
            
        elif freq_type == "weekly":
            weekdays_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            ctk.CTkLabel(self.backup_freq_frame, text="每週").grid(row=0, column=0, padx=5)
            self.backup_weekday_var = ctk.StringVar(value=weekdays_cn[self.config.get("backup_weekday", 0)])
            ctk.CTkOptionMenu(self.backup_freq_frame, values=weekdays_cn, 
                            variable=self.backup_weekday_var, width=100,
                            command=lambda x: self.check_backup_settings_changed()).grid(row=0, column=1, padx=5)
            self.backup_hour_var = ctk.StringVar(value=str(self.config.get("backup_time_hour", 3)))
            self.backup_minute_var = ctk.StringVar(value=str(self.config.get("backup_time_minute", 0)))
            hour_options = [str(i) for i in range(24)]
            minute_options = ["0", "15", "30", "45"]
            ctk.CTkOptionMenu(self.backup_freq_frame, variable=self.backup_hour_var,
                            values=hour_options, width=70,
                            command=lambda x: self.check_backup_settings_changed()).grid(row=0, column=2, padx=5)
            ctk.CTkLabel(self.backup_freq_frame, text="時").grid(row=0, column=3, padx=5)
            ctk.CTkOptionMenu(self.backup_freq_frame, variable=self.backup_minute_var,
                            values=minute_options, width=70,
                            command=lambda x: self.check_backup_settings_changed()).grid(row=0, column=4, padx=5)
            ctk.CTkLabel(self.backup_freq_frame, text="分").grid(row=0, column=5, padx=5)
            
        elif freq_type == "monthly":
            ctk.CTkLabel(self.backup_freq_frame, text="每月").grid(row=0, column=0, padx=5)
            self.backup_day_var = ctk.StringVar(value=str(self.config.get("backup_day", 1)))
            day_options = [str(i) for i in range(1, 29)]  # 1-28號，避免月份差異問題
            ctk.CTkOptionMenu(self.backup_freq_frame, variable=self.backup_day_var,
                            values=day_options, width=70,
                            command=lambda x: self.check_backup_settings_changed()).grid(row=0, column=1, padx=5)
            ctk.CTkLabel(self.backup_freq_frame, text="號").grid(row=0, column=2, padx=5)
            self.backup_hour_var = ctk.StringVar(value=str(self.config.get("backup_time_hour", 3)))
            self.backup_minute_var = ctk.StringVar(value=str(self.config.get("backup_time_minute", 0)))
            hour_options = [str(i) for i in range(24)]
            minute_options = ["0", "15", "30", "45"]
            ctk.CTkOptionMenu(self.backup_freq_frame, variable=self.backup_hour_var,
                            values=hour_options, width=70,
                            command=lambda x: self.check_backup_settings_changed()).grid(row=0, column=3, padx=5)
            ctk.CTkLabel(self.backup_freq_frame, text="時").grid(row=0, column=4, padx=5)
            ctk.CTkOptionMenu(self.backup_freq_frame, variable=self.backup_minute_var,
                            values=minute_options, width=70,
                            command=lambda x: self.check_backup_settings_changed()).grid(row=0, column=5, padx=5)
            ctk.CTkLabel(self.backup_freq_frame, text="分").grid(row=0, column=6, padx=5)
    
    def update_update_frequency_ui(self, freq_type):
        """更新更新檢查頻率設定介面"""
        # 清除舊的 widget
        for widget in self.update_freq_frame.winfo_children():
            widget.destroy()
        
        if freq_type == "hours":
            ctk.CTkLabel(self.update_freq_frame, text="每").grid(row=0, column=0, padx=5)
            self.update_hours_var = ctk.StringVar(value=str(self.config.get("update_frequency_value", 24)))
            hours_options = ["1", "2", "3", "4", "6", "8", "12", "24", "48", "72"]
            ctk.CTkOptionMenu(self.update_freq_frame, variable=self.update_hours_var,
                            values=hours_options, width=80,
                            command=lambda x: self.check_update_settings_changed()).grid(row=0, column=1, padx=5)
            ctk.CTkLabel(self.update_freq_frame, text="小時").grid(row=0, column=2, padx=5)
            
        elif freq_type == "daily":
            ctk.CTkLabel(self.update_freq_frame, text="每天").grid(row=0, column=0, padx=5)
            self.update_hour_var = ctk.StringVar(value=str(self.config.get("update_time_hour", 4)))
            self.update_minute_var = ctk.StringVar(value=str(self.config.get("update_time_minute", 0)))
            hour_options = [str(i) for i in range(24)]
            minute_options = ["0", "15", "30", "45"]
            ctk.CTkOptionMenu(self.update_freq_frame, variable=self.update_hour_var,
                            values=hour_options, width=70,
                            command=lambda x: self.check_update_settings_changed()).grid(row=0, column=1, padx=5)
            ctk.CTkLabel(self.update_freq_frame, text="時").grid(row=0, column=2, padx=5)
            ctk.CTkOptionMenu(self.update_freq_frame, variable=self.update_minute_var,
                            values=minute_options, width=70,
                            command=lambda x: self.check_update_settings_changed()).grid(row=0, column=3, padx=5)
            ctk.CTkLabel(self.update_freq_frame, text="分").grid(row=0, column=4, padx=5)
            
        elif freq_type == "weekly":
            weekdays_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            ctk.CTkLabel(self.update_freq_frame, text="每週").grid(row=0, column=0, padx=5)
            self.update_weekday_var = ctk.StringVar(value=weekdays_cn[self.config.get("update_weekday", 0)])
            ctk.CTkOptionMenu(self.update_freq_frame, values=weekdays_cn, 
                            variable=self.update_weekday_var, width=100,
                            command=lambda x: self.check_update_settings_changed()).grid(row=0, column=1, padx=5)
            self.update_hour_var = ctk.StringVar(value=str(self.config.get("update_time_hour", 4)))
            self.update_minute_var = ctk.StringVar(value=str(self.config.get("update_time_minute", 0)))
            hour_options = [str(i) for i in range(24)]
            minute_options = ["0", "15", "30", "45"]
            ctk.CTkOptionMenu(self.update_freq_frame, variable=self.update_hour_var,
                            values=hour_options, width=70,
                            command=lambda x: self.check_update_settings_changed()).grid(row=0, column=2, padx=5)
            ctk.CTkLabel(self.update_freq_frame, text="時").grid(row=0, column=3, padx=5)
            ctk.CTkOptionMenu(self.update_freq_frame, variable=self.update_minute_var,
                            values=minute_options, width=70,
                            command=lambda x: self.check_update_settings_changed()).grid(row=0, column=4, padx=5)
            ctk.CTkLabel(self.update_freq_frame, text="分").grid(row=0, column=5, padx=5)
            
        elif freq_type == "monthly":
            ctk.CTkLabel(self.update_freq_frame, text="每月").grid(row=0, column=0, padx=5)
            self.update_day_var = ctk.StringVar(value=str(self.config.get("update_day", 1)))
            day_options = [str(i) for i in range(1, 29)]  # 1-28號，避免月份差異問題
            ctk.CTkOptionMenu(self.update_freq_frame, variable=self.update_day_var,
                            values=day_options, width=70,
                            command=lambda x: self.check_update_settings_changed()).grid(row=0, column=1, padx=5)
            ctk.CTkLabel(self.update_freq_frame, text="號").grid(row=0, column=2, padx=5)
            self.update_hour_var = ctk.StringVar(value=str(self.config.get("update_time_hour", 4)))
            self.update_minute_var = ctk.StringVar(value=str(self.config.get("update_time_minute", 0)))
            hour_options = [str(i) for i in range(24)]
            minute_options = ["0", "15", "30", "45"]
            ctk.CTkOptionMenu(self.update_freq_frame, variable=self.update_hour_var,
                            values=hour_options, width=70,
                            command=lambda x: self.check_update_settings_changed()).grid(row=0, column=3, padx=5)
            ctk.CTkLabel(self.update_freq_frame, text="時").grid(row=0, column=4, padx=5)
            ctk.CTkOptionMenu(self.update_freq_frame, variable=self.update_minute_var,
                            values=minute_options, width=70,
                            command=lambda x: self.check_update_settings_changed()).grid(row=0, column=5, padx=5)
            ctk.CTkLabel(self.update_freq_frame, text="分").grid(row=0, column=6, padx=5)
    
    def on_backup_frequency_type_change(self, value):
        """備份頻率類型改變時更新UI並標記變更"""
        self.update_backup_frequency_ui(value)
        self.check_backup_settings_changed()
    
    def on_backup_frequency_change(self, value):
        """備份頻率改變時標記變更（保留供舊代碼相容）"""
        self.update_backup_frequency_ui(value)
        self.check_backup_settings_changed()
    
    def on_backup_notify_change(self, value):
        """備份通知時間改變時自動儲存（提前通知保持自動保存）"""
        int_value = int(float(value))
        self.backup_notify_label.configure(text=f"{int_value}秒")
        # 提前通知保持自動保存
        self.config["backup_notify_seconds"] = int_value
        self.save_config()
    
    def on_backup_size_slider_change(self, value):
        """備份容量滑條改變時更新顯示並標記變更"""
        float_value = round(float(value) * 2) / 2  # 確保是0.5的倍數
        self.backup_size_var.set(float_value)
        self.backup_size_label.configure(text=f"{float_value:.1f} GB")
        self.check_backup_settings_changed()
    
    def check_backup_settings_changed(self):
        """檢查備份設定是否有變更"""
        changed = False
        
        # 檢查頻率類型
        if self.backup_freq_type_var.get() != self.config.get("backup_frequency_type"):
            changed = True
        
        # 檢查最大容量
        if abs(float(self.backup_size_var.get()) - self.config.get("backup_max_size_gb", 10)) > 0.01:
            changed = True
        
        # 檢查頻率相關設定
        freq_type = self.backup_freq_type_var.get()
        if freq_type == "hours" and hasattr(self, 'backup_hours_var'):
            if int(self.backup_hours_var.get()) != self.config.get("backup_frequency_value", 6):
                changed = True
        elif freq_type in ["daily", "weekly", "monthly"]:
            if hasattr(self, 'backup_hour_var') and hasattr(self, 'backup_minute_var'):
                if (int(self.backup_hour_var.get()) != self.config.get("backup_time_hour", 3) or
                    int(self.backup_minute_var.get()) != self.config.get("backup_time_minute", 0)):
                    changed = True
            if freq_type == "weekly" and hasattr(self, 'backup_weekday_var'):
                weekdays_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
                if weekdays_cn.index(self.backup_weekday_var.get()) != self.config.get("backup_weekday", 0):
                    changed = True
            elif freq_type == "monthly" and hasattr(self, 'backup_day_var'):
                if int(self.backup_day_var.get()) != self.config.get("backup_day", 1):
                    changed = True
        
        self.backup_settings_changed = changed
        
        # 更新保存按鈕狀態
        if hasattr(self, 'backup_save_settings_btn'):
            if changed:
                self.backup_save_settings_btn.configure(state="normal", fg_color="#17A2B8", hover_color="#138496")
            else:
                self.backup_save_settings_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
    
    def save_backup_settings(self, show_dialog=True):
        """儲存所有備份設定
        
        Args:
            show_dialog: 是否顯示成功/錯誤對話框，預設為True
        """
        try:
            # 保存頻率類型
            self.config["backup_frequency_type"] = self.backup_freq_type_var.get()
            
            # 保存最大容量
            self.config["backup_max_size_gb"] = float(self.backup_size_var.get())
            
            # 根據頻率類型保存相關設定
            freq_type = self.backup_freq_type_var.get()
            if freq_type == "hours" and hasattr(self, 'backup_hours_var'):
                self.config["backup_frequency_value"] = int(self.backup_hours_var.get())
            elif freq_type in ["daily", "weekly", "monthly"]:
                if hasattr(self, 'backup_hour_var') and hasattr(self, 'backup_minute_var'):
                    self.config["backup_time_hour"] = int(self.backup_hour_var.get())
                    self.config["backup_time_minute"] = int(self.backup_minute_var.get())
                if freq_type == "weekly" and hasattr(self, 'backup_weekday_var'):
                    weekdays_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
                    self.config["backup_weekday"] = weekdays_cn.index(self.backup_weekday_var.get())
                elif freq_type == "monthly" and hasattr(self, 'backup_day_var'):
                    self.config["backup_day"] = int(self.backup_day_var.get())
            
            self.save_config()
            self.setup_schedules()
            
            self.log_message("已儲存備份設定")
            
            # 延遲刷新頁面和更新狀態（確保刷新後狀態保持正確）
            self.after(100, lambda: self._post_save_backup_refresh(show_dialog))
            
        except Exception as e:
            self.log_message(f"儲存備份設定時發生錯誤: {str(e)}")
            if show_dialog:
                self.show_error("錯誤", f"儲存備份設定失敗：\n\n{str(e)}")
    
    def _post_save_backup_refresh(self, show_dialog):
        """保存備份設定後的刷新處理"""
        try:
            # 刷新頁面
            self.refresh_backup_update_page()
            
            # 強制標記設定未變更（刷新後再次確認）
            self.backup_settings_changed = False
            if hasattr(self, 'backup_save_settings_btn'):
                self.backup_save_settings_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
            
            # 顯示成功訊息
            if show_dialog:
                self.show_info("成功", "備份設定已儲存")
        except Exception as e:
            self.log_message(f"刷新備份頁面時發生錯誤: {str(e)}")
    
    def save_backup_size(self):
        """保存備份容量設定（保留供相容性）"""
        self.save_backup_settings()
        
        # 更新容量進度條
        self.update_backup_capacity_bar()
        
        # 清理舊備份
        self.cleanup_old_backups()
        
        self.log_message(f"已保存備份容量設定: {float_value:.1f} GB")
    
    def on_backup_size_change(self, value):
        """備份容量改變時自動儲存（舊版本相容性保留）"""
        self.on_backup_size_slider_change(value)
    
    def on_update_frequency_type_change(self, value):
        """更新頻率類型改變時更新UI並標記變更"""
        self.update_update_frequency_ui(value)
        self.check_update_settings_changed()
    
    def on_update_frequency_change(self, value):
        """更新頻率改變時標記變更（保留供舊代碼相容）"""
        self.update_update_frequency_ui(value)
        self.check_update_settings_changed()
    
    def on_update_notify_change(self, value):
        """更新通知時間改變時自動儲存（提前通知保持自動保存）"""
        int_value = int(float(value))
        self.update_notify_label.configure(text=f"{int_value}分")
        # 提前通知保持自動保存
        self.config["update_notify_minutes"] = int_value
        self.save_config()
    
    def check_update_settings_changed(self):
        """檢查更新設定是否有變更"""
        changed = False
        
        # 檢查頻率類型
        if self.update_freq_type_var.get() != self.config.get("update_frequency_type"):
            changed = True
        
        # 檢查頻率相關設定
        freq_type = self.update_freq_type_var.get()
        if freq_type == "hours" and hasattr(self, 'update_hours_var'):
            if int(self.update_hours_var.get()) != self.config.get("update_frequency_value", 24):
                changed = True
        elif freq_type in ["daily", "weekly", "monthly"]:
            if hasattr(self, 'update_hour_var') and hasattr(self, 'update_minute_var'):
                if (int(self.update_hour_var.get()) != self.config.get("update_time_hour", 4) or
                    int(self.update_minute_var.get()) != self.config.get("update_time_minute", 0)):
                    changed = True
            if freq_type == "weekly" and hasattr(self, 'update_weekday_var'):
                weekdays_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
                if weekdays_cn.index(self.update_weekday_var.get()) != self.config.get("update_weekday", 0):
                    changed = True
            elif freq_type == "monthly" and hasattr(self, 'update_day_var'):
                if int(self.update_day_var.get()) != self.config.get("update_day", 1):
                    changed = True
        
        self.update_settings_changed = changed
        
        # 更新保存按鈕狀態
        if hasattr(self, 'update_save_settings_btn'):
            if changed:
                self.update_save_settings_btn.configure(state="normal", fg_color="#17A2B8", hover_color="#138496")
            else:
                self.update_save_settings_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
    
    def save_update_settings(self, show_dialog=True):
        """儲存所有更新設定
        
        Args:
            show_dialog: 是否顯示成功/錯誤對話框，預設為True
        """
        try:
            # 保存頻率類型
            self.config["update_frequency_type"] = self.update_freq_type_var.get()
            
            # 根據頻率類型保存相關設定
            freq_type = self.update_freq_type_var.get()
            if freq_type == "hours" and hasattr(self, 'update_hours_var'):
                self.config["update_frequency_value"] = int(self.update_hours_var.get())
            elif freq_type in ["daily", "weekly", "monthly"]:
                if hasattr(self, 'update_hour_var') and hasattr(self, 'update_minute_var'):
                    self.config["update_time_hour"] = int(self.update_hour_var.get())
                    self.config["update_time_minute"] = int(self.update_minute_var.get())
                if freq_type == "weekly" and hasattr(self, 'update_weekday_var'):
                    weekdays_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
                    self.config["update_weekday"] = weekdays_cn.index(self.update_weekday_var.get())
                elif freq_type == "monthly" and hasattr(self, 'update_day_var'):
                    self.config["update_day"] = int(self.update_day_var.get())
            
            self.save_config()
            self.setup_schedules()
            
            self.log_message("已儲存更新設定")
            
            # 延遲刷新頁面和更新狀態（確保刷新後狀態保持正確）
            self.after(100, lambda: self._post_save_update_refresh(show_dialog))
            
        except Exception as e:
            self.log_message(f"儲存更新設定時發生錯誤: {str(e)}")
            if show_dialog:
                self.show_error("錯誤", f"儲存更新設定失敗：\n\n{str(e)}")
    
    def _post_save_update_refresh(self, show_dialog):
        """保存更新設定後的刷新處理"""
        try:
            # 刷新頁面
            self.refresh_backup_update_page()
            
            # 強制標記設定未變更（刷新後再次確認）
            self.update_settings_changed = False
            if hasattr(self, 'update_save_settings_btn'):
                self.update_save_settings_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
            
            # 顯示成功訊息
            if show_dialog:
                self.show_info("成功", "更新設定已儲存")
        except Exception as e:
            self.log_message(f"刷新更新頁面時發生錯誤: {str(e)}")
    
    def reload_backup_update_settings(self):
        """重新載入備份和更新設定（捨棄未保存的變更）"""
        try:
            # 重新載入配置文件
            self.load_config()
            
            # 重新設置備份區域的值
            self.backup_freq_type_var.set(self.config["backup_frequency_type"])
            self.backup_size_var.set(self.config["backup_max_size_gb"])
            self.backup_size_label.configure(text=f"{self.config['backup_max_size_gb']:.1f} GB")
            
            # 重新設置更新區域的值
            self.update_freq_type_var.set(self.config["update_frequency_type"])
            
            # 重新創建頻率UI
            self.update_backup_frequency_ui(self.config["backup_frequency_type"])
            self.update_update_frequency_ui(self.config["update_frequency_type"])
            
            # 標記設定未變更
            self.backup_settings_changed = False
            self.update_settings_changed = False
            
            # 禁用保存按鈕
            if hasattr(self, 'backup_save_settings_btn'):
                self.backup_save_settings_btn.configure(state="disabled", fg_color="#6C757D")
            if hasattr(self, 'update_save_settings_btn'):
                self.update_save_settings_btn.configure(state="disabled", fg_color="#6C757D")
            
            # 使用after延遲刷新，避免UI衝突
            self.after(100, self.refresh_backup_update_page)
            
            self.log_message("已重新載入設定")
            
        except Exception as e:
            self.log_message(f"重新載入設定時發生錯誤: {str(e)}")
    
    def refresh_backup_update_page(self):
        """刷新備份與更新頁面的所有顯示資訊"""
        try:
            # 保存當前的變更狀態
            backup_changed_before = self.backup_settings_changed
            update_changed_before = self.update_settings_changed
            
            # 重新載入備份時間
            self.load_backup_times()
            
            # 更新所有時間標籤
            if hasattr(self, 'last_manual_backup_label'):
                self.update_last_manual_backup_label()
            if hasattr(self, 'last_auto_backup_label'):
                self.update_last_auto_backup_label()
            if hasattr(self, 'next_backup_label'):
                self.update_next_backup_time()
            
            # 更新容量進度條
            if hasattr(self, 'backup_capacity_bar'):
                self.update_backup_capacity_bar()
            
            # 清理舊備份（可能觸發變更檢查）
            self.cleanup_old_backups()
            
            # 恢復變更狀態（避免刷新過程中意外改變狀態）
            self.backup_settings_changed = backup_changed_before
            self.update_settings_changed = update_changed_before
            
            self.log_message("已刷新備份與更新頁面")
        except Exception as e:
            self.log_message(f"刷新頁面時發生錯誤: {str(e)}")
    
    def show_info(self, title, message):
        """顯示資訊對話框"""
        dialog = CustomDialog(self, title, message, dialog_type="info", buttons=("確定",))
        dialog.get_result()
    
    def show_error(self, title, message):
        """顯示錯誤對話框"""
        dialog = CustomDialog(self, title, message, dialog_type="error", buttons=("確定",))
        dialog.get_result()
    
    def show_warning(self, title, message):
        """顯示警告對話框"""
        dialog = CustomDialog(self, title, message, dialog_type="warning", buttons=("確定",))
        dialog.get_result()
    
    def ask_yes_no(self, title, message):
        """顯示是否對話框"""
        dialog = CustomDialog(self, title, message, dialog_type="question", buttons=("是", "否"))
        return dialog.get_result() == "是"
    
    def update_backup_notify_label(self, value):
        """更新備份通知標籤（保留向後兼容）"""
        int_value = int(float(value))
        self.backup_notify_label.configure(text=f"{int_value} 秒")
    
    def update_update_notify_label(self, value):
        """更新更新通知標籤（保留向後兼容）"""
        int_value = int(float(value))
        self.update_notify_label.configure(text=f"{int_value} 分鐘")
    
    def update_backup_size_label(self, value):
        """更新備份容量標籤並控制相關功能（保留向後兼容）"""
        float_value = round(float(value) * 2) / 2  # 確保是0.5的倍數
        self.backup_size_var.set(float_value)
        self.backup_size_label.configure(text=f"{float_value:.1f} GB")
        
        # 當容量為 0 時顯示警告並禁用相關功能
        if float_value == 0:
            # 顯示警告
            try:
                self.backup_disabled_label.grid(row=0, column=3, padx=(10,0), sticky="w")
            except:
                pass
            # 禁用自動備份開關
            self.auto_backup_var.set(False)
            self.toggle_auto_backup()
        else:
            # 隱藏警告
            try:
                self.backup_disabled_label.grid_forget()
            except:
                pass
    
    def toggle_auto_backup(self):
        """切換自動備份"""
        enabled = self.auto_backup_var.get()
        
        self.config["auto_backup_enabled"] = enabled
        self.save_config()
        self.setup_schedules()
        status = "啟用" if enabled else "停用"
        self.log_message(f"自動備份已{status}")
        
        # 更新下次備份時間顯示
        self.update_next_backup_time()
        
        # 控制相關控件的啟用/禁用狀態和顏色
        if enabled:
            state = "normal"
            # 頻率類型選單 - 恢復原色
            if hasattr(self, 'backup_freq_menu'):
                self.backup_freq_menu.configure(state=state, fg_color=["#3B8ED0", "#1F6AA5"], button_color=["#3B8ED0", "#1F6AA5"], button_hover_color=["#36719F", "#144870"])
            
            # 頻率設定區域的所有子控件
            if hasattr(self, 'backup_freq_frame'):
                for widget in self.backup_freq_frame.winfo_children():
                    try:
                        # 恢復不同類型控件的原色
                        if isinstance(widget, ctk.CTkOptionMenu):
                            widget.configure(state=state, fg_color=["#3B8ED0", "#1F6AA5"], button_color=["#3B8ED0", "#1F6AA5"], button_hover_color=["#36719F", "#144870"])
                        elif isinstance(widget, ctk.CTkSlider):
                            widget.configure(state=state, button_color="#1F6AA5", button_hover_color="#144870")
                        else:
                            widget.configure(state=state)
                    except:
                        pass
            
            # 最大容量滑條 - 恢復原色
            if hasattr(self, 'backup_size_slider'):
                self.backup_size_slider.configure(state=state, button_color="#1F6AA5", button_hover_color="#144870")
            
            # 儲存設定按鈕
            if hasattr(self, 'backup_save_settings_btn'):
                self.check_backup_settings_changed()
        else:
            state = "disabled"
            # 頻率類型選單
            if hasattr(self, 'backup_freq_menu'):
                self.backup_freq_menu.configure(state=state, fg_color="#6C757D", button_color="#6C757D", button_hover_color="#6C757D")
            
            # 頻率設定區域的所有子控件
            if hasattr(self, 'backup_freq_frame'):
                for widget in self.backup_freq_frame.winfo_children():
                    try:
                        # 針對不同類型的控件設置灰色
                        if isinstance(widget, ctk.CTkButton):
                            widget.configure(state=state, fg_color="#6C757D", hover_color="#6C757D")
                        elif isinstance(widget, ctk.CTkSlider):
                            widget.configure(state=state, button_color="#6C757D", button_hover_color="#6C757D")
                        elif isinstance(widget, ctk.CTkOptionMenu):
                            widget.configure(state=state, fg_color="#6C757D", button_color="#6C757D", button_hover_color="#6C757D")
                        else:
                            widget.configure(state=state)
                    except:
                        pass
            
            # 最大容量滑條 - 灰色
            if hasattr(self, 'backup_size_slider'):
                self.backup_size_slider.configure(state=state, button_color="#6C757D", button_hover_color="#6C757D")
            
            # 儲存設定按鈕
            if hasattr(self, 'backup_save_settings_btn'):
                self.backup_save_settings_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
        
        # 更新容量進度條顏色
        if hasattr(self, 'backup_capacity_bar'):
            if enabled:
                # 根據使用率設置顏色（在 update_backup_capacity_bar 中處理）
                self.update_backup_capacity_bar()
            else:
                # 禁用時設為灰色
                self.backup_capacity_bar.configure(progress_color="#6C757D")
    
    def toggle_auto_update(self):
        """切換自動更新"""
        enabled = self.auto_update_var.get()
        
        self.config["auto_update_enabled"] = enabled
        self.save_config()
        self.setup_schedules()
        status = "啟用" if enabled else "停用"
        self.log_message(f"自動更新檢查已{status}")
        
        # 控制相關控件的啟用/禁用狀態和顏色
        if enabled:
            state = "normal"
            # 頻率類型選單 - 恢復原色
            if hasattr(self, 'update_freq_menu'):
                self.update_freq_menu.configure(state=state, fg_color=["#3B8ED0", "#1F6AA5"], button_color=["#3B8ED0", "#1F6AA5"], button_hover_color=["#36719F", "#144870"])
            
            # 頻率設定區域的所有子控件
            if hasattr(self, 'update_freq_frame'):
                for widget in self.update_freq_frame.winfo_children():
                    try:
                        # 恢復不同類型控件的原色
                        if isinstance(widget, ctk.CTkOptionMenu):
                            widget.configure(state=state, fg_color=["#3B8ED0", "#1F6AA5"], button_color=["#3B8ED0", "#1F6AA5"], button_hover_color=["#36719F", "#144870"])
                        elif isinstance(widget, ctk.CTkSlider):
                            widget.configure(state=state, button_color="#1F6AA5", button_hover_color="#144870")
                        else:
                            widget.configure(state=state)
                    except:
                        pass
            
            # 儲存設定按鈕
            if hasattr(self, 'update_save_settings_btn'):
                self.check_update_settings_changed()
        else:
            state = "disabled"
            # 頻率類型選單
            if hasattr(self, 'update_freq_menu'):
                self.update_freq_menu.configure(state=state, fg_color="#6C757D", button_color="#6C757D", button_hover_color="#6C757D")
            
            # 頻率設定區域的所有子控件
            if hasattr(self, 'update_freq_frame'):
                for widget in self.update_freq_frame.winfo_children():
                    try:
                        # 針對不同類型的控件設置灰色
                        if isinstance(widget, ctk.CTkButton):
                            widget.configure(state=state, fg_color="#6C757D", hover_color="#6C757D")
                        elif isinstance(widget, ctk.CTkSlider):
                            widget.configure(state=state, button_color="#6C757D", button_hover_color="#6C757D")
                        elif isinstance(widget, ctk.CTkOptionMenu):
                            widget.configure(state=state, fg_color="#6C757D", button_color="#6C757D", button_hover_color="#6C757D")
                        else:
                            widget.configure(state=state)
                    except:
                        pass
            
            # 儲存設定按鈕
            if hasattr(self, 'update_save_settings_btn'):
                self.update_save_settings_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
    
    def auto_save_backup_settings(self):
        """自動儲存備份設定（不顯示訊息）"""
        try:
            self.config["backup_notify_seconds"] = int(self.backup_notify_var.get())
            self.config["backup_max_size_gb"] = float(self.backup_size_var.get())
            self.config["backup_frequency_type"] = self.backup_freq_type_var.get()
            
            # 根據頻率類型保存相關設定
            freq_type = self.backup_freq_type_var.get()
            if freq_type == "hours" and hasattr(self, 'backup_hours_var'):
                self.config["backup_frequency_value"] = int(self.backup_hours_var.get())
            elif freq_type in ["daily", "weekly", "monthly"]:
                if hasattr(self, 'backup_hour_var') and hasattr(self, 'backup_minute_var'):
                    self.config["backup_time_hour"] = int(self.backup_hour_var.get())
                    self.config["backup_time_minute"] = int(self.backup_minute_var.get())
                if freq_type == "weekly" and hasattr(self, 'backup_weekday_var'):
                    weekdays_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
                    self.config["backup_weekday"] = weekdays_cn.index(self.backup_weekday_var.get())
                elif freq_type == "monthly" and hasattr(self, 'backup_day_var'):
                    self.config["backup_day"] = int(self.backup_day_var.get())
            
            self.save_config()
            self.setup_schedules()
            
            # 更新下次備份時間顯示
            self.update_next_backup_time()
        except Exception as e:
            self.log_message(f"自動儲存備份設定時發生錯誤: {str(e)}")
    
    def auto_save_update_settings(self):
        """自動儲存更新設定（不顯示訊息）"""
        try:
            self.config["update_notify_minutes"] = int(self.update_notify_var.get())
            self.config["update_frequency_type"] = self.update_freq_type_var.get()
            
            # 根據頻率類型保存相關設定
            freq_type = self.update_freq_type_var.get()
            if freq_type == "hours" and hasattr(self, 'update_hours_var'):
                self.config["update_frequency_value"] = int(self.update_hours_var.get())
            elif freq_type in ["daily", "weekly", "monthly"]:
                if hasattr(self, 'update_hour_var') and hasattr(self, 'update_minute_var'):
                    self.config["update_time_hour"] = int(self.update_hour_var.get())
                    self.config["update_time_minute"] = int(self.update_minute_var.get())
                if freq_type == "weekly" and hasattr(self, 'update_weekday_var'):
                    weekdays_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
                    self.config["update_weekday"] = weekdays_cn.index(self.update_weekday_var.get())
                elif freq_type == "monthly" and hasattr(self, 'update_day_var'):
                    self.config["update_day"] = int(self.update_day_var.get())
            
            self.save_config()
            self.setup_schedules()
        except Exception as e:
            self.log_message(f"自動儲存更新設定時發生錯誤: {str(e)}")
    
    def manual_backup_with_notification(self):
        """手動備份（帶通知）"""
        # 立即禁用按鈕
        self._disable_operation_buttons()
        
        if self.backup_manual_notify_var.get():
            notify_minutes = int(self.backup_notify_var.get())
            threading.Thread(target=lambda: self.perform_backup_with_notification(notify_minutes, False), daemon=True).start()
        else:
            threading.Thread(target=self._perform_backup, daemon=True).start()
    
    def manual_update_no_notification(self):
        """手動更新（無通知）"""
        if not hasattr(self, 'download_url'):
            self.show_error("錯誤", "請先檢查更新")
            return
        result = self.ask_yes_no("確認", "確定要更新伺服器嗎？")
        if result:
            # 立即禁用按鈕
            self._disable_operation_buttons()
            threading.Thread(target=self._perform_update, daemon=True).start()
    
    def manual_update_with_notification(self):
        """手動更新（帶通知），使用滑條設定的通知時間"""
        if not hasattr(self, 'download_url'):
            self.show_error("錯誤", "請先檢查更新")
            return
        
        result = self.ask_yes_no("確認", "確定要更新伺服器嗎？\n將會發送通知給玩家。")
        if result:
            # 立即禁用按鈕
            self._disable_operation_buttons()
            
            notify_minutes = int(self.update_notify_var.get())
            if notify_minutes > 0:
                threading.Thread(target=lambda: self.perform_update_with_notification(notify_minutes, False), daemon=True).start()
            else:
                threading.Thread(target=self._perform_update, daemon=True).start()
    
    def toggle_force_update(self):
        """切換手動更新/取消更新"""
        if self.update_notification_active:
            # 如果正在通知階段，取消更新
            self.cancel_update()
        else:
            # 開始手動更新
            self.force_update()
    
    def force_update(self):
        """手動更新（即使版本相同），使用滑條設定的通知時間"""
        result = self.ask_yes_no("確認", 
            "手動更新將會重新下載並安裝伺服器，即使當前已是最新版本。\n確定要繼續嗎？")
        if not result:
            return
        
        # 重置取消標誌
        self.update_cancel_requested = False
        self.update_in_progress = False
        
        # 立即禁用其他按鈕
        if hasattr(self, 'manual_backup_btn'):
            self.manual_backup_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
        if hasattr(self, 'check_update_btn'):
            self.check_update_btn.configure(state="disabled", fg_color="#6C757D", hover_color="#6C757D")
        
        # 將手動更新按鈕改為取消按鈕（紅色）
        self.force_update_btn.configure(
            text="取消更新",
            fg_color="#DC3545",
            hover_color="#C82333"
        )
        
        # 以靜默模式檢查更新獲取下載連結（不顯示提示框，不影響按鈕狀態）
        self._check_update(is_auto=False, silent=True)
        
        if not hasattr(self, 'download_url') or not self.download_url:
            self.show_error("錯誤", "無法獲取下載連結，請檢查網路連接")
            # 檢查更新失敗，恢復按鈕狀態
            self._reset_update_buttons()
            return
        
        # 使用滑條設定的通知時間
        notify_minutes = int(self.update_notify_var.get())
        if notify_minutes > 0:
            threading.Thread(target=lambda: self.perform_update_with_notification(notify_minutes, False), daemon=True).start()
        else:
            # 沒有通知時間，直接進入更新階段
            self.update_in_progress = True
            self.force_update_btn.configure(
                text="手動更新",
                state="disabled",
                fg_color="#6C757D",
                hover_color="#6C757D"
            )
            threading.Thread(target=self._perform_update, daemon=True).start()
    
    def cancel_update(self):
        """取消更新"""
        if self.update_in_progress:
            # 已經在更新階段，無法取消
            self.show_warning("警告", "更新已開始執行，無法取消")
            return
        
        # 顯示確認對話框
        result = self.ask_yes_no("確認取消", 
            "確定要取消更新嗎？\n\n已下載的檔案將被刪除。")
        if not result:
            # 用戶選擇不取消
            return
        
        # 設置取消標誌
        self.update_cancel_requested = True
        self.update_notification_active = False
        
        self.log_message("用戶取消了更新")
        
        # 不等待下載線程，讓它自己清理
        # 啟動一個異步清理線程來處理
        if self.update_download_thread and self.update_download_thread.is_alive():
            self.log_message("正在停止下載...")
            threading.Thread(target=self._async_cleanup_after_cancel, daemon=True).start()
        else:
            # 如果沒有下載線程或已結束，直接清理
            self._cleanup_update_temp_files()
            self._reset_update_buttons()
        
        self.show_info("取消更新", "更新已取消，正在清理臨時檔案...")
    
    def _async_cleanup_after_cancel(self):
        """異步清理：等待下載線程結束後清理（不阻塞UI）"""
        try:
            # 在背景線程中等待下載線程結束（使用短超時循環，最多3秒）
            max_wait_time = 3.0
            wait_interval = 0.1
            elapsed = 0.0
            
            if self.update_download_thread and self.update_download_thread.is_alive():
                while elapsed < max_wait_time and self.update_download_thread.is_alive():
                    time.sleep(wait_interval)
                    elapsed += wait_interval
                
                if self.update_download_thread.is_alive():
                    # 下載線程仍在運行，但會在下一個chunk檢查時自動停止
                    pass
            
            # 延遲一下再清理，確保下載線程已釋放文件
            time.sleep(0.5)
            
            # 清理臨時檔案
            self._cleanup_update_temp_files()
            
            # 恢復按鈕狀態（必須在主線程執行）
            self.after(0, self._reset_update_buttons)
            
            # 通知用戶清理完成
            self.after(0, lambda: self.log_message("清理完成"))
        except Exception as e:
            self.log_message(f"異步清理時發生錯誤: {str(e)}")
    
    def _cleanup_update_temp_files(self):
        """清理更新臨時檔案"""
        try:
            if hasattr(self, '_downloaded_zip') and self._downloaded_zip:
                if self._downloaded_zip.exists():
                    self._downloaded_zip.unlink()
                    self.log_message(f"已刪除臨時檔案: {self._downloaded_zip.name}")
                delattr(self, '_downloaded_zip')
        except Exception as e:
            self.log_message(f"清理臨時檔案時發生錯誤: {str(e)}")
    
    def _reset_update_buttons(self):
        """重置更新相關按鈕狀態"""
        # 恢復手動更新按鈕
        self.force_update_btn.configure(
            text="手動更新",
            state="normal",
            fg_color="#17A2B8",
            hover_color="#138496"
        )
        
        # 恢復其他按鈕
        if hasattr(self, 'manual_backup_btn'):
            self.manual_backup_btn.configure(state="normal", fg_color="#17A2B8", hover_color="#138496")
        if hasattr(self, 'check_update_btn'):
            self.check_update_btn.configure(state="normal", fg_color="#17A2B8", hover_color="#138496")
    
    def manual_backup_with_prompt(self):
        """手動備份，使用滑條設定的通知時間"""
        # 立即禁用按鈕
        self._disable_operation_buttons()
        
        seconds = int(self.backup_notify_var.get())
        if seconds > 0:
            threading.Thread(target=lambda: self.perform_backup_with_notification(seconds, False), daemon=True).start()
        else:
            threading.Thread(target=self._perform_backup, daemon=True).start()
    
    def _perform_backup(self, is_auto=False):
        """執行備份"""
        backup_start_time = None
        backup_file = None
        backup_success = False
        
        try:
            # 僅在自動備份時禁用操作按鈕（手動備份已在外層處理）
            if is_auto:
                self.after(0, self._disable_operation_buttons)
            
            # 記錄開始時間
            from datetime import datetime
            backup_start_time = datetime.now()
            
            self.log_message("開始備份世界...")
            self.update_status("備份", "yellow")
            
                       
            # 暫停伺服器自動儲存
            if self.server_process:
                self.server_process.stdin.write("save hold\n")
                self.server_process.stdin.flush()
                time.sleep(2)
            
            # 壓縮worlds資料夾
            worlds_dir = self.server_dir / "worlds"
            if not worlds_dir.exists():
                self.log_message("找不到worlds資料夾")
                return
            
            timestamp = backup_start_time.strftime("%Y%m%d_%H%M%S")
            # 根據是否為自動備份選擇不同的資料夾
            backup_folder = "worlds_auto" if is_auto else "worlds_manual"
            backup_file = self.backup_dir / backup_folder / f"world_backup_{timestamp}.zip"
            
            # 確保備份資料夾存在
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(worlds_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(worlds_dir.parent)
                        zipf.write(file_path, arcname)
            
            # 恢復自動儲存
            if self.server_process:
               
                self.server_process.stdin.write("save resume\n")
                self.server_process.stdin.flush()
            
            # 計算耗時和備份大小
            backup_end_time = datetime.now()
            elapsed_time = backup_end_time - backup_start_time
            backup_size_bytes = backup_file.stat().st_size
            backup_size_mb = backup_size_bytes / (1024 * 1024)
            
            backup_success = True
            
            # 更新備份時間
            if is_auto:
                self.last_auto_backup_time = backup_start_time
                self.update_last_auto_backup_label()
                # 自動備份後，同步更新自動更新檢查時間
                if hasattr(self, 'last_auto_update_check_time'):
                    self.last_auto_update_check_time = backup_start_time
                    self.log_message("已同步自動更新檢查時間與備份時間")
            else:
                self.last_manual_backup_time = backup_start_time
                self.update_last_manual_backup_label()
            
            # 保存備份時間到文件
            self.save_backup_times()
            
            self.log_message(f"備份完成: {backup_file.name}")
            self.update_status("運行", "green")
            
            # 清理舊備份
            self.cleanup_old_backups()
            
            # 更新容量進度條
            self.update_backup_capacity_bar()
            
            # 只在手動備份時顯示備份完成回報窗口
            if not is_auto:
                self.after(100, lambda: self.show_backup_result(
                    backup_start_time,
                    elapsed_time,
                    backup_size_mb,
                    backup_file.name,
                    success=True
                ))
            
            # 重新啟用操作按鈕
            self.after(0, self._enable_operation_buttons)
            
        except Exception as e:
            self.log_message(f"備份失敗: {str(e)}")
            if self.server_process:
                self.server_process.stdin.write("save resume\n")
                self.server_process.stdin.flush()
            self.update_status("運行", "green")
            
            # 只在手動備份時顯示備份失敗回報窗口
            if not is_auto:
                self.after(100, lambda: self.show_error(
                    "備份失敗",
                    f"備份過程中發生錯誤：\n\n{str(e)}"
                ))
            
            # 重新啟用操作按鈕
            self.after(0, self._enable_operation_buttons)
    
    def show_backup_result(self, start_time, elapsed_time, size_mb, filename, success=True):
        """顯示備份結果窗口"""
        if success:
            # 格式化時間
            backup_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 格式化耗時
            total_seconds = int(elapsed_time.total_seconds())
            if total_seconds < 60:
                elapsed_str = f"{total_seconds} 秒"
            else:
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                elapsed_str = f"{minutes} 分 {seconds} 秒"
            
            # 格式化大小
            if size_mb < 1:
                size_str = f"{size_mb * 1024:.2f} KB"
            elif size_mb < 1024:
                size_str = f"{size_mb:.2f} MB"
            else:
                size_str = f"{size_mb / 1024:.2f} GB"
            
            self.show_info(
                "備份完成",
                f"✓ 世界備份已完成\n\n"
                f"備份時間：{backup_time_str}\n"
                f"耗時：{elapsed_str}\n"
                f"備份大小：{size_str}\n"
                f"檔案名稱：{filename}"
            )
    
    def cleanup_old_backups(self):
        """清理舊備份（只清理自動備份資料夾，手動備份不受容量限制）"""
        try:
            max_size_gb = float(self.backup_size_var.get())
            max_size_bytes = max_size_gb * 1024 * 1024 * 1024
            
            # 只清理自動備份資料夾，手動備份永久保留
            backup_folder = self.backup_dir / "worlds_auto"
            if not backup_folder.exists():
                self.update_backup_capacity_bar()
                return
            
            backups = sorted(backup_folder.glob("*.zip"), key=lambda x: x.stat().st_mtime)
            
            # 計算該資料夾的總大小
            folder_total_size = sum(f.stat().st_size for f in backups)
            
            # 只在超過容量時清理自動備份
            while folder_total_size > max_size_bytes and backups:
                old_backup = backups.pop(0)
                folder_total_size -= old_backup.stat().st_size
                old_backup.unlink()
                self.log_message(f"已刪除舊備份: {old_backup.name} (自動備份)")
            
            # 更新容量進度條
            self.update_backup_capacity_bar()
                
        except Exception as e:
            self.log_message(f"清理備份失敗: {str(e)}")
    
    def update_backup_capacity_bar(self):
        """更新備份容量進度條（計算手動和自動備份的總和）"""
        try:
            max_size_gb = float(self.backup_size_var.get())
            max_size_bytes = max_size_gb * 1024 * 1024 * 1024
            
            # 計算兩個備份資料夾的總大小
            total_size = 0
            for folder_name in ["worlds_manual", "worlds_auto"]:
                backup_folder = self.backup_dir / folder_name
                if backup_folder.exists():
                    backups = list(backup_folder.glob("*.zip"))
                    total_size += sum(f.stat().st_size for f in backups)
            
            # 計算使用百分比
            usage_percentage = min((total_size / max_size_bytes) * 100, 100.0) if max_size_bytes > 0 else 0
            
            # 更新進度條
            if hasattr(self, 'backup_capacity_bar'):
                self.backup_capacity_bar.set(usage_percentage / 100.0)
                
                # 當容量接近滿時顯示提示文字
                if usage_percentage >= 95:
                    self.backup_capacity_label.configure(text=f"{usage_percentage:.1f}% (將覆蓋舊備份)")
                else:
                    self.backup_capacity_label.configure(text=f"{usage_percentage:.1f}%")
                
                # 根據使用率改變進度條顏色
                if usage_percentage >= 90:
                    self.backup_capacity_bar.configure(progress_color="#FF6B35")  # 紅色
                elif usage_percentage >= 70:
                    self.backup_capacity_bar.configure(progress_color="#FFA500")  # 橘色
                else:
                    self.backup_capacity_bar.configure(progress_color="#17A2B8")  # 藍色
                
        except Exception as e:
            self.log_message(f"更新容量進度條失敗: {str(e)}")
    
    def update_last_manual_backup_label(self):
        """更新上次手動備份時間標籤"""
        if hasattr(self, 'last_manual_backup_label'):
            if self.last_manual_backup_time:
                time_str = self.last_manual_backup_time.strftime("%Y-%m-%d %H:%M:%S")
                self.last_manual_backup_label.configure(text=time_str)
            else:
                self.last_manual_backup_label.configure(text="尚未備份")
    
    def update_last_auto_backup_label(self):
        """更新上次自動備份時間標籤"""
        if hasattr(self, 'last_auto_backup_label'):
            if self.last_auto_backup_time:
                time_str = self.last_auto_backup_time.strftime("%Y-%m-%d %H:%M:%S")
                self.last_auto_backup_label.configure(text=time_str)
            else:
                self.last_auto_backup_label.configure(text="尚未備份")
    
    def update_next_backup_time(self):
        """更新下次備份時間標籤"""
        if not hasattr(self, 'next_backup_label'):
            return
            
        if not self.config["auto_backup_enabled"]:
            self.next_backup_label.configure(text="未啟用")
            return
        
        try:
            from datetime import datetime, timedelta
            
            freq_type = self.config["backup_frequency_type"]
            now = datetime.now()
            next_time = None
            
            if freq_type == "hours":
                # 小時頻率：從現在開始計算下次時間
                hours = self.config["backup_frequency_value"]
                next_time = now + timedelta(hours=hours)
            
            elif freq_type == "daily":
                # 每日固定時間
                hour = self.config["backup_time_hour"]
                minute = self.config["backup_time_minute"]
                next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_time <= now:
                    next_time += timedelta(days=1)
            
            elif freq_type == "weekly":
                # 每週固定時間
                target_weekday = self.config["backup_weekday"]
                hour = self.config["backup_time_hour"]
                minute = self.config["backup_time_minute"]
                
                # 計算距離目標星期幾的天數
                current_weekday = now.weekday()
                days_ahead = target_weekday - current_weekday
                if days_ahead <= 0:  # 如果已經過了本週的目標日期
                    days_ahead += 7
                
                next_time = now + timedelta(days=days_ahead)
                next_time = next_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                # 如果計算出的時間就是今天但已經過了，則推到下週
                if days_ahead == 0 and next_time <= now:
                    next_time += timedelta(weeks=1)
            
            elif freq_type == "monthly":
                # 每月固定日期
                day = self.config["backup_day"]
                hour = self.config["backup_time_hour"]
                minute = self.config["backup_time_minute"]
                
                try:
                    next_time = now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    if next_time <= now:
                        # 推到下個月
                        if now.month == 12:
                            next_time = next_time.replace(year=now.year + 1, month=1)
                        else:
                            next_time = next_time.replace(month=now.month + 1)
                except ValueError:
                    # 處理日期無效的情況（如31日在某些月份）
                    next_time = None
            
            if next_time:
                time_str = next_time.strftime("%Y-%m-%d %H:%M:%S")
                self.next_backup_label.configure(text=time_str)
            else:
                self.next_backup_label.configure(text="無法計算")
        
        except Exception as e:
            self.log_message(f"更新下次備份時間失敗: {str(e)}")
            self.next_backup_label.configure(text="計算錯誤")
    
    def _auto_download_and_install_server(self):
        """自動下載並安裝伺服器（在找不到 bedrock_server.exe 時使用）"""
        try:
            self.log_message("=" * 60)
            self.log_message("開始自動下載並安裝 Bedrock Server...")
            self.log_message("=" * 60)
            
            # 步驟 1: 獲取下載連結
            self.log_message("步驟 1/3: 獲取最新版本下載連結...")
            
            download_api = "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            }
            
            response = requests.get(download_api, headers=headers, timeout=30)
            if response.status_code != 200:
                raise Exception(f"API 回應錯誤: {response.status_code}")
            
            data = response.json()
            links = data.get("result", {}).get("links", [])
            
            target_link = None
            for link in links:
                if link.get("downloadType") == "serverBedrockWindows":
                    target_link = link
                    break
            
            if not target_link:
                raise Exception("找不到 'serverBedrockWindows' 對應的下載連結")
            
            download_url = target_link.get("downloadUrl", "")
            if not download_url:
                raise Exception("下載連結為空")
            
            # 提取版本號
            import re
            version_match = re.search(r'bedrock-server-([\d\.]+)\.zip', download_url)
            if not version_match:
                raise Exception(f"無法從連結中提取版本號: {download_url}")
            
            version = version_match.group(1)
            self.log_message(f"最新版本：{version}")
            self.log_message(f"下載連結：{download_url}")
            self.log_message("-" * 60)
            
            # 步驟 2: 下載伺服器檔案
            self.log_message("步驟 2/3: 下載伺服器檔案...")
            
            temp_zip = self.temp_dir / f"bedrock-server-{version}.zip"
            
            response = requests.get(download_url, headers=headers, stream=True, timeout=300)
            total_size = int(response.headers.get('content-length', 0))
            
            downloaded = 0
            with open(temp_zip, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            if percent % 20 == 0 and percent != getattr(self, '_last_progress', -1):
                                self.log_message(f"下載進度：{percent}%")
                                self._last_progress = percent
            
            self.log_message(f"下載完成：{temp_zip.name}")
            self.log_message("-" * 60)
            
            # 步驟 3: 解壓縮到 server_files
            self.log_message("步驟 3/3: 安裝伺服器檔案...")
            
            # 確保 server_files 資料夾存在
            self.server_dir.mkdir(parents=True, exist_ok=True)
            
            # 解壓縮
            with zipfile.ZipFile(temp_zip, 'r') as zipf:
                zipf.extractall(self.server_dir)
            
            self.log_message("伺服器檔案已解壓縮完成")
            
            # 清理暫存檔
            if temp_zip.exists():
                temp_zip.unlink()
                self.log_message("暫存檔已清理")
            
            self.log_message("-" * 60)
            self.log_message("✓ 伺服器安裝完成！")
            self.log_message(f"版本：{version}")
            self.log_message("=" * 60)
            
            # 更新伺服器版本資訊
            self.server_version = version
            if hasattr(self, 'version_label'):
                self.version_label.configure(text=version)
            
            # 重新讀取 server.properties（安裝後會生成）
            self.load_server_properties()
            self.log_message("已重新載入伺服器配置檔案")
            
            # 重新創建設定頁面以顯示新載入的配置
            if "伺服器設定" in self.pages:
                # 記住使用者當前所在的頁面
                current_page = None
                for name, page in self.pages.items():
                    if page.winfo_ismapped():
                        current_page = name
                        break
                
                # 移除舊的設定頁面
                old_page = self.pages["伺服器設定"]
                old_page.destroy()
                # 重新創建設定頁面
                self.create_settings_page()
                self.log_message("已更新伺服器設定介面")
                
                # 如果使用者原本不在伺服器設定頁面,切換回原本的頁面
                if current_page and current_page != "伺服器設定" and current_page in self.pages:
                    self.show_page(current_page)
            
            # 提示使用者並詢問是否立即啟動
            self.after(100, lambda: self._prompt_start_after_install())
            
        except Exception as e:
            self.log_message("=" * 60)
            self.log_message(f"✗ 自動安裝失敗: {str(e)}")
            self.log_message("=" * 60)
            self.show_error("安裝失敗", f"自動安裝伺服器失敗: {str(e)}\n\n請手動從官網下載：\nhttps://www.minecraft.net/download/server/bedrock")
    
    def _prompt_start_after_install(self):
        """安裝完成後詢問是否啟動伺服器"""
        result = self.ask_yes_no(
            "安裝完成",
            "Bedrock Server 安裝完成！\n\n是否立即啟動伺服器？"
        )
        if result:
            self.start_server()
    
    def auto_check_update_on_startup(self):
        """啟動時自動檢查更新（靜默模式，只在有新版本時彈窗）"""
        threading.Thread(target=lambda: self._check_update(is_auto=True), daemon=True).start()
    
    def check_update(self):
        """檢查伺服器更新"""
        threading.Thread(target=self._check_update, daemon=True).start()
    
    def _check_update(self, is_auto=False, silent=False):
        """檢查更新（執行緒）- 使用官方 API
        
        Args:
            is_auto: 是否為自動檢查（影響按鈕禁用和提示框顯示）
            silent: 是否為靜默模式（不顯示提示框，僅獲取下載連結）
        """
        try:
            # 僅在手動檢查且非靜默模式時禁用操作按鈕
            if not is_auto and not silent:
                self.after(0, self._disable_operation_buttons)
            
            self.log_message("正在檢查更新...")
            
            # 使用官方 API
            download_api = "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            }
            
            # 步驟 1: 取得 JSON 並篩選對應下載連結
            response = requests.get(download_api, headers=headers, timeout=30)
            
            if response.status_code != 200:
                raise Exception(f"API 回應錯誤: {response.status_code}")
            
            data = response.json()
            
            # 尋找 serverBedrockWindows 類型的下載連結
            links = data.get("result", {}).get("links", [])
            target_link = None
            
            for link in links:
                if link.get("downloadType") == "serverBedrockWindows":
                    target_link = link
                    break
            
            if not target_link:
                raise Exception("找不到 'serverBedrockWindows' 對應的下載連結")
            
            download_url = target_link.get("downloadUrl", "")
            
            if not download_url:
                raise Exception("下載連結為空")
            
            # 從下載連結中提取版本號 (例如：1.21.113.1)
            import re
            version_match = re.search(r'bedrock-server-([\d\.]+)\.zip', download_url)
            
            if not version_match:
                raise Exception(f"無法從連結中提取版本號: {download_url}")
            
            latest_version = version_match.group(1)
            
            # 更新介面
            self.latest_version_label.configure(text=latest_version)
            
            # 儲存下載資訊
            self.download_url = download_url
            self.latest_version = latest_version
            
            # 比較版本並記錄
            self.has_new_version = False  # 預設沒有新版本
            
            if self.server_version == "未知":
                self.log_message(f"已是最新版本: {latest_version}（當前版本未知，無法比較）")
                
                # 只在手動模式且非靜默模式下顯示回報窗口
                if not is_auto and not silent:
                    self.after(100, lambda: self.show_info(
                        "檢查更新",
                        f"目前版本：未知\n"
                        f"最新版本：{latest_version}\n\n"
                        f"無法比較版本，建議檢查伺服器是否正常運行。"
                    ))
            else:
                # 使用版本比較函數
                comparison = self._compare_versions(latest_version, self.server_version)
                
                if comparison > 0:
                    # 最新版本較新
                    self.has_new_version = True
                    self.log_message(f"找到最新版本: {latest_version}")
                    
                    # 只在手動模式且非靜默模式下詢問是否立即更新
                    if not is_auto and not silent:
                        self.after(100, lambda: self.ask_for_immediate_update(latest_version))
                elif comparison == 0:
                    # 版本相同
                    self.log_message(f"已是最新版本: {latest_version}")
                    
                    # 只在手動模式且非靜默模式下顯示已是最新版本的回報窗口
                    if not is_auto and not silent:
                        self.after(100, lambda: self.show_update_check_result(
                            self.server_version, 
                            latest_version, 
                            is_latest=True
                        ))
                else:
                    # 最新版本較舊（不應該發生，但以防萬一）
                    self.log_message(f"已是最新版本: {self.server_version}（檢測版本: {latest_version}）")
                    
                    # 只在手動模式且非靜默模式下顯示回報窗口
                    if not is_auto and not silent:
                        self.after(100, lambda: self.show_update_check_result(
                            self.server_version, 
                            latest_version, 
                            is_latest=True
                        ))

                
        except Exception as e:
            self.log_message(f"檢查更新錯誤: {str(e)}")
            # 只在錯誤時記錄下載連結
            if hasattr(self, 'download_url') and self.download_url:
                self.log_message(f"下載連結：{self.download_url}")
            self.latest_version_label.configure(text="檢查失敗")
            
            # 只在手動模式且非靜默模式下顯示錯誤回報窗口
            if not is_auto and not silent:
                self.after(100, lambda: self.show_error(
                    "檢查更新失敗",
                    f"檢查更新時發生錯誤：\n\n{str(e)}"
                ))
        finally:
            # 僅在手動檢查且非靜默模式時重新啟用操作按鈕
            if not is_auto and not silent:
                self.after(0, self._enable_operation_buttons)
    
    def show_update_check_result(self, current_version, latest_version, is_latest=True):
        """顯示檢查更新結果窗口"""
        if is_latest:
            self.show_info(
                "檢查更新",
                f"✓ 已是最新版本\n\n"
                f"目前版本：{current_version}\n"
                f"最新版本：{latest_version}\n\n"
                f"您的伺服器已是最新版本，無需更新。"
            )
        else:
            self.show_info(
                "檢查更新",
                f"目前版本：{current_version}\n"
                f"最新版本：{latest_version}"
            )
    
    def ask_for_immediate_update(self, latest_version):
        """詢問是否立即更新"""
        result = self.ask_yes_no(
            "發現新版本", 
            f"發現新版本: {latest_version}\n當前版本: {self.server_version}\n\n是否立即更新伺服器？\n（將會發送通知給玩家）"
        )
        if result:
            # 執行帶通知的更新
            self.manual_update_with_notification()
            self.log_message("提示：您也可以手動從 https://www.minecraft.net/download/server/bedrock 下載")
    
    def update_server(self):
        """更新伺服器"""
        if not hasattr(self, 'download_url'):
            self.show_error("錯誤", "沒有可用的更新")
            return
        
        result = self.ask_yes_no("確認", "確定要更新伺服器嗎？\n伺服器將會關閉並進行更新。")
        if not result:
            return
        
        threading.Thread(target=self._perform_update, daemon=True).start()
    
    def _download_update_file(self):
        """下載更新檔案（可獨立執行）"""
        try:
            if not hasattr(self, 'download_url') or not hasattr(self, 'latest_version'):
                self.log_message("錯誤：缺少下載資訊")
                return None
            
            self.log_message("正在下載更新檔...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            }
            
            temp_zip = self.temp_dir / f"bedrock-server-{self.latest_version}.zip"
            
            # 下載檔案（帶進度）
            response = requests.get(self.download_url, headers=headers, stream=True, timeout=300)
            total_size = int(response.headers.get('content-length', 0))
            
            downloaded = 0
            with open(temp_zip, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    # 檢查是否請求取消
                    if self.update_cancel_requested:
                        self.log_message("下載已取消")
                        # 關閉文件並刪除不完整的下載
                        f.close()
                        if temp_zip.exists():
                            temp_zip.unlink()
                        return None
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            # 只在每個新的整數倍20%時顯示一次進度
                            if percent % 20 == 0 and percent != getattr(self, '_last_progress', -1):
                                self.log_message(f"下載進度：{percent}%")
                                self._last_progress = percent
            
            # 再次檢查是否在下載完成時請求取消
            if self.update_cancel_requested:
                self.log_message("下載已取消")
                if temp_zip.exists():
                    temp_zip.unlink()
                return None
            
            self.log_message(f"下載完成：{temp_zip.name}")
            return temp_zip
            
        except Exception as e:
            self.log_message(f"下載失敗: {str(e)}")
            return None
    
    def _perform_update(self):
        """執行更新（執行緒）- 優化版本"""
        try:
            # 注意：按鈕禁用已在調用前處理，這裡不需要重複調用
            
            if not hasattr(self, 'download_url') or not hasattr(self, 'latest_version'):
                self.log_message("錯誤：缺少下載資訊")
                # 缺少資訊時重新啟用按鈕
                self.update_in_progress = False
                self.after(0, self._reset_update_buttons)
                return
            
            self.log_message("=" * 60)
            self.log_message("開始更新伺服器...")
            self.log_message(f"目標版本：{self.latest_version}")
            self.log_message("=" * 60)
            
            # 步驟 1/5: 下載更新檔（如果還沒下載）
            temp_zip = getattr(self, '_downloaded_zip', None)
            if not temp_zip or not temp_zip.exists():
                self.log_message("步驟 1/5: 下載更新檔...")
                temp_zip = self._download_update_file()
                if not temp_zip:
                    # 檢查是否為取消操作
                    if self.update_cancel_requested:
                        # 取消時不記錄為失敗，靜默返回
                        return
                    else:
                        raise Exception("下載失敗")
            else:
                self.log_message("步驟 1/5: 使用已下載的更新檔")
            
            self.log_message("-" * 60)
            
            # 步驟 2/5: 關閉伺服器
            self.log_message("步驟 2/5: 關閉伺服器...")
            
            if self.server_process:
                self._do_stop_server()
                time.sleep(3)
            
            self.log_message("伺服器已關閉")
            self.log_message("-" * 60)
            
            # 步驟 3/5: 將舊的 server_files 改名為 server_old
            self.log_message("步驟 3/5: 處理舊版本伺服器...")
            
            server_old = self.base_dir / "server_old"
            
            # 如果 server_old 已存在，先刪除
            if server_old.exists():
                self.log_message("刪除舊的 server_old 資料夾...")
                shutil.rmtree(server_old)
            
            # 將 server_files 改名為 server_old（作為唯一備份）
            if self.server_dir.exists():
                self.log_message("將 server_files 改名為 server_old（備份）...")
                self.server_dir.rename(server_old)
            
            self.log_message("舊版本已備份至 server_old")
            self.log_message("-" * 60)
            
            # 步驟 4/5: 建立新的 server_files 並解壓縮
            self.log_message("步驟 4/5: 安裝新版本...")
            
            # 建立新的 server_files 資料夾
            self.server_dir.mkdir(exist_ok=True)
            
            # 直接解壓縮到 server_files
            self.log_message("解壓縮更新檔到 server_files...")
            with zipfile.ZipFile(temp_zip, 'r') as zipf:
                zipf.extractall(self.server_dir)
            
            self.log_message("新版本安裝完成")
            self.log_message("-" * 60)
            
            # 步驟 5/5: 從 server_old 恢復設定與世界
            self.log_message("步驟 5/5: 恢復設定檔和世界資料...")
            
            important_items = ["worlds", "allowlist.json", "permissions.json", "server.properties"]
            
            for item in important_items:
                src = server_old / item
                if src.exists():
                    dst = self.server_dir / item
                    try:
                        # 先刪除新版本中的同名檔案（避免內容衝突）
                        if dst.exists():
                            if dst.is_dir():
                                shutil.rmtree(dst)
                            else:
                                dst.unlink()
                            self.log_message(f"已刪除新版本的 {item}")
                        
                        # 從 server_old 複製
                        if src.is_dir():
                            shutil.copytree(src, dst)
                        else:
                            shutil.copy2(src, dst)
                        self.log_message(f"已恢復: {item}")
                    except Exception as e:
                        self.log_message(f"恢復 {item} 失敗: {str(e)}")
            
            self.log_message("設定檔和世界資料恢復完成")
            self.log_message("-" * 60)
            
            # 清理暫存檔
            self.log_message("清理暫存檔...")
            try:
                if temp_zip.exists():
                    temp_zip.unlink()
                # 清除下載標記
                if hasattr(self, '_downloaded_zip'):
                    delattr(self, '_downloaded_zip')
                self.log_message("暫存檔已清理")
            except Exception as e:
                self.log_message(f"清理暫存檔時發生錯誤: {str(e)}")
            
            self.log_message("-" * 60)
            self.log_message("✓ 更新完成！")
            self.log_message(f"伺服器已更新至版本：{self.latest_version}")
            self.log_message("=" * 60)
            
            # 重新啟動伺服器
            time.sleep(2)
            self.log_message("正在重新啟動伺服器...")
            self.start_server()
            
            # 更新當前版本
            self.server_version = self.latest_version
            self.version_label.configure(text=self.server_version)
            
            # 重置更新狀態
            self.update_in_progress = False
            self.update_cancel_requested = False
            
            # 重新啟用操作按鈕
            self.after(0, self._reset_update_buttons)
            
        except Exception as e:
            self.log_message("=" * 60)
            self.log_message(f"✗ 更新失敗: {str(e)}")
            self.log_message("=" * 60)
            self.show_error("錯誤", f"更新失敗: {str(e)}\n\n您可以嘗試從 server_old 恢復伺服器。")
            
            # 嘗試恢復 server_old
            try:
                server_old = self.base_dir / "server_old"
                if server_old.exists() and not self.server_dir.exists():
                    self.log_message("嘗試從 server_old 恢復...")
                    server_old.rename(self.server_dir)
                    self.log_message("已恢復舊版本伺服器")
            except Exception as restore_error:
                self.log_message(f"恢復失敗: {str(restore_error)}")
            
            # 嘗試啟動伺服器
            try:
                time.sleep(2)
                self.start_server()
            except:
                pass
            
            # 重置更新狀態
            self.update_in_progress = False
            self.update_cancel_requested = False
            
            # 重新啟用操作按鈕
            self.after(0, self._reset_update_buttons)
    
    def change_theme(self, theme):
        """切換主題並保存設定"""
        ctk.set_appearance_mode(theme)
        self.config["theme"] = theme
        self.save_config()
        self.log_message(f"主題已切換為: {theme}")
    
    def log_message(self, message):
        """添加日誌訊息"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        if hasattr(self, 'log_text'):
            self.log_text.insert("end", log_entry)
            self.log_text.see("end")
    
    def on_closing(self):
        """視窗關閉處理"""
        if self.server_process is not None:
            result = self.ask_yes_no("確認", "伺服器正在運行中，確定要關閉嗎？")
            if result:
                self.log_message("正在關閉伺服器...")
                self._do_stop_server()
                time.sleep(2)
                self.destroy()
        else:
            self.destroy()

if __name__ == "__main__":
    app = BDSConsole()
    app.mainloop()