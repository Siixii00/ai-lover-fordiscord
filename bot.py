import discord
from discord import app_commands
import os
import json
import aiohttp
import threading
import asyncio
import time
from flask import Flask
from datetime import datetime, timedelta, timezone

# ───────── Flask 心跳伺服器 (修正 Railway 埠號綁定) ─────────
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    # Railway 會自動分配 PORT，若無則預設 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 在背景執行 Flask 避免卡住 Discord Bot
threading.Thread(target=run_flask, daemon=True).start()

# ───────── 設定檔處理 (JSON) ─────────
CONFIG_FILE = "config.json"
MEMORY_FILE = "memory.json"

def load_config():
    env_api_url = os.environ.get("API_URL", "https://api.openai.com/v1")
    env_api_key = os.environ.get("API_KEY", "")
    env_model = os.environ.get("MODEL", "gpt-3.5-turbo")
    env_prompt = os.environ.get("SYSTEM_PROMPT", "你是一個友善的助手。")

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("api_url", env_api_url)
                data.setdefault("api_key", env_api_key)
                data.setdefault("model", env_model)
                data.setdefault("system_prompt", env_prompt)
                data.setdefault("forbidden", [])
                data.setdefault("timeout_minutes", 10)
                data.setdefault("auto_chime_in", True)
                return data
        except:
            pass
    return {
        "api_url": env_api_url,
        "api_key": env_api_key,
        "model": env_model,
        "system_prompt": env_prompt,
        "forbidden": [],
        "timeout_minutes": 10,
        "auto_chime_in": True
    }

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ───────── 對話紀錄與變數 ─────────
channel_history = {}
channel_last_time = {}
MAX_HISTORY = 10
memory_lock = threading.Lock()

def save_runtime_state():
    """把對話記憶與最後活動時間持久化到磁碟。"""
    try:
        with memory_lock:
            payload = {
                "channel_history": {str(k): v for k, v in channel_history.items()},
                "channel_last_time": {str(k): v for k, v in channel_last_time.items()}
            }
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
    except:
        pass

def load_runtime_state():
    """啟動時載入既有對話記憶，避免重啟後全部遺失。"""
    global channel_history, channel_last_time
    if not os.path.exists(MEMORY_FILE):
        return
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        loaded_history = data.get("channel_history", {})
        loaded_last_time = data.get("channel_last_time", {})

        channel_history = {
            int(k): v[-MAX_HISTORY:]
            for k, v in loaded_history.items()
            if isinstance(v, list)
        }
        channel_last_time = {
            int(k): float(v)
            for k, v in loaded_last_time.items()
        }
    except:
        channel_history = {}
        channel_last_time = {}

config = load_config()
load_runtime_state()

def _extract_speaker_and_text(content: str):
    """從 `顯示名稱: 訊息內容` 格式中切出發言者與內容。"""
    if not isinstance(content, str):
        return None, content
    if ": " in content:
        speaker, text = content.split(": ", 1)
        if speaker.strip():
            return speaker.strip(), text
    return None, content

def get_recent_speakers_summary(channel_id, limit=6):
    """整理最近對話中的發言者摘要，提供給 system prompt 做身分辨識。"""
    history = channel_history.get(channel_id, [])
    recent = history[-limit:]
    lines = []
    for item in recent:
        role = item.get("role")
        content = item.get("content", "")
        speaker, text = _extract_speaker_and_text(content)
        if role == "user":
            if speaker:
                lines.append(f"- 使用者({speaker}): {text}")
            else:
                lines.append(f"- 使用者(未知名稱): {content}")
        else:
            lines.append(f"- 助手: {content}")
    return "\n".join(lines) if lines else "- (目前沒有可用上下文)"

def add_to_history(channel_id, role, content):
    if channel_id not in channel_history:
        channel_history[channel_id] = []
    channel_history[channel_id].append({"role": role, "content": content})
    if len(channel_history[channel_id]) > MAX_HISTORY:
        channel_history[channel_id].pop(0)
    save_runtime_state()

# ───────── 核心工具：拉取模型清單 ─────────
async def fetch_models():
    """從自定義 API 網址拉取可用模型列表供選單使用"""
    if not config["api_key"] or not config["api_url"]:
        return []
    url = f"{config['api_url'].rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {config['api_key']}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m["id"] for m in data.get("data", [])]
                    return sorted(models)
    except:
        pass
    return []

# ───────── Discord Bot 設定 ─────────
intents = discord.Intents.default()
intents.message_content = True 

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # 自動同步斜線指令
        await self.tree.sync()
        # 啟動超時檢查背景任務
        self.loop.create_task(timeout_checker())

client = MyClient()
OWNER_ID = int(os.environ.get("OWNER_ID", 0))

def is_owner(interaction: discord.Interaction):
    return interaction.user.id == OWNER_ID

# ───────── API 呼叫邏輯 ─────────
def build_system_prompt(channel_id=None, author=None):
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    current_time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    weekday_list = ["一", "二", "三", "四", "五", "六", "日"]
    weekday = weekday_list[now.weekday()]

    prompt = config["system_prompt"]

    # 將時間資訊注入到 Prompt 中
    prompt += f"\n\n【目前時間感知】"
    prompt += f"\n現在的精確時間是：{current_time_str} (星期{weekday})"
    prompt += f"\n你必須根據這個時間來回應使用者（例如打招呼或提及日期）。"

    if author:
        is_boss = (author.id == OWNER_ID)
        # 取得使用者的顯示名稱 (伺服器暱稱優先，沒有就用一般名稱)
        display_name = author.display_name
        prompt += f"\n\n【目前的對話對象】"
        prompt += f"\n名稱：{display_name}"
        if is_boss:
            prompt += f"\n身份：他是你的【交往對象】。你對他應該展現出最高的忠誠度與親暱感。"
        else:
            prompt += f"\n身份：他是你主人的【朋友】。你可以對他友善，但要清楚知道誰才是真正的戀人。"

    # 身分辨識與上下文一致性規範（所有情境都必須遵守）
    prompt += (
        "\n\n【回覆前必做流程】"
        "\n1) 先閱讀最近上下文，辨識『最後一位人類發言者』是誰。"
        "\n2) 僅依該發言者的身分與語氣回覆，不可把其他角色當成目前對象。"
        "\n3) 若上下文不足以確認對象，必須明確用中性方式回覆，不能擅自捏造對象或關係。"
        "\n4) 任何回覆（被標記回覆、主動插嘴、沉默破冰）都必須遵守本 prompt 的人設與禁令。"
    )

    if channel_id is not None:
        prompt += "\n\n【最近對話摘要（請用於辨識發言者）】\n"
        prompt += get_recent_speakers_summary(channel_id)

    
    if config["forbidden"]:
        forbidden_list = "、".join(config["forbidden"])
        prompt += f"\n\n【絕對禁令】請絕對避免討論或提及以下話題：{forbidden_list}。如果使用者問到，請禮貌拒絕。"
    return prompt

async def call_api(channel_id, user_text=None, special_instruction=None, author=None):
    if not config["api_key"]: return "⚠️ 請先設定 API Key。"
    
    endpoint = f"{config['api_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    system_content = build_system_prompt(channel_id=channel_id, author=author)
    if special_instruction:
        system_content += f"\n\n[系統指令: {special_instruction}]"

    messages = [{"role": "system", "content": system_content}]
    messages += channel_history.get(channel_id, [])
    if user_text:
        messages.append({"role": "user", "content": user_text})

    body = {"model": config["model"], "messages": messages}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, json=body, timeout=45) as resp:
                if resp.status != 200:
                    res_text = await resp.text()
                    return f"❌ API 錯誤 ({resp.status}): {res_text[:100]}"
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ 連線失敗: {str(e)}"

async def check_if_should_chime(message):
    """讓 AI 決定是否要針對目前的對話進行插嘴"""
    if not config["api_key"]: return False, ""
    
    # 取得最近的對話內容作為判斷依據
    history = channel_history.get(message.channel.id, [])
    if not history: return False, ""
    
    # 構建判斷用的 Prompt（含發言者資訊）
    history_str = "\n".join([f"{m['role']}: {m['content']}" for m in history[-5:]])
    
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    
    decision_prompt = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": (
                "你是一個聊天室觀察者。你必須先辨識最後一位人類發言者與目前話題，再決定是否要『主動插嘴』。"
                "只需判斷是否插嘴，不要生成實際回覆內容。"
                "如果值得插嘴（可提供幫助、澄清、或符合人設），請回覆：{\"chime\": true}。"
                "如果不需要你參與，請回覆：{\"chime\": false}。"
                "注意：請只回覆 JSON 格式，不要有其他廢話。"
            )},
            {"role": "user", "content": (
                f"系統人設摘要：{config['system_prompt']}\n"
                f"最近對話摘要：\n{get_recent_speakers_summary(message.channel.id)}\n\n"
                f"原始對話紀錄：\n{history_str}"
            )}
        ],
        "response_format": { "type": "json_object" } # 確保回傳 JSON
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{config['api_url'].rstrip('/')}/chat/completions", 
                                   headers=headers, json=decision_prompt, timeout=10) as resp:
                data = await resp.json()
                result = json.loads(data["choices"][0]["message"]["content"])
                return result.get("chime", False), ""
    except:
        return False, ""

# ───────── 背景任務：超時主動說話 ─────────
async def timeout_checker():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(60)
        now = time.time()
        timeout_sec = config["timeout_minutes"] * 60

        for channel_id, last_time in list(channel_last_time.items()):
            if now - last_time >= timeout_sec:
                channel = client.get_channel(channel_id)
                if channel:
                    try:
                        reply = await call_api(
                            channel_id,
                            special_instruction=(
                                "目前頻道沉默中。請先確認最近對話中的最後發言者身分，"
                                "再以你的人設自然地說一句破冰話；若無明確對象，"
                                "請用中性、非指定對象的方式開場。"
                            )
                        )
                        await channel.send(reply)
                        add_to_history(channel_id, "assistant", reply)
                    except: pass
                channel_last_time[channel_id] = now
                save_runtime_state()

# ───────── Discord 事件 ─────────
@client.event
async def on_ready():
    print(f"✅ Bot 已在 Railway 上線：{client.user}")

@client.event
async def on_message(message):
    if message.author == client.user: return
    
    # 紀錄訊息（包含發言者名稱，這能幫助 AI 識別誰是誰）
    display_text = f"{message.author.display_name}: {message.content}"
    add_to_history(message.channel.id, "user", display_text)
    channel_last_time[message.channel.id] = time.time()
    save_runtime_state()

    # 情況 A：被標記 (@Bot) -> 必定回覆
    if client.user in message.mentions:
        async with message.channel.typing():
            reply = await call_api(
                message.channel.id,
                special_instruction=(
                    f"你正在回覆被標記訊息。最後發言者是 {message.author.display_name}，"
                    "請以此人為對象並嚴格遵守人設。"
                ),
                author=message.author
            )
            await message.reply(reply)
            add_to_history(message.channel.id, "assistant", reply)
        return

    # 情況 B：沒被標記 -> 判斷是否要自動插嘴
    if config.get("auto_chime_in", True):
        # 隨機等待 1~3 秒，模擬真人在看訊息的感覺
        await asyncio.sleep(2) 
        
        should_chime, _ = await check_if_should_chime(message)
        
        if should_chime:
            async with message.channel.typing():
                chime_reply = await call_api(
                    message.channel.id,
                    special_instruction=(
                        f"你決定要主動插嘴。請先確認最後發言者是 {message.author.display_name}，"
                        "再依照人設給出簡短、自然且不搶戲的一句話。"
                    ),
                    author=message.author
                )
                await message.channel.send(chime_reply)
                add_to_history(message.channel.id, "assistant", chime_reply)
# ───────── 斜線指令面板 ─────────

# 自動補完模型清單
async def model_autocomplete(interaction: discord.Interaction, current: str):
    models = await fetch_models()
    return [app_commands.Choice(name=m, value=m) for m in models if current.lower() in m.lower()][:25]

@client.tree.command(name="config", description="查看機器人完整設定項目")
async def slash_config(interaction: discord.Interaction):
    if not is_owner(interaction): return
    forbidden_str = ", ".join(config["forbidden"]) if config["forbidden"] else "無"
    info = (
        f"**🤖 機器人目前設定**\n"
        f"🔗 **API URL**: `{config['api_url']}`\n"
        f"🤖 **模型**: `{config['model']}`\n"
        f"📝 **個性**: `{config['system_prompt']}`\n"
        f"🚫 **禁止詞**: `{forbidden_str}`\n"
        f"⏱️ **超時時間**: `{config['timeout_minutes']} 分鐘`"
    )
    await interaction.response.send_message(info, ephemeral=True)

@client.tree.command(name="set_url", description="設定 API 基礎網址")
async def set_url(interaction: discord.Interaction, url: str):
    if not is_owner(interaction): return
    config["api_url"] = url
    save_config(config)
    await interaction.response.send_message(f"✅ API URL 已更新：`{url}`", ephemeral=True)

@client.tree.command(name="set_key", description="設定 API 金鑰")
async def set_key(interaction: discord.Interaction, key: str):
    if not is_owner(interaction): return
    config["api_key"] = key
    save_config(config)
    await interaction.response.send_message("✅ API Key 已更新。", ephemeral=True)

@client.tree.command(name="set_model", description="設定 AI 模型 (可自動補完清單)")
@app_commands.autocomplete(model=model_autocomplete)
async def set_model(interaction: discord.Interaction, model: str):
    if not is_owner(interaction): return
    config["model"] = model
    save_config(config)
    await interaction.response.send_message(f"✅ 模型已切換為：`{model}`", ephemeral=True)

@client.tree.command(name="set_prompt", description="設定機器人個性/規則")
async def set_prompt(interaction: discord.Interaction, prompt: str):
    if not is_owner(interaction): return
    config["system_prompt"] = prompt
    save_config(config)
    await interaction.response.send_message(f"✅ 個性設定已更新！", ephemeral=True)

@client.tree.command(name="add_forbidden", description="新增禁止提及的詞彙")
async def add_forbidden(interaction: discord.Interaction, word: str):
    if not is_owner(interaction): return
    if word not in config["forbidden"]:
        config["forbidden"].append(word)
        save_config(config)
    await interaction.response.send_message(f"✅ 已將 `{word}` 加入禁止詞清單。", ephemeral=True)

@client.tree.command(name="clear_forbidden", description="清空所有禁止詞")
async def clear_forbidden(interaction: discord.Interaction):
    if not is_owner(interaction): return
    config["forbidden"] = []
    save_config(config)
    await interaction.response.send_message("✅ 禁止詞清單已清空。", ephemeral=True)

@client.tree.command(name="set_timeout", description="設定沉默多久(分)後機器人主動開話題")
async def set_timeout(interaction: discord.Interaction, minutes: int):
    if not is_owner(interaction): return
    config["timeout_minutes"] = minutes
    save_config(config)
    await interaction.response.send_message(f"✅ 超時設定為 `{minutes}` 分鐘。", ephemeral=True)

@client.tree.command(name="sync", description="強制同步指令選單")
async def sync(interaction: discord.Interaction):
    if not is_owner(interaction): return
    await client.tree.sync()
    await interaction.response.send_message("🔄 指令已同步，請重啟 Discord 查看。", ephemeral=True)

# ───────── 啟動 ─────────
if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if TOKEN:
        client.run(TOKEN)
    else:
        print("❌ 錯誤：找不到 DISCORD_TOKEN 環境變數")
