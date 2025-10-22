# ================================
# 📘 安安專案主程式 app.py
# v5.0.1-stable（含自動修復 users 表＋自動建立管理員帳號）
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, base64, requests, sqlite3, uuid, re, bcrypt
from datetime import datetime, timedelta

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
    cur.execute("SELECT * FROM users WHERE username='anan_admin'")
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
# ✅ API 金鑰檢查與初始化
# -------------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

print("🔍 環境變數檢查：")
print("✅ DEEPSEEK_API_KEY" if DEEPSEEK_API_KEY else "❌ DEEPSEEK_API_KEY 缺失")
print("✅ OPENAI_API_KEY" if OPENAI_API_KEY else "❌ OPENAI_API_KEY 缺失")
print("✅ GOOGLE_API_KEY" if GOOGLE_API_KEY else "❌ GOOGLE_API_KEY 缺失")

# -------------------------------
# ✅ 資料庫初始化
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
# ✅ 路由區
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
