# ==================================================
# 📘 數學小老師安安主程式 app.py
# v5.0.24-stable：一次到位修正版（環境變數檢查＋/chat＋/upload＋/clear GET）
# ==================================================

from flask import Flask, render_template, request, jsonify, redirect, session
import os, json, sqlite3, bcrypt
from datetime import timedelta

# -------------------------------
# ✅ Flask 初始化
# -------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.permanent_session_lifetime = timedelta(days=30)

# -------------------------------
# ✅ 環境變數檢查（部署時可在 Log 看狀態）
# -------------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_APPLICATION_CREDENTIALS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

print("🔍 環境變數檢查：",
      f"DEEPSEEK={'OK' if DEEPSEEK_API_KEY else 'MISS'};",
      f"GOOGLE_API_KEY={'OK' if GOOGLE_API_KEY else 'MISS'};",
      f"OPENAI_API_KEY={'OK' if OPENAI_API_KEY else 'MISS'};",
      f"GAC_JSON={'OK' if bool(GOOGLE_APPLICATION_CREDENTIALS_JSON) else 'MISS'}")

# -------------------------------
# ✅ 資料庫初始化（含 admin/demo 帳號）
# -------------------------------
def initialize_admin_user():
    os.makedirs("data", exist_ok=True)
    db_path = os.path.join("data", "anan.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 建立 users 資料表
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

    # 建立管理員 anan_admin
    cur.execute("SELECT 1 FROM users WHERE username = 'anan_admin'")
    if not cur.fetchone():
        pw = bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    ("anan_admin", pw, "admin"))
        print("✅ 已建立 anan_admin / 密碼 admin123")

    # 建立 demo_user
    cur.execute("SELECT 1 FROM users WHERE username = 'demo_user'")
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
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

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
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

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
    session["role"] = role  # 同步一次

    if role == "admin":
        return render_template("index.html", username=username, role=role)
    elif not profile_type:
        return redirect("/cognitive_test")
    else:
        return render_template("index.html", username=username, role=role)

# -------------------------------
# ✅ 認知測驗頁面
# -------------------------------
@app.route("/cognitive_test")
def cognitive_test():
    if "username" not in session:
        return redirect("/login")
    # 你目前提供的是 test_intro.html（含 7 題互動腳本）
    return render_template("test_intro.html")

# -------------------------------
# ✅ 認知測驗提交 /submit_test
# -------------------------------
@app.route("/submit_test", methods=["POST"])
def submit_test():
    data = request.get_json(silent=True) or {}
    answers = data.get("answers", [])

    if not answers or len(answers) != 7:
        return jsonify({"success": False, "error": "答案格式錯誤"})

    a_count = answers.count("A")
    b_count = answers.count("B")

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

# -------------------------------
# ✅ 測驗結果頁 /test_result
# -------------------------------
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
    role = session.get("role", "user")
    return render_template("test_result.html", username=username, role=role, result=result, description=description)

# -------------------------------
# ✅ 安安對話主系統（/chat）
#   備註：目前先提供穩定可用回覆；要串接模型可在此加入 API 呼叫。
# -------------------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_input = (data.get("message") or "").strip()
    if not user_input:
        return jsonify({"reply": "請輸入題目或問題內容喔～"})

    # 之後你要接 DeepSeek / Gemini / OpenAI，就在這裡寫真實呼叫。
    # 先給穩定模板回覆，確保服務不中斷。
    if "我不懂" in user_input:
        reply = ("沒關係，我們換個方法：\n"
                 "1) 圈出已知與未知量\n"
                 "2) 寫下關係式（方程／比例）\n"
                 "3) 代入數值一步步計算\n"
                 "4) 檢查單位與答案是否合理\n"
                 "告訴我你卡在第幾步，我只針對那一步再講清楚。")
    elif "我懂了" in user_input or "懂了" in user_input:
        reply = "太棒了！想挑戰更難一點的嗎？或是換一題同類型的練習？"
    else:
        reply = ("收到題目！目前採本地穩定回覆模式：\n"
                 "• 請貼出完整題目（或上傳圖片），我會拆解成步驟\n"
                 "• 公式請用 $...$ 包住，我會幫你排版\n"
                 "• 若你想用圖解，我也可以用圖像化比喻帶你理解")

    return jsonify({"reply": reply})

# -------------------------------
# ✅ 圖片上傳（/upload）
#   前端 script.js：fetch('/upload', { method:'POST', body: FormData })
# -------------------------------
@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file") or request.files.get("image")
    if not file:
        return jsonify({"reply": "⚠️ 沒有收到圖片檔案，請重新選擇後上傳。"})
    # 目前不落地；若要 OCR / 視覺模型，未來在此接入
    return jsonify({"reply": "📷 圖片已收到！請簡要描述題目，我會一步步帶你解。"})

# -------------------------------
# ✅ 清除紀錄（與前端 location.href='/clear' 對應 → 必須是 GET）
# -------------------------------
@app.route("/clear")
def clear():
    # 若未來有對話快取，可在此處清除；目前導回首頁即可
    return redirect("/")

# -------------------------------
# ✅ 健康檢查 / 404
# -------------------------------
@app.route("/health")
def health():
    return "OK", 200

@app.errorhandler(404)
def not_found(e):
    return "404 Not Found", 404

# -------------------------------
# ✅ 啟動伺服器（本地開發用；Railway 用 gunicorn 啟動）
# -------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
