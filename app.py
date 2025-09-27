import os
import logging
from datetime import timedelta
from typing import List, Dict

import requests
from flask import Flask, request, render_template, session, redirect, url_for, make_response

# ---------- 基本設定 ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

DEBUG = os.getenv("DEBUG", "false").lower() == "true"

app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY") or os.urandom(24)
app.permanent_session_lifetime = timedelta(hours=2)

# Railway 環境設定
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

# ---------- DeepSeek API 設定 ----------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
TIMEOUT = 30

if DEEPSEEK_API_KEY:
    logger.info("✅ 成功讀到 DEEPSEEK_API_KEY | 安安 v1.3D，DEBUG=%s", DEBUG)
else:
    logger.warning("⚠️ 沒有讀到 DEEPSEEK_API_KEY，請在本地/部署平台設定環境變數。")

# ---------- 共同常數 ----------
SYSTEM_PROMPT = """你是數學老師安安，請遵守以下要求：
1. 使用繁體中文回答
2. 不要使用 - 符號，改用 • 符號或數字編號
3. 用台灣常用的數學術語
4. 回答要清晰易懂"""

# ---------- DeepSeek 呼叫函式 ----------
def ask_deepseek(user_message: str, conversation_history: List[Dict]) -> str:
    if not DEEPSEEK_API_KEY:
        return "系統尚未設定 DEEPSEEK_API_KEY，請先於環境變數加入後再試一次。"

    # 組訊息：system +（截斷）歷史 + 當前 user
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    # 避免對話過長，取最後 12 則歷史
    for msg in conversation_history[-12:]:
        role = "assistant" if msg.get("role") == "assistant" else "user"
        content = str(msg.get("content", ""))
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2000,
    }

    try:
        if DEBUG:
            logger.info("🔎 DEBUG 請求 payload=%s", payload)

        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=TIMEOUT)

        if DEBUG:
            logger.info("🔎 DEBUG status=%s, body=%s", resp.status_code, resp.text)

        resp.raise_for_status()
        data = resp.json()

        if "choices" in data and data["choices"]:
            content = data["choices"][0]["message"]["content"]
            return content.replace("- ", "• ")
        else:
            return "安安好像沒聽懂，可以換個方式問嗎？"

    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", None)
        if code in (401, 403):
            return "安安無法連線：API 金鑰無效或沒有權限（401/403）。請更新 DEEPSEEK_API_KEY 後再試。"
        elif code == 429:
            return "安安目前太忙（429）。請稍後再試或降低頻率。"
        else:
            logger.error("❌ DeepSeek HTTP 錯誤：%s | body=%s", e, getattr(e.response, "text", ""))
            return f"安安出現錯誤：HTTP {code}，請稍後再試。"
    except requests.RequestException as e:
        logger.error("❌ DeepSeek 連線例外：%s", e)
        return "安安連線出了一點小狀況，請檢查網路或稍後再試。"
    except Exception as e:
        logger.exception("❌ 非預期錯誤")
        return f"安安出現錯誤：{e}"

# ---------- 路由 ----------
@app.route("/", methods=["GET", "POST"])
def home():
    session.permanent = True
    if "conversation" not in session:
        session["conversation"] = [{"role": "assistant", "content": "我是安安，你的數學小老師"}]

    if request.method == "POST":
        user_message = (request.form.get("message") or "").strip()
        if user_message:
            session["conversation"].append({"role": "user", "content": user_message})
            ai_response = ask_deepseek(user_message, session["conversation"])
            session["conversation"].append({"role": "assistant", "content": ai_response})
            session.modified = True

    return render_template("index.html", conversation=session["conversation"])

@app.route("/clear")
def clear_conversation():
    session["conversation"] = [{"role": "assistant", "content": "對話已清除，從頭開始吧！"}]
    return redirect(url_for("home"))

@app.route("/healthz")
def healthz():
    return "ok", 200

@app.route("/favicon.ico")
def favicon():
    return make_response("", 204)

# ---------- 啟動設定 ----------
if __name__ == "__main__":
    if os.getenv("RAILWAY_ENVIRONMENT") is None and os.getenv("RAILWAY_RUN") is None:
        port = int(os.environ.get("PORT", 5000))
        logger.info("🚀 安安 v1.3D 本地模式啟動，http://127.0.0.1:%s | DEBUG=%s", port, DEBUG)
        app.run(host="0.0.0.0", port=port, debug=DEBUG)
    else:
        logger.info("✅ 應用程式已載入，由 Gunicorn 負責服務")
