import os
import logging
import base64
import json
from datetime import timedelta
from typing import List, Dict

import requests
from flask import Flask, request, render_template, session, redirect, url_for, make_response, jsonify

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

# ---------- API 金鑰設定 ----------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
TIMEOUT = 30

# 顯示環境變數資訊
PORT = os.environ.get("PORT")
logger.info("🔍 環境變數檢查: PORT=%s", PORT)

if DEEPSEEK_API_KEY:
    logger.info("✅ 成功讀到 DEEPSEEK_API_KEY")
else:
    logger.warning("⚠️ 沒有讀到 DEEPSEEK_API_KEY")

if GOOGLE_CREDENTIALS_JSON:
    logger.info("✅ 成功讀到 GOOGLE_APPLICATION_CREDENTIALS_JSON")
else:
    logger.warning("⚠️ 沒有讀到 GOOGLE_APPLICATION_CREDENTIALS_JSON")

# ---------- 共同常數 ----------
SYSTEM_PROMPT = """你是數學老師安安，請遵守以下要求：
1. 使用繁體中文回答
2. 不要使用 - 符號，改用 • 符號或數字編號
3. 用台灣常用的數學術語
4. 回答要清晰易懂
5. 使用蘇格拉底式教學法，透過提問引導學生思考
6. 遇到數學問題時，要一步步引導學生理解和解答
7. 用台灣小學生熟悉的例子來解釋數學概念
8. 如果學生只是打招呼，就正常回應問候，但可以友善地詢問是否需要數學協助"""

# ---------- 全域請求日誌 ----------
@app.before_request
def _log_request():
    logger.info("➡️ %s %s", request.method, request.path)

@app.after_request
def _log_response(resp):
    logger.info("⬅️ %s %s -> %s", request.method, request.path, resp.status)
    return resp

# ---------- Google Vision OCR 函式 ----------
def extract_text_from_image(image_data):
    """使用 Google Vision OCR 辨識圖片中的文字"""
    try:
        # 動態導入 Google Vision，避免在沒有金鑰時出錯
        from google.cloud import vision
        from google.oauth2 import service_account
        
        if not GOOGLE_CREDENTIALS_JSON:
            return None, "未設定 Google Vision API 金鑰"
        
        # 從環境變數解析 JSON 金鑰
        credentials_info = json.loads(GOOGLE_CREDENTIALS_JSON)
        credentials = service_account.Credentials.from_service_account_info(credentials_info)
        client = vision.ImageAnnotatorClient(credentials=credentials)
        
        # 處理圖片數據
        if hasattr(image_data, 'read'):
            # 如果是檔案物件
            image_content = image_data.read()
        else:
            # 如果是 base64 字串
            if 'base64,' in image_data:
                image_data = image_data.split('base64,')[1]
            image_content = base64.b64decode(image_data)
        
        image = vision.Image(content=image_content)
        response = client.text_detection(image=image)
        
        if response.text_annotations:
            detected_text = response.text_annotations[0].description
            logger.info(f"✅ OCR 辨識成功: {detected_text[:100]}...")
            return detected_text, None
        else:
            return None, "圖片中未偵測到文字"
            
    except Exception as e:
        logger.error(f"❌ OCR 辨識錯誤: {str(e)}")
        return None, f"OCR 辨識失敗: {str(e)}"

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
            logger.info("🔎 DEBUG 請求 payload=%s", payload)

        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=TIMEOUT)

        if DEBUG:
            logger.info("🔎 DEBUG status=%s, body=%s", resp.status_code, resp.text)

        resp.raise_for_status()
        data = resp.json()

        if "choices" in data and data["choices"]:
            content = data["choices"][0]["message"]["content"]
            
            # 只過濾特定的那道討厭題目，保留其他數學教學功能
            if "人數除以6等於24餘2" in content and "146" in content:
                return "我是安安老師！我們來看看這道數學題目，你覺得應該從哪裡開始思考呢？"
            
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
            session["conversation"] = [{"role": "assistant", "content": "我是安安，你的數學小老師！我會用最簡單易懂的方式教你數學。有什麼數學問題想問我嗎？"}]

        if request.method == "POST":
            # 檢查是否是圖片上傳
            if 'image' in request.files:
                image_file = request.files['image']
                if image_file and image_file.filename:
                    logger.info("📸 收到圖片上傳")
                    detected_text, error = extract_text_from_image(image_file)
                    
                    if detected_text:
                        # 將辨識結果加入對話
                        ocr_message = f"📷 我從圖片中辨識到：\n{detected_text}\n\n請幫我解答這個數學問題！"
                        session["conversation"].append({"role": "user", "content": ocr_message})
                        ai_response = ask_deepseek(ocr_message, session["conversation"])
                        session["conversation"].append({"role": "assistant", "content": ai_response})
                    else:
                        error_msg = f"❌ 圖片辨識失敗：{error}"
                        session["conversation"].append({"role": "assistant", "content": error_msg})
                    
                    session.modified = True
                    return redirect(url_for('home'))
            
            # 原有的文字訊息處理
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

@app.route("/api/ocr", methods=["POST"])
def ocr_api():
    """獨立的 OCR API 端點"""
    try:
        if 'image' not in request.files:
            return jsonify({"success": False, "error": "沒有上傳圖片"})
        
        image_file = request.files['image']
        if not image_file or not image_file.filename:
            return jsonify({"success": False, "error": "圖片檔案無效"})
        
        detected_text, error = extract_text_from_image(image_file)
        
        if detected_text:
            return jsonify({
                "success": True, 
                "text": detected_text,
                "message": "辨識成功"
            })
        else:
            return jsonify({
                "success": False,
                "error": error
            })
            
    except Exception as e:
        logger.error(f"❌ OCR API 錯誤: {str(e)}")
        return jsonify({"success": False, "error": f"伺服器錯誤: {str(e)}"})

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
    logger.info("🚀 安安啟動中... 端口: %s", port)
    app.run(host="0.0.0.0", port=port, debug=DEBUG)