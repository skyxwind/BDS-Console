# BDS Console

## ⚠️ 關於【 Windows 已保護您的電腦 】

1. 由於此應用程式並未經過數位簽證認證，因此您的電腦可能會封鎖此應用程式的 exe 執行檔，您可以透過點擊【其他資訊】→【仍要執行】來開啟此應用程式
2. 若您仍然不放心，可以透過 [Source Code](source_code/BDS_Console.py) 自行編譯，

## 📖 簡介

BDS Console 是一個專為 Minecraft Bedrock Dedicated Server 設計的繁體中文圖形化管理工具，提供直觀的操作介面，讓伺服器管理變得簡單輕鬆。無需複雜的命令列操作，透過友善的 GUI 即可完成所有伺服器管理任務。

### ✨ 為什麼選擇 BDS Console？

- 🎨 **現代化介面** - 基於 CustomTkinter 打造，支援深色/淺色主題
- 🚀 **一鍵安裝** - 自動下載並安裝 Minecraft Bedrock Server
- 💾 **智能備份** - 支援手動和自動排程備份
- 🔄 **輕鬆更新** - 支援手動和自動檢查並更新伺服器版本
- 👥 **玩家管理** - 完整的白名單、權限和玩家管理功能
- 📊 **即時監控** - 即時顯示伺服器狀態和玩家資訊
- ⚙️ **全面設定** - GUI 化的 server.properties 編輯器

## 🎯 功能特色

### 🖥️ 伺服器管理
- **啟動/停止/重啟** 伺服器
- **即時日誌顯示** - 查看伺服器輸出和事件
- **控制台命令** - 直接發送命令到伺服器
- **狀態監控** - 即時顯示伺服器狀態和在線玩家數

### ⚙️ 設定管理
- **視覺化編輯器** - 無需手動編輯設定檔
- **完整參數支援** - 涵蓋所有 server.properties 選項
- **即時驗證** - 自動檢查設定值的有效性
- **配置說明** - 每個選項都有詳細的繁體中文說明

### 👥 玩家管理
- **線上/離線玩家** - 查看所有玩家資訊
- **白名單管理** - 新增/移除白名單玩家
- **權限控制** - 管理玩家的 OP 權限
- **玩家操作** - 踢出玩家、發送訊息
- **批次操作** - 支援批次匯入/匯出玩家列表

### 💾 備份與更新
- **手動備份** - 隨時備份世界和設定檔
- **自動備份** - 設定排程自動備份（支援每日/每週/每月）
- **備份管理** - 瀏覽、還原、刪除歷史備份
- **版本更新** - 自動檢查並更新到最新版本
- **安全回退** - 更新失敗時自動還原

### 🎨 個人化設定
- **主題切換** - 深色模式/淺色模式
- **自動啟動** - 程式啟動時自動啟動伺服器
- **更新檢查** - 自動檢查 BDS 更新
- **視窗設定** - 可調整視窗大小和位置

## 📁 檔案結構

```
Your Folder/
├── BDS_Console.exe           # 主程式
├── data/                     # 管理介面的檔案資料夾
│   ├── config.json           # 介面設定檔
│   ├── backup_time.json      # 備份時間記錄檔
│   └── player_list.json      # 上線玩家紀錄檔
├── server_files/             # BDS 伺服器檔案
│   ├── bedrock_server.exe
│   ├── server.properties
│   ├── allowlist.json
│   ├── permissions.json
│   └── worlds/               
├── backup/                   # 備份資料夾
│   ├── server_settings/      # 伺服器設定檔 備份資料夾
│   ├── worlds_auto/          # 自動備份 世界資料夾
│   └── worlds_manual/        # 手動備份 世界資料夾
└── server_old/               # 舊 BDS 伺服器檔案(更新時產生)
```

## 📝 授權與致謝

### 授權條款

本專案採用 **GNU General Public License v3.0 (GPL-3.0)** 授權發布。

完整授權條款請參閱 [LICENSE](LICENSE)。

### 第三方程式庫

本專案使用以下開源程式庫，感謝這些優秀的專案：

| 程式庫 | 授權 | 用途 |
|--------|------|------|
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | MIT | 現代化 GUI 框架 |
| [Requests](https://github.com/psf/requests) | Apache-2.0 | HTTP 請求處理 |
| [Schedule](https://github.com/dbader/schedule) | MIT | 任務排程功能 |
| Python 標準庫 | PSF | 核心功能支援 |

詳細的授權來源引用說明請參閱 [授權來源引用](授權來源引用.md)。

### 重要聲明

⚠️ **本專案與 Minecraft 官方的關係**

- 本工具是獨立的第三方管理工具，不包含 Minecraft 或其任何衍生內容
- Minecraft®、Minecraft Bedrock Edition™ 及相關商標屬於 Microsoft Corporation 、 Mojang Studios 所有
- 本工具不由 Microsoft、Mojang Studios 或 Minecraft 官方開發、背書或關聯
- 使用者需遵守 [Minecraft 最終使用者授權合約 (EULA)](https://www.minecraft.net/eula) 和相關服務條款
  
