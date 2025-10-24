# ==================================================
# 📘 數學小老師安安主程式 app.py
# v5.0.23-hotfix：補回 /chat /upload /clear ＋ 金鑰讀取與啟動健康檢查
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
# ✅ 環境變數讀取與啟動健康檢查（重要：方便你在 Railway log 看到狀態）
# -------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GOOGLE_APPLICATION_CREDENTIALS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

if DEEPSEEK_API_KEY:
    print("✅ 成功讀到 DEEPSEEK_API_KEY")
else:
    print("⚠️ DEEPSEEK_API_KEY 未設定")

if GOOGLE_API_KEY:
    print("✅ 成功讀到 GOOGLE_API_KEY")
else:
    print("⚠️ GOOGLE_API_KEY 未設定")

if OPENAI_API_KEY:
    print("✅ 成功讀到 OPENAI_API_KEY")
else:
    print("⚠️ OPENAI_API_KEY 未設定（可選，作為備援）")

if GOOGLE_APPLICATION_CREDENTIALS_JSON:
    try:
        _ = json.loads(GOOGLE_APPLICATION_CREDENTIALS_JSON)
        print("✅ 成功讀到 GOOGLE_APPLICATION_CREDENTIALS_JSON（JSON 可解析）")
    except Exception as e:
        print(f"⚠️ GOOGLE_APPLICATION_CREDENTIALS_JSON 內容無法解析：{e}")
else:
    print("⚠️ GOOGLE_APPLICATION_CREDENTIALS_JSON 未設定（若你用雲端 Vision / Gemini 才需要）")

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
    cur.execute("SELECT * FROM users WHERE username = 'anan_admin'")
    if not cur.fetchone():
        # 若你想用 Railway 變數覆蓋預設，可在 Variables 放 ADMIN_DEFAULT_PASSWORD
        admin_pw = os.getenv("ADMIN_DEFAULT_PASSWORD", "admin123")
        pw = bcrypt.hashpw(admin_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    ("anan_admin", pw, "admin"))
        print("✅ 已建立 anan_admin / 密碼", admin_pw)

    # 建立 demo_user
    cur.execute("SELECT * FROM users WHERE username = 'demo_user'")
    if not cur.fetchone():
        demo_pw = os.getenv("DEMO_DEFAULT_PASSWORD", "demo123")
        pw = bcrypt.hashpw(demo_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    ("demo_user", pw, "user"))
        print("✅ 已建立 demo_user / 密碼", demo_pw)

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
    # 你的問卷頁面名稱若為 test_questions.html 也可用那個
    # 目前你提供的是 test_intro.html（含 7 題互動腳本）
    return render_template("test_intro.html")

# -------------------------------
# ✅ 認知測驗提交 /submit_test
# -------------------------------
@app.route("/submit_test", methods=["POST"])
def submit_test():
    data = request.get_json()
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
    return render_template("test_result.html", username=username, result=result, description=description)

# -------------------------------
# ✅ 安安對話主系統（/chat）
#   備註：為了避免 404 直接癱瘓，這裡提供穩定回覆邏輯；
//   若你要串接雲端模型，請在此處加入實際 API 呼叫。
# -------------------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_input = (data.get("message") or "").strip()
    if not user_input:
        return jsonify({"reply": "請輸入題目或問題內容喔～"})

    # ====== 你可以在這裡加上實際的 AI 提示或模型呼叫 ======
    # 範例：優先 DeepSeek，再退到 Gemini，再退到 OpenAI（略）
    # 這份 hotfix 先保證服務不中斷，給出可用的教學步驟模板
    # ===============================================

    # 極簡步驟產生器（避免 404 先讓系統能回答）
    def simple_solver(text: str) -> str:
        # 針對常見訊息提供一致回覆
        if "我不懂" in text:
            return ("沒關係，我們換個方法：\n"
                    "1) 先圈出題目中已知與未知量\n"
                    "2) 寫下關係式（例如方程或比例）\n"
                    "3) 代入數值一步步計算\n"
                    "4) 檢查單位與是否合理\n"
                    "若你告訴我卡在哪一步，我就針對那一步再展開。")
        if "我懂了" in text or "懂了" in text:
            return "太棒了！再挑戰一題吧～如果願意可以簡單說說你是怎麼想通的 😄"

        return ("收到你的題目了！目前雲端解題服務保持簡化模式：\n"
                "• 請貼出完整題目或拍照上傳，我會幫你拆解成小步驟。\n"
                "• 若有方程式，用 $...$ 包住，我會以數學格式顯示。\n"
                "• 你也可以直接說：『我卡在第幾步』，我就只講那一步。")

    reply = simple_solver(user_input)
    return jsonify({"reply": reply})

# -------------------------------
# ✅ 圖片上傳（/upload）
#   前端 script.js 會用 <input type="file"> 送 key: "file"
# -------------------------------
@app.route("/upload", methods=["POST"])
def upload():
    # 接受 "file" 或 "image" 兩種鍵名，兼容不同前端版本
    file = request.files.get("file") or request.files.get("image")
    if not file:
        return jsonify({"reply": "⚠️ 沒有收到圖片檔案，請再試一次（選擇圖片後再送出）。"})

    # 若你需要保存上傳檔案，可自行存到 /tmp 或雲端空間
    # 這裡先不落地存檔，直接回覆
    return jsonify({"reply": "📷 已收到圖片！目前為簡化流程，請同時文字說明題目，我會用小步驟帶你解。"})
    
# -------------------------------
# ✅ 清除紀錄（/clear）— 與前端按鈕對應
# -------------------------------
@app.route("/clear")
def clear():
    # 這裡僅做導回首頁，若有對話快取可在這裡清除
    return redirect("/")

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
    # 本地開發用；Railway 會用 Gunicorn 啟動
    app.run(host="0.0.0.0", port=8080)
