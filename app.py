# ================================
# 📘 安安專案主程式 app.py
# v4.3.2 No-Extra-Deps：移除 PIL/Vision，相容現有 requirements
# - Plan C：雙 Gemini（免費）→ 失敗才 GPT-4o
# - DeepSeek 文字教學（主答）+ GPT 備援
# - /feedback 回傳 reply、三層「不懂」策略
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, base64, requests, sqlite3, uuid, re
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制 16MB

# -------------------------------
# ✅ 環境變數
# -------------------------------
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
openai_api_key  = os.getenv("OPENAI_API_KEY")
google_api_key  = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")  # 兼容兩種命名

# 初始化 Gemini SDK
genai = None
try:
    import google.generativeai as genai_mod
    if google_api_key:
        genai_mod.configure(api_key=google_api_key)
        genai = genai_mod
        print("✅ Gemini API 已就緒")
    else:
        print("⚠️ 未設定 GOOGLE_API_KEY（或 GEMINI_API_KEY）")
except Exception as e:
    print(f"⚠️ Gemini 初始化失敗: {e}")

# -------------------------------
# 📊 SQLite 初始化
# -------------------------------
DB_PATH = "data/anan.db"
os.makedirs("data", exist_ok=True)

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        question TEXT,
        topic TEXT,
        is_correct INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()
    print("✅ [安安] 資料庫就緒 (v4.3.2)")
init_db()

# -------------------------------
# 🧠 DeepSeek / GPT 文字問答
# -------------------------------
def ask_anan(question: str, mode="socratic"):
    if mode == "socratic":
        style = "採用蘇格拉底式提問法，引導學生思考，不直接給答案。"
    else:
        style = "用正常教學方式清楚給出解題步驟與答案。"

    system_prompt = f"""
你是「數學小老師安安」，一位專業、親切、幽默的數學教學助理。
請使用繁體中文回答。
教學風格：{style}

解題要求：
1. 若是計算題，請務必逐步列出完整計算過程
2. 若是幾何題，請先分析圖形條件，再應用定理
3. 每個步驟都要說明理由
4. 最後要驗證答案的合理性
5. 用溫暖鼓勵的語氣引導學生思考
"""

    # DeepSeek 主答
    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
        }
        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=40)
        return r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        print("⚠️ DeepSeek 失敗，改用 GPT 備援：", e)

    # GPT 備援
    try:
        backup_headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
        }
        r2 = requests.post("https://api.openai.com/v1/chat/completions", headers=backup_headers, json=payload, timeout=40)
        return r2.json().get("choices", [{}])[0].get("message", {}).get("content", "（無回應）")
    except Exception as e:
        print("❌ GPT 備援也失敗：", e)
        return "（無回應）"

# -------------------------------
# 🎯 答題正確率（簡易）
# -------------------------------
def evaluate_answer(question, student_answer):
    try:
        if not re.search(r"[0-9=＋×÷\-*/]", question):
            return None
        headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "你是一位數學老師，請判斷學生答案是否正確，只回答「正確」或「錯誤」。"},
                {"role": "user", "content": f"題目：{question}\n學生回答：{student_answer}"}
            ]
        }
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=25)
        reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if "正確" in reply: return 1
        if "錯誤" in reply: return 0
        return None
    except Exception as e:
        print("⚠️ evaluate_answer 錯誤：", e)
        return None

# -------------------------------
# 💬 首頁與對話
# -------------------------------
@app.before_request
def ensure_user():
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())

@app.route("/", methods=["GET", "POST"])
def home():
    if "conversation" not in session:
        session["conversation"] = []
        session["confused_count"] = 0
        session["understand_level"] = 0

    conversation = session["conversation"]

    if request.method == "POST":
        user_msg = request.form.get("message", "").strip()
        if not user_msg:
            return render_template("index.html", conversation=conversation)

        # 打字輸入的「不懂」→ 不丟模型，走三層話術
        if any(kw in user_msg for kw in ["不懂", "不會", "看不懂", "再說一次"]):
            session["understand_level"] = session.get("understand_level", 0) + 1
            level = session["understand_level"]
            if level == 1:
                ai_reply = "沒關係～老師換個說法試試看 👇"
            elif level == 2:
                ai_reply = "我們用另一個角度再走一次解題步驟 💡"
            else:
                ai_reply = "別擔心，我直接一步步列出完整算式給你看 🧮（先整理條件，再代公式、計算與驗證）"
                session["understand_level"] = 0
            conversation.append({"role": "user", "content": user_msg})
            conversation.append({"role": "assistant", "content": ai_reply})
            session["conversation"] = conversation
            return render_template("index.html", conversation=conversation)

        # 一般問題：蘇格拉底/正常模式
        mode = "normal" if session.get("confused_count", 0) >= 2 else "socratic"
        ai_reply = ask_anan(user_msg, mode)

        conversation.append({"role": "user", "content": user_msg})
        conversation.append({"role": "assistant", "content": ai_reply})
        session["conversation"] = conversation

        # 紀錄
        correctness = evaluate_answer(user_msg, ai_reply)
        conn = get_conn()
        conn.execute(
            "INSERT INTO records (user_id, question, topic, is_correct) VALUES (?, ?, ?, ?)",
            (session["user_id"], user_msg, "一般", correctness)
        )
        conn.commit()
        conn.close()

    return render_template("index.html", conversation=conversation)

# -------------------------------
# 🧭 學生自評回饋
# -------------------------------
@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json()
    understood = data.get("understood")
    if understood is None:
        return jsonify({"status": "error"})

    if understood:
        session["confused_count"] = 0
        reply = "太棒了～安安替你開心 💪 你真的越來越厲害了！"
    else:
        session["confused_count"] = session.get("confused_count", 0) + 1
        count = session["confused_count"]
        if count >= 3:
            reply = "第三次了，老師直接一步步列出算式與理由，帶你完整走一次 🧮"
            session["confused_count"] = 0
        elif count == 2:
            reply = "好～我換個角度，再提供一個思考提示給你 💡"
        else:
            reply = "沒關係，我先用更簡單的方式說一次，跟著我一步步來 👇"

    session["conversation"].append({"role": "assistant", "content": reply})
    session.modified = True
    return jsonify({"status": "ok", "confused_count": session.get("confused_count", 0), "reply": reply})

# -------------------------------
# 🗑️ 清除對話
# -------------------------------
@app.route("/clear")
def clear():
    session.pop("conversation", None)
    session["confused_count"] = 0
    session["understand_level"] = 0
    return redirect("/")

# -------------------------------
# 🧮 圖片題解（Plan C：雙 Gemini + GPT-4o 備援）
# -------------------------------
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
def allowed_file(filename): return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"result": "⚠️ 沒有收到圖片"}), 400
    image_file = request.files["image"]
    if image_file.filename == '':
        return jsonify({"result": "⚠️ 沒有選擇檔案"}), 400
    if not allowed_file(image_file.filename):
        return jsonify({"result": "⚠️ 不支援的圖片格式，請使用 PNG、JPG 或 JPEG"}), 400

    try:
        image_bytes = image_file.read()
        if len(image_bytes) > 10 * 1024 * 1024:
            return jsonify({"result": "⚠️ 圖片太大，請使用小於 10MB 的圖片"}), 400
    except Exception as e:
        return jsonify({"result": f"⚠️ 讀取圖片失敗: {e}"}), 400

    result = None

    # 先用 Gemini（兩個模型 × 最多各兩次）
    if genai and google_api_key:
        model_names = ['gemini-1.5-flash-latest', 'gemini-pro-vision']
        for model_name in model_names:
            for attempt in range(2):
                try:
                    print(f"🔵 嘗試使用 {model_name}（第 {attempt+1} 次）進行辨識...")
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content([
                        "你是台灣數學老師「安安」，請完整解析圖片中的數學題：\n"
                        "1️⃣ 辨識題目與條件（看不清楚請說明）\n"
                        "2️⃣ 分析幾何/代數關係\n"
                        "3️⃣ 逐步計算並解釋每步理由\n"
                        "4️⃣ 驗證答案合理性\n"
                        "5️⃣ 給一句鼓勵\n"
                        "請用繁體中文，條列清楚。",
                        {"mime_type": "image/jpeg", "data": image_bytes}
                    ])
                    text = (response.text or "").strip()
                    if len(text) > 80:
                        result = text
                        print(f"✅ Gemini 成功（{model_name} 第 {attempt+1} 次）")
                        break
                    else:
                        print(f"⚠️ {model_name} 回覆過短（{len(text)} 字），重試中...")
                except Exception as e:
                    print(f"⚠️ {model_name} 第 {attempt+1} 次失敗：{e}")
                    continue
            if result:
                break
    else:
        print("⚠️ Gemini 未初始化或缺金鑰，略過")

    # 若 Gemini 無結果 → GPT-4o 備援
    if not result:
        try:
            print("🟢 使用 GPT-4o 備援中...")
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-4o",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "你是數學老師安安，請用繁體中文詳細逐步解這道圖片數學題，列出算式與答案："},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                    ]
                }],
                "max_tokens": 1200
            }
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=80)
            result = r.json()["choices"][0]["message"]["content"]
            print("✅ GPT-4o 備援成功")
        except Exception as e:
            print(f"❌ GPT 備援失敗：{e}")
            return jsonify({"result": "⚠️ 圖片辨識失敗，請再試一次！"}), 500

    # 儲存對話
    if "conversation" not in session:
        session["conversation"] = []
    conversation = session["conversation"]
    conversation.append({"role": "user", "content": "📷 [上傳了數學題目圖片]"})
    conversation.append({"role": "assistant", "content": result})
    session["conversation"] = conversation
    session.modified = True

    # 寫入 DB
    conn = get_conn()
    conn.execute(
        "INSERT INTO records (user_id, question, topic, is_correct) VALUES (?, ?, ?, ?)",
        (session["user_id"], "[圖片題目]", "圖片辨識", None)
    )
    conn.commit()
    conn.close()

    return jsonify({"result": result, "success": True}), 200

# -------------------------------
# 🩺 健康檢查
# -------------------------------
@app.route("/health")
def health():
    ok = {
        "deepseek_key": bool(deepseek_api_key),
        "openai_key": bool(openai_api_key),
        "google_key": bool(google_api_key)
    }
    return jsonify({"status": "ok", **ok}), 200

# -------------------------------
# 🚀 主程式入口
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"✅ 啟動 | DeepSeek={bool(deepseek_api_key)} | OpenAI={bool(openai_api_key)} | Gemini={bool(google_api_key)} | PORT={port}")
    app.run(host="0.0.0.0", port=port)
