# =====================================================
# 📘 安安專案主程式 app.py — Plan C 最終穩定版
# =====================================================
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os, base64, requests, sqlite3, google.generativeai as genai
from datetime import datetime

app = Flask(__name__)
app.secret_key = "anan-secret-key"

# ---------- 資料庫 ----------
def get_conn():
    conn = sqlite3.connect("data/anan.db")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            question TEXT,
            topic TEXT,
            is_correct INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    return conn

# ---------- API 金鑰 ----------
genai.configure(api_key=os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("GEMINI_API_KEY"))
openai_api_key = os.environ.get("OPENAI_API_KEY")

# ---------- 首頁 ----------
@app.route("/")
def index():
    session.setdefault("conversation", [])
    return render_template("index.html", conversation=session["conversation"])

# ---------- 清除對話 ----------
@app.route("/clear")
def clear():
    session.pop("conversation", None)
    return redirect(url_for("index"))

# ---------- 學生輸入文字 ----------
@app.route("/", methods=["POST"])
def chat():
    msg = request.form["message"].strip()
    if not msg:
        return redirect(url_for("index"))

    # 學生訊息
    session["conversation"].append({"role": "user", "content": msg})

    # 🔹 依內容決定回覆邏輯
    try:
        model = genai.GenerativeModel("gemini-1.5-flash-latest")
        response = model.generate_content([
            f"你是數學老師安安。請用繁體中文一步步講解這道題：{msg}\n"
            "若學生多次說不懂，請換不同方式講解，例如舉例或畫線思考。"
        ])
        reply = (response.text or "⚠️ 安安暫時想不到，請再試一次。").strip()
    except Exception as e:
        reply = f"⚠️ 解題時出現問題：{e}"

    session["conversation"].append({"role": "assistant", "content": reply})
    session.modified = True

    return redirect(url_for("index"))

# ---------- 回饋 ----------
@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json()
    understood = data.get("understood")
    reply = ""

    if understood:
        reply = "太棒了～安安替你開心 💪 你真的越來越厲害了！"
    else:
        # 第三次不懂 → 強制列算式講解
        confused_count = session.get("confused_count", 0) + 1
        session["confused_count"] = confused_count
        if confused_count >= 3:
            reply = "這題我們來一步步列算式看看：先寫出條件、代入公式、計算，再觀察答案。"
            session["confused_count"] = 0
        else:
            reply = "沒關係，我再用另一個方式說明一次 💭"

    session["conversation"].append({"role": "assistant", "content": reply})
    session.modified = True
    return jsonify({"status": "ok", "reply": reply})

# =====================================================
# 🧮 圖片題解（Plan C 雙 Gemini + GPT-4o 備援）
# =====================================================
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
def allowed_file(fn): return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"result": "⚠️ 沒有收到圖片"}), 400
    image = request.files["image"]
    if image.filename == '' or not allowed_file(image.filename):
        return jsonify({"result": "⚠️ 請選擇 PNG/JPG/JPEG 圖片"}), 400
    image_bytes = image.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        return jsonify({"result": "⚠️ 圖片太大，請使用小於 10 MB 的圖片"}), 400

    result = None
    model_names = ['gemini-1.5-flash-latest', 'gemini-pro-vision']

    # ---------- 雙 Gemini 重試 ----------
    for model_name in model_names:
        for attempt in range(2):
            try:
                print(f"🔵 使用 {model_name} 第 {attempt+1} 次嘗試")
                model = genai.GenerativeModel(model_name)
                res = model.generate_content([
                    "你是台灣數學老師安安，請完整解析圖片中的數學題：\n"
                    "1️⃣ 辨識題目與條件\n"
                    "2️⃣ 分析幾何或算式關係\n"
                    "3️⃣ 逐步計算並說明理由\n"
                    "4️⃣ 檢查答案合理性\n"
                    "5️⃣ 最後給一句鼓勵\n"
                    "請用繁體中文，條列清楚。",
                    {"mime_type": "image/jpeg", "data": image_bytes}
                ])
                text = (res.text or "").strip()
                if len(text) > 80:
                    result = text
                    print(f"✅ Gemini 成功 ({model_name} 第 {attempt+1} 次)")
                    break
            except Exception as e:
                print(f"⚠️ Gemini 失敗：{e}")
                continue
        if result:
            break

    # ---------- GPT-4o 備援 ----------
    if not result:
        try:
            print("🟢 啟用 GPT-4o 備援 中...")
            image_b64 = base64.b64encode(image_bytes).decode()
            headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-4o",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "你是數學老師安安，請用繁體中文詳細逐步解這道圖片題，列出算式與答案："},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                    ]
                }],
                "max_tokens": 1200
            }
            r = requests.post("https://api.openai.com/v1/chat/completions",
                               headers=headers, json=payload, timeout=80)
            result = r.json()["choices"][0]["message"]["content"]
            print("✅ GPT-4o 備援成功")
        except Exception as e:
            print(f"❌ GPT 備援失敗：{e}")
            return jsonify({"result": "⚠️ 圖片辨識失敗，請再試一次"}), 500

    # ---------- 儲存紀錄 ----------
    session.setdefault("conversation", [])
    session["conversation"] += [
        {"role": "user", "content": "📷 [上傳了數學題目圖片]"},
        {"role": "assistant", "content": result}
    ]
    session.modified = True
    conn = get_conn()
    conn.execute(
        "INSERT INTO records (user_id, question, topic, is_correct) VALUES (?,?,?,?)",
        (session.get("user_id", "guest"), "[圖片題目]", "圖片辨識", None)
    )
    conn.commit()
    conn.close()
    return jsonify({"result": result, "success": True}), 200

# ---------- 啟動 ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("✅ 安安 伺服器 啟動中... PORT=", port)
    app.run(host="0.0.0.0", port=port)
