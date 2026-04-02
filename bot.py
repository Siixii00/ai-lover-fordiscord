import discord
from discord import app_commands
import os
import json
import aiohttp
import threading
import asyncio
import time
import random
from flask import Flask
from typing import Optional
import re
import base64
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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
CHAT_LOG_DIR = "chat_logs"

def load_config():
    env_api_url = os.environ.get("API_URL", "https://api.openai.com/v1")
    env_api_key = os.environ.get("API_KEY", "")
    env_model = os.environ.get("MODEL", "gpt-3.5-turbo")
    env_prompt = os.environ.get("SYSTEM_PROMPT", "你是一個友善的助手。")
    env_roleplay_prompt = os.environ.get("ROLEPLAY_PROMPT", "")
    env_character_prompt = os.environ.get("CHARACTER_PROMPT", "")

    default_forbidden_words = [
        "說教",
        "重複 prompt 內容",
        "AI 原生模型"
    ]

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("api_url", env_api_url)
                data.setdefault("api_key", env_api_key)
                data.setdefault("model", env_model)
                data.setdefault("system_prompt", env_prompt)
                data.setdefault("roleplay_prompt", env_roleplay_prompt)
                data.setdefault("character_prompt", env_character_prompt)
                if "forbidden" in data and "forbidden_words" not in data:
                    data["forbidden_words"] = data.get("forbidden", default_forbidden_words)
                data.setdefault("forbidden_words", default_forbidden_words)
                data.setdefault("forbidden_foods", [])
                data.setdefault("hated_foods", [])
                data.setdefault("forbidden_actions", [])
                data.setdefault("github", {
                    "repo": "",
                    "branch": "main",
                    "path": "summaries/",
                    "token_env": "GITHUB_TOKEN"
                })
                data.setdefault("summary_schedule", {
                    "enabled": False,
                    "time": "",
                    "timezone": "Asia/Taipei",
                    "last_sent_date": ""
                })
                data.setdefault("response_style", "請用更少斷句、口語對話感，篇幅可略長。若有動作描述，請用()括起來。禁止暴露或逐步展示思考過程。")
                data.setdefault("owner_profile", {
                    "name": "",
                    "id": "",
                    "title": "",
                    "pronoun": ""
                })
                data.setdefault("timeout_minutes", 10)
                data.setdefault("dinner_location", "")
                data.setdefault("auto_chime_in", True)
                data.setdefault("chime_in_channels", [])
                data.setdefault("user_profile", {
                    "appearance": "",
                    "personality": "",
                    "occupation": ""
                })
                data.setdefault("weather_reminder", {
                    "enabled": False,
                    "location": "",
                    "time": "",
                    "channel_id": 0,
                    "timezone": "Asia/Taipei",
                    "last_sent_date": ""
                })
                return data
        except:
            pass
    return {
        "api_url": env_api_url,
        "api_key": env_api_key,
        "model": env_model,
        "system_prompt": env_prompt,
        "roleplay_prompt": env_roleplay_prompt,
        "character_prompt": env_character_prompt,
        "forbidden_words": default_forbidden_words,
        "forbidden_foods": [],
        "hated_foods": [],
        "forbidden_actions": [],
        "github": {
            "repo": "",
            "branch": "main",
            "path": "summaries/",
            "token_env": "GITHUB_TOKEN"
        },
        "summary_schedule": {
            "enabled": False,
            "time": "",
            "timezone": "Asia/Taipei",
            "last_sent_date": ""
        },
        "response_style": "請用更少斷句、口語對話感，篇幅可略長。若有動作描述，請用()括起來。禁止暴露或逐步展示思考過程。",
        "owner_profile": {
            "name": "",
            "id": "",
            "title": "",
            "pronoun": ""
        },
        "timeout_minutes": 10,
        "dinner_location": "",
        "auto_chime_in": True,
        "chime_in_channels": [],
        "user_profile": {
            "appearance": "",
            "personality": "",
            "occupation": ""
        },
        "weather_reminder": {
            "enabled": False,
            "location": "",
            "time": "",
            "channel_id": 0,
            "timezone": "Asia/Taipei",
            "last_sent_date": ""
        }
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

def _get_summary_timezone():
    tz_name = str(config.get("summary_schedule", {}).get("timezone", "Asia/Taipei")).strip()
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("Asia/Taipei")

def _append_chat_log(channel_id: int, role: str, content: str):
    try:
        os.makedirs(CHAT_LOG_DIR, exist_ok=True)
        now_local = datetime.now(_get_summary_timezone())
        date_str = now_local.strftime("%Y-%m-%d")
        log_path = os.path.join(CHAT_LOG_DIR, f"{date_str}.jsonl")
        entry = {
            "ts": now_local.isoformat(),
            "channel_id": int(channel_id),
            "role": role,
            "content": content
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except:
        pass

config = load_config()
load_runtime_state()

DINNER_OPTIONS = [
    "日式咖哩飯",
    "牛肉麵",
    "壽司",
    "韓式拌飯",
    "泰式打拋豬",
    "義大利麵",
    "披薩",
    "滷肉飯",
    "雞肉飯",
    "火鍋",
    "麻辣燙",
    "海鮮粥",
    "鍋貼",
    "水餃",
    "燒肉飯",
    "拉麵",
    "炒飯",
    "炒麵",
    "漢堡",
    "三明治",
    "沙拉",
    "關東煮",
    "鹽酥雞",
    "烤雞腿便當",
    "蔬食便當",
    "咖哩烏龍",
    "清燉雞湯麵",
    "壽喜燒",
    "鐵板燒",
    "燉飯"
]

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
    _append_chat_log(channel_id, role, content)
    save_runtime_state()

def _remove_last_assistant_message(channel_id):
    history = channel_history.get(channel_id, [])
    for i in range(len(history) - 1, -1, -1):
        if history[i].get("role") == "assistant":
            history.pop(i)
            channel_history[channel_id] = history
            save_runtime_state()
            return True
    return False

def _get_last_user_message(channel_id):
    history = channel_history.get(channel_id, [])
    for i in range(len(history) - 1, -1, -1):
        if history[i].get("role") == "user":
            return history[i].get("content", "")
    return ""

def _is_chime_channel_allowed(channel_id: int):
    allowed = config.get("chime_in_channels", [])
    if not isinstance(allowed, list) or not allowed:
        return True
    try:
        allowed_ids = {int(cid) for cid in allowed}
    except Exception:
        return True
    return int(channel_id) in allowed_ids

def _parse_channel_id(raw: str) -> Optional[int]:
    if raw is None:
        return None
    digits = re.findall(r"\d+", str(raw))
    if not digits:
        return None
    try:
        return int(digits[0])
    except Exception:
        return None

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
        # 啟動每日天氣提醒背景任務
        self.loop.create_task(weather_reminder_checker())
        # 啟動每日總結背景任務
        self.loop.create_task(daily_summary_checker())

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

    owner_profile = config.get("owner_profile", {})
    owner_name = owner_profile.get("name", "")
    owner_id_text = owner_profile.get("id", "")
    owner_title = owner_profile.get("title", "")
    owner_pronoun = owner_profile.get("pronoun", "")
    if owner_name or owner_id_text or owner_title or owner_pronoun:
        prompt += "\n\n【Owner 身分提醒】"
        if owner_name:
            prompt += f"\n- Discord 名字：{owner_name}"
        if owner_id_text:
            prompt += f"\n- Discord ID：{owner_id_text}"
        if owner_title:
            prompt += f"\n- 你對 Owner 的稱呼：{owner_title}"
        if owner_pronoun:
            prompt += f"\n- Owner 人稱代詞：{owner_pronoun}"

    response_style = str(config.get("response_style", "")).strip()
    if response_style:
        prompt += f"\n\n【回應文風】\n{response_style}"

    roleplay_prompt = str(config.get("roleplay_prompt", "")).strip()
    character_prompt = str(config.get("character_prompt", "")).strip()
    if roleplay_prompt:
        prompt += f"\n\n【Roleplay 守則】\n{roleplay_prompt}"
    if character_prompt:
        prompt += f"\n\n【角色設定】\n{character_prompt}"

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

        if is_boss:
            profile = config.get("user_profile", {})
            appearance = profile.get("appearance", "").strip()
            personality = profile.get("personality", "").strip()
            occupation = profile.get("occupation", "").strip()
            prompt += "\n\n【主要使用者設定】"
            prompt += f"\n外觀：{appearance or '（未設定）'}"
            prompt += f"\n個性：{personality or '（未設定）'}"
            prompt += f"\n職業：{occupation or '（未設定）'}"
            prompt += (
                "\n你必須讀取並記住上述設定，"
                "在回覆主要使用者時融入外觀、個性與職業相關的細節，"
                "以提升代入感。"
            )

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

    
    forbidden_words = config.get("forbidden_words", []) or []
    forbidden_foods = config.get("forbidden_foods", []) or []
    hated_foods = config.get("hated_foods", []) or []
    forbidden_actions = config.get("forbidden_actions", []) or []

    if forbidden_words or forbidden_foods or hated_foods or forbidden_actions:
        prompt += "\n\n【絕對禁令】"
        if forbidden_words:
            prompt += f"\n- 禁止詞彙：{'、'.join(forbidden_words)}"
        if forbidden_foods:
            prompt += f"\n- 禁止出現的食物：{'、'.join(forbidden_foods)}"
        if hated_foods:
            prompt += f"\n- OWNER 討厭的食物：{'、'.join(hated_foods)}"
        if forbidden_actions:
            prompt += f"\n- 禁止行為：{'、'.join(forbidden_actions)}"
        prompt += "\n若使用者提到上述內容，請禮貌拒絕並避免延伸。"
    return prompt

def profile_incomplete():
    profile = config.get("user_profile", {})
    return any(
        not str(profile.get(key, "")).strip()
        for key in ["appearance", "personality", "occupation"]
    )

async def call_api(channel_id, user_text=None, special_instruction=None, author=None):
    if not config["api_key"]: return "⚠️ 請先設定 API Key。"
    if author and author.id == OWNER_ID and profile_incomplete():
        return "⚠️ 主要使用者的外觀、個性或職業尚未設定，請先使用 /set_profile 完成設定。"
    
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

# ───────── 天氣查詢工具 ─────────
async def fetch_weather_summary(location: str):
    """使用 wttr.in 取得天氣資訊（免金鑰）"""
    query = location.strip()
    if not query:
        return "⚠️ 請提供有效地點。"

    url = f"https://wttr.in/{query}?format=j1"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return f"❌ 天氣服務錯誤 ({resp.status})，請稍後再試。"
                data = await resp.json()

        current = (data.get("current_condition") or [{}])[0]
        nearest = (data.get("nearest_area") or [{}])[0]
        area = ((nearest.get("areaName") or [{}])[0].get("value") or query)
        region = ((nearest.get("region") or [{}])[0].get("value") or "")
        country = ((nearest.get("country") or [{}])[0].get("value") or "")

        desc = ((current.get("weatherDesc") or [{}])[0].get("value") or "未知")
        temp_c = current.get("temp_C", "-")
        feels_c = current.get("FeelsLikeC", "-")
        humidity = current.get("humidity", "-")
        wind_kph = current.get("windspeedKmph", "-")

        location_display = "、".join([p for p in [area, region, country] if p])
        return (
            f"🌦️ {location_display} 天氣提醒\n"
            f"- 目前天氣：{desc}\n"
            f"- 溫度：{temp_c}°C（體感 {feels_c}°C）\n"
            f"- 濕度：{humidity}%\n"
            f"- 風速：{wind_kph} km/h"
        )
    except Exception as e:
        return f"❌ 無法取得天氣資料：{str(e)}"

def is_valid_hhmm(time_str: str):
    try:
        datetime.strptime(time_str, "%H:%M")
        return True
    except:
        return False

def is_valid_timezone(tz_name: str):
    try:
        ZoneInfo(tz_name)
        return True
    except:
        return False

async def build_personalized_weather_text(location: str, raw_weather: str, channel_id=None):
    """用目前 system_prompt 角色語氣包裝天氣提醒。"""
    if raw_weather.startswith("❌") or raw_weather.startswith("⚠️"):
        return raw_weather

    if not config.get("api_key"):
        return raw_weather

    endpoint = f"{config['api_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    system_content = build_system_prompt(channel_id=channel_id, author=None)
    system_content += (
        "\n\n【任務】"
        "\n你現在要發送『天氣提醒』。"
        "\n請使用目前角色個性與語氣，"
        "內容包含：1) 目前天氣重點 2) 一句貼心的生活建議。"
        "\n請僅依據提供的原始天氣資料，不可捏造數字。"
    )
    body = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"地點：{location}\n原始天氣資料：\n{raw_weather}"}
        ]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, json=body, timeout=20) as resp:
                if resp.status != 200:
                    return raw_weather
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except:
        return raw_weather

# ───────── 晚餐推薦工具 ─────────
async def generate_dinner_suggestion(location: str, channel_id=None):
    if not config.get("api_key"):
        return "⚠️ 請先設定 API Key。"

    location = location.strip()
    if not location:
        return "⚠️ 尚未設定所在地點，請先使用 /set_location 設定。"

    endpoint = f"{config['api_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }

    system_content = build_system_prompt(channel_id=channel_id, author=None)
    system_content += (
        "\n\n【任務】"
        "\n你現在要做『晚餐推薦』。"
        "\n請根據使用者所在地點推薦 1~2 種在當地常見、容易取得的料理或餐點。"
        "\n請以角色語氣回覆，簡短自然。"
    )

    body = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"使用者所在地點：{location}"}
        ]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, json=body, timeout=20) as resp:
                if resp.status != 200:
                    res_text = await resp.text()
                    return f"❌ API 錯誤 ({resp.status}): {res_text[:100]}"
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ 連線失敗: {str(e)}"

def _get_summary_file_path(date_str: str):
    github_cfg = config.get("github", {})
    base_path = str(github_cfg.get("path", "summaries/") or "summaries/")
    if not base_path.endswith("/"):
        base_path += "/"
    return f"{base_path}{date_str}.md"

async def _generate_daily_summary(date_str: str):
    log_path = os.path.join(CHAT_LOG_DIR, f"{date_str}.jsonl")
    if not os.path.exists(log_path):
        return ""

    lines = []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line.strip())
                    role = item.get("role")
                    content = item.get("content", "")
                    if role and content:
                        lines.append(f"{role}: {content}")
                except:
                    continue
    except:
        return ""

    if not lines:
        return ""

    if not config.get("api_key"):
        return ""

    endpoint = f"{config['api_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }

    system_content = build_system_prompt(channel_id=None, author=None)
    system_content += (
        "\n\n【任務】"
        "\n請將以下聊天室紀錄整理成每日總結。"
        "\n要求：1) 100~200 字 2) 重點條列 3) 不洩露敏感資訊 4) 不要逐字重複對話。"
    )

    body = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": "\n".join(lines[-300:])}
        ]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, json=body, timeout=30) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except:
        return ""

async def _push_summary_to_github(date_str: str, content: str):
    github_cfg = config.get("github", {})
    repo = str(github_cfg.get("repo", "")).strip()
    branch = str(github_cfg.get("branch", "main")).strip() or "main"
    token_env = str(github_cfg.get("token_env", "GITHUB_TOKEN")).strip() or "GITHUB_TOKEN"
    token = os.environ.get(token_env, "")

    if not repo or not token:
        return False, "⚠️ GitHub 未設定，已略過推送。"

    path = _get_summary_file_path(date_str)
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

    # 取得既有檔案的 sha（若存在）
    sha = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params={"ref": branch}, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sha = data.get("sha")
    except:
        sha = None

    payload = {
        "message": f"daily summary {date_str}",
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "branch": branch
    }
    if sha:
        payload["sha"] = sha

    try:
        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=headers, json=payload, timeout=20) as resp:
                if resp.status in (200, 201):
                    return True, "✅ 已推送每日總結到 GitHub。"
                error_text = await resp.text()
                return False, f"❌ GitHub 上傳失敗 ({resp.status}): {error_text[:120]}"
    except Exception as e:
        return False, f"❌ GitHub 連線失敗: {str(e)}"

async def daily_summary_checker():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(20)

        schedule = config.get("summary_schedule", {})
        if not schedule.get("enabled", False):
            continue

        remind_time = str(schedule.get("time", "")).strip()
        tz_name = str(schedule.get("timezone", "")).strip()

        if not remind_time or not is_valid_hhmm(remind_time) or not is_valid_timezone(tz_name):
            continue

        now_local = datetime.now(ZoneInfo(tz_name))
        if now_local.strftime("%H:%M") != remind_time:
            continue

        today = now_local.strftime("%Y-%m-%d")
        if schedule.get("last_sent_date") == today:
            continue

        summary = await _generate_daily_summary(today)
        if summary:
            ok, _ = await _push_summary_to_github(today, summary)
            if ok:
                config.setdefault("summary_schedule", {})["last_sent_date"] = today
                save_config(config)

async def weather_reminder_checker():
    """每天定時推送一次天氣提醒到指定頻道。"""
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(20)

        reminder = config.get("weather_reminder", {})
        if not reminder.get("enabled", False):
            continue

        location = str(reminder.get("location", "")).strip()
        remind_time = str(reminder.get("time", "")).strip()
        tz_name = str(reminder.get("timezone", "")).strip()
        channel_id = int(reminder.get("channel_id", 0) or 0)

        if not location or not remind_time or not tz_name or channel_id <= 0:
            continue
        if not is_valid_hhmm(remind_time) or not is_valid_timezone(tz_name):
            continue

        now_local = datetime.now(ZoneInfo(tz_name))
        if now_local.strftime("%H:%M") != remind_time:
            continue

        today = now_local.strftime("%Y-%m-%d")
        if reminder.get("last_sent_date") == today:
            continue

        channel = client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(channel_id)
            except:
                continue

        try:
            raw_weather = await fetch_weather_summary(location)
            final_text = await build_personalized_weather_text(location, raw_weather, channel_id=channel_id)
            await channel.send(final_text)
            config.setdefault("weather_reminder", {})["last_sent_date"] = today
            save_config(config)
        except:
            pass

# ───────── 背景任務：超時主動說話 ─────────
async def timeout_checker():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(60)
        now = time.time()
        timeout_sec = config["timeout_minutes"] * 60

        for channel_id, last_time in list(channel_last_time.items()):
            if not _is_chime_channel_allowed(channel_id):
                continue
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
    if config.get("auto_chime_in", True) and _is_chime_channel_allowed(message.channel.id):
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

# /api 指令用：只有 action=model 時才顯示模型清單
async def api_value_autocomplete(interaction: discord.Interaction, current: str):
    try:
        action = getattr(interaction.namespace, "action", "")
    except Exception:
        action = ""
    if action == "model":
        return await model_autocomplete(interaction, current)
    return []

@client.tree.command(name="config", description="查看機器人設定（可指定分類/項目）")
@app_commands.choices(
    category=[
        app_commands.Choice(name="basic", value="basic"),
        app_commands.Choice(name="prompt", value="prompt"),
        app_commands.Choice(name="owner", value="owner"),
        app_commands.Choice(name="dinner", value="dinner"),
        app_commands.Choice(name="chime", value="chime"),
        app_commands.Choice(name="weather", value="weather"),
        app_commands.Choice(name="forbidden", value="forbidden"),
        app_commands.Choice(name="github", value="github"),
        app_commands.Choice(name="summary", value="summary")
    ]
)
async def slash_config(
    interaction: discord.Interaction,
    category: Optional[app_commands.Choice[str]] = None,
    item: Optional[str] = None
):
    if not is_owner(interaction): return

    forbidden_words = config.get("forbidden_words", []) or []
    forbidden_foods = config.get("forbidden_foods", []) or []
    hated_foods = config.get("hated_foods", []) or []
    forbidden_actions = config.get("forbidden_actions", []) or []
    forbidden_words_str = ", ".join(forbidden_words) if forbidden_words else "無"
    forbidden_foods_str = ", ".join(forbidden_foods) if forbidden_foods else "無"
    hated_foods_str = ", ".join(hated_foods) if hated_foods else "無"
    forbidden_actions_str = ", ".join(forbidden_actions) if forbidden_actions else "無"

    profile = config.get("user_profile", {})
    reminder = config.get("weather_reminder", {})
    appearance = profile.get("appearance", "") or "未設定"
    personality = profile.get("personality", "") or "未設定"
    occupation = profile.get("occupation", "") or "未設定"
    weather_enabled = "開啟" if reminder.get("enabled") else "關閉"
    weather_location = reminder.get("location", "") or "未設定"
    weather_time = reminder.get("time", "") or "未設定"
    weather_channel = reminder.get("channel_id", 0) or "未設定"
    weather_tz = reminder.get("timezone", "") or "未設定"

    dinner_location = config.get("dinner_location", "") or "未設定"
    chime_channels = config.get("chime_in_channels", [])
    if isinstance(chime_channels, list) and chime_channels:
        chime_channels_str = ", ".join([str(c) for c in chime_channels])
    else:
        chime_channels_str = "未設定(不限)"

    roleplay_prompt = config.get("roleplay_prompt", "") or "未設定"
    character_prompt = config.get("character_prompt", "") or "未設定"
    response_style = config.get("response_style", "") or "未設定"

    owner_profile = config.get("owner_profile", {})
    owner_name = owner_profile.get("name", "") or "未設定"
    owner_id_text = owner_profile.get("id", "") or "未設定"
    owner_title = owner_profile.get("title", "") or "未設定"
    owner_pronoun = owner_profile.get("pronoun", "") or "未設定"

    github_cfg = config.get("github", {})
    github_repo = github_cfg.get("repo", "") or "未設定"
    github_branch = github_cfg.get("branch", "main") or "main"
    github_path = github_cfg.get("path", "summaries/") or "summaries/"
    github_token_env = github_cfg.get("token_env", "GITHUB_TOKEN") or "GITHUB_TOKEN"

    summary_cfg = config.get("summary_schedule", {})
    summary_enabled = "開啟" if summary_cfg.get("enabled") else "關閉"
    summary_time = summary_cfg.get("time", "") or "未設定"
    summary_tz = summary_cfg.get("timezone", "") or "未設定"

    sections = {
        "basic": {
            "title": "🔧 基本設定",
            "fields": {
                "api_url": ("API URL", config.get("api_url", "")),
                "model": ("模型", config.get("model", "")),
                "system_prompt": ("個性", config.get("system_prompt", "")),
                "response_style": ("回應文風", response_style)
            }
        },
        "prompt": {
            "title": "🧩 Prompt 設定",
            "fields": {
                "roleplay_prompt": ("Roleplay 守則", roleplay_prompt),
                "character_prompt": ("角色設定", character_prompt)
            }
        },
        "owner": {
            "title": "🧑‍🤝‍🧑 Owner 設定",
            "fields": {
                "owner_name": ("Owner 名字", owner_name),
                "owner_id": ("Owner ID", owner_id_text),
                "owner_title": ("Owner 稱呼", owner_title),
                "owner_pronoun": ("Owner 代詞", owner_pronoun)
            }
        },
        "dinner": {
            "title": "🍽️ 晚餐推薦",
            "fields": {
                "dinner_location": ("晚餐推薦地點", dinner_location)
            }
        },
        "chime": {
            "title": "💬 插嘴/破冰",
            "fields": {
                "chime_channels": ("可插嘴/破冰頻道", chime_channels_str)
            }
        },
        "weather": {
            "title": "🌦️ 天氣提醒",
            "fields": {
                "weather_enabled": ("天氣提醒", weather_enabled),
                "weather_location": ("提醒地點", weather_location),
                "weather_time": ("提醒時間", weather_time),
                "weather_channel": ("提醒頻道ID", weather_channel),
                "weather_tz": ("提醒時區", weather_tz)
            }
        },
        "forbidden": {
            "title": "🚫 禁止清單",
            "fields": {
                "forbidden_words": ("禁止詞彙", forbidden_words_str),
                "forbidden_foods": ("禁止出現的食物", forbidden_foods_str),
                "hated_foods": ("OWNER 討厭的食物", hated_foods_str),
                "forbidden_actions": ("禁止行為", forbidden_actions_str)
            }
        },
        "github": {
            "title": "🗂️ GitHub",
            "fields": {
                "github_repo": ("GitHub Repo", github_repo),
                "github_branch": ("GitHub Branch", github_branch),
                "github_path": ("Summary 路徑", github_path),
                "github_token_env": ("Token Env", github_token_env)
            }
        },
        "summary": {
            "title": "📝 每日總結",
            "fields": {
                "summary_enabled": ("每日總結", summary_enabled),
                "summary_time": ("總結時間", summary_time),
                "summary_tz": ("總結時區", summary_tz)
            }
        }
    }

    if category is None:
        categories = ", ".join([f"`{k}`" for k in sections.keys()])
        guide = (
            "**📌 /config 使用方式**\n"
            f"可用分類：{categories}\n"
            "範例：/config category:forbidden\n"
            "或 /config category:prompt item:roleplay_prompt"
        )
        await interaction.response.send_message(guide, ephemeral=True)
        return

    key = category.value
    section = sections.get(key)
    if not section:
        await interaction.response.send_message("⚠️ 找不到該分類。", ephemeral=True)
        return

    if item:
        search = item.strip().lower()
        for field_key, (label, value) in section["fields"].items():
            if search == field_key.lower() or search == label.lower():
                await interaction.response.send_message(
                    f"**{section['title']}**\n- {label}: `{value or '未設定'}`",
                    ephemeral=True
                )
                return
        await interaction.response.send_message("⚠️ 找不到該項目，請確認 item 名稱。", ephemeral=True)
        return

    lines = [f"**{section['title']}**"]
    for _, (label, value) in section["fields"].items():
        display_value = value if str(value).strip() else "未設定"
        lines.append(f"- {label}: `{display_value}`")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

@client.tree.command(name="api", description="設定 API URL / Key / 模型")
@app_commands.choices(
    action=[
        app_commands.Choice(name="url", value="url"),
        app_commands.Choice(name="key", value="key"),
        app_commands.Choice(name="model", value="model")
    ]
)
@app_commands.autocomplete(value=api_value_autocomplete)
async def api(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    value: str
):
    if not is_owner(interaction): return

    if action.value == "url":
        config["api_url"] = value
        save_config(config)
        await interaction.response.send_message(f"✅ API URL 已更新：`{value}`", ephemeral=True)
        return

    if action.value == "key":
        config["api_key"] = value
        save_config(config)
        await interaction.response.send_message("✅ API Key 已更新。", ephemeral=True)
        return

    if action.value == "model":
        config["model"] = value
        save_config(config)
        await interaction.response.send_message(f"✅ 模型已切換為：`{value}`", ephemeral=True)
        return

@client.tree.command(name="set_prompt", description="設定 Roleplay 守則 / 角色設定 / Owner 身分")
async def set_prompt(
    interaction: discord.Interaction,
    rule: Optional[str] = None,
    char: Optional[str] = None,
    owner_name: Optional[str] = None,
    owner_id: Optional[str] = None,
    owner_title: Optional[str] = None,
    owner_pronoun: Optional[str] = None
):
    if not is_owner(interaction): return

    updated = False
    if rule is not None:
        config["roleplay_prompt"] = rule
        updated = True
    if char is not None:
        config["character_prompt"] = char
        updated = True

    owner_profile = config.get("owner_profile", {})
    if owner_name is not None:
        owner_profile["name"] = owner_name
        updated = True
    if owner_id is not None:
        owner_profile["id"] = owner_id
        updated = True
    if owner_title is not None:
        owner_profile["title"] = owner_title
        updated = True
    if owner_pronoun is not None:
        owner_profile["pronoun"] = owner_pronoun
        updated = True
    config["owner_profile"] = owner_profile

    if not updated:
        await interaction.response.send_message("⚠️ 請至少提供任一欄位（rule/char/owner_*）。", ephemeral=True)
        return

    save_config(config)
    await interaction.response.send_message("✅ Prompt 設定已更新！", ephemeral=True)

@client.tree.command(name="set_style", description="設定回應文風（斷句/語氣/動作格式）")
async def set_style(interaction: discord.Interaction, style: str):
    if not is_owner(interaction): return
    config["response_style"] = style
    save_config(config)
    await interaction.response.send_message("✅ 回應文風已更新！", ephemeral=True)

@client.tree.command(name="set_location", description="設定晚餐推薦預設所在地點")
async def set_location(interaction: discord.Interaction, location: str):
    if not is_owner(interaction): return
    config["dinner_location"] = location.strip()
    save_config(config)
    await interaction.response.send_message(f"✅ 已設定晚餐推薦地點：`{config['dinner_location']}`", ephemeral=True)

@client.tree.command(name="add_chime_channel", description="新增可插嘴/破冰的頻道")
async def add_chime_channel(interaction: discord.Interaction, channel_id: str):
    if not is_owner(interaction): return
    parsed_channel_id = _parse_channel_id(channel_id)
    if parsed_channel_id is None:
        await interaction.response.send_message("⚠️ 頻道 ID 格式錯誤，請輸入數字或 #頻道。", ephemeral=True)
        return

    channel = client.get_channel(parsed_channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(parsed_channel_id)
        except:
            await interaction.response.send_message("⚠️ 找不到該頻道 ID，或 Bot 沒有權限存取該頻道。", ephemeral=True)
            return

    chime_channels = config.get("chime_in_channels", [])
    if not isinstance(chime_channels, list):
        chime_channels = []
    if int(channel.id) not in [int(c) for c in chime_channels]:
        chime_channels.append(int(channel.id))
        config["chime_in_channels"] = chime_channels
        save_config(config)
    await interaction.response.send_message(f"✅ 已加入可插嘴/破冰頻道：`{channel.id}`", ephemeral=True)

@client.tree.command(name="remove_chime_channel", description="移除可插嘴/破冰的頻道")
async def remove_chime_channel(interaction: discord.Interaction, channel_id: str):
    if not is_owner(interaction): return
    parsed_channel_id = _parse_channel_id(channel_id)
    if parsed_channel_id is None:
        await interaction.response.send_message("⚠️ 頻道 ID 格式錯誤，請輸入數字或 #頻道。", ephemeral=True)
        return
    chime_channels = config.get("chime_in_channels", [])
    if not isinstance(chime_channels, list):
        chime_channels = []
    filtered = [int(c) for c in chime_channels if int(c) != int(parsed_channel_id)]
    config["chime_in_channels"] = filtered
    save_config(config)
    await interaction.response.send_message(f"✅ 已移除可插嘴/破冰頻道：`{parsed_channel_id}`", ephemeral=True)

@client.tree.command(name="clear_chime_channels", description="清空可插嘴/破冰頻道清單（不限）")
async def clear_chime_channels(interaction: discord.Interaction):
    if not is_owner(interaction): return
    config["chime_in_channels"] = []
    save_config(config)
    await interaction.response.send_message("✅ 已清空可插嘴/破冰頻道清單（不限）。", ephemeral=True)

@client.tree.command(name="dinner", description="根據所在地點推薦晚餐")
async def dinner(interaction: discord.Interaction):
    await interaction.response.defer()
    location = str(config.get("dinner_location", "")).strip()
    suggestion = await generate_dinner_suggestion(location, channel_id=interaction.channel_id)
    await interaction.followup.send(f"🍽️ {suggestion}")

@client.tree.command(name="weather", description="根據地點提醒天氣")
async def weather(interaction: discord.Interaction, location: str):
    await interaction.response.defer(ephemeral=True)
    raw_weather = await fetch_weather_summary(location)
    final_text = await build_personalized_weather_text(location, raw_weather, channel_id=interaction.channel_id)
    await interaction.followup.send(final_text, ephemeral=True)

@client.tree.command(name="set_weather_reminder", description="設定每日定時天氣提醒（地點/時間/頻道ID/時區）")
async def set_weather_reminder(
    interaction: discord.Interaction,
    location: str,
    remind_time: str,
    channel_id: str,
    tz_name: str
):
    if not is_owner(interaction): return

    if not is_valid_hhmm(remind_time):
        await interaction.response.send_message("⚠️ 時間格式錯誤，請使用 HH:MM（24 小時制），例如 19:30。", ephemeral=True)
        return

    if not is_valid_timezone(tz_name):
        await interaction.response.send_message("⚠️ 時區格式錯誤，請使用 IANA 時區名稱，例如 Asia/Taipei。", ephemeral=True)
        return

    parsed_channel_id = _parse_channel_id(channel_id)
    if parsed_channel_id is None:
        await interaction.response.send_message("⚠️ 頻道 ID 格式錯誤，請輸入數字或 #頻道。", ephemeral=True)
        return

    channel = client.get_channel(parsed_channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(parsed_channel_id)
        except:
            await interaction.response.send_message("⚠️ 找不到該頻道 ID，或 Bot 沒有權限存取該頻道。", ephemeral=True)
            return

    config["weather_reminder"] = {
        "enabled": True,
        "location": location.strip(),
        "time": remind_time,
        "channel_id": int(channel.id),
        "timezone": tz_name.strip(),
        "last_sent_date": ""
    }
    save_config(config)
    await interaction.response.send_message(
        f"✅ 已設定天氣提醒：每天 `{remind_time}`（`{tz_name}`）推送到頻道 `{channel.id}`，地點 `{location}`。",
        ephemeral=True
    )

@client.tree.command(name="clear_weather_reminder", description="關閉每日定時天氣提醒")
async def clear_weather_reminder(interaction: discord.Interaction):
    if not is_owner(interaction): return
    config["weather_reminder"] = {
        "enabled": False,
        "location": "",
        "time": "",
        "channel_id": 0,
        "timezone": "Asia/Taipei",
        "last_sent_date": ""
    }
    save_config(config)
    await interaction.response.send_message("✅ 已關閉每日定時天氣提醒。", ephemeral=True)

@client.tree.command(name="set_profile", description="設定主要使用者外觀/個性/職業")
async def set_profile(
    interaction: discord.Interaction,
    appearance: str,
    personality: str,
    occupation: str
):
    if not is_owner(interaction): return
    config["user_profile"] = {
        "appearance": appearance,
        "personality": personality,
        "occupation": occupation
    }
    save_config(config)
    await interaction.response.send_message("✅ 主要使用者設定已更新！", ephemeral=True)

@client.tree.command(name="set_github", description="設定每日總結的 GitHub 目標")
async def set_github(
    interaction: discord.Interaction,
    repo: str,
    branch: str = "main",
    path: str = "summaries/",
    token_env: str = "GITHUB_TOKEN"
):
    if not is_owner(interaction): return
    config["github"] = {
        "repo": repo.strip(),
        "branch": branch.strip() or "main",
        "path": path.strip() or "summaries/",
        "token_env": token_env.strip() or "GITHUB_TOKEN"
    }
    save_config(config)
    await interaction.response.send_message("✅ GitHub 設定已更新。", ephemeral=True)

@client.tree.command(name="set_summary_time", description="設定每日總結時間與時區")
async def set_summary_time(
    interaction: discord.Interaction,
    time_str: str,
    tz_name: str
):
    if not is_owner(interaction): return

    if not is_valid_hhmm(time_str):
        await interaction.response.send_message("⚠️ 時間格式錯誤，請使用 HH:MM（24 小時制），例如 23:30。", ephemeral=True)
        return

    if not is_valid_timezone(tz_name):
        await interaction.response.send_message("⚠️ 時區格式錯誤，請使用 IANA 時區名稱，例如 Asia/Taipei。", ephemeral=True)
        return

    config["summary_schedule"] = {
        "enabled": True,
        "time": time_str,
        "timezone": tz_name.strip(),
        "last_sent_date": ""
    }
    save_config(config)
    await interaction.response.send_message(
        f"✅ 已設定每日總結時間：每天 `{time_str}`（`{tz_name}`）。",
        ephemeral=True
    )

@client.tree.command(name="set_summary_enabled", description="開啟或關閉每日總結")
async def set_summary_enabled(interaction: discord.Interaction, enabled: bool):
    if not is_owner(interaction): return
    config.setdefault("summary_schedule", {})["enabled"] = bool(enabled)
    save_config(config)
    if enabled:
        await interaction.response.send_message("✅ 已開啟每日總結。", ephemeral=True)
    else:
        await interaction.response.send_message(
            "⚠️ 已關閉每日總結。若未連接 GitHub，聊天記憶可能會隨重啟或資料清理而流失。",
            ephemeral=True
        )

@client.tree.command(name="run_summary", description="立即產出並推送當日總結")
async def run_summary(interaction: discord.Interaction):
    if not is_owner(interaction): return
    await interaction.response.defer(ephemeral=True)
    now_local = datetime.now(_get_summary_timezone())
    today = now_local.strftime("%Y-%m-%d")
    summary = await _generate_daily_summary(today)
    if not summary:
        await interaction.followup.send("⚠️ 找不到可用聊天紀錄或摘要生成失敗。", ephemeral=True)
        return
    ok, msg = await _push_summary_to_github(today, summary)
    await interaction.followup.send(msg, ephemeral=True)

@client.tree.command(name="reroll", description="重新生成上一則回應")
async def reroll(interaction: discord.Interaction):
    if not is_owner(interaction): return
    await interaction.response.defer(ephemeral=True)

    last_user = _get_last_user_message(interaction.channel_id)
    if not last_user:
        await interaction.followup.send("⚠️ 找不到上一則使用者訊息，無法 reroll。", ephemeral=True)
        return

    removed = _remove_last_assistant_message(interaction.channel_id)
    if not removed:
        await interaction.followup.send("⚠️ 找不到上一則回應，無法 reroll。", ephemeral=True)
        return

    async with interaction.channel.typing():
        reply = await call_api(
            interaction.channel_id,
            user_text=last_user,
            special_instruction="使用者要求重新生成回應，請避免與上一版本重複。",
            author=interaction.user
        )
        await interaction.followup.send(reply, ephemeral=True)
        add_to_history(interaction.channel_id, "assistant", reply)

@client.tree.command(name="clear_summary_time", description="關閉每日總結排程")
async def clear_summary_time(interaction: discord.Interaction):
    if not is_owner(interaction): return
    config["summary_schedule"] = {
        "enabled": False,
        "time": "",
        "timezone": "Asia/Taipei",
        "last_sent_date": ""
    }
    save_config(config)
    await interaction.response.send_message(
        "⚠️ 已關閉每日總結排程。若未連接 GitHub，聊天記憶可能會隨重啟或資料清理而流失。",
        ephemeral=True
    )

@client.tree.command(name="add_forbidden", description="新增禁止項目（詞彙/食物/行為）")
@app_commands.choices(
    category=[
        app_commands.Choice(name="禁止詞彙", value="forbidden_words"),
        app_commands.Choice(name="禁止出現的食物", value="forbidden_foods"),
        app_commands.Choice(name="OWNER 討厭的食物", value="hated_foods"),
        app_commands.Choice(name="禁止行為", value="forbidden_actions")
    ]
)
async def add_forbidden(
    interaction: discord.Interaction,
    category: app_commands.Choice[str],
    item: str
):
    if not is_owner(interaction): return
    key = category.value
    items = config.get(key, [])
    if not isinstance(items, list):
        items = []
    if item not in items:
        items.append(item)
        config[key] = items
        save_config(config)
    await interaction.response.send_message(f"✅ 已將 `{item}` 加入 `{category.name}` 清單。", ephemeral=True)

@client.tree.command(name="clear_forbidden", description="清空禁止清單（可指定分類）")
@app_commands.choices(
    category=[
        app_commands.Choice(name="禁止詞彙", value="forbidden_words"),
        app_commands.Choice(name="禁止出現的食物", value="forbidden_foods"),
        app_commands.Choice(name="OWNER 討厭的食物", value="hated_foods"),
        app_commands.Choice(name="禁止行為", value="forbidden_actions")
    ]
)
async def clear_forbidden(
    interaction: discord.Interaction,
    category: Optional[app_commands.Choice[str]] = None
):
    if not is_owner(interaction): return

    if category is None:
        config["forbidden_words"] = []
        config["forbidden_foods"] = []
        config["hated_foods"] = []
        config["forbidden_actions"] = []
        save_config(config)
        await interaction.response.send_message("✅ 所有禁止清單已清空。", ephemeral=True)
        return

    key = category.value
    config[key] = []
    save_config(config)
    await interaction.response.send_message(f"✅ `{category.name}` 清單已清空。", ephemeral=True)

@client.tree.command(name="set_timeout", description="設定沉默多久(分)後機器人主動開話題")
async def set_timeout(interaction: discord.Interaction, minutes: int):
    if not is_owner(interaction): return
    config["timeout_minutes"] = minutes
    save_config(config)
    await interaction.response.send_message(f"✅ 超時設定為 `{minutes}` 分鐘。", ephemeral=True)

@client.tree.command(name="sync", description="強制同步指令選單")
async def sync(interaction: discord.Interaction):
    if not is_owner(interaction): return
    await interaction.response.defer(ephemeral=True)
    await client.tree.sync()
    await interaction.followup.send("🔄 指令已同步，請重啟 Discord 查看。", ephemeral=True)

# ───────── 啟動 ─────────
if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if TOKEN:
        client.run(TOKEN)
    else:
        print("❌ 錯誤：找不到 DISCORD_TOKEN 環境變數")
