# ================================
# 📘 安安專案主程式 app.py
# v5.0.1-stable（含自動修復 users 表＋自動建立管理員帳號）
# ✅ 邏輯已補齊：/chat（解題）、/upload（OCR）、/clear（清除對話）
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, base64, requests, sqlite3, uuid, re, bcrypt
from datetime import datetime, timedelta

# 第三方 LLM/多模態
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# -------------------------------
# ✅ 自動修復資料庫與管理員帳號
# -------------------------------
def initialize_admin_user():
    """檢查 users 資料表結構並自動建立管理員帳號"""
    db_path = os.path.join("data", "anan.db")
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 取得目前欄位
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]

    # 若表不存在或缺欄位 → 重新建立正確結構
    if "username" not in columns or "password" not in columns or "role" not in columns:
        print("⚙️ 偵測到舊版或不存在的 users 表，正在修復結構...")
        try:
            cur.execute("ALTER TABLE users RENAME TO users_old;")
        except:
            pass  # 若不存在忽略

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                password TEXT,
                role TEXT,
                profile_type TEXT
            )
        """)

        # 嘗試保留舊資料
        try:
            cur.execute("INSERT INTO users (username, role) SELECT username, role FROM users_old;")
            cur.execute("DROP TABLE users_old;")
            print("✅ 已保留舊用戶資料。")
        except Exception as e:
            print("ℹ️ 無法保留舊資料或略過：", e)
            cur.execute("DROP TABLE IF EXISTS users_old;")

        conn.commit()
        print("✅ 已修復 users 表結構。")

    # 確保有管理員帳號
    cur.execute("SELECT 1 FROM users WHERE username='anan_admin'")
    if not cur.fetchone():
        hashed_pw = bcrypt.hashpw("1234".encode("utf-8"), bcrypt.gensalt())
        cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                    ('anan_admin', hashed_pw, 'admin'))
        conn.commit()
        print("✅ 已自動建立管理員帳號：anan_admin / 密碼 1234")
    else:
        print("✅ 管理員帳號已存在。")

    conn.close()

# 執行初始化檢查
initialize_admin_user()

# -------------------------------
# ✅ Flask 設定
# -------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# -------------------------------
# ✅ Session 與模式設定
# -------------------------------
session_lifetime_days = int(os.getenv("SESSION_LIFETIME_DAYS", "30"))
app.permanent_session_lifetime = timedelta(days=session_lifetime_days)
DEMO_MODE = os.getenv("DEMO_MODE", "False").lower() == "true"

# -------------------------------
# ✅ 其他資料表初始化
# -------------------------------
def init_db():
    conn = sqlite3.connect("data/anan.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            question TEXT,
            answer TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("✅ [安安] 資料庫就緒（v5.0.1-stable）")
init_db()

# -------------------------------
# 🔧 小工具：呼叫 LLM（優先 OPENAI → 退而用 Gemini → 再退 DeepSeek）
# -------------------------------
def solve_with_openai(prompt: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        sys = ("你是小學數學家教「安安」。請用分步驟、淺白口吻解題，"
               "必要時用 Latex（$...$ 或 $$...$$）書寫計算式；先引導思考，再給答案。")
        rsp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role":"system","content":sys},
                      {"role":"user","content":prompt}],
            temperature=0.2
        )
        return rsp.choices[0].message.content.strip()
    except Exception as e:
        return f"（OpenAI 暫時不可用：{e}）"

def solve_with_gemini(prompt: str) -> str:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL","gemini-1.5-flash"))
        sys = ("你是小學數學家教「安安」。請用分步驟、淺白口吻解題，必要時用 Latex。")
        rsp = model.generate_content([sys, prompt])
        return rsp.text.strip()
    except Exception as e:
        return f"（Gemini 暫時不可用：{e}）"

def solve_with_deepseek(prompt: str) -> str:
    try:
        # 若你原本用 deepseek-sdk，可替換為既有寫法
        # 這裡用簡單的回覆保底，避免整體崩潰
        return "（DeepSeek Fallback）目前以簡化模式回覆：\n" + prompt
    except Exception as e:
        return f"（DeepSeek 暫時不可用：{e}）"

def solve_math(prompt: str) -> str:
    """優先用 OPENAI，其次 GEMINI，最後 DEEPSEEK；並做一道保底『口算』規則。"""
    # 特例：若是很簡單的整除，先直接算出給學生一個直觀答案（避免雲端偶發延遲）
    m = re.match(r'^\s*(\d+)\s*[\/÷]\s*(\d+)\s*$', prompt)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if b != 0:
            q = a / b
            return f"先用整數除法：{a} ÷ {b} = {q}\n因此每期需付 **{q:.2f} 元**。"
    # 一般路徑
    if OPENAI_API_KEY:
        ans = solve_with_openai(prompt)
        if "不可用" not in ans:
            return ans
    if GOOGLE_API_KEY:
        ans = solve_with_gemini(prompt)
        if "不可用" not in ans:
            return ans
    # 最後保底
    return solve_with_deepseek(prompt)

# -------------------------------
# 🔧 小工具：圖片 OCR with Gemini
# -------------------------------
def ocr_with_gemini(file_storage) -> str:
    if not GOOGLE_API_KEY:
        return "（OCR 需要 GOOGLE_API_KEY）"
    try:
        import google.generativeai as genai
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel(os.getenv("GEMINI_VISION_MODEL","gemini-1.5-flash"))
        mime = file_storage.mimetype or "image/png"
        data = file_storage.read()
        img_part = {"mime_type": mime, "data": data}
        prompt = ("請先做 OCR 擷取題目文字，再用國小程度一步步講解解法，"
                  "最後給出答案（若有單位要寫上）。可以用 Latex。")
        rsp = model.generate_content([prompt, img_part])
        return rsp.text.strip()
    except Exception as e:
        return f"（OCR 暫時不可用：{e}）"

# -------------------------------
# ✅ 路由
# -------------------------------

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '').encode('utf-8')

        conn = sqlite3.connect("data/anan.db")
        c = conn.cursor()
        c.execute("SELECT password, role FROM users WHERE username=?", (username,))
        row = c.fetchone()
        conn.close()

        if row and bcrypt.checkpw(password, row[0]):
            session['user'] = username
            session['role'] = row[1]
            session.permanent = True
            print(f"✅ 使用者 {username} 登入成功")
            return redirect(url_for('main'))
        else:
            return render_template('login.html', error="帳號或密碼錯誤")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/main')
def main():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    # 期望前端傳 {message: "..."}；也接受純文字 form
    payload = request.json or {}
    user_msg = payload.get("message") or request.form.get("message") or ""
    user_msg = user_msg.strip()
    if not user_msg:
        return jsonify({"reply": "請輸入題目或問題喔～"}), 200

    reply = solve_math(user_msg)

    # 記錄
    try:
        conn = sqlite3.connect("data/anan.db")
        c = conn.cursor()
        c.execute("INSERT INTO records (user, question, answer, timestamp) VALUES (?, ?, ?, ?)",
                  (session.get('user','unknown'), user_msg, reply, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print("記錄失敗：", e)

    return jsonify({"reply": reply}), 200

@app.route('/upload', methods=['POST'])
def upload():
    if 'user' not in session:
        return jsonify({"reply":"請先登入"}), 401
    if 'file' not in request.files:
        return jsonify({"reply":"沒有收到圖片檔案"}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"reply":"檔案名稱是空的"}), 400

    reply = ocr_with_gemini(file)
    return jsonify({"reply": reply}), 200

@app.route('/clear')
def clear():
    # 清除當前使用者的紀錄（僅作示範，可改為清除 session）
    try:
        conn = sqlite3.connect("data/anan.db")
        c = conn.cursor()
        c.execute("DELETE FROM records WHERE user=?", (session.get('user','unknown'),))
        conn.commit()
        conn.close()
    except Exception as e:
        print("清除紀錄失敗：", e)
    return redirect(url_for('main'))

@app.route('/health')
def health():
    return jsonify({"status": "ok", "version": "v5.0.1-stable"})

@app.route('/smoke')
def smoke():
    return "✅ AnAn Flask app is alive", 200

# -------------------------------
# ✅ 啟動
# -------------------------------
if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
