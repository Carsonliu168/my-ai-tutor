# ================================
# 📘 數學小老師安安主程式 app.py
# v4.7.9：恢復安安角色 + 蘇格拉底式教學 + 禁寒暄 + 修正 UTF-8
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session
import os, json, base64, requests, sqlite3, uuid, re
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# API Keys
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
openai_api_key   = os.getenv("OPENAI_API_KEY", "")
gemini_api_key   = os.getenv("GEMINI_API_KEY", "")

# SQLite
DB_PATH = "data/anan.db"
os.makedirs("data", exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        created_at TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS records(
        id TEXT PRIMARY KEY,
        user TEXT,
        question TEXT,
        answer TEXT,
        correct INTEGER,
        created_at TEXT
    )""")
    conn.commit(); conn.close()

init_db()

def seed_admin():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE username='anan_admin'")
    if not c.fetchone():
        c.execute(
            "INSERT INTO users (username, password, role, created_at) VALUES ('anan_admin','1234','admin',datetime('now'))"
        )
        conn.commit()
        print("✅ 已自動建立管理員帳號：anan_admin / 密碼 1234")
    conn.close()

seed_admin()
print("✅ [安安] 資料庫就緒，含 users 登入表 (v4.7.9)")

# ---- 工具
def normalize_math_terms(text):
    if not text: return text
    text = text.replace("π", "3.1416")
    text = re.sub(r"(\d+)\s*cm²", r"\1 平方公分", text)
    return text

def build_system_prompt(style: str) -> str:
    return f"""你是「數學小老師安安」，用繁體中文與學生互動教學。
請直接進入數學內容，**不要自我介紹、不要寒暄、不要重複開場白**。

教學風格：
- 用溫柔、親切、鼓勵式語氣。
- 採用蘇格拉底式提問法，引導學生一步步思考。
- 若模式為 direct，請直接給出完整步驟、公式、代入與答案。
- 若學生輸入簡短或不完整，請先釐清再教。

教學原則：
1️⃣ 若學生答對，請肯定並補上完整算式。
2️⃣ 若學生答錯，請鼓勵並引導他找出錯誤。
3️⃣ 若學生問公式或概念，請結合例題說明。
4️⃣ 不要閒聊、不要說自己是 AI，只要以「安安」的身份教學。
5️⃣ {style}
"""

def ask_anan(question, mode="socratic"):
    if len((question or "").strip()) < 5:
        mode = "direct"
    style = (
        "採用蘇格拉底式提問法，引導學生一步步思考。"
        if mode == "socratic"
        else "請用清楚步驟直接講解完整解法，包含公式、代入、計算與答案。"
    )
    system_prompt = build_system_prompt(style)

    # DeepSeek 主模型
    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.2,
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
                {"role": "user", "content": question},
            ],
            "temperature": 0.2,
        }
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload2, timeout=40)
        reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if reply:
            return normalize_math_terms(reply)
    except Exception as e:
        print("OpenAI 備援失敗:", e)

    return "（安安暫時沒回應，請稍後再試一次）"

# ---- 登入
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session["user"] = username
            return redirect("/")
        return render_template("login.html", error="帳號或密碼錯誤，請再試一次。")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

# ---- 首頁互動（含舊表相容寫入）
@app.route("/", methods=["GET", "POST"])
def home():
    if "user" not in session:
        return redirect("/login")
    if request.method == "POST":
        msg = request.form.get("message", "").strip()
        reply = ask_anan(msg, mode="socratic")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO records (id,user,question,answer,correct,created_at) VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), session["user"], msg, reply, 1, datetime.now().isoformat()),
            )
            conn.commit()
        except sqlite3.Error as e:
            try:
                c.execute(
                    "INSERT INTO records (user_id,question,topic,is_correct) VALUES (?,?,?,?)",
                    (session["user"], msg, "一般", None),
                )
                conn.commit()
                print("ℹ️ 已自動使用舊版 records 結構寫入成功")
            except sqlite3.Error as e2:
                print("⚠️ 寫入 records 失敗：", e, " / fallback:", e2)
        finally:
            conn.close()

        return jsonify({"reply": reply})
    return render_template("index.html")

# ---- 清除對話（僅清 session）
@app.route("/clear")
def clear():
    session.pop("conversation", None)
    return redirect("/")

# ---- 學生回饋
@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json(silent=True) or {}
    fb = data.get("feedback", "")
    if fb == "understood":
        return jsonify({"reply": "太棒了～安安替你開心 💪"})
    if fb == "confused":
        return jsonify({"reply": "沒關係，我再換個方式說一次，記得抓住關鍵公式喔～"})
    return jsonify({"reply": "收到你的回饋，謝謝！"})

# ---- 啟動
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
