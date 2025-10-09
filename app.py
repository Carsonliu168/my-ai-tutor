# ================================
# 📘 安安專案主程式 app.py
# v4.3a：Railway 相容修正版（使用 gemini-pro-vision 模型）
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session
import os, json, base64, requests, sqlite3, uuid, re
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制 16MB

# -------------------------------
# ✅ 環境變數與 API 初始化
# -------------------------------
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")
google_api_key = os.getenv("GOOGLE_API_KEY")

# 初始化 Gemini（使用舊版 SDK 相容）
try:
    import google.generativeai as genai
    if google_api_key:
        genai.configure(api_key=google_api_key)
        print("✅ Gemini API 已就緒 (相容版)")
    else:
        print("⚠️ 未設定 GOOGLE_API_KEY")
except Exception as e:
    print(f"⚠️ Gemini 初始化失敗: {e}")


# -------------------------------
# 🧠 DeepSeek 主模型
# -------------------------------
def ask_anan(question: str, mode="socratic"):
    style = "採用蘇格拉底式提問法，引導學生思考，不直接給答案。" if mode == "socratic" else "用正常教學方式清楚給出解題步驟與答案。"
    system_prompt = f"""
你是「數學小老師安安」，一位親切、幽默、溫柔的教學助理。
請使用繁體中文回答。
教學風格：{style}
若題目中有算式，請條列步驟並清楚說明。
"""

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
    except:
        # 備援 GPT
        try:
            backup_headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            payload["model"] = "gpt-4o-mini"
            r2 = requests.post("https://api.openai.com/v1/chat/completions", headers=backup_headers, json=payload, timeout=40)
            return r2.json().get("choices", [{}])[0].get("message", {}).get("content", "（無回應）")
        except:
            return "（無回應）"


# -------------------------------
# 📊 SQLite 資料庫初始化
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
    print("✅ [安安] 資料庫就緒 (v4.3a)")
init_db()


# -------------------------------
# 🎯 自動判斷答題正確率
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
# 💬 首頁與對話保存
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
    conversation = session["conversation"]

    if request.method == "POST":
        user_msg = request.form.get("message", "")
        if user_msg:
            mode = "normal" if session.get("confused_count", 0) >= 2 else "socratic"
            ai_reply = ask_anan(user_msg, mode)

            conversation.append({"role": "user", "content": user_msg})
            conversation.append({"role": "assistant", "content": ai_reply})
            session["conversation"] = conversation

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
    else:
        session["confused_count"] = session.get("confused_count", 0) + 1
    return jsonify({"status": "ok", "confused_count": session["confused_count"]})


# -------------------------------
# 🗑️ 清除對話
# -------------------------------
@app.route("/clear")
def clear():
    session.pop("conversation", None)
    session["confused_count"] = 0
    return redirect("/")


# -------------------------------
# 🧮 圖片解題（Gemini 相容版 + GPT 備援）
# -------------------------------
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"result": "⚠️ 沒有收到圖片"}), 400

    image_file = request.files["image"]
    if image_file.filename == '':
        return jsonify({"result": "⚠️ 沒有選擇檔案"}), 400
    if not allowed_file(image_file.filename):
        return jsonify({"result": "⚠️ 不支援的圖片格式"}), 400

    try:
        image_bytes = image_file.read()
        if len(image_bytes) > 10 * 1024 * 1024:
            return jsonify({"result": "⚠️ 圖片太大，請使用小於 10MB 的圖片"}), 400
    except Exception as e:
        return jsonify({"result": f"⚠️ 讀取圖片失敗: {e}"}), 400

    # 使用 Gemini (舊SDK) - gemini-pro-vision
    result = None
    try:
        print("🔵 使用 Gemini 相容版辨識中...")
        model = genai.GenerativeModel("gemini-pro-vision")
        response = model.generate_content([
            "你是數學老師安安，請幫我看這道數學題，用親切可愛的語氣，條列清楚步驟與答案。",
            {"mime_type": "image/jpeg", "data": image_bytes}
        ])
        result = response.text
        print("✅ Gemini 成功！")
    except Exception as e:
        print(f"⚠️ Gemini 相容版失敗: {e}")

    # 備援 GPT
    if not result:
        try:
            print("🟢 使用 GPT-4o-mini 備援...")
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "你是安安老師，請幫我看這張數學題圖片，條列清楚解題步驟與答案。"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                    ]
                }],
                "max_tokens": 1000
            }
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
            result = r.json()["choices"][0]["message"]["content"]
            print("✅ GPT 備援成功！")
        except Exception as e:
            print(f"❌ GPT 備援失敗: {e}")
            return jsonify({"result": "⚠️ 圖片辨識失敗，請重試！"}), 500

    # ✅ 儲存對話
    if "conversation" not in session:
        session["conversation"] = []
    conversation = session["conversation"]
    conversation.append({"role": "user", "content": "📷 [上傳了數學題目圖片]"})
    conversation.append({"role": "assistant", "content": result})
    session["conversation"] = conversation
    session.modified = True

    # 存入資料庫
    conn = get_conn()
    conn.execute("INSERT INTO records (user_id, question, topic, is_correct) VALUES (?, ?, ?, ?)",
                 (session["user_id"], "[圖片題目]", "圖片辨識", None))
    conn.commit()
    conn.close()

    return jsonify({"result": result, "success": True}), 200


# -------------------------------
# 🩺 健康檢查
# -------------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


# -------------------------------
# 🚀 主程式入口
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
