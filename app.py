# ================================
# 📘 安安專案主程式 app.py
# v4.7-login-ui：加入 /login /logout、到期檢查、未登入自動導向
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, base64, requests, sqlite3, uuid, re
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制 16MB

# -------------------------------
# ✅ 登入設定
# -------------------------------
session_lifetime_days = int(os.getenv("SESSION_LIFETIME_DAYS", "30"))
app.permanent_session_lifetime = timedelta(days=session_lifetime_days)
DEMO_MODE = os.getenv("DEMO_MODE", "False").lower() == "true"

# -------------------------------
# ✅ API 初始化
# -------------------------------
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")
google_api_key = os.getenv("GOOGLE_API_KEY")

try:
    import google.generativeai as genai
    if google_api_key:
        genai.configure(api_key=google_api_key)
        print("✅ Gemini API 已就緒")
    else:
        print("⚠️ 未設定 GOOGLE_API_KEY")
except Exception as e:
    print(f"⚠️ Gemini 初始化失敗: {e}")
    genai = None

# -------------------------------
# 🧩 工具函式
# -------------------------------
def normalize_math_terms(s: str) -> str:
    if not s:
        return s
    s = re.sub(r'\blcm\b', '最小公倍數', s, flags=re.IGNORECASE)
    s = re.sub(r'\bgcd\b', '最大公因數', s, flags=re.IGNORECASE)
    s = re.sub(r'\bmod\b', '模（取餘數）', s, flags=re.IGNORECASE)
    s = s.replace("质数","質數").replace("质因数","質因數").replace("余数","餘數")
    s = s.replace("最小公倍数","最小公倍數").replace("最大公约数","最大公因數")
    s = s.replace("这","這").replace("个","個").replace("写","寫").replace("为","為")
    return s

def is_pure_help_phrase(msg: str) -> bool:
    """判斷是否為純粹『我不懂／我不會／看不懂』"""
    return bool(re.fullmatch(r'\s*(我不會|不會|不懂|看不懂)\s*', msg or ""))

# -------------------------------
# 🗃️ SQLite
# -------------------------------
DB_PATH = "data/anan.db"
os.makedirs("data", exist_ok=True)
def get_conn(): return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # 學習紀錄
    c.execute("""
    CREATE TABLE IF NOT EXISTS records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        question TEXT,
        topic TEXT,
        is_correct INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 使用者登入表
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        start_date TEXT NOT NULL,
        expire_date TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    )
    """)

    conn.commit(); conn.close()
    print("✅ [安安] 資料庫就緒，含 users 登入表 (v4.7-login-ui)")

init_db()

# ---- 使用者查詢 / 建立（for 初始管理員） ----
def get_user(username: str):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT id, username, password_hash, start_date, expire_date, is_active FROM users WHERE username=?", (username,))
    row = c.fetchone(); conn.close()
    if not row: return None
    keys = ["id","username","password_hash","start_date","expire_date","is_active"]
    return dict(zip(keys, row))

def create_user(username: str, raw_password: str, days_valid: int = 365):
    today = date.today()
    expire = today + timedelta(days=days_valid)
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO users (username,password_hash,start_date,expire_date,is_active) VALUES (?,?,?,?,1)",
              (username, generate_password_hash(raw_password), today.isoformat(), expire.isoformat()))
    conn.commit(); conn.close()

def seed_admin_from_env():
    u = os.getenv("ADMIN_DEFAULT_USERNAME")
    p = os.getenv("ADMIN_DEFAULT_PASSWORD")
    if not u or not p: return
    if get_user(u) is None:
        try:
            create_user(u, p, days_valid=365)
            print(f"✅ 已建立初始管理員帳號：{u}（有效期 365 天）")
        except Exception as e:
            print("⚠️ 建立初始管理員失敗：", e)

seed_admin_from_env()

# -------------------------------
# 🧠 DeepSeek / GPT 備援
# -------------------------------
def ask_anan(question, mode="socratic"):
    style = "採用蘇格拉底式提問法，引導學生思考。" if mode=="socratic" else "用清楚步驟給出答案。"
    system_prompt = f"""你是台灣數學小老師安安。
請使用繁體中文（臺灣用語），親切、幽默地教學。
教學規範：
- 術語用中文（最小公倍數、最大公因數、模運算等）。
- 用鼓勵的語氣引導學生。
- {style}
"""
    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat","messages": [{"role":"system","content":system_prompt},{"role":"user","content":question}],"temperature":0.3}
        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=40)
        reply = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
        if reply: return normalize_math_terms(reply)
    except Exception as e: print("DeepSeek 失敗:", e)
    try:
        if not openai_api_key: raise RuntimeError("未設定 OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
        payload2 = {"model":"gpt-4o-mini","messages":[{"role":"system","content":system_prompt},{"role":"user","content":question}],"temperature":0.3}
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload2, timeout=40)
        reply = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
        if reply: return normalize_math_terms(reply)
    except Exception as e: print("OpenAI 備援失敗:", e)
    return "（無回應）"

# -------------------------------
# 🔐 登入驗證＋導向
# -------------------------------
def is_login_required_endpoint(endpoint: str) -> bool:
    """哪些端點需要登入"""
    if not endpoint:
        return True
    allow_list = {"login", "static"}  # 登入頁、靜態資源放行
    return endpoint not in allow_list

def is_user_expired(u: dict) -> bool:
    try:
        return date.today() > date.fromisoformat(u["expire_date"])
    except Exception:
        return True

@app.before_request
def auth_and_bootstrap_session():
    # 讓 session 進入永久模式（依據 app.permanent_session_lifetime）
    session.permanent = True

    # 若還沒有匿名 user_id，先給一個（不等同登入身分）
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())

    # 未登入者導向 /login
    if is_login_required_endpoint(request.endpoint):
        if not session.get("auth_user"):
            return redirect(url_for("login"))

# -------------------------------
# 🧮 analyze_image（含圖片記憶）
# -------------------------------
ALLOWED = {'png','jpg','jpeg'}
def allow(f): return '.' in f and f.rsplit('.',1)[1].lower() in ALLOWED

@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files: return jsonify({"result":"⚠️ 沒有收到圖片"}),400
    img = request.files["image"]
    if img.filename=='' or not allow(img.filename): return jsonify({"result":"⚠️ 圖片格式錯誤"}),400
    data = img.read(); res = None
    try:
        if not google_api_key or genai is None:
            raise RuntimeError("未設定 GOOGLE_API_KEY")
        model = genai.GenerativeModel("gemini-1.5-flash")
        r = model.generate_content([
            "你是台灣數學老師安安，用繁體中文詳細逐步講解這張圖片題。請分三到六個步驟說明，最後給出答案與單位。",
            {"mime_type":"image/jpeg","data":data}],
            generation_config={"max_output_tokens":1024})
        res = r.text
    except Exception as e: print("Gemini 失敗：", e)
    if not res:
        try:
            if not openai_api_key: raise RuntimeError("未設定 OPENAI_API_KEY")
            b64 = base64.b64encode(data).decode()
            h = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            p = {"model":"gpt-4o","messages":[{"role":"user","content":[
                {"type":"text","text":"你是台灣數學老師安安，用繁體中文詳細講解這張圖片題，請分三到六個步驟說明，最後給出答案與單位。"},
                {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}]}],"temperature":0.2}
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=h, json=p, timeout=60)
            res = r.json()["choices"][0]["message"]["content"]
        except Exception as e: return jsonify({"result":f"⚠️ 辨識失敗:{e}"}),500
    res = normalize_math_terms(res)
    session["guided_topic"] = "image_explain"
    session["image_b64"] = base64.b64encode(data).decode()
    session["image_confused_count"] = 0
    if "conversation" not in session: session["conversation"]=[]
    session["conversation"].append({"role":"user","content":"📷 [圖片題]"})
    session["conversation"].append({"role":"assistant","content":res})
    session.modified = True
    return jsonify({"result":res,"success":True}),200

# -------------------------------
# 🧠 主頁（需登入）
# -------------------------------
@app.route("/", methods=["GET","POST"])
def home():
    if "conversation" not in session: session["conversation"]=[]; session["confused_count"]=0
    convo=session["conversation"]

    if request.method=="POST":
        msg=request.form.get("message","").strip()
        if not msg: return render_template("index.html",conversation=convo)

        if is_pure_help_phrase(msg):
            if session.get("guided_topic")=="image_explain":
                reply = next_help_response("image_confused_count")
            else:
                reply = next_help_response("confused_count")
            convo.append({"role":"user","content":msg})
            convo.append({"role":"assistant","content":normalize_math_terms(reply)})
            session["conversation"]=convo
            return render_template("index.html",conversation=convo)

        session["confused_count"]=0
        session["image_confused_count"]=0

        reply = ask_anan(msg, mode="socratic")
        convo.append({"role":"user","content":msg})
        convo.append({"role":"assistant","content":reply})
        session["conversation"]=convo

        conn=get_conn()
        conn.execute("INSERT INTO records (user_id,question,topic,is_correct) VALUES (?,?,?,?)",
                     (session["user_id"],msg,session.get("guided_topic","一般"),None))
        conn.commit(); conn.close()

    return render_template("index.html",conversation=session["conversation"])

# -------------------------------
# 🧭 feedback 按鈕
# -------------------------------
TEACHER_HINT = "安安發現你還是有點困惑，這很正常喔。建議你把這題抄下來，明天上課時問老師，他一定會替你解釋得更仔細！"

def next_help_response(counter_name):
    c = session.get(counter_name, 0) + 1
    session[counter_name] = c
    if c == 1:
        return "沒關係，我再簡單講一次：找對公式→代入數字→計算→加單位。"
    elif c == 2:
        return "我們換個說法試試～你記得剛剛的公式是哪一個嗎？"
    elif c == 3:
        return ask_anan("請直接用最簡單方式重講上一題，清楚列出公式、代入與答案。", mode="normal")
    else:
        session[counter_name] = 3
        return TEACHER_HINT

@app.route("/feedback", methods=["POST"])
def feedback():
    d=request.get_json(); under=d.get("understood")
    if under is None: return jsonify({"status":"error"})
    if under:
        session["confused_count"]=0; session["image_confused_count"]=0
        return jsonify({"status":"ok","reply":"太棒了～安安替你開心 💪"})
    if session.get("guided_topic")=="image_explain":
        reply = next_help_response("image_confused_count")
    else:
        reply = next_help_response("confused_count")
    return jsonify({"status":"ok","reply":normalize_math_terms(reply)})

# -------------------------------
# 🗑️ clear
# -------------------------------
@app.route("/clear")
def clear():
    for k in ["conversation","confused_count","guided_topic","image_b64","image_confused_count"]:
        session.pop(k,None)
    return redirect("/")

# -------------------------------
# 🔐 /login /logout
# -------------------------------
@app.route("/login", methods=["GET","POST"])
def login():
    # 若已登入，直接回首頁
    if session.get("auth_user"):
        return redirect(url_for("home"))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        u = get_user(username)
        if not u:
            error = "帳號或密碼錯誤"
        elif not u["is_active"]:
            error = "此帳號已被停用"
        elif is_user_expired(u):
            error = "帳號已到期，請聯絡管理員"
        elif not check_password_hash(u["password_hash"], password):
            error = "帳號或密碼錯誤"
        else:
            session["auth_user"] = u["username"]
            return redirect(url_for("home"))

    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    for k in ["auth_user"]:
        session.pop(k, None)
    return redirect(url_for("login"))

# -------------------------------
# 🚀 run
# -------------------------------
if __name__=="__main__":
    port=int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0",port=port)
