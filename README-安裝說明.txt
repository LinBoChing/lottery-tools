# 安裝方式

1. 把這個資料夾內的所有內容，連同 `.github` 隱藏資料夾，一起覆蓋到 GitHub Pages 倉庫根目錄。
2. 到 GitHub 倉庫的 **Actions**，點選 **Update lottery results**。
3. 點 **Run workflow**，等待約一分鐘。
4. 確認倉庫根目錄的 `latest-draws.json` 已更新。
5. 重新開啟網站，按「更新539＋天天樂」。

之後 GitHub Actions 每四小時自動檢查。手機只讀取自己網站的 `latest-draws.json`，不再直接連外站，因此不會遇到瀏覽器 CORS／HTTP 403。
