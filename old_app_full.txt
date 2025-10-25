# ==================================================
# 📘 數學小老師安安主程式 app.py
# v5.0.25-stable-realAI：全功能整合 + DeepSeek/OpenAI 真實串接 + UTF-8 完整支援
# ==================================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, sqlite3, bcrypt, requests
from datetime import datetime, timedelta

# -------------------------------
# ✅ Flask 初始化
# -------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.permanent_session_lifetime = timedelta(days=30)

# -------------------------------
# ✅ 模型金鑰讀取與檢查
# -------------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GAC_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", "")

print(f"🔍 環境變數檢查： DEEPSEEK={'OK' if DEEPSEEK_API_KEY else '❌'}; "
      f"GOOGLE_API_KEY={'OK' if GOOGLE_API_KEY else '❌'}; "
      f"OPENAI_API_KEY={'OK' if OPENAI_API_KEY else '❌'}; "
      f"GAC_JSON={'OK' if GAC_JSON else '❌'}")

# -------------------------------
# ✅ 資料庫初始化（含 admin/demo 帳號）
# -------------------------------
def initialize_admin_user():
    os.makedirs("data", exist_ok=True)
    db_path = os.path.join("data", "anan.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            role TEXT DEFAULT 'user',
            profile_type TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("SELECT * FROM users WHERE username='anan_admin'")
    if not cur.fetchone():
        pw = bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    ("anan_admin", pw, "admin"))
        print("✅ 已建立 anan_admin / 密碼 admin123")

    cur.execute("SELECT * FROM users WHERE username='demo_user'")
    if not cur.fetchone():
        pw = bcrypt.hashpw("demo123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    ("demo_user", pw, "user"))
        print("✅ 已建立 demo_user / 密碼 demo123")

    conn.commit()
    conn.close()

initialize_admin_user()

# -------------------------------
# ✅ 登入 / 登出 / 註冊
# -------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        conn = sqlite3.connect("data/anan.db")
        cur = conn.cursor()
        cur.execute("SELECT password_hash, role FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        conn.close()

        if row and bcrypt.checkpw(password.encode("utf-8"), row[0].encode("utf-8")):
            session["username"] = username
            session["role"] = row[1]
            session.permanent = True
            return redirect("/")
        else:
            return render_template("login.html", error="帳號或密碼錯誤")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form.get("email", "").strip()
        password = request.form["password"].strip()

        if not username or not password:
            return render_template("register.html", error="請輸入帳號與密碼")

        conn = sqlite3.connect("data/anan.db")
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cur.fetchone():
            conn.close()
            return render_template("register.html", error="此帳號已存在")

        pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    (username, pw, "user"))
        conn.commit()
        conn.close()
        return redirect("/login")
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# -------------------------------
# ✅ 首頁導向
# -------------------------------
@app.route("/")
def home():
    username = session.get("username")
    role = session.get("role", "user")

    if not username:
        return redirect("/login")

    conn = sqlite3.connect("data/anan.db")
    cur = conn.cursor()
    cur.execute("SELECT role, profile_type FROM users WHERE username = ?", (username,))
    user = cur.fetchone()
    conn.close()

    if not user:
        return redirect("/login")

    role, profile_type = user
    session["role"] = role

    if role == "admin":
        return render_template("index.html", username=username, role=role)
    elif not profile_type:
        return redirect("/cognitive_test")
    else:
        return render_template("index.html", username=username, role=role)

# -------------------------------
# ✅ 認知測驗頁面與提交
# -------------------------------
@app.route("/cognitive_test")
def cognitive_test():
    if "username" not in session:
        return redirect("/login")
    return render_template("test_intro.html")

@app.route("/submit_test", methods=["POST"])
def submit_test():
    data = request.get_json()
    answers = data.get("answers", [])

    if not answers or len(answers) != 7:
        return jsonify({"success": False, "error": "答案格式錯誤"})

    a_count, b_count = answers.count("A"), answers.count("B")

    if a_count - b_count >= 3:
        profile_type = "邏輯戰略家"
    elif b_count - a_count >= 3:
        profile_type = "創意視覺家"
    else:
        profile_type = "平衡大師"

    username = session.get("username")
    if username:
        conn = sqlite3.connect("data/anan.db")
        cur = conn.cursor()
        cur.execute("UPDATE users SET profile_type = ? WHERE username = ?", (profile_type, username))
        conn.commit()
        conn.close()

    return jsonify({"success": True, "result": profile_type})

@app.route("/test_result")
def test_result():
    result = request.args.get("result", "未知類型")
    descriptions = {
        "邏輯戰略家": "你擅長以條理與策略解決問題，喜歡從全局推理出答案，是理性與分析的高手。",
        "創意視覺家": "你具有豐富的想像力與整體感知力，習慣用圖像、感覺和關聯去理解知識。",
        "平衡大師": "你能靈活切換邏輯與直覺的思維，能在不同學習情境中找到最適合的方式。"
    }
    description = descriptions.get(result, "每個人都有不同的思考方式，這是你獨特的優勢！")
    username = session.get("username", "未知使用者")
    return render_template("test_result.html", username=username, result=result, description=description)

# -------------------------------
# ✅ 聊天 / 清除 / 上傳
# -------------------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_input = (data.get("message") or "").strip()
    if not user_input:
        return jsonify({"reply": "請輸入題目或問題內容喔～"})

    try:
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是台灣小學生的數學小老師安安，用繁體中文蘇格拉底式教學。"},
                {"role": "user", "content": user_input}
            ],
            "temperature": 0.7
        }
        r = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            data = r.json()
            reply = data["choices"][0]["message"]["content"].strip()
        else:
            raise Exception("DeepSeek failed")

    except Exception:
        try:
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "你是台灣小學生的數學小老師安安，用繁體中文蘇格拉底式教學。"},
                    {"role": "user", "content": user_input}
                ]
            }
            r2 = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30)
            if r2.status_code == 200:
                data = r2.json()
                reply = data["choices"][0]["message"]["content"].strip()
            else:
                reply = f"⚠️ 備援模型無回覆（{r2.status_code}）"
        except Exception:
            reply = "⚠️ 系統忙碌中，請稍後再試。"

    return jsonify({"reply": reply})

@app.route("/clear")
def clear():
    session.pop("records", None)
    return redirect("/")

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file") or request.files.get("image")
    if not file:
        return jsonify({"reply": "⚠️ 沒有收到圖片檔案，請再選一次並上傳。"})
    return jsonify({"reply": "📷 圖片已收到！請簡要描述題目重點，我會一步步帶你解。"})

# -------------------------------
# ✅ 404 / 健康檢查
# -------------------------------
@app.errorhandler(404)
def not_found(e):
    return "404 Not Found", 404

@app.route("/health")
def health():
    return "OK", 200

# -------------------------------
# ✅ 啟動伺服器
# -------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
