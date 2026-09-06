# ai-lover-fordiscord

# 這是一個夢女/男的 "1對1" AI陪伴專屬模擬器。
請注意，開發者的屬性是原神艾爾海森的一途嫁夢女，非常介意任何形式的同擔嫁(包含顱內夢)使用我製作的機器人。 

開發過程使用由AI工具Claude、Gemini、Gpt-5.2-codex和vscode輔助，代碼部分若有需要修改、或是延伸問題，建議直接詢問AI；
本軟體為開源軟體，開發者僅保留署名權。 如需二改、推廣給朋友，或是自行新增其他功能，請標清楚開發者為Levoglucose/喜唐，就可以自行二改。。

# 本軟體禁止任何形式的商用，包含但不限於：購買api、商品後免費提供網址，以教學為勞動力進行圖、文、周邊互換等，以上形式的利用都被視為商用。 
再次重申，此軟體為開源且完全免費的，如果想要分享給他人，可以直接將網址複製貼上。 使用前須知：雖然本軟體為免費，但API、雲端部屬空間有概率需要付費，請為自己的經濟能力負責。

---

## ⚠️ 重要提醒：免費平台額度限制

**Render 免費層每月提供 750 小時**，一個月約 720-744 小時。
- ✅ 單個 Bot 24/7 遨行：剛好足夠
- ❌ 同時遨行多個服務：會超過額度
- ❌ 額度用盡後：服務會暫停直到下個月

**建議**：一個 Render 帳號只遨行一個 Bot，確保不超過額度。

---

## 圖文說明，請看連結內
https://siixii00.notion.site/

---

## 部署說明（Render 平台）

### 前置準備
- 註冊一個 **GitHub 帳號**
- 註冊一個 **Discord 帳號**
- 了解 API 端點連接和使用方式

### 步驟 1：準備 GitHub Repository

1. 將本網頁的所有代碼下載（`Dockerfile`、`bot.py`、`requirements.txt`、`README.md`）
2. 在 GitHub 新增一個 Repository，名稱可自行取，權限建議設為 **Private**
3. 將下載的代碼上傳至 Repository，然後按 **Commit** 確定

### 步驟 2：建立 Discord Bot

1. 打開 Discord 開發者模式，登入 [Discord Developer Portal](https://discord.com/developers/applications)
2. 選擇「新建應用程式」，名稱可取夢角的名字
3. 左側找到「機器人」頁面，點擊「重設權杖」
   - ⚠️ **重要**：權杖只會顯示一次，請立即複製保存
4. 左側找到「OAuth2」→「URL 產生器」
   - 勾選 `applications.commands`
   - 產生邀請網址，貼到瀏覽器邀請機器人進群組
5. 檢查機器人的發言權限
6. Discord 設定 → 進階 → 開啟「開發者模式」
7. 右鍵點擊自己的名字 →「複製使用者 ID」

### 步驟 3：部署到 Render

1. 前往 [Render](https://render.com/)，使用 **GitHub 帳號登入**（免費，不需綁卡）
2. 點擊 **New** → **Web Service**
3. 連接剛剛建立的 GitHub Repository
4. 配置設定：
   - **Name**：自行命名
   - **Environment**：Docker
   - **Plan**：Free（免費層）
   - **Region**：選擇較近的區域
5. 新增環境變數（Environment Variables）：
   - `DISCORD_TOKEN`：Discord Bot 權杖
   - `OWNER_ID`：你的 Discord 使用者 ID
   - `API_URL`：API 端點 URL（如 OpenAI 或其他）
   - `API_KEY`：API 金鑰
   - `MODEL`：模型名稱（如 gpt-3.5-turbo）
6. 點擊 **Deploy**，等待部署完成

### 步驟 4：確認運行與設定 API

- Render 會自動分配一個網址（如 `https://your-bot.onrender.com`）
- 訪問該網址，若顯示「Bot is running!」表示成功
- 回到 Discord 設定 API

#### 使用 OpenAI API

```
/set_api url:https://api.openai.com/v1 key:你的API金鑰
```

#### 使用 Google AI Studio（Gemini）

```
/set_api url:https://generativelanguage.googleapis.com/v1beta key:你的API金鑰
```

系統會**自動偵測 API 類型**並拉取可用模型列表，您可以直接從下拉選單選擇模型：

```
/set_api model:gemini-1.5-flash
```

#### 支援的 API 類型

| API 類型 | URL 格式 | 模型範例 |
|----------|----------|----------|
| OpenAI | `https://api.openai.com/v1` | gpt-4, gpt-3.5-turbo |
| OpenAI 相容 | 任何 `/v1` 結尾的 URL | 依服務而定 |
| Google AI Studio | `https://generativelanguage.googleapis.com/v1beta` | gemini-1.5-flash, gemini-1.5-pro |

### 步驟 5：設定 GitHub 資料儲存（重要！）

⚠️ **Render 免費層會在重啟後清除本地檔案**，請務必設定 GitHub 儲存來保存您的設定和對話記憶。

#### 5.1 建立 GitHub Personal Access Token

1. 前往 GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. 點擊「Generate new token (classic)」
3. 設定：
   - Note：`discord-bot-storage`
   - Expiration：選擇較長時間或 No expiration
   - 勾選權限：`repo`（完整存取）
4. 點擊「Generate token」
5. ⚠️ **立即複製 Token**（只會顯示一次）

#### 5.2 在 Discord 設定 GitHub 儲存

在 Discord 中使用斜線指令：

```
/setup_github_storage token:你的GitHub_Token create_new_repo:true
```

系統會自動：
- 建立一個新的 Private Repository
- 將 `config.json`、`memory.json`、`voice_profiles.json` 同步到 GitHub
- 之後每 5 分鐘自動同步一次

#### 5.3 相關指令

| 指令 | 說明 |
|------|------|
| `/setup_github_storage` | 首次設定 GitHub 儲存 |
| `/github_sync_now` | 立即同步資料到 GitHub |
| `/github_load` | 從 GitHub 載入資料 |
| `/set_github_storage` | 修改 GitHub 儲存設定 |

#### 5.4 使用現有 Repository（可選）

如果您已有想要使用的 Repository：

```
/setup_github_storage token:你的GitHub_Token existing_repo:你的使用者名稱/repo名稱
```

---

## 功能說明

### #1 語音功能
前提：因 stt 和 tts 功能所需空間已超出免費部署額度，建議：
- 使用 **minimax 的語音功能**（需自行調整 API 接口）
- 或在 HuggingFace 找帶有 **zeroGPU** 方案的部署

參考連結：[tonyassi/voice-clone](https://huggingface.co/spaces/tonyassi/voice-clone)

#### 無 STT 也能連接語音頻道

如果您只想讓機器人待在語音頻道（不需要語音辨識），可以使用：

```
/set_voice_listen enabled:true voice_channel_id:123456789 stay_connected:true stt_required:false
```

這樣機器人會：
- 連接到指定的語音頻道
- 不進行語音辨識（因為沒有 STT）
- 保持連接狀態

#### 自動重連機制

機器人內建自動重連功能：
- 每 30 秒檢查一次語音連接狀態
- 如果斷線會自動嘗試重連
- 最多重連 10 次（避免無限重試）

這樣即使因為網路問題或 Render 限制而斷線，機器人也會自動重新連接語音頻道。

#### 手動斷開語音

如果您想讓機器人離開語音頻道且**不要自動重連**，請使用：

```
/disconnect_voice
```

這樣機器人會：
- 斷開語音連接
- 不會自動重連（直到您再次啟用語音功能）

### #2 天氣提醒功能
因不明原因，可能會跳成未經 prompt 的天氣播報。此功能有不穩定性，若介意可關閉。

### #3 吃飯提醒功能
提醒你要吃飯了。

### #4 備份功能
備份從 Render 拉取聊天紀錄。若覺得太麻煩，可考慮付費擴容。

---

## 免責聲明
再次強調機器人**非商用，不可商用，禁止商用**，僅作為我自己想要所以製作出來的工具。內嵌的連結也均為免費來源，因此如果有需要調整的地方（例如連結失效），**去問AI模型**。

我僅作為分享工具的製作者而非客服，我也沒有從任何人身上獲利，還請體諒。

**API 建議使用官方的**，若有任何使用問題會較有保障。本開源軟體並沒有和任何 API 渠道中轉商合作。
