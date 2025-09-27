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
    SESSION_COOKIE_SECURE=False,
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
logger.info("PORT environment variable: %s", PORT)

if DEEPSEEK_API_KEY:
    logger.info("Successfully loaded DEEPSEEK_API_KEY | DEBUG=%s", DEBUG)
else:
    logger.warning("DEEPSEEK_API_KEY not found, please set environment variable")

# ---------- 共同常數 ----------
SYSTEM_PROMPT = """你是數學老師安安，請遵守以下要求：
1. 使用繁體中文回答
2. 數學公式用易讀的文字表示，例如：
   - 用 "N = 72k + 2" 而不是複雜符號
   - 用 "N ÷ 6 餘 2" 而不是特殊符號
   - 用 "根號x" 表示 sqrt(x)，"x的平方" 表示 x²
   - 用 "分數 a/b" 而不是特殊格式
3. 使用清晰的分步驟格式
4. 用 ● 或數字編號來列點
5. 使用蘇格拉底式教學法：多問引導性問題，讓學生思考
6. 回答要清晰易懂，避免任何可能顯示錯誤的特殊符號
7. 重要答案用【答案：xxx】格式標示
8. 每個步驟都要解釋為什麼這樣做"""

# ---------- 全域請求日誌 ----------
@app.before_request
def _log_request():
    logger.info("Request: %s %s", request.method, request.path)

@app.after_request
def _log_response(resp):
    logger.info("Response: %s %s -> %s", request.method, request.path, resp.status)
    return resp

# ---------- DeepSeek 呼叫函式 ----------
def ask_deepseek(user_message: str, conversation_history: List[Dict]) -> str:
    if not DEEPSEEK_API_KEY:
        return "系統尚未設定 DEEPSEEK_API_KEY，請先於環境變數加入後再試一次。"

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
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
            logger.info("DEBUG request payload=%s", payload)

        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=TIMEOUT)

        if DEBUG:
            logger.info("DEBUG response status=%s, body=%s", resp.status_code, resp.text)

        resp.raise_for_status()
        data = resp.json()

        if "choices" in data and data["choices"]:
            content = data["choices"][0]["message"]["content"]
            # 清理可能有問題的符號
            content = content.replace("\\", "")
            content = content.replace("$", "")
            return content
        else:
            return "安安好像沒聽懂，可以換個方式問嗎？"

    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", None)
        if code in (401, 403):
            return "安安無法連線：API 金鑰無效或沒有權限（401/403）。請更新 DEEPSEEK_API_KEY 後再試。"
        elif code == 429:
            return "安安目前太忙（429）。請稍後再試或降低頻率。"
        else:
            logger.error("DeepSeek HTTP error: %s | body=%s", e, getattr(e.response, "text", ""))
            return f"安安出現錯誤：HTTP {code}，請稍後再試。"
    except requests.RequestException as e:
        logger.error("DeepSeek connection error: %s", e)
        return "安安連線出了一點小狀況，請檢查網路或稍後再試。"
    except Exception as e:
        logger.exception("Unexpected error")
        return f"安安出現錯誤：{e}"

# ---------- 路由 ----------
@app.route("/", methods=["GET", "POST"])
def home():
    session.permanent = True
    try:
        if "conversation" not in session:
            session["conversation"] = [{"role": "assistant", "content": "我是安安，你的數學小老師！我會用簡單易懂的方式教你數學，並且引導你自己思考找到答案。有什麼數學問題想問我嗎？"}]

        if request.method == "POST":
            user_message = (request.form.get("message") or "").strip()
            if user_message:
                session["conversation"].append({"role": "user", "content": user_message})
                ai_response = ask_deepseek(user_message, session["conversation"])
                session["conversation"].append({"role": "assistant", "content": ai_response})
                session.modified = True

        return render_template("index.html", conversation=session["conversation"])
    except Exception as e:
        logger.exception("Error in home() function")
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
    session["conversation"] = [{"role": "assistant", "content": "對話已清除！我是安安，你的數學小老師，讓我們重新開始學習數學吧！"}]
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
    port = int(os.environ.get("PORT", 5000))
    logger.info("Starting app on port: %s", port)
    app.run(host="0.0.0.0", port=port, debug=DEBUG)