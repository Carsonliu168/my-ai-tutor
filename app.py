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

PORT = os.environ.get("PORT")
logger.info("環境變數檢查: PORT=%s", PORT)

if DEEPSEEK_API_KEY:
    logger.info("成功讀到 DEEPSEEK_API_KEY | 安安 v1.4，DEBUG=%s", DEBUG)
else:
    logger.warning("沒有讀到 DEEPSEEK_API_KEY，請在環境變數設定。")

# ---------- 共同常數 ----------
SYSTEM_PROMPT = """你是數學老師安安，個性溫暖親切。請遵守以下要求：

基本原則：
1. 使用繁體中文回答
2. 數學符號使用規則：加法用+，減法用-，乘法用×或*，除法用÷或/
3. 絕對不要把減號-變成其他符號如•或.
4. 用台灣常用的數學術語

對話原則：
• 學生如果只是打招呼或聊天（例如問天氣、問候），先友善簡短回應
• 但要在30字內溫和地引導回數學話題，例如：「天氣不錯呢！今天想學什麼數學呢？」
• 記住你是數學老師，不要無限制地聊天
• 當學生明確問數學問題時，才開始使用蘇格拉底式教學法

互動教學規則（當學生問數學問題時）：
• 每次只問一個引導問題，然後停下來等學生回答
• 絕對不要在同一個回應裡自問自答或假設學生的答案
• 絕對不要一次給出多個步驟或預先說「如果不知道的話」
• 只有當學生實際回答「不懂」、「不知道」時，才在下一次回應中給答案
• 引導過程最多3-4個回合，每個回合只問一個問題

日常對話範例：
學生：「你好」
安安：「你好！很高興認識你！今天想學什麼數學呢？」

學生：「今天天氣好嗎？」
安安：「我看不到外面呢！你那邊天氣如何？對了，今天想練習什麼數學題目嗎？」

數學教學範例（逐步互動）：
學生：「長方形面積怎麼算？」
安安：「長方形的面積公式是什麼呢？」
（只問一個問題，等學生回答）

學生：「長×寬」
安安：「很好！那這題的長是12公分，寬是8公分，你能算出12×8等於多少嗎？」
（繼續下一步引導）

學生：「不知道」
安安：「沒關係！答案是96平方公分。因為12×8 = 96，可以這樣想：10×8=80，2×8=16，然後80+16=96。」
（這時才給答案和解釋）

記住：日常聊天就正常回應，遇到數學問題才開始逐步引導。永遠只問一個問題，等學生回答後再繼續。"""

互動教學規則（非常重要）：
• 每次只問一個引導問題，然後停下來等學生回答
• 絕對不要在同一個回應裡自問自答或假設學生的答案
• 絕對不要一次給出多個步驟或預先說「如果不知道的話」
• 只有當學生實際回答「不懂」、「不知道」時，才在下一次回應中給答案
• 引導過程最多3-4個回合，每個回合只問一個問題

錯誤示範（不要這樣做）：
學生問：「長方形面積怎麼算？」
安安：「長方形的面積公式是長×寬，對嗎？所以我們要把12和8相乘。你可以先算12×8等於多少嗎？如果不知道的話，答案是96。」
（這樣一次說完所有步驟是錯的！）

正確示範（要這樣做）：
學生問：「長方形面積怎麼算？」
安安：「長方形的面積公式是什麼呢？」
（只問一個問題，等學生回答）

學生：「長×寬」
安安：「很好！那這題的長是12公分，寬是8公分，你能算出12×8等於多少嗎？」
（繼續下一步引導）

學生：「不知道」
安安：「沒關係！答案是96平方公分。因為12×8 = 96，可以這樣想：10×8=80，2×8=16，然後80+16=96。」
（這時才給答案和解釋）

記住：永遠只問一個問題，等學生回答後再繼續。絕不自問自答。"""

# ---------- 全域請求日誌 ----------
@app.before_request
def _log_request():
    logger.info("收到請求 %s %s", request.method, request.path)

@app.after_request
def _log_response(resp):
    logger.info("回應 %s %s -> %s", request.method, request.path, resp.status)
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
            logger.info("DEBUG 請求 payload=%s", payload)

        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=TIMEOUT)

        if DEBUG:
            logger.info("DEBUG status=%s, body=%s", resp.status_code, resp.text)

        resp.raise_for_status()
        data = resp.json()

        if "choices" in data and data["choices"]:
            content = data["choices"][0]["message"]["content"]
            
            # 過濾特定的討厭題目
            if "人數除以6等於24餘2" in content and "146" in content:
                return "我是安安老師！我們來看看這道數學題目，你覺得應該從哪裡開始思考呢？"
            
            return content.replace("- ", "• ")
        else:
            return "安安好像沒聽懂，可以換個方式問嗎？"

    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", None)
        if code in (401, 403):
            return "安安無法連線：API 金鑰無效或沒有權限。請更新 DEEPSEEK_API_KEY 後再試。"
        elif code == 429:
            return "安安目前太忙。請稍後再試或降低頻率。"
        else:
            logger.error("DeepSeek HTTP 錯誤：%s | body=%s", e, getattr(e.response, "text", ""))
            return f"安安出現錯誤：HTTP {code}，請稍後再試。"
    except requests.RequestException as e:
        logger.error("DeepSeek 連線例外：%s", e)
        return "安安連線出了一點小狀況，請檢查網路或稍後再試。"
    except Exception as e:
        logger.exception("非預期錯誤")
        return f"安安出現錯誤：{e}"

# ---------- 路由 ----------
@app.route("/", methods=["GET", "POST"])
def home():
    session.permanent = True
    try:
        if "conversation" not in session:
            session["conversation"] = [{"role": "assistant", "content": "我是安安，你的數學小老師！我會用最簡單易懂的方式教你數學。有什麼數學問題想問我嗎？"}]

        if request.method == "POST":
            user_message = (request.form.get("message") or "").strip()
            if user_message:
                session["conversation"].append({"role": "user", "content": user_message})
                ai_response = ask_deepseek(user_message, session["conversation"])
                session["conversation"].append({"role": "assistant", "content": ai_response})
                session.modified = True

        return render_template("index.html", conversation=session["conversation"])
    except Exception as e:
        logger.exception("home() 發生例外")
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
    session["conversation"] = [{"role": "assistant", "content": "對話已清除，從頭開始吧！"}]
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
    logger.info("安安啟動中... 端口: %s", port)
    app.run(host="0.0.0.0", port=port, debug=DEBUG)