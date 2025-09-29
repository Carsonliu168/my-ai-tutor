import os
import logging
from datetime import timedelta
from typing import List, Dict
import re

import requests
from flask import Flask, request, render_template, session, redirect, url_for, make_response

# ---------- Log settings ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

DEBUG = os.getenv("DEBUG", "false").lower() == "true"

app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY") or os.urandom(24)
app.permanent_session_lifetime = timedelta(hours=2)

# Railway config
app.config.update(
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

# ---------- DeepSeek API settings ----------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
TIMEOUT = 30

PORT = os.environ.get("PORT")
logger.info("PORT check: %s", PORT)

if DEEPSEEK_API_KEY:
    logger.info("AnAn v1.6 ready, DEBUG=%s", DEBUG)
else:
    logger.warning("No DEEPSEEK_API_KEY found")

# ---------- System Prompt ----------
SYSTEM_PROMPT = """You are AnAn, a math teacher. Follow these rules:

1. Use Traditional Chinese
2. Math symbols: use +, -, x or *, divide or /
3. Never change minus sign - to other symbols
4. Use Taiwan math terms
5. Use Socratic method with step-by-step interaction

Chat rules:
- If student greets or chats (weather, hello), reply friendly but guide back to math within 30 characters
- Example: "Hello! Nice to meet you! Want to learn math today?"
- Example: "I can't see weather! What's it like there? Want to practice math?"
- When student asks math questions, use Socratic method

Teaching rules (for math questions):
- Ask ONE question at a time, wait for student response
- Never self-answer or assume student's answer
- Never say multiple steps or "if you don't know" in same response
- Only when student actually says "don't know", then give answer in next response
- Max 3-4 rounds of guidance

Wrong example:
Student: "How to calculate rectangle area?"
AnAn: "Rectangle area formula is length x width, right? So we multiply 12 and 8. Can you calculate 12x8? If you don't know, answer is 96."
(Wrong - said everything at once!)

Correct example:
Student: "How to calculate rectangle area?"
AnAn: "What is the rectangle area formula?"
(Only ask one question, wait)

Student: "length x width"
AnAn: "Great! Length is 12cm, width is 8cm. Can you calculate 12x8?"
(Continue next step)

Student: "don't know"
AnAn: "No problem! Answer is 96 square cm. Because 12x8 = 96, think of it as: 10x8=80, 2x8=16, then 80+16=96."
(Now give answer and explanation)

Remember: For chat, reply friendly and guide to math within 30 chars. For math, ask one question at a time."""

# ---------- Request logging ----------
@app.before_request
def _log_request():
    logger.info("Request: %s %s", request.method, request.path)

@app.after_request
def _log_response(resp):
    logger.info("Response: %s %s -> %s", request.method, request.path, resp.status)
    return resp

# ---------- DeepSeek function ----------
def ask_deepseek(user_message: str, conversation_history: List[Dict]) -> str:
    if not DEEPSEEK_API_KEY:
        return "System not configured with DEEPSEEK_API_KEY"

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
            logger.info("DEBUG payload=%s", payload)

        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=TIMEOUT)

        if DEBUG:
            logger.info("DEBUG status=%s, body=%s", resp.status_code, resp.text)

        resp.raise_for_status()
        data = resp.json()

        if "choices" in data and data["choices"]:
            content = data["choices"][0]["message"]["content"]
            
            # Filter specific problem
            if "人數除以6等於24餘2" in content and "146" in content:
                return "我是安安老師！我們來看看這道數學題目，你覺得應該從哪裡開始思考呢？"
            
            # Force fix all symbol issues
            content = content.replace("•", "-")
            content = content.replace("• ", "- ")
            content = content.replace(" • ", " - ")
            content = content.replace("·", "-")
            content = content.replace(" · ", " - ")
            
            # Fix specific patterns like N•2, N.2, N·2
            content = re.sub(r'([A-Z])•(\d)', r'\1-\2', content)
            content = re.sub(r'([A-Z])\.(\d)', r'\1-\2', content)
            content = re.sub(r'([A-Z])·(\d)', r'\1-\2', content)
            content = re.sub(r'([A-Z])\s•\s(\d)', r'\1-\2', content)
            content = re.sub(r'([A-Z])\s·\s(\d)', r'\1-\2', content)
            
            return content
        else:
            return "安安好像沒聽懂，可以換個方式問嗎？"

    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", None)
        if code in (401, 403):
            return "安安無法連線：API 金鑰無效或沒有權限。"
        elif code == 429:
            return "安安目前太忙。請稍後再試。"
        else:
            logger.error("DeepSeek HTTP error: %s | body=%s", e, getattr(e.response, "text", ""))
            return f"安安出現錯誤：HTTP {code}，請稍後再試。"
    except requests.RequestException as e:
        logger.error("DeepSeek connection error: %s", e)
        return "安安連線出了一點小狀況，請檢查網路或稍後再試。"
    except Exception as e:
        logger.exception("Unexpected error")
        return f"安安出現錯誤：{e}"

# ---------- Routes ----------
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
        logger.exception("home() exception")
        html = f"""
        <html><body style="font-family:Arial;max-width:720px;margin:40px auto">
        <h2>AnAn started but template has issue</h2>
        <p>Exception: <code>{e.__class__.__name__}: {e}</code></p>
        <p>Check if templates/index.html exists</p>
        <a href="/healthz">Health check</a>
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

# ---------- Startup ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("AnAn starting... port: %s", port)
    app.run(host="0.0.0.0", port=port, debug=DEBUG)# force redeploy 
# force redeploy 
