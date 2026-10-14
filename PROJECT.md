# Animeko ads clean

## 專案特徵與範圍

- 上游：open-ani/animeko；本儲存庫：ezn24/animeko-ads-clean；預設分支：noad-ci。
- 輕量補丁儲存庫：每次建置解析官方 release tag 為固定 commit，各平台共用同一份來源。
- scripts/patch_source.py 透過 Kotlin token 辨識類別與函式，過濾播放頁推薦項目（只保留 uri 為 null 且 subjectId > 0），停用官方更新檢查。noad.patch 僅供舊版參考。
- 不處理影片內嵌廣告；不修改資料源、播放器或核心 UI。
- 本地測試需求：只建置 Android 手機版 debug APK，不在 GitHub Actions 執行 debug 建置。
- 正式版需求：workflow 涵蓋上游已發布的平台。上游程式碼在無 Secrets 的工作中建置，Android APK 再由獨立乾淨工作使用 GitHub Actions Secrets 簽署。

## 全平台正式版

| 目標 | Runner | 產物 |
| --- | --- | --- |
| Android 手機與 Android TV | ubuntu-24.04 | 各自的 arm64-v8a、armeabi-v7a、x86_64、universal release APK |
| Windows x86_64 | windows-2025 | ZIP |
| Windows ARM64 | windows-11-arm | ZIP |
| macOS Apple Silicon | macos-15 | DMG |
| macOS Intel | macos-15-intel | ZIP |
| Linux x86_64 | ubuntu-24.04 | AppImage |
| iOS／iPadOS ARM64 | macos-15、Xcode 26.3 | IPA |

桌面套件沒有開發者憑證簽署或公證。iOS 產生需自行簽署安裝的 IPA；workflow 不接觸 Apple 私鑰，也不會自動上傳 App Store／TestFlight。

iOS 使用上游所需的 12g／20g JVM 設定。建構時先由 Gradle 產生 podspec 與 CocoaPods 所需的 dummy framework，再更新 Info.plist 並依上游文件直接執行 `pod install`；若首次安裝失敗，使用 `pod install --repo-update` 更新規格庫後重試。IPA 任務保留自動重試。由於 GitHub 標準 macOS runner 的 Kotlin/Native linking 資源可能不足，iOS 為實驗性矩陣項目；其失敗不阻斷 Android 簽章及其他平台發佈，Release 可在缺少 iOS artifact 時完成。

## 操作

Actions → noad multiplatform → Run workflow：

- tag：留空為官方最新穩定版，或填入例如 v6.2.0。
- workflow 每 6 小時檢查最新穩定版；尚無對應 `vX.Y.Z-noad` Release 時自動建構並發佈，已有版本則略過。
- `noad-ci` 的 workflow、補丁或 scripts 變更會自動觸發尚未發佈版本的建構；單純文件修改不觸發。
- 手動執行可重建已存在版本並保留 Actions artifacts，但不覆蓋既有 Release。
- 平台建構前由共用 preflight 執行離線測試與修改器相容檢查；import、註解、行號、排版與目標檔名／位置變更不依赖 diff context。功能結構不相容時只在 preflight 停止，不啟動平台建構，也不發布未修改的官方版本。
- 每個平台均提供 build-info、實際 tracked source diff 與 SHA-256。

## GitHub Secrets

位置：Settings → Secrets and variables → Actions → Secrets。

Android release 必填，缺少任一項時獨立簽署 job 會失敗：

| Secret | 內容 |
| --- | --- |
| SIGNING_RELEASE_STOREFILE | 自己的 .jks／.keystore 檔案經 Base64 編碼 |
| SIGNING_RELEASE_STOREPASSWORD | keystore 密碼 |
| SIGNING_RELEASE_KEYALIAS | key alias |
| SIGNING_RELEASE_KEYPASSWORD | 私鑰密碼 |

PowerShell 取得檔案的 Base64（自行將結果貼到 GitHub Secret，勿貼到公開 issue 或程式碼）：

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes('C:\path\release.jks')) | Set-Clipboard
```

請持續使用同一組 keystore，才能升級此 fork 的既有安裝。它無法以不同憑證直接覆蓋官方安裝。

可在 Actions **Variables** 設定 IOS_BUNDLE_ID；未設定則沿用上游 Bundle ID。iOS IPA 仍需在可信任環境自行簽署。

彈彈play（DanDanPlay）使用 `DANDANPLAY_APP_ID` 與 `DANDANPLAY_APP_SECRET` 兩個 GitHub Secrets；兩者齊全時寫入上游要求的 local.properties 建構參數，未設定時該彈幕來源不可用。Firebase 預設關閉。

私密檔案不提交、不上傳到 artifacts。彈彈play 憑證由 Gradle／Xcode 在建構時嵌入用戶端；Android keystore 不會交給上游建構程式，僅存在獨立簽署工作並在結束前刪除。建置命令不使用 --scan。

## 本地手機版測試

- 使用 JBR 21（含 JCEF）、Android SDK platform 37.0、build-tools 36.0.0。
- 執行 `python scripts/patch_source.py <上游根目錄>` 套用修改；加上 `--check` 可只檢查相容性。local.properties 設定 sdk.dir、ani.android.abis=all、ani.android.debug.applicationIdSuffix=.noad.debug、ani.enable.firebase=false。
- 執行 `gradlew.bat :app:android:assembleDefaultDebug`；不要執行 assembleDebug（後者也會建 TV）。
- 產物：app/android/build/outputs/apk/default/debug/。universal APK 可涵蓋所有建置架構。
- Debug 套件名稱 me.him188.ani.noad.debug，可與正式版並存；採本地 debug key 簽署。
- 未設定服務金鑰時，彈彈play彈幕來源不可用，其他功能仍須由使用者實機驗證。

## 驗證狀態

目前以官方 v6.3.0 作為適配基準。2026-10-14 起的近期排程在所有平台的 `Apply patch and configure build` 同時失敗，完整 log 顯示上游 `UpdateChecker.kt` 新增 import 後使舊補丁 context 失效；補丁已用較小 context 重新產生，並以 `git apply --check` 驗證同時相容 v6.2.0 與 v6.3.0。iOS 建構會在 `pod install` 前產生 Kotlin dummy framework。Android 使用 6 GiB Gradle heap、單一 worker，並依序建構手機與 TV。發布時明確傳入 `GITHUB_REPOSITORY`。各平台 UI 與播放功能仍需實機驗證。Android 手機 debug APK 已由本地獨立編譯，不以 CI 產物替代。

## 儲存庫維護

- 2026-10-15：以程式 token 修改器取代正式建構的 unified diff 套用，避免 v6.3.0 新增 import 導致的同類失敗。兩個目標均驗證後才寫入，重複套用不會重複加入修改。build-info 使用 patcher_sha256 記錄修改器雜湊，實際修改仍以 source-changes patch 提供。
- 不長時間輪詢 Actions 或建構 log；Android 實機測試由使用者進行。大量消耗額度的操作須先取得批准。

- README 需直接說明補丁功能、支援平台、建構方式、Android Secrets 與已知限制。
- `noad-ci` 保持精簡歷史，避免保留 workflow 觸發、已撤回方案與逐步修正等過程型 commit。

