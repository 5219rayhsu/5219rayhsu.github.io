# 網站維護與驗收

## 日常修改

既有靜態 HTML 保留；不需安裝大型前端框架。人物的共用結構化資料維護在
`site-data/person.json`；三語主導覽維護在 `site-data/navigation.json`。
作品題名、原文與圖說在原本 HTML，`llms.txt` 仍獨立維護。

```sh
python -m pip install -r tools/requirements.txt
python -m playwright install --with-deps chromium webkit
python tools/sync_site.py
python tools/check_site.py
python tools/browser_check.py
BROWSER=webkit python tools/browser_check.py
```

`sync_site.py --check` 拒絕過期的共用資料、圖片提示及 CSS/JS 雜湊版本。
新產生的 320px 寬預覽圖不覆寫原圖；既有 506px 版本與放大圖保留。
`site-data/content-baseline.json` 保護本次核准的 main 文字、題名及替代文字。
日後站主有意編輯原文時，應連同審查後的 baseline 一起更新，不能為讓測試通過
而自動接受所有文字變更。

## 發布

先在工作分支完成上述測試，等待 `Site quality / validate` 成功才更新 main；
本次修復也採相同順序。既有 Pages 由 main 發布，不更換網址或刪除舊入口。
發布後執行 `python tools/verify_live.py`，它用 GET 比對正式站 36 頁與資源的
實際內容雜湊，也檢查 llms.txt、舊 index.html 入口與 404 回應。

注意：新增 CI 檢查不等於 GitHub 分支保護。Repo 管理員須將 validate 設為
必要檢查並要求修改提案，才能阻止有權限的人繞過流程直接推送 main。
沒有足夠 administration 權限時，不應聲稱已完成這項帳號設定。

## SEO 成效基線：帳號資料不可編造

Search Console 的擁有權、收錄狀態、Google 選定的 canonical、查詢與點擊均須
在已授權的 GSC 帳號取得。現有驗證 HTML 檔保留，但檔案存在不等於帳號驗證完成。
先匯出最近 28 天的 Queries、Pages、Devices 資料，保存在被 gitignore 排除的
`seo-exports/`，不要將完整查詢報表或任何認證資料上傳公開 repo。

```sh
python tools/seo_baseline.py seo-exports/Queries.csv > seo-exports/baseline.json
```

比較同等長度期間，區分姓名品牌詞與非品牌詞、中文/英文/日文頁面、手機/桌機。
CSV 工具只彙整已匯出的列；匿名化及列數限制可能使其不等於整個資源總量。
網站的 `portfolio:interaction` 自訂事件已備妥作品、展覽、文字及聯絡點擊；
預設不傳送、不儲存資料，也不載入外部追蹤。要做實際分析須另接經站主核准的
收集端，不把「事件可發出」說成「已收集訪客成效」。

## 已知驗證邊界

Playwright WebKit 不是實體 iPhone Safari；Chromium/WebKit 自動測試也不能替代
螢幕閱讀器人工測試或真實使用者效能數據。`verify_live.py` 記錄實際 HTTP 標頭，
不因原始碼缺 CSP 就自行宣告資安漏洞；不變更 GitHub Pages 平台控制的標頭。
