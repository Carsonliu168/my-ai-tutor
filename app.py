# ================================
# AnAn Math Tutor - Main Application
# v5.0.12-bracket-check (Add bracket validation)
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
    print("Database ready (v5.0.12-bracket-check)")
init_db()

def solve_with_deepseek(prompt: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
        sys = """你是數學小老師「安安」。請用繁體中文、淺白易懂的方式一步步解題。

嚴格格式規則(必須100%遵守):
1. 數學公式只能使用 $公式$ (行內) 或 $$公式$$ (獨立行)
2. 嚴格禁止使用反斜線小括號或反斜線中括號的 LaTeX 格式
3. 嚴格禁止使用減號或星號開頭的列表,直接用數字或文字
4. 嚴格禁止使用兩個星號或底線包圍文字,直接用普通文字
5. 每個步驟之間空一行
6. 數學公式中的所有大括號必須成對出現

正確範例:
步驟一: 設未知數為 $x$
我們列出方程式 $2x + 3 = 7$
使用分數表示為 $\\frac{1}{2}$
解得 $x = 2$

請先引導思考過程,最後給出答案。"""
        
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
        sys = """你是數學小老師「安安」。請用繁體中文、淺白易懂的方式一步步解題。

嚴格格式規則(必須100%遵守):
1. 數學公式只能使用 $公式$ (行內) 或 $$公式$$ (獨立行)
2. 嚴格禁止使用反斜線小括號或反斜線中括號的 LaTeX 格式
3. 嚴格禁止使用減號或星號開頭的列表,直接用數字或文字
4. 嚴格禁止使用兩個星號或底線包圍文字,直接用普通文字
5. 每個步驟之間空一行
6. 數學公式中的所有大括號必須成對出現

正確範例:
步驟一: 設未知數為 $x$
我們列出方程式 $2x + 3 = 7$
使用分數表示為 $\\frac{1}{2}$
解得 $x = 2$

請先引導思考過程,最後給出答案。"""
        
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
        sys = """你是數學小老師「安安」。請用繁體中文、淺白易懂的方式一步步解題。

嚴格格式規則(必須100%遵守):
1. 數學公式只能使用 $公式$ (行內) 或 $$公式$$ (獨立行)
2. 嚴格禁止使用反斜線小括號或反斜線中括號的 LaTeX 格式
3. 嚴格禁止使用減號或星號開頭的列表,直接用數字或文字
4. 嚴格禁止使用兩個星號或底線包圍文字,直接用普通文字
5. 每個步驟之間空一行
6. 數學公式中的所有大括號必須成對出現

正確範例:
步驟一: 設未知數為 $x$
我們列出方程式 $2x + 3 = 7$
使用分數表示為 $\\frac{1}{2}$
解得 $x = 2$

請先引導思考過程,最後給出答案。"""
        
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
        return f"好的，我們來算：{a} × {b} = {result}\n\n是不是很簡單呢？ 😊"
    
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
    """Use Gemini for OCR (primary)"""
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
        
        prompt = """請用繁體中文辨識圖片中的數學題目，然後一步步解題。

嚴格格式規則(必須100%遵守):
1. 數學公式只能使用 $公式$ (行內) 或 $$公式$$ (獨立行)
2. 嚴格禁止使用反斜線小括號或反斜線中括號的 LaTeX 格式
3. 嚴格禁止使用減號或星號開頭的列表
4. 嚴格禁止使用兩個星號粗體語法
5. 每個步驟之間空一行
6. 數學公式中的所有大括號必須成對出現"""
        
        rsp = model.generate_content([prompt, image])
        print("Using Gemini OCR")
        return rsp.text.strip()
        
    except Exception as e:
        print(f"Gemini OCR error: {e}")
        return None

def ocr_with_openai(file_storage) -> str:
    """Use OpenAI Vision for OCR (backup)"""
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        import base64
        
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        image_data = file_storage.read()
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        prompt = """請用繁體中文辨識圖片中的數學題目，然後一步步解題。

嚴格格式規則(必須100%遵守):
1. 數學公式只能使用 $公式$ (行內) 或 $$公式$$ (獨立行)
2. 嚴格禁止使用反斜線小括號或反斜線中括號的 LaTeX 格式
3. 嚴格禁止使用減號或星號開頭的列表
4. 嚴格禁止使用兩個星號粗體語法
5. 每個步驟之間空一行
6. 數學公式中的所有大括號必須成對出現"""
        
        response = client.chat.completions.create(
            model="gpt-4o",
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
        
        print("Using OpenAI Vision OCR (backup)")
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
    return jsonify({"status": "ok", "version": "v5.0.12-bracket-check"})

@app.route('/smoke')
def smoke():
    return "AnAn Flask app is alive", 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)