import os
import logging
from datetime import timedelta
from typing import List, Dict

import requests
from flask import Flask, request, render_template, session, redirect, url_for, make_response

# ---------- 日誌設定 ----------
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
    SESSION_COOKIE_SECURE=False,  # 本地測試設為 False
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

# ---------- DeepSeek API 設定 ----------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
TIMEOUT = 30

# 顯示端口資訊
PORT = os.environ.get("PORT")
logger.info("🔍 環境變數檢查: PORT=%s", PORT)

if DEEPSEEK_API_KEY:
    logger.info("✅ 成功讀到 DEEPSEEK_API_KEY | 安安 v2.0，DEBUG=%s", DEBUG)
else:
    logger.warning("⚠️ 沒有讀到 DEEPSEEK_API_KEY，請在本地/部署平台設定環境變數。")

# ---------- 共同常數 ----------
# 🔥 超強力個性設定 - 完全重新定義安安
SYSTEM_PROMPT = """你是安安老師，一個溫暖親切的小學數學老師。

🚫 重要禁令：
• 絕對不要提到任何關於「人數除以6等於24餘2」的題目
• 絕對不要主動出數學題給學生
• 忘記所有之前的對話內容

✅ 正確行為：
• 學生打招呼時，就正常聊天
• 學生問天氣，就聊天氣
• 學生問日常問題，就正常回答
• 只有學生明確問數學問題時，才開始教數學
• 教數學時用引導方式，不直接給答案

對話範例：
學生：「你好」
安安：「你好！很高興見到你！今天過得怎麼樣？」

學生：「今天天氣好嗎」
安安：「我看不到外面的天氣呢！你那邊天氣如何？是晴天還是下雨？」

學生：「5+3等於多少」
安安：「這是加法題目呢！你覺得可以怎麼算？比如用手指頭或者想像5顆糖果再加3顆？」

記住：你是一個正常的老師，會聊天、會關心學生，不是只會出題的機器人！"""

# ---------- 全域請求日誌 ----------
@app.before_request
def _log_request():
    logger.info("➡️ %s %s", request.method, request.path)

@app.after_request
def _log_response(resp):
    logger.info("⬅️ %s %s -> %s", request.method, request.path, resp.status)
    return resp

# ---------- DeepSeek 呼叫函式 ----------
def ask_deepseek(user_message: str, conversation_history: List[Dict]) -> str:
    if not DEEPSEEK_API_KEY:
        return "系統尚未設定 DEEPSEEK_API_KEY，請先於環境變數加入後再試一次。"

    # 🔥 記憶清除：只保留最近3次對話，避免舊記憶干擾
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # 只取最近的3次對話（6條訊息）
    recent_history = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
    
    for msg in recent_history:
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
        "temperature": 0.8,  # 提高一點創造性，避免重複回答
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
            
            # 🔥 後處理：如果回答中出現禁止內容，強制替換
            forbidden_keywords = ["人數除以6", "24餘2", "146", "144"]
            for keyword in forbidden_keywords:
                if keyword in content:
                    return "我是安安老師！今天想聊什麼呢？有什麼我可以幫你的嗎？😊"
            
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
    try:
        if "conversation" not in session:
            # 🔥 全新開場白
            session["conversation"] = [{"role": "assistant", "content": "哈囉！我是安安老師！😊 今天想聊什麼呢？不一定要聊數學，什麼都可以聊喔！"}]

        if request.method == "POST":
            user_message = (request.form.get("message") or "").strip()
            if user_message:
                session["conversation"].append({"role": "user", "content": user_message})
                ai_response = ask_deepseek(user_message, session["conversation"])
                session["conversation"].append({"role": "assistant", "content": ai_response})
                session.modified = True

        return render_template("index.html", conversation=session["conversation"])
    except Exception as e:
        logger.exception("❌ home() 發生例外")
        html = f"""
        <html><body style="font-family:Arial;max-width:720px;margin:40px auto">
        <h2>安安已啟動，但首頁模板有點狀況</h2>
        <p>例外：<code>{e.__class__.__name__}: {e}</code></p>
        <p>請確認 templates/index.html 是否存在</p>
        <a href="/healthz">健康檢查</a>
        </body></html>
        """
        return html, 500

@app.route("/clear")
def clear_conversation():
    # 🔥 強力清除，完全重新開始
    session.clear()  # 清除所有session資料
    session["conversation"] = [{"role": "assistant", "content": "Hi！我是安安老師！😊 很開心重新認識你！今天想聊什麼呢？"}]
    session.modified = True
    return redirect(url_for("home"))

@app.route("/reset")  # 🔥 新增：緊急重置路由
def emergency_reset():
    session.clear()
    session["conversation"] = [{"role": "assistant", "content": "我是全新的安安老師！之前的記憶都清除了！😊 我們重新開始吧！"}]
    session.modified = True
    return redirect(url_for("home"))

@app.route("/healthz")
def healthz():
    return "ok", 200

@app.route("/live")
def live():
    return "live", 200

@app.route("/favicon.ico")
def favicon():
    return make_response("", 204)

# ---------- 啟動設定 ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("🚀 安安啟動中... 端口: %s", port)
    app.run(host="0.0.0.0", port=port, debug=DEBUG)
    
# 版本更新 v2.0 - 記憶清除版# �j���s 
 
