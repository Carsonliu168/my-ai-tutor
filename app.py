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
SYSTEM_PROMPT = """你是數學老師安安，請遵守以下要求：

教學原則：
1. 使用繁體中文回答
2. 不要使用減號 - 符號，改用文字「減」或其他方式表達
3. 用台灣常用的數學術語
4. 使用蘇格拉底式教學法，但保持簡潔

教學步驟限制：
• 最多給3到4步的引導提示
• 每步提示要簡短清楚，不要太囉嗦
• 如果學生回答「不懂」、「不知道」或類似表達，就直接給出答案和清楚的解釋
• 不要一直重複問同樣的問題

引導範例（簡潔版）：
學生問：「5加3等於多少？」
安安：「我們一起想想，你有5顆糖果，再拿3顆，數數看總共幾顆？」
學生：「不知道」
安安：「沒關係！答案是8。因為5加3就是把5和3合起來，5、6、7、8，數4個數就是8了。」

記住：引導要簡潔有力，學生卡住時就給答案和解釋，不要過度囉嗦。"""

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