# Cloudflare SNI マッピングツール / CF SNI 映射工具

透過 Chromium 的 `--host-resolver-rules` 參數，把指定域名強制解析到自訂 IP，
**同時保留真實的 SNI 與 Host 頭**。適用於「DNS 被攔截、但 IP 可達」的網路環境。

> ⚠️ **進階使用者工具**。請自行確認使用情境符合當地法規、目標網站的服務條款，
> 以及所在網路環境（學校 / 公司）的使用政策。

---

## ✨ 功能

- **域名 → 自訂 IP 映射**：等價於 `curl --resolve`，但作用於完整瀏覽器
- **子域名自動覆蓋**：`www.a.com` 自動展開成 `a.com` + `*.a.com`，靜態資源免手動設定
- **追加マッピング**：頁面引用的外部域名（如 API、CDN）也能一併映射
- **失敗域名診斷**：載入完成後自動列出所有 `requestfailed` 的域名
- **信使域名池**：用未被封鎖的 Cloudflare 域名解析出可用邊緣 IP
- **`/cdn-cgi/trace` 節點查詢**：即時顯示命中哪個 CF 邊緣節點（`HKG` / `NRT` / `KHH` …）
- **離線瀏覽器路徑**：可手動指定 Playwright 瀏覽器所在資料夾，適合內網 / 無網環境
- **自動偵測瀏覽器**：解壓到程式同目錄時免設定，支援帶版本號的資料夾名
- **可捲動介面**：小視窗也不會擠破版面
- **深 / 淺色主題**、日文介面
- **完整日誌**：GUI ログ + `app.log` + stdout 三通道

---

## 🖼 介面

![screenshot](screenshot.png)

---

## 🚀 下載即用（一般使用者）

### 1. 到 [Releases](../../releases) 頁面下載**兩個**檔案

| 檔案 | 內容 | 
|---|---|
| `sni-tool-vX.Y.Z-windows.exe` | 主程式（單一 exe，onefile） |
| `playwright-browsers-vX.Y.Z-windows.zip` | Chromium 瀏覽器本體 |

> ⚠️ **兩個檔案必須從同一個 Release 下載**。混用不同版本會導致啟動失敗。
>
> ⏱ **首次啟動需等待 10–30 秒**（onefile 模式會把內部檔案解壓到臨時目錄），
> 第二次啟動仍需幾秒。如果頻繁使用、想要更快的啟動速度，
> 請自行從原始碼用 `--onedir` 模式建置（見下方說明）。

### 2. 解壓瀏覽器 zip 到 exe 同目錄

```
sni-tool\
├── sni-tool-v1.0.0-windows.exe
└── playwright-browsers\           ← 瀏覽器 zip 解壓到這裡
    └── chromium-XXXX\
        └── chrome-win64\
            └── chrome.exe
```

資料夾名稱不一定要是 `playwright-browsers`，`playwright-browsers-v1.0.0-windows` 這類帶版本號的名稱也能被自動偵測。

### 3. 雙擊 exe

啟動時會自動偵測瀏覽器資料夾，日誌會顯示：

```
[ブラウザパス] 自動検出: ...\playwright-browsers
```

沒有自動偵測到也無妨——點「参照…」手動選擇即可。

不需要設定環境變數、不需要安裝 Python、不需要連網。

### 4. 填入設定，點「🚀 ブラウザ起動」

| 欄位 | 說明 |
|---|---|
| ターゲットドメイン | 被封鎖的目標域名（例：`www.aiixi.cc`） |
| ターゲット URL | 完整 URL（可留空，預設 `https://<域名>/`） |
| メッセンジャードメイン | 學校 / 公司放行且走 Cloudflare 的域名（例：`www.gov.tw`） |
| ターゲット IP | 目標 IP。留空時自動用信使域名解析 |
| ブラウザパス | Chromium 所在資料夾。留空用 Playwright 預設 |
| 追加マッピング | 需要額外映射的第三方域名（見下方說明） |
| ヘッドレスモード | 不顯示瀏覽器視窗 |

---

## 🔗 追加マッピング：處理跨域資源

主域名下的**子域名會自動覆蓋**：

- 目標填 `www.aiixi.cc` → 規則自動包含 `MAP www.aiixi.cc`、`MAP aiixi.cc`、`MAP *.aiixi.cc`
- 頁面上的 `cdn.aiixi.cc`、`static.aiixi.cc` 等子域名全部走同一個 IP，無需手動設定

只有以下情況需要在「追加マッピング」補充：

1. 頁面引用了**其他域名**（如 `api.partner.com`、`cdn.other-site.net`）**且該域名也被封鎖**
2. 該域名**不在 Cloudflare 上**，需要指定真實 IP

格式（每行一個，`#` 開頭為註解）：

```
# 只寫域名 → 使用主 IP（對方在 CF 上時適用）
api.partner.com

# 域名 + IP → 使用指定 IP（對方不在 CF 上時適用）
cdn.example.net 203.0.113.42
```

### 怎麼知道要補哪些域名？

頁面載入完後，關閉瀏覽器視窗，日誌會列出所有失敗的請求：

```
[リクエスト失敗] net::ERR_NAME_NOT_RESOLVED - https://api.partner.com/v1/data
...
[注意] 以下のドメインでリクエストが失敗しました。必要なら「追加マッピング」に追加してください：
  - api.partner.com
```

照著加進「追加マッピング」即可。

---

## 🐍 從原始碼執行（開發者）

### 需求

- Python 3.11（3.12 也可，但 PyInstaller 打包建議 3.11）
- Windows 10 / 11（其他平台理論上可行但未測試）

### 步驟

```bash
# 1. 安裝依賴
pip install -r requirements.txt

# 2. 下載 Chromium
playwright install chromium

# 3. 執行
python app.py
```

---

## 📴 離線 / 內網環境

如果目標電腦無法連網下載 Chromium：

**A. 在有網的電腦上下載瀏覽器**

```powershell
# PowerShell
$env:PLAYWRIGHT_BROWSERS_PATH = "C:\playwright-browsers"
playwright install chromium
```

**B. 把 `C:\playwright-browsers` 整個資料夾拷到目標電腦**（例如 `D:\tools\playwright-browsers`）

**C. 把資料夾放在 exe 同目錄**（自動偵測），或在 GUI 的「ブラウザパス」欄位填入完整路徑

程式會自動設定 `PLAYWRIGHT_BROWSERS_PATH`，**不需要**設定系統環境變數。

---

## 🔧 原理

Chromium 支援 `--host-resolver-rules="MAP <域名> <IP>"` 啟動參數，
讓瀏覽器在 DNS 解析階段就把域名映射到指定 IP，
但後續 TLS 握手依然使用原始域名作為 SNI、HTTP 請求使用原始域名作為 Host。

這在 Cloudflare 的 anycast 架構下成立：CF 邊緣 IP 全球共享，
具體路由到哪個客戶的源站由 SNI 決定。因此可以用「未被封鎖的 CF 域名解析出的 IP」
去訪問「被封鎖但也在 CF 上的目標域名」。

多條規則用逗號分隔，支援 `*.` 通配符：

```
--host-resolver-rules=MAP www.a.com [IP], MAP *.a.com [IP], MAP a.com [IP]
```

注意 `*.a.com` **不匹配** `a.com` 本身，所以裸域名要單獨一條。

---

## ❓ 常見問題

### Q：啟動時報 `Executable doesn't exist at ...`

瀏覽器路徑沒設對。三個檢查點：

1. 「ブラウザパス」欄位是否填了正確路徑（要包含 `chromium-*` 子資料夾的那一層）
2. 瀏覽器 zip 和 exe 是否從**同一個 Release** 下載
3. 日誌中 `[実行ファイル]` 那行指向的路徑是否存在

### Q：`421 Misdirected Request`

Cloudflare 判斷 SNI 和 Host 不一致。通常是目標域名不在 Cloudflare 上，
或信使 IP 和目標站點屬於不同的 CF 帳號 / 方案。

### Q：頁面顯示出來但樣式 / 圖片跑不出來

通常是子域名或第三方域名被封。看日誌裡的 `[リクエスト失敗]` 清單，
把相關域名加進「追加マッピング」。

### Q：`/cdn-cgi/trace` 查不到節點

信使 IP 可能被學校 / 公司攔截，或本身不可達。試著換一個信使域名重試。

### Q：學校封鎖的是 SNI 而不是 IP

本工具**不修改 SNI**，只修改 DNS 解析結果。如果學校是基於 SNI 黑名單封鎖，
本工具無效。請改用其他方案。

### Q：exe 啟動很慢 / 被防毒軟體報毒

onefile 模式每次啟動都會把內部檔案解壓到 `%TEMP%\_MEIxxxxx\`，
首次啟動 10–30 秒屬正常。若 Windows Defender 或其他防毒軟體攔截，
請把 exe 加入白名單（onefile 的解壓行為是 PyInstaller 正常機制，非惡意代碼）。

---

## 🛠 自行建置

### 使用 GitHub Actions（推薦）

見 [.github/workflows/release.yml](.github/workflows/release.yml)。
打上 `v*` 標籤即自動觸發建置與發佈：

```bash
git tag v1.0.0
git push origin v1.0.0
```

CI 會自動：

1. 用 PyInstaller `--onefile` 打包成單一 exe
2. 用 `playwright install chromium` 下載瀏覽器並壓縮成 zip
3. 兩者一起附到 Release

### 本機建置

```bat
pip install setuptools==81.0.0
pip install -r requirements.txt
pip install pyinstaller==5.13.2

pyinstaller --onefile --console --clean --noupx ^
  --collect-all=playwright ^
  --collect-all=customtkinter ^
  --hidden-import=greenlet ^
  --hidden-import=pyee ^
  app.py
```

> **提示**：如果偏好啟動更快的資料夾模式，把 `--onefile` 改成 `--onedir`。
> 代價是分發時要壓縮整個 `dist/app/` 資料夾。

### 手動準備瀏覽器 zip

```powershell
# PowerShell
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\browsers"
python -m playwright install chromium
Compress-Archive -Path "$env:PLAYWRIGHT_BROWSERS_PATH\*" -DestinationPath playwright-browsers.zip
```

---

## ⚠️ 免責聲明

本工具僅供網路診斷、研究與個人學習使用。使用者需自行負責：

- 確認使用情境符合當地法規
- 確認符合目標網站的服務條款
- 確認符合所在網路環境（學校 / 公司）的使用政策

作者不對任何濫用行為負責。

---

## 📄 授權

[MIT License](LICENSE)
