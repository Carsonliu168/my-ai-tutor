# ================================
# 📘 安安專案主程式 app.py
# v5.0.1-stable
# -------------------------------
# ✅ Python 3.13 相容（無 imghdr）
# ✅ 含登入 / 註冊 / 問卷 / 方案 / 聊天 / 健康檢查
# ✅ 登入後自動清空前次對話、顯示完整介面
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, base64, requests, sqlite3, uuid, re, mimetypes
from datetime import datetime, timedelta
from functools import wraps

# ---------------------------------------------------
# ✅ 模擬 imghdr：新版 Python (3.13) 不再內建
# ---------------------------------------------------
def detect_mime_by_bytes(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    elif data[:2] == b"\xff\xd8":
        return "image/jpeg"
    return "image/jpeg"

# ---------------------------------------------------
# ✅ 密碼加密
# ---------------------------------------------------
try:
    from werkzeug.security import generate_password_hash, check_password_hash
except Exception:
    def generate_password_hash(p): return p
    def check_password_hash(h, p): return h == p

# ---------------------------------------------------
# ✅ Flask 初始化
# ---------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
session_lifetime_days = int(os.getenv("SESSION_LIFETIME_DAYS", "30"))
app.permanent_session_lifetime = timedelta(days=session_lifetime_days)
DEMO_MODE = os.getenv("DEMO_MODE", "False").lower() == "true"
APP_VERSION = "v5.0.1-stable"

# ---------------------------------------------------
# ✅ API 金鑰設定
# ---------------------------------------------------
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")
google_api_key = os.getenv("GOOGLE_API_KEY")

print("🔍 環境變數檢查：")
print("✅ DEEPSEEK_API_KEY" if deepseek_api_key else "⚠️ 未設定 DeepSeek")
print("✅ OPENAI_API_KEY" if openai_api_key else "⚠️ 未設定 OpenAI")
print("✅ GOOGLE_API_KEY" if google_api_key else "⚠️ 未設定 Google")

# ---------------------------------------------------
# ✅ Gemini 初始化
# ---------------------------------------------------
try:
    import google.generativeai as genai
    if google_api_key:
        genai.configure(api_key=google_api_key)
        try:
            _ = list(genai.list_models())
            print("✅ Gemini API 已就緒")
        except Exception as e:
            print(f"⚠️ Gemini 模型列表載入失敗: {e}")
    else:
        print("⚠️ 未設定 GOOGLE_API_KEY，略過 Gemini")
        genai = None
except Exception as e:
    print(f"⚠️ Gemini 初始化失敗：{e}")
    genai = None

# ---------------------------------------------------
# ✅ 資料庫設定
# ---------------------------------------------------
DB_PATH = "data/anan.db"
os.makedirs("data", exist_ok=True)

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        email TEXT,
        profile_type TEXT,
        start_date TEXT,
        expire_date TEXT,
        is_active INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        question TEXT,
        topic TEXT,
        is_correct INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit(); conn.close()
    print(f"✅ [安安] 資料庫就緒（{APP_VERSION}）")

init_db()

# ---------------------------------------------------
# ✅ 登入 / 註冊 / 登出
# ---------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if not username or not password:
            return render_template("login.html", error="請輸入帳號與密碼")

        conn = get_conn(); c = conn.cursor()
        c.execute("SELECT id,password_hash FROM users WHERE username=?", (username,))
        row = c.fetchone(); conn.close()
        if not row or not check_password_hash(row[1], password):
            return render_template("login.html", error="帳號或密碼錯誤")

        session["auth_user_id"], session["auth_username"] = row[0], username
        session.modified = True
        # 登入後自動清空舊對話
        session.pop("conversation", None)
        session["last_user"] = username
        return redirect(url_for("home"))

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        if not username or not password or not email:
            return render_template("register.html", error="請完整填寫資料")

        conn = get_conn(); c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=?", (username,))
        if c.fetchone():
            conn.close()
            return render_template("register.html", error="此帳號已被註冊")

        start = datetime.now().strftime("%Y-%m-%d")
        expire = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        c.execute("""INSERT INTO users(username,email,password_hash,start_date,expire_date)
                     VALUES(?,?,?,?,?)""",
                  (username, email, generate_password_hash(password), start, expire))
        conn.commit(); conn.close()
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/logout")
def logout():
    for k in ["auth_user_id", "auth_username", "conversation", "last_user"]:
        session.pop(k, None)
    session.modified = True
    return redirect(url_for("login"))

# ---------------------------------------------------
# ✅ 問卷測驗
# ---------------------------------------------------
@app.route("/cognitive_test")
def cognitive_test():
    return render_template("test_intro.html")

@app.route("/submit_questionnaire", methods=["POST"])
def submit_questionnaire():
    data = request.get_json(silent=True) or {}
    answers = data.get("answers") or []
    logic = sum(1 for a in answers if str(a).upper()=="A")
    visual = sum(1 for a in answers if str(a).upper()=="B")
    profile = "平衡大師"
    if logic - visual >= 3: profile = "邏輯戰略家"
    elif visual - logic >= 3: profile = "創意視覺家"

    if profile == "邏輯戰略家":
        desc = "你的思考邏輯超強！適合逐步講解與高效率演練。"
        plan = {"key":"pro","price":390,"name":"🎯 開啟策略思考模式"}
    elif profile == "創意視覺家":
        desc = "你擅長以畫面理解世界！建議使用圖像互動式教學。"
        plan = {"key":"vision","price":490,"name":"🎨 體驗視覺化教學冒險"}
    else:
        desc = "你的思維均衡又靈活！你是安安最理想的全能型學習者。"
        plan = {"key":"basic","price":290,"name":"⚖️ 啟動全方面學習力"}

    result = {"type":profile,"description":desc,"logic_score":logic,"intuition_score":visual,"plan":plan}
    session["cognitive_profile"] = result; session.modified = True

    try:
        conn = get_conn(); c = conn.cursor()
        c.execute("UPDATE users SET profile_type=? WHERE id=?", (profile, session.get("auth_user_id")))
        conn.commit(); conn.close()
    except: pass
    return jsonify({"success":True})

@app.route("/questionnaire_result")
def questionnaire_result():
    profile = session.get("cognitive_profile")
    if not profile: return redirect(url_for("cognitive_test"))
    return render_template("test_result.html", profile=profile)

# ---------------------------------------------------
# ✅ 訂閱方案
# ---------------------------------------------------
PLAN_MAP = {
    "basic": {"title":"⚖️ 啟動全方面學習力","price":290},
    "pro": {"title":"🎯 開啟策略思考模式","price":390},
    "vision": {"title":"🎨 體驗視覺化教學冒險","price":490}
}

@app.route("/subscribe/<plan>")
def subscribe(plan):
    p = PLAN_MAP.get(plan)
    if not p: return redirect(url_for("questionnaire_result"))
    return render_template("subscribe.html", plan_key=plan, plan=p, username=session.get("auth_username"))

# ---------------------------------------------------
# ✅ 首頁 / 聊天（v5.0.1 修正版）
# ---------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def home():
    # 未登入 → 跳轉登入
    if not session.get("auth_user_id") and not DEMO_MODE:
        return redirect(url_for("login"))

    # 登入變更 → 清除舊對話
    last_user = session.get("last_user")
    current_user = session.get("auth_username")
    if last_user != current_user:
        session["conversation"] = []
        session["last_user"] = current_user
        session.modified = True

    convo = session.setdefault("conversation", [])

    # 使用者輸入訊息
    if request.method == "POST":
        msg = request.form.get("message", "").strip()
        if msg:
            convo.append({"role": "user", "content": msg})
            reply = f"👩‍🏫 安安老師：我收到你的問題「{msg}」，讓我想想看怎麼幫你解釋～"
            convo.append({"role": "assistant", "content": reply})
            session["conversation"] = convo[-10:]
            session.modified = True

    return render_template(
        "index.html",
        show_chat=True,
        show_login=False,
        conversation=session.get("conversation", []),
        username=session.get("auth_username")
    )

# ---------------------------------------------------
# ✅ 健康檢查
# ---------------------------------------------------
@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "version": APP_VERSION,
        "deepseek": bool(deepseek_api_key),
        "openai": bool(openai_api_key),
        "google": bool(google_api_key)
    })

# ---------------------------------------------------
# ✅ 啟動主程式
# ---------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 啟動安安：{APP_VERSION}")
    app.run(host="0.0.0.0", port=port)
