# app.py
# -*- coding: utf-8 -*-

import os
import json
import logging
from datetime import timedelta

from flask import (
    Flask, request, render_template, session, redirect, url_for, jsonify
)
from werkzeug.middleware.proxy_fix import ProxyFix

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ====== 版本號 ======
APP_VERSION = "安安 v1.3D"

# ====== 基本設定 ======
def str2bool(v: str) -> bool:
    return str(v).lower() in {"1", "true", "yes", "y", "on"}

DEBUG = str2bool(os.getenv("DEBUG", "0"))

app = Flask(__name__, template_folder="templates", static_folder="static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# 重要：Production 請設定固定的 SECRET_KEY，避免多進程/多機 session 失效
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))
app.permanent_session_lifetime = timedelta(hours=2)
app.config["JSON_AS_ASCII"] = False

# ====== Logging ======
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)
logger.info("啟動版本：%s，DEBUG=%s", APP_VERSION, DEBUG)

# ====== API 設定 ======
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

if DEEPSEEK_API_KEY:
    logger.info("✅ 成功讀到 DEEPSEEK_API_KEY | %s", APP_VERSION)
else:
    # 不要在程式裡硬寫金鑰（安全風險），請在 Railway 變數設定 DEEPSEEK_API_KEY
    logger.warning("⚠️ 沒有讀到 DEEPSEEK_API_KEY，請在環境變數中設定。")

# ====== requests session + retry 機制 ======
session_req = requests.Session()
retries = Retry(
    total=3,
    connect=3,
    read=3,
    backoff_factor=1.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["GET", "POST"]),
)
adapter = HTTPAdapter(max_retries=retries)
session_req.mount("https://", adapter)
session_req.mount("http://", adapter)
DEFAULT_TIMEOUT = 30  # 秒

# ====== before_request：讓 session 採用「滑動式」過期 ======
@app.before_request
def make_session_permanent():
    session.permanent = True

# ====== 健康檢查（Railway 用） ======
@app.route("/health")
def health_check():
    return jsonify({"status": "healthy", "version": APP_VERSION})

@app.route("/favicon.ico")
def favicon():
    # 避免 404 汙染 log
    return ("", 204)

# ====== DeepSeek 問答函數 ======
def ask_deepseek(user_message: str, conversation_history: list) -> str:
    if not DEEPSEEK_API_KEY:
        return "系統尚未設定 DEEPSEEK_API_KEY，請在 Railway 變數中加入後再試一次。"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }

    system_prompt = (
        "你是數學老師安安，請用蘇格拉底式的引導教學方式協助學生。\n"
        "規則如下：\n"
        "1. 使用繁體中文回答。\n"
        "2. 不直接給完整解答，要先引導學生思考下一步，並提出提示或問題。\n"
        "3. 逐步拆解題目，讓學生一步一步回答。\n"
        "4. 使用台灣常用的數學術語。\n"
        "5. 語氣要親切、鼓勵，像一位耐心的小老師。\n"
        "6. 如果需要舉例說明，請使用台灣常見的食物或生活物品（例如：珍珠奶茶、蔥油餅、滷肉飯、刈包、雞排）。\n"
        "7. 如果學生多次回答不出來，再給更多提示，最後才提供完整解答。\n"
        "8. 在完整解答結束後，請再出一題同樣概念的練習題，鼓勵學生自己嘗試。\n"
        "9. 如果學生的問題與數學學習無關（閒聊、歌曲、娛樂等），請用簡短幽默可愛的方式回答，並引導學生回到數學學習主題。"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1500,
    }

    try:
        resp = session_req.post(
            DEEPSEEK_API_URL,
            headers=headers,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json()

        if "choices" in result and result["choices"]:
            raw = result["choices"][0]["message"]["content"]

            # 後處理：清理常見 LaTeX 符號
            latex_map = {
                "\\times": "×",
                "\\cdot": "×",
                "\\div": "÷",
                "\\(": "",
                "\\)": "",
                "$": "",
            }
            formatted = raw
            for k, v in latex_map.items():
                formatted = formatted.replace(k, v)
            formatted = formatted.replace("• ", "")

            return formatted.strip() or "（空回應）"
        else:
            logger.warning("DeepSeek 回傳內容無 choices：%s", result)
            return "安安好像沒聽懂，可以換個方式問嗎？"

    except requests.exceptions.RequestException as e:
        logger.exception("❌ 與 DeepSeek 通訊發生錯誤：%s", e)
        return "安安連線出了一點小狀況，稍後再試或換個題目吧！"
    except Exception as e:
        logger.exception("❌ 未預期錯誤：%s", e)
        return "安安暫時肚子餓了（系統小故障），等一下再來問我～"

# ====== 首頁 ======
@app.route("/", methods=["GET", "POST"])
def home():
    if "conversation" not in session or not isinstance(session["conversation"], list):
        session["conversation"] = [
            {"role": "assistant", "content": "我是安安，你的數學小老師"}
        ]

    if request.method == "POST":
        user_message = (request.form.get("message") or "").strip()
        if user_message:
            session["conversation"].append({"role": "user", "content": user_message})
            ai_reply = ask_deepseek(user_message, session["conversation"])
            session["conversation"].append({"role": "assistant", "content": ai_reply})
            session.modified = True

    return render_template(
        "index.html",
        conversation=session["conversation"],
        app_version=APP_VERSION,
    )

# ====== 清除對話 ======
@app.route("/clear")
def clear_conversation():
    session["conversation"] = [
        {"role": "assistant", "content": "對話已清除，從頭開始吧！"}
    ]
    session.modified = True
    return redirect(url_for("home"))

# ====== 本地啟動（Railway 由 gunicorn 啟動，不會走到這裡） ======
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    logger.info("🚀 %s 本地模式啟動，http://0.0.0.0:%d", APP_VERSION, port)
    app.run(host="0.0.0.0", port=port, debug=DEBUG)
