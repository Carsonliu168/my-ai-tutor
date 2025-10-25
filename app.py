# ================================
# 📘 數學小老師安安主程式 app.py
# v4.8.1-secure-chat-fixed
# - 登入保護（未登入 POST 拒絕）
# - 「我不懂」三段式教學
# - bcrypt 密碼雜湊 + 舊明文自動升級
# - 以環境變數建立 admin/demo（不在 log 顯示密碼）
# - 後台守門骨架（/admin）
# - 🔧 新增 /chat 路由相容舊前端
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, base64, requests, sqlite3, uuid, re, random, bcrypt
from datetime import datetime, timedelta

# -------------------------------
# ✅ Flask 初始化
# -------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# -------------------------------
# ✅ 模型金鑰
# -------------------------------
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
openai_api_key   = os.getenv("OPENAI_API_KEY", "")
gemini_api_key   = os.getenv("GEMINI_API_KEY", "")

# -------------------------------
# ✅ 資料庫初始化
# -------------------------------
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
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS records(
        id TEXT PRIMARY KEY,
        user TEXT,
        question TEXT,
        answer TEXT,
        correct INTEGER,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()

# -------------------------------
# ✅ 密碼雜湊與驗證
# -------------------------------
def hash_password(plain: str) -> bytes:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())

def check_password(plain: str, hashed: bytes | str) -> bool:
    if isinstance(hashed, str):
        hashed = hashed.encode("utf-8")
    return bcrypt.checkpw(plain.encode("utf-8"), hashed)

# -------------------------------
# ✅ 以環境變數建立帳號（不印密碼）
# -------------------------------
ADMIN_USER = os.getenv("ADMIN_USER", "anan_admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "")
DEMO_USER  = os.getenv("DEMO_USER", "demo_user")
DEMO_PASS  = os.getenv("DEMO_PASS", "")

def seed_accounts():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing = {row[0] for row in c.execute("SELECT username FROM users").fetchall()}

    if ADMIN_PASS and ADMIN_USER not in existing:
        hashed = hash_password(ADMIN_PASS).decode("utf-8")
        c.execute(
            "INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, datetime('now'))",
            (ADMIN_USER, hashed, "admin")
        )
        conn.commit()
        print(f"✅ 已建立管理員帳號：{ADMIN_USER}（密碼已隱藏）")

    if DEMO_PASS and DEMO_USER not in existing:
        hashed = hash_password(DEMO_PASS).decode("utf-8")
        c.execute(
            "INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, datetime('now'))",
            (DEMO_USER, hashed, "student")
        )
        conn.commit()
        print(f"✅ 已建立示範帳號：{DEMO_USER}（密碼已隱藏）")

    conn.close()

seed_accounts()
print("✅ [安安] 資料庫就緒（v4.8.1-secure-chat-fixed）")

# -------------------------------
# ✅ 文字處理
# -------------------------------
def format_ai_reply(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'^\s*\d+\.\s*', '', text, flags=re.MULTILINE)
    text = text.replace('\n\n', '<br><br>').replace('\n', '<br>')
    text = re.sub(r'\$([A-Za-z0-9])\$', r'\1', text)
    return text.strip()

def normalize_math_terms(text: str) -> str:
    if not text:
        return text
    text = text.replace("π", "3.1416")
    text = re.sub(r"(\d+)\s*cm²", r"\1 平方公分", text)
    return text

# -------------------------------
# ✅ AI 教學主程式
# -------------------------------
def build_system_prompt(style: str) -> str:
    return f"""你是「數學小老師安安」，用繁體中文與學生互動教學。
請直接進入數學內容，**不要自我介紹、不要寒暄、不要重複開場白**。

教學風格：
- 溫柔、親切、鼓勵。
- 蘇格拉底式提問（socratic）或直接講解（direct）。

教學原則：
1️⃣ 答對→肯定並補上完整算式。
2️⃣ 答錯→鼓勵並引導修正。
3️⃣ 問概念→結合例題。
4️⃣ 嚴禁閒聊與自介，只以「安安」身份教學。
5️⃣ {style}
"""

def ask_anan(question: str, mode="socratic") -> str:
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

# -------------------------------
# ✅ 登入 / 登出
# -------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        row = c.execute("SELECT password, role FROM users WHERE username=?", (username,)).fetchone()
        conn.close()

        if not row:
            return render_template("login.html", error="帳號或密碼錯誤，請再試一次。")

        stored_pw, role = row[0], (row[1] or "student")
        ok = False

        if stored_pw:
            try:
                ok = check_password(password, stored_pw)
            except Exception:
                ok = False
            if not ok and len(stored_pw) < 60:
                if password == stored_pw:
                    new_hash = hash_password(password).decode("utf-8")
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    c.execute("UPDATE users SET password=? WHERE username=?", (new_hash, username))
                    conn.commit()
                    conn.close()
                    ok = True

        if ok:
            session["user"] = username
            session["role"] = role
            session["confusion_count"] = 0
            return redirect(url_for("home"))
        else:
            return render_template("login.html", error="帳號或密碼錯誤，請再試一次。")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# -------------------------------
# ✅ 主互動（守門＋三段式不懂）
# -------------------------------
@app.route("/", methods=["GET", "POST"])
def home():
    if "user" not in session:
        if request.method == "GET":
            return redirect("/login")
        return jsonify({"reply": "⚠️ 請先登入後再使用安安老師喔～"})

    if request.method == "POST":
        msg = request.form.get("message", "").strip()
        confusion_count = session.get("confusion_count", 0)

        if "懂了" in msg:
            praise_list = [
                "太棒了！你真的很努力 👍",
                "安安老師為你鼓掌 👏",
                "很好～你已經掌握這個觀念了！",
                "非常好！我們繼續挑戰下一題吧 💪"
            ]
            reply = random.choice(praise_list)
            session["current_problem"] = None
            session["in_progress"] = False
            session["confusion_count"] = 0
            return jsonify({"reply": reply})

        if "不懂" in msg:
            if session.get("current_problem"):
                confusion_count += 1
                session["confusion_count"] = confusion_count

                if confusion_count == 1:
                    followup = f"學生說他不太懂這題「{session['current_problem']}」，請換個角度、舉例或更簡單的方式再教一次。"
                    reply = ask_anan(followup, mode="direct")
                elif confusion_count == 2:
                    followup = f"學生第二次說他還是不懂這題「{session['current_problem']}」，請再用不同的方式簡短解釋，語氣更鼓勵。"
                    reply = ask_anan(followup, mode="direct")
                else:
                    reply = "沒關係～學習本來就是一步步來！這題你可以先記下來，明天拿去問老師，安安為你加油 💪"

                reply = format_ai_reply(reply)
            else:
                reply = "沒問題，我們可以換一題或再問別的問題喔～"
            return jsonify({"reply": reply})

        # 一般新提問
        reply = ask_anan(msg, mode="socratic")
        reply = format_ai_reply(reply)
        session["current_problem"] = msg
        session["in_progress"] = True
        session["confusion_count"] = 0

        # 寫入紀錄
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO records (id,user,question,answer,correct,created_at) VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), session["user"], msg, reply, 1, datetime.now().isoformat())
            )
            conn.commit()
        except sqlite3.Error as e:
            print("⚠️ 寫入 records 失敗：", e)
        finally:
            conn.close()

        return jsonify({"reply": reply})

    return render_template("index.html", username=session.get("user"), role=session.get("role"))

# -------------------------------
# ✅ 後台骨架
# -------------------------------
@app.route("/admin")
def admin_panel():
    if session.get("role") != "admin":
        return redirect("/login")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    users = c.execute("SELECT username, role, created_at FROM users ORDER BY created_at DESC").fetchall()
    records = c.execute("SELECT user, question, created_at FROM records ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    return render_template("admin.html", users=users, records=records)

# -------------------------------
# ✅ /chat 相容舊前端
# -------------------------------
@app.route("/chat", methods=["POST"])
def chat():
    return home()

# -------------------------------
# ✅ 清除
# -------------------------------
@app.route("/clear")
def clear():
    session.clear()
    return redirect("/login")

# -------------------------------
# ✅ 啟動
# -------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print("🚀 安安 v4.8.1-secure-chat-fixed 啟動完成")
    app.run(host="0.0.0.0", port=port)
