# ================================
# AnAn Math Tutor - Main Application
# v5.0.5-stable (Traditional Chinese output)
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, base64, requests, sqlite3, uuid, re, bcrypt
from datetime import datetime, timedelta

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

def initialize_admin_user():
    db_path = os.path.join("data", "anan.db")
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]

    if "username" not in columns or "password" not in columns or "role" not in columns:
        print("Fixing users table structure...")
        try:
            cur.execute("ALTER TABLE users RENAME TO users_old;")
        except:
            pass

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                password TEXT,
                role TEXT,
                profile_type TEXT
            )
        """)

        try:
            cur.execute("INSERT INTO users (username, role) SELECT username, role FROM users_old;")
            cur.execute("DROP TABLE users_old;")
            print("Old user data preserved.")
        except Exception as e:
            print(f"Cannot preserve old data: {e}")
            cur.execute("DROP TABLE IF EXISTS users_old;")

        conn.commit()
        print("Users table structure fixed.")

    cur.execute("SELECT 1 FROM users WHERE username='anan_admin'")
    if not cur.fetchone():
        hashed_pw = bcrypt.hashpw("1234".encode("utf-8"), bcrypt.gensalt())
        cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                    ('anan_admin', hashed_pw, 'admin'))
        conn.commit()
        print("Admin account created: anan_admin / 1234")
    else:
        print("Admin account exists.")

    conn.close()

initialize_admin_user()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

session_lifetime_days = int(os.getenv("SESSION_LIFETIME_DAYS", "30"))
app.permanent_session_lifetime = timedelta(days=session_lifetime_days)
DEMO_MODE = os.getenv("DEMO_MODE", "False").lower() == "true"

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
    print("Database ready (v5.0.5-stable)")
init_db()

def solve_with_deepseek(prompt: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
        sys = "你是小學數學家教「安安」。請用繁體中文、淺白易懂的方式一步步解題，必要時用 Latex 數學公式（$...$ 或 $$...$$）。先引導思考過程，最後給出答案。"
        rsp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role":"system","content":sys},
                      {"role":"user","content":prompt}],
            temperature=0.2
        )
        return rsp.choices[0].message.content.strip()
    except Exception as e:
        print(f"DeepSeek error: {e}")
        return None

def solve_with_openai(prompt: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        sys = "你是小學數學家教「安安」。請用繁體中文、淺白易懂的方式一步步解題，必要時用 Latex 數學公式（$...$ 或 $$...$$）。先引導思考過程，最後給出答案。"
        rsp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role":"system","content":sys},
                      {"role":"user","content":prompt}],
            temperature=0.2
        )
        return rsp.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI error: {e}")
        return None

def solve_with_gemini(prompt: str) -> str:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL","gemini-1.5-flash"))
        sys = "你是小學數學家教「安安」。請用繁體中文、淺白易懂的方式一步步解題，必要時用 Latex 數學公式（$...$ 或 $$...$$）。先引導思考過程，最後給出答案。"
        rsp = model.generate_content([sys, prompt])
        return rsp.text.strip()
    except Exception as e:
        print(f"Gemini error: {e}")
        return None

def solve_math(prompt: str) -> str:
    m = re.match(r'^\s*(\d+)\s*[×x*]\s*(\d+)\s*=?\s*$', prompt, re.IGNORECASE)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        result = a * b
        return f"好的，我們來算：{a} × {b} = **{result}**\n\n是不是很簡單呢？ 😊"
    
    if DEEPSEEK_API_KEY:
        ans = solve_with_deepseek(prompt)
        if ans:
            print("Using DeepSeek")
            return ans
    
    if OPENAI_API_KEY:
        ans = solve_with_openai(prompt)
        if ans:
            print("Using OpenAI (DeepSeek backup)")
            return ans
    
    if GOOGLE_API_KEY:
        ans = solve_with_gemini(prompt)
        if ans:
            print("Using Gemini (last backup)")
            return ans
    
    return "抱歉，所有 AI 服務暫時不可用，請稍後再試。"

def ocr_with_gemini(file_storage) -> str:
    if not GOOGLE_API_KEY:
        return None
    try:
        import google.generativeai as genai
        from PIL import Image
        import io
        
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        image_data = file_storage.read()
        image = Image.open(io.BytesIO(image_data))
        
        prompt = "請用繁體中文回答。先做 OCR 辨識題目文字，再用國小到國中程度一步步詳細講解解法，最後給出完整答案（若有單位請標示）。數學公式請用 Latex 格式（例如 $x^2$ 或 $$...$$）。"
        
        rsp = model.generate_content([prompt, image])
        print("Using Gemini OCR")
        return rsp.text.strip()
        
    except Exception as e:
        print(f"Gemini OCR error: {e}")
        return None

def ocr_with_openai(file_storage) -> str:
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        import base64
        
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        image_data = file_storage.read()
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        prompt = "請用繁體中文回答。先做 OCR 辨識題目文字，再用國小到國中程度一步步詳細講解解法，最後給出完整答案（若有單位請標示）。數學公式請用 Latex 格式（例如 $x^2$ 或 $$...$$）。"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1500
        )
        
        print("Using OpenAI Vision OCR (Gemini backup)")
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"OpenAI Vision OCR error: {e}")
        return None

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
            print(f"User {username} logged in")
            return redirect(url_for('main'))
        else:
            return render_template('login.html', error="Invalid username or password")

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
    payload = request.json or {}
    user_msg = payload.get("message") or request.form.get("message") or ""
    user_msg = user_msg.strip()
    if not user_msg:
        return jsonify({"reply": "請輸入題目或問題喔～"}), 200

    reply = solve_math(user_msg)

    try:
        conn = sqlite3.connect("data/anan.db")
        c = conn.cursor()
        c.execute("INSERT INTO records (user, question, answer, timestamp) VALUES (?, ?, ?, ?)",
                  (session.get('user','unknown'), user_msg, reply, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Record save failed:", e)

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
    
    if not reply:
        file.seek(0)
        reply = ocr_with_openai(file)
    
    if not reply:
        reply = "抱歉，圖片辨識服務暫時不可用，請稍後再試。"
    
    return jsonify({"reply": reply}), 200

@app.route('/clear')
def clear():
    try:
        conn = sqlite3.connect("data/anan.db")
        c = conn.cursor()
        c.execute("DELETE FROM records WHERE user=?", (session.get('user','unknown'),))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Clear records failed:", e)
    return redirect(url_for('main'))

@app.route('/health')
def health():
    return jsonify({"status": "ok", "version": "v5.0.5-stable"})

@app.route('/smoke')
def smoke():
    return "AnAn Flask app is alive", 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)