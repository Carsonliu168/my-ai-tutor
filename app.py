# ================================
# 📘 安安專案主程式 app.py
# v4.7.5：統一資料庫路徑（data/anan.db）+ 登入修復 + 圖片題/互動穩定
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session
import os, json, base64, requests, sqlite3, uuid, re
from datetime import datetime, timedelta

# ------------------------
# 🔧 Flask 初始化
# ------------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# ------------------------
# 🔑 API 金鑰設定
# ------------------------
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
openai_api_key = os.getenv("OPENAI_API_KEY", "")
gemini_api_key = os.getenv("GEMINI_API_KEY", "")

# ------------------------
# 📁 SQLite 初始化
# ------------------------
DB_PATH = "data/anan.db"
os.makedirs("data", exist_ok=True)  # 確保 data 目錄存在

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS records
                 (id TEXT PRIMARY KEY, user TEXT, question TEXT, answer TEXT, correct INTEGER, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT, created_at TEXT)''')
    conn.commit()
    conn.close()

init_db()
print("✅ [安安] 資料庫就緒，含 users 登入表 (v4.7.5 - data/anan.db)")

# ------------------------
# 🧮 教學邏輯核心：ask_anan
# ------------------------
def normalize_math_terms(text):
    text = text.replace("π", "3.1416")
    text = re.sub(r"(\d+)\s*cm²", r"\1 平方公分", text)
    return text

def ask_anan(question, mode="socratic"):
    if len(question.strip()) < 5:
        mode = "direct"

    style = (
        "採用蘇格拉底式提問法，引導學生一步步思考，但不要閒聊。"
        if mode == "socratic"
        else "請用清楚步驟直接講解完整解法，包含公式、代入、計算與答案。"
    )

    system_prompt = f"""你是台灣國中數學助教「安安」，用繁體中文教學。
風格：親切、有耐心，但不寒暄、不離題。
原則：
- 若學生回答正確，先肯定再補上完整算式。
- 若學生答錯，請用鼓勵語氣引導。
- 若學生輸入簡短詞（如公式或關鍵字），請直接用「公式應用 + 範例 + 最後答案」教學。
- 語氣自然口語化，結尾請說出具體答案與單位。
- {style}
"""

    # DeepSeek 主模型
    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            "temperature": 0.2
        }
        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=40)
        reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if reply:
            return normalize_math_terms(reply)
    except Exception as e:
        print("DeepSeek 失敗:", e)

    # OpenAI 備援
    try:
        if not openai_api_key:
            raise RuntimeError("未設定 OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
        payload2 = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            "temperature": 0.2
        }
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload2, timeout=40)
        reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if reply:
            return normalize_math_terms(reply)
    except Exception as e:
        print("OpenAI 備援失敗:", e)

    return "（安安暫時沒回應，請稍後再試一次）"

# ------------------------
# 🔒 登入系統
# ------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session["user"] = username
            return redirect("/")
        else:
            return render_template("login.html", error="帳號或密碼錯誤，請再試一次。")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

# ------------------------
# 🏠 主頁與互動
# ------------------------
@app.route("/", methods=["GET", "POST"])
def home():
    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":
        msg = request.form.get("message", "")
        reply = ask_anan(msg, mode="socratic")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)",
                  (str(uuid.uuid4()), session["user"], msg, reply, 1, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return jsonify({"reply": reply})
    return render_template("index.html")

# ------------------------
# 🧹 清除對話
# ------------------------
@app.route("/clear")
def clear():
    session.pop("conversation", None)
    return redirect("/")

# ------------------------
# 💬 學生回饋（懂了 / 不懂）
# ------------------------
@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.json
    feedback_type = data.get("feedback", "")
    if feedback_type == "understood":
        return jsonify({"reply": "太棒了～安安替你開心 💪"})
    elif feedback_type == "confused":
        return jsonify({"reply": "沒關係，我再簡單講一次：記得公式與步驟才是關鍵喔～"})
    else:
        return jsonify({"reply": "收到你的回饋，謝謝！"})

# ------------------------
# 🚀 啟動
# ------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
