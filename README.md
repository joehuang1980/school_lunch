# school_lunch

每週自動抓取「復興國小午餐廚房」頁面中的 Google Drive 菜單檔案，並推送到 Discord。

## 功能

- 每週日晚上 21:00（台灣時間）自動執行
- 從目標頁面擷取 Google Drive 檔案連結
- 下載檔案後直接上傳到 Discord 頻道
- 只發送新檔案（已發送過的檔案 ID 會自動略過）
- 支援手動觸發（GitHub Actions）

## 目錄

- `.github/workflows/weekly_menu_to_discord.yml`：每週排程
- `scripts/post_menu_to_discord.py`：抓取、下載、推送邏輯
- `requirements.txt`：Python 套件

## 設定方式

1. 在 Discord 建立新的伺服器或頻道。
2. 在該頻道建立 Webhook，取得 Webhook URL。
3. 到 GitHub 專案 `Settings -> Secrets and variables -> Actions` 新增 Secret：
	- `DISCORD_WEBHOOK_URL`：Discord Webhook URL
4. （可選）如果要更換來源網址，可在 GitHub `Variables` 設定：
	- `SOURCE_URL`：預設為復興國小午餐廚房頁面
5. 推上 GitHub 後，workflow 會在每週日 13:00 UTC（台灣時間 21:00）自動執行。

## 手動測試

在 GitHub Actions 頁面選擇 `Weekly Lunch Menu To Discord`，點 `Run workflow`。

## 本機執行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DISCORD_WEBHOOK_URL='你的 webhook URL'
python scripts/post_menu_to_discord.py
```

## 備註

- 目前是根據頁面中的 Google Drive 檔案連結抓檔案。
- 發送紀錄會儲存在 workflow cache 的 `.state/posted_files.json`，用來避免重複發送。
- 如果學校未來改版（例如改成圖片或其他嵌入來源），需要再調整抓取規則。
