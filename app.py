# ============================================
# 📘 安安專案主程式 app.py v4.4
# 功能：三層教學回饋 + Gemini主模型 + GPT備援 + Vision OCR
# ============================================

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import requests, os, io, base64, json, logging
from PIL import Image
from google.cloud import vision
from datetime import datetime

# -------------------------------
# 初始化 Flask App
# -------------------------------
app = Flask(__name__)
app.secret_key = "anan-secret-key"

# -------------------------------
# 環境變數檢查
# -------------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_APPLICATION_CREDENTIALS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

print("🔍 環境變數檢查：")
if DEEPSEEK_API_KEY: print("✅ 成功讀到 DEEPSEEK_API_KEY")
else: print("⚠️ 未讀到 DEEPSEEK_API_KEY")
if GEMINI_API_KEY: print("✅ 成功讀到 GEMINI_API_KEY")
else: print("⚠️ 未讀到 GEMINI_API_KEY")
if GOOGLE_APPLICATION_CREDENTIALS_JSON: print("✅ 成功讀到 GOOGLE_APPLICATION_CREDENTIALS_JSON")
else: print("⚠️ 未讀到 Vision JSON 金鑰")

# -------------------------------
# Vision OCR 初始化
# -------------------------------
vision_client = None
if GOOGLE_APPLICATION_CREDENTIALS_JSON:
    try:
        creds_dict = json.loads(GOOGLE_APPLICATION_CREDENTIALS_JSON)
        with open("vision_key.json", "w", encoding="utf-8") as f:
            json.dump(creds_dict, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "vision_key.json"
        vision_client = vision.ImageAnnotatorClient()
        print("✅ Vision API 初始化成功")
    except Exception as e:
        print(f"❌ Vision 初始化失敗：{e}")

# -------------------------------
# 全域對話狀態儲存
# -------------------------------
conversation_history = []
confused_count = 0  # 計算「不懂」次數


# ============================================================
# 🧠 AI 模型調用邏輯
# ============================================================
def ask_gemini(prompt):
    """呼叫 Gemini API"""
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
        headers = {"Content-Type": "application/json"}
        data = {"contents": [{"parts": [{"text": prompt}]}]}
        params = {"key": GEMINI_API_KEY}
        r = requests.post(url, headers=headers, json=data, params=params, timeout=25)
        res = r.json()
        return res["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"⚠️ Gemini 回答失敗：{e}")
        return None


def ask_gpt_backup(prompt):
    """呼叫 GPT-5 備援"""
    try:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
        payload = {
            "model": "gpt-5",
            "messages": [{"role": "system", "content": "你是台灣數學小老師，用繁體中文一步步講解。"},
                         {"role": "user", "content": prompt}],
            "max_tokens": 800,
            "temperature": 0.6
        }
        r = requests.post(url, headers=headers, json=payload, timeout=25)
        res = r.json()
        return res["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"❌ GPT 備援失敗：{e}")
        return "⚠️ 系統忙碌中，請稍後再試～"


def get_ai_response(prompt):
    """Plan C: 先用 Gemini，失敗再用 GPT 備援"""
    res = ask_gemini(prompt)
    if not res or "error" in str(res).lower():
        print("⚠️ Gemini 失敗，改用 GPT 備援。")
        res = ask_gpt_backup(prompt)
    return res or "⚠️ 系統暫時無法回答，請稍後重試。"


# ============================================================
# 🧮 文字問題處理主路由
# ============================================================
@app.route("/", methods=["GET", "POST"])
def index():
    global conversation_history, confused_count

    if request.method == "POST":
        user_msg = request.form["message"].strip()
        if not user_msg:
            return redirect(url_for("index"))

        # 檢查是否為重複題目（避免亂跳舊題）
        if conversation_history and user_msg == conversation_history[-1]["content"]:
            reply = "這題我們剛剛討論過囉～要不要試試下一題呢？"
        else:
            prompt = f"請以台灣國中數學老師的口吻，用繁體中文、逐步引導學生思考並講解這題：\n{user_msg}"
            reply = get_ai_response(prompt)

        conversation_history.append({"role": "user", "content": user_msg})
        conversation_history.append({"role": "assistant", "content": reply})

    return render_template("index.html", conversation=conversation_history)


# ============================================================
# 📷 圖片上傳與 OCR
# ============================================================
@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    global conversation_history
    if not vision_client:
        return jsonify({"success": False, "result": "⚠️ 無法使用 Vision OCR 功能。"}), 400

    file = request.files.get("image")
    if not file:
        return jsonify({"success": False, "result": "⚠️ 沒有收到圖片。"}), 400

    try:
        content = file.read()
        image = vision.Image(content=content)
        response = vision_client.text_detection(image=image)
        text = response.text_annotations[0].description if response.text_annotations else ""

        if not text.strip():
            return jsonify({"success": False, "result": "⚠️ 沒辨識到文字，請重新拍照試試～"}), 200

        # 取得AI解答
        prompt = f"題目內容如下：{text}\n請以繁體中文、逐步講解解題過程，適合國中生理解。"
        answer = get_ai_response(prompt)

        conversation_history.append({"role": "user", "content": f"[圖片題目]\n{text}"})
        conversation_history.append({"role": "assistant", "content": answer})

        return jsonify({"success": True, "result": answer})
    except Exception as e:
        print(f"❌ 圖片分析錯誤：{e}")
        return jsonify({"success": False, "result": "⚠️ 圖片辨識失敗，請重試！"})


# ============================================================
# 🧩 三層回饋機制
# ============================================================
@app.route("/feedback", methods=["POST"])
def feedback():
    global confused_count, conversation_history
    data = request.get_json()
    understood = data.get("understood")

    if understood:
        confused_count = 0
        reply = "太棒了～安安替你開心 💪 這樣就能更有自信地面對數學題囉！"
    else:
        confused_count += 1
        if confused_count == 1:
            reply = "沒關係，我給你一個提示：想想題目裡的條件有沒有關聯？💭"
        elif confused_count == 2:
            reply = "還是不太懂嗎？我幫你回顧關鍵概念，再舉一個相似例子試試 🔄"
        else:
            reply = "看來我們需要一起算一遍！\n以下是詳細的逐步講解👇\n"
            if conversation_history:
                last_q = next((m["content"] for m in reversed(conversation_history) if m["role"] == "user"), "")
                full_prompt = f"請直接完整講解這題：{last_q}"
                reply += get_ai_response(full_prompt)
            confused_count = 0  # 重置次數

    conversation_history.append({"role": "assistant", "content": reply})
    return jsonify({"status": "ok", "reply": reply})


# ============================================================
# 🧹 清除對話
# ============================================================
@app.route("/clear")
def clear_chat():
    global conversation_history, confused_count
    conversation_history = []
    confused_count = 0
    return redirect(url_for("index"))


# ============================================================
# 🚀 啟動伺服器
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 安安伺服器啟動中... Port={port}")
    app.run(host="0.0.0.0", port=port)
