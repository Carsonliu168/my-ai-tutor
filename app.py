# ================================
# 📘 數學小老師安安主程式 app.py
# v4.9.10 Debug 版 (加入串流 debug + 優化 Prompt)
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for, Response, stream_with_context
import os, json, base64, requests, sqlite3, uuid, re, random, bcrypt
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# ===== API Keys =====
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
openai_api_key   = os.getenv("OPENAI_API_KEY", "")
gemini_api_key   = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")

# ===== DB =====
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
        profile_type TEXT,
        created_at TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS records(
        id TEXT PRIMARY KEY,
        user TEXT,
        question TEXT,
        answer TEXT,
        correct INTEGER,
        created_at TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

# ===== 密碼雜湊 / 驗證 =====
def hash_password(plain: str) -> bytes:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())

def check_password(plain: str, hashed: bytes | str) -> bool:
    if isinstance(hashed, str):
        hashed = hashed.encode("utf-8")
    return bcrypt.checkpw(plain.encode("utf-8"), hashed)

# ===== 內建預設帳號 =====
ADMIN_USER = os.getenv("ADMIN_USER", "anan_admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "1234")
DEMO_USER  = os.getenv("DEMO_USER", "demo_user")
DEMO_PASS  = os.getenv("DEMO_PASS", "demo123")

def seed_accounts():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing = {row[0] for row in c.execute("SELECT username FROM users").fetchall()}
    if ADMIN_USER not in existing:
        hashed = hash_password(ADMIN_PASS).decode("utf-8")
        c.execute(
            "INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, datetime('now'))",
            (ADMIN_USER, hashed, "admin")
        )
        print(f"✅ 已建立管理員帳號：{ADMIN_USER} / 密碼已隱藏")
    if DEMO_USER not in existing:
        hashed = hash_password(DEMO_PASS).decode("utf-8")
        c.execute(
            "INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, datetime('now'))",
            (DEMO_USER, hashed, "student")
        )
        print(f"✅ 已建立示範帳號：{DEMO_USER} / 密碼已隱藏")
    conn.commit(); conn.close()

seed_accounts()
print("✅ [安安] 資料庫就緒（v4.9.12 強制分段版 - 後端自動加換行）")

# ===== 🆕 自動分段函數 =====
def auto_add_paragraphs(text: str) -> str:
    """
    在適當位置自動插入換行，讓回答更易讀
    """
    if not text: return text
    
    # 🆕 在 emoji 後面加空格（如果後面緊接著中文或英文）
    text = re.sub(r'([\U0001F300-\U0001F9FF])([^\s\n])', r'\1 \2', text)
    
    # 在中文句號、驚嘆號、問號後面加換行（如果後面還有內容且不是換行）
    text = re.sub(r'([。！？])([^。！？\n\s])', r'\1\n\n\2', text)
    
    # 在冒號後面加換行（定義、說明類）- 但要確保後面有實質內容
    text = re.sub(r'(：)([^\n\s])', r'\1\n\n\2', text)
    
    # 🆕 在列表項目前加換行（如果前面不是換行）
    text = re.sub(r'([^\n])(-\s+[^\n])', r'\1\n\2', text)
    
    # 在「---」分隔線前後加換行
    text = re.sub(r'([^\n])(---)', r'\1\n\n\2', text)
    text = re.sub(r'(---)([^\n])', r'\1\n\n\2', text)
    
    # 移除多餘的連續換行（超過2個）
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

# ===== 🔧 優化版數學符號處理 =====
def normalize_math_terms(text: str) -> str:
    """
    智慧處理數學符號，移除所有 LaTeX 語法
    """
    if not text: return text
    
    # 🔧 第一步：移除 LaTeX 數學模式 $$...$$ 和 $...$
    text = re.sub(r'\$\$(.+?)\$\$', r'\1', text)  # 移除 $$...$$
    text = re.sub(r'\$([^\$]+)\$', r'\1', text)  # 移除 $...$（任何內容）
    
    # 🔧 第二步：移除所有剩餘的單獨 $ 符號（包括 $2$ 這種）
    text = re.sub(r'\$+', '', text)  # 移除所有剩餘的 $
    
    # 移除其他 LaTeX 語法
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)  # 移除 \command{...}
    text = re.sub(r'\\[a-zA-Z]+', '', text)  # 移除 \command
    
    # 移除 Markdown 標題符號
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    
    # 數學符號標準化（保持不變）
    text = text.replace("π", "3.1416")
    text = re.sub(r"(\d+)\s*cm²", r"\1 平方公分", text)
    
    # 移除多餘空格
    text = re.sub(r'[ \t]+', ' ', text)
    
    return text.strip()

# ===== 文字格式化 =====
def format_ai_reply(text: str) -> str:
    """
    將 AI 回覆格式化為 HTML（轉換換行為 <br>）
    """
    if not text: return text
    
    # 🔧 保留列表符號，不要移除（讓學生看到完整格式）
    # 只移除行首多餘的空白
    text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)
    
    # 轉換換行為 HTML
    text = text.replace('\n\n', '<br><br>').replace('\n', '<br>')
    
    return text.strip()

# ===== System Prompt 建構 =====
def build_system_prompt(style: str, profile_type=None) -> str:
    base_prompt = f"""你是「數學小老師安安」，用繁體中文與學生互動教學。

⚠️ 超級重要：回答時每個段落之間必須空一行！
請按照這個格式回答：

公式說明

生活例子

計算步驟

答案

教學原則：
- 溫柔、親切、鼓勵、活潑
- {style}
- 多用台灣生活例子（珍奶、雞排等）
- 直接回答問題，不要過度延伸
- 禁止開場寒暄或自我介紹
- 禁止主動出題

數學符號規範：
- 使用 ×（乘）、÷（除）、=（等於）
- 禁止使用 $、LaTeX 語法
- 每個計算步驟要換行

範例格式：
問：三角形面積？
答：
公式是：底×高÷2

舉例：雞排底10公分、高8公分

計算：
10×8=80
80÷2=40

答案是40平方公分！
"""

    # ===== 根據學習風格添加專屬指示 =====
    if profile_type == "邏輯戰略家":
        base_prompt += "\n特殊要求：極簡風格、不用 emoji、直接給公式和步驟。"
    elif profile_type == "創意視覺家":
        base_prompt += "\n特殊要求：多用 emoji 和生動比喻、讓學生有畫面。"
    elif profile_type == "平衡大師":
        base_prompt += "\n特殊要求：結構化呈現、清楚但不冗長。"
    
    return base_prompt

# ===== 🆕 串流版本：ask_anan_stream =====
def ask_anan_stream(question: str, mode="socratic", profile_type=None, history=None):
    """
    Generator 函數，逐字 yield AI 回應
    """
    if len((question or "").strip()) < 5:
        mode = "direct"
    
    style = (
        "採用蘇格拉底式提問法，引導學生一步步思考。"
        if mode == "socratic"
        else "請用清楚步驟直接講解完整解法，包含公式、代入、計算與答案。"
    )
    system_prompt = build_system_prompt(style, profile_type)

    # 建構完整對話記錄
    messages = [{"role": "system", "content": system_prompt}]
    
    if history and isinstance(history, list):
        messages.extend(history)
    
    messages.append({"role": "user", "content": question})

    # 🆕 DeepSeek 串流模式
    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": 0.2,
            "stream": True
        }
        
        response = requests.post(
            "https://api.deepseek.com/chat/completions", 
            headers=headers, 
            json=payload, 
            stream=True,
            timeout=60
        )
        
        if response.status_code == 200:
            full_content = ""
            for line in response.iter_lines():
                if line:
                    line_text = line.decode('utf-8')
                    if line_text.startswith('data: '):
                        data_str = line_text[6:]
                        
                        if data_str == '[DONE]':
                            break
                        
                        try:
                            data = json.loads(data_str)
                            delta = data.get('choices', [{}])[0].get('delta', {})
                            content = delta.get('content', '')
                            
                            if content:
                                full_content += content
                                # 🔍 Debug：印出每個片段（可以看到 \n）
                                print(f"📤 Chunk: {repr(content)}")
                                
                                # 🆕 強制分段：在特定標點符號後加換行
                                processed_content = normalize_math_terms(content)
                                
                                # 如果內容包含這些標點符號，後面加上換行
                                if any(punct in processed_content for punct in ['：', '！', '？']):
                                    # 在標點符號後面加 \n\n（但不要重複加）
                                    if not processed_content.endswith('\n'):
                                        processed_content += '\n\n'
                                
                                yield processed_content
                        except json.JSONDecodeError:
                            continue
            
            # 🆕 回傳完整內容（加入自動分段）
            # 注意：這個 return 值在 generator 中不會被直接使用
            # 但我們保留它以便在需要時可以取得完整內容
            print(f"✅ 串流完成，總長度: {len(full_content)} 字元")
            return auto_add_paragraphs(normalize_math_terms(full_content))
        else:
            raise Exception(f"DeepSeek API 錯誤: {response.status_code}")
            
    except Exception as e:
        print(f"DeepSeek 串流失敗: {e}")
        
        # OpenAI 備援
        try:
            if not openai_api_key:
                raise RuntimeError("未設定 OPENAI_API_KEY")
            
            headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-4o-mini",
                "messages": messages,
                "temperature": 0.2,
                "stream": True
            }
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=60
            )
            
            if response.status_code == 200:
                full_content = ""
                for line in response.iter_lines():
                    if line:
                        line_text = line.decode('utf-8')
                        if line_text.startswith('data: '):
                            data_str = line_text[6:]
                            
                            if data_str == '[DONE]':
                                break
                            
                            try:
                                data = json.loads(data_str)
                                delta = data.get('choices', [{}])[0].get('delta', {})
                                content = delta.get('content', '')
                                
                                if content:
                                    full_content += content
                                    # 🔍 Debug：印出每個片段
                                    print(f"📤 Chunk (OpenAI): {repr(content)}")
                                    
                                    # 🆕 強制分段：在特定標點符號後加換行
                                    processed_content = normalize_math_terms(content)
                                    
                                    # 如果內容包含這些標點符號，後面加上換行
                                    if any(punct in processed_content for punct in ['：', '！', '？']):
                                        # 在標點符號後面加 \n\n（但不要重複加）
                                        if not processed_content.endswith('\n'):
                                            processed_content += '\n\n'
                                    
                                    yield processed_content
                            except json.JSONDecodeError:
                                continue
                
                print(f"✅ OpenAI 串流完成，總長度: {len(full_content)} 字元")
                return auto_add_paragraphs(normalize_math_terms(full_content))
            else:
                raise Exception(f"OpenAI API 錯誤: {response.status_code}")
                
        except Exception as e2:
            print(f"OpenAI 備援失敗: {e2}")
            yield "[ERROR]安安暫時無法回應，請稍後再試。"
            return ""

# ===== 非串流版本：ask_anan (保留作為備援) =====
def ask_anan(question: str, mode="socratic", profile_type=None, history=None) -> str:
    """
    傳統版本，用於圖片辨識等不需串流的場景
    """
    if len((question or "").strip()) < 5:
        mode = "direct"
    
    style = (
        "採用蘇格拉底式提問法，引導學生一步步思考。"
        if mode == "socratic"
        else "請用清楚步驟直接講解完整解法，包含公式、代入、計算與答案。"
    )
    system_prompt = build_system_prompt(style, profile_type)

    messages = [{"role": "system", "content": system_prompt}]
    
    if history and isinstance(history, list):
        messages.extend(history)
    
    messages.append({"role": "user", "content": question})

    # DeepSeek 主模型
    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": 0.2,
        }
        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=40)
        reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if reply:
            # 🆕 加入自動分段處理
            reply = auto_add_paragraphs(normalize_math_terms(reply))
            return reply
    except Exception as e:
        print("DeepSeek 失敗:", e)

    # OpenAI 備援
    try:
        if not openai_api_key:
            raise RuntimeError("未設定 OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
        payload2 = {
            "model": "gpt-4o-mini",
            "messages": messages,
            "temperature": 0.2,
        }
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload2, timeout=40)
        reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if reply:
            # 🆕 加入自動分段處理
            reply = auto_add_paragraphs(normalize_math_terms(reply))
            return reply
    except Exception as e:
        print("OpenAI 備援失敗:", e)

    return "（安安暫時沒回應，請稍後再試一次）"

# ===== 登入 / 登出 =====
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
            return render_template("login.html", error="帳號或密碼錯誤。")

        stored_pw, role = row[0], (row[1] or "student")
        ok = False
        try:
            ok = check_password(password, stored_pw)
        except Exception:
            ok = False
        if not ok and len(stored_pw) < 60:
            if password == stored_pw:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                new_hash = hash_password(password).decode("utf-8")
                c.execute("UPDATE users SET password=? WHERE username=?", (new_hash, username))
                conn.commit(); conn.close()
                ok = True

        if ok:
            session["user"] = username
            session["role"] = role
            session["confusion_count"] = 0
            session["chat_history"] = []
            
            if username == DEMO_USER:
                conn2 = sqlite3.connect(DB_PATH)
                c2 = conn2.cursor()
                c2.execute("UPDATE users SET profile_type=NULL WHERE username=?", (username,))
                conn2.commit()
                conn2.close()
                print(f"✅ {username} 登入時已自動清空問卷記錄")
            
            return redirect(url_for("home"))
        else:
            return render_template("login.html", error="帳號或密碼錯誤。")
    return render_template("login.html")

@app.route("/logout")
def logout():
    username = session.get("user")
    if username == DEMO_USER:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET profile_type=NULL WHERE username=?", (username,))
        conn.commit()
        conn.close()
        print(f"✅ 已清空 {username} 的問卷記錄")
    
    session.clear()
    return redirect("/login")

# ===== 問卷相關路由 =====
@app.route("/questionnaire")
def questionnaire():
    if "user" not in session:
        return redirect("/login")
    return render_template("questionnaire.html")

@app.route("/submit_questionnaire", methods=["POST"])
def submit_questionnaire():
    if "user" not in session:
        return jsonify({"success": False, "error": "未登入"})
    
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
    
    username = session.get("user")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET profile_type=? WHERE username=?", (profile_type, username))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "result": profile_type})

@app.route("/questionnaire_result")
def questionnaire_result():
    if "user" not in session:
        return redirect("/login")
    
    result = request.args.get("result", "未知類型")
    descriptions = {
        "邏輯戰略家": "你擅長以條理與策略解決問題，喜歡從全局推理出答案，是理性與分析的高手。",
        "創意視覺家": "你具有豐富的想像力與整體感知力，習慣用圖像、感覺和關聯去理解知識。",
        "平衡大師": "你能靈活切換邏輯與直覺的思維，能在不同學習情境中找到最適合的方式。"
    }
    description = descriptions.get(result, "每個人都有不同的思考方式，這是你獨特的優勢！")
    username = session.get("user", "未知使用者")
    role = session.get("role", "student")
    
    return render_template("questionnaire_result.html", 
                         username=username, 
                         role=role,
                         result=result, 
                         description=description)

@app.route("/reset_questionnaire")
def reset_questionnaire():
    if "user" not in session:
        return redirect("/login")
    
    username = session.get("user")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET profile_type=NULL WHERE username=?", (username,))
    conn.commit()
    conn.close()
    
    return redirect("/questionnaire")

# ===== 🔧 串流路由 =====
@app.route("/stream")
def stream_chat():
    """
    SSE 串流端點
    """
    if "user" not in session:
        def error_stream():
            yield "data: [ERROR]請先登入\n\n"
        return Response(error_stream(), mimetype='text/event-stream')
    
    message = request.args.get("message", "").strip()
    if not message:
        def error_stream():
            yield "data: [ERROR]訊息不能為空\n\n"
        return Response(error_stream(), mimetype='text/event-stream')
    
    # 確保 chat_history 存在
    if "chat_history" not in session:
        session["chat_history"] = []
    
    # 讀取學生風格
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    row = c.execute("SELECT profile_type FROM users WHERE username=?", (session["user"],)).fetchone()
    conn.close()
    profile_type = row[0] if row else None
    
    print(f"🎯 學生風格：{profile_type}")
    print(f"💬 串流訊息：{message[:50]}...")
    
    # 處理「懂了」→ 清空記憶
    if "懂了" in message or "明白" in message or "了解" in message:
        session["confusion_count"] = 0
        session["chat_history"] = []
        session.pop("current_problem", None)
        
        reply = random.choice([
            "太棒了！你真的很努力 👍 還有其他數學問題想問我嗎？",
            "安安老師為你鼓掌 👏 有新的題目要挑戰嗎？",
            "很好～你已經掌握這個觀念了！繼續加油 💪",
            "非常好！有其他問題隨時可以問我喔～"
        ])
        
        def simple_stream():
            yield f"data: {reply}\n\n"
            yield "data: [DONE]\n\n"
        
        return Response(stream_with_context(simple_stream()), mimetype='text/event-stream')
    
    # 處理「不懂」→ 使用對話記憶
    if "不懂" in message:
        confusion_count = session.get("confusion_count", 0)
        current_problem = session.get("current_problem", "")
        
        print(f"📝 current_problem: {current_problem}")
        print(f"🔢 confusion_count: {confusion_count}")
        
        if current_problem:
            confusion_count += 1
            session["confusion_count"] = confusion_count
            
            if confusion_count == 1:
                followup = f"學生說他不太懂這個問題：「{current_problem}」，請換個角度、舉例或更簡單的方式再教一次。"
            elif confusion_count == 2:
                followup = f"學生第二次說他還是不懂這個問題：「{current_problem}」，請再用不同方式簡短解釋，語氣更鼓勵。"
            else:
                reply = "沒關係～學習本來就是一步步來！這題你可以先記下來，明天拿去問老師，安安為你加油 💪"
                
                def simple_stream():
                    yield f"data: {reply}\n\n"
                    yield "data: [DONE]\n\n"
                
                return Response(stream_with_context(simple_stream()), mimetype='text/event-stream')
            
            # 用串流回應
            def generate():
                full_reply = ""
                try:
                    for chunk in ask_anan_stream(followup, mode="direct", 
                                                 profile_type=profile_type, 
                                                 history=session["chat_history"]):
                        if chunk.startswith("[ERROR]"):
                            yield f"data: {chunk}\n\n"
                            yield "data: [DONE]\n\n"
                            return
                        
                        full_reply += chunk
                        yield f"data: {chunk}\n\n"
                    
                    # 記錄對話
                    session["chat_history"].append({"role": "user", "content": followup})
                    session["chat_history"].append({"role": "assistant", "content": full_reply})
                    
                    if len(session["chat_history"]) > 20:
                        session["chat_history"] = session["chat_history"][-20:]
                    
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    print(f"串流錯誤: {e}")
                    yield f"data: [ERROR]發生錯誤: {str(e)}\n\n"
                    yield "data: [DONE]\n\n"
            
            return Response(stream_with_context(generate()), mimetype='text/event-stream')
        else:
            reply = "沒問題，我們可以換一題或再問別的問題喔～"
            
            def simple_stream():
                yield f"data: {reply}\n\n"
                yield "data: [DONE]\n\n"
            
            return Response(stream_with_context(simple_stream()), mimetype='text/event-stream')
    
    # 🔧 一般問題 - 在 generator 之前設定 session
    session["current_problem"] = message
    session["confusion_count"] = 0
    print(f"✅ 已設定 current_problem: {message[:50]}...")
    
    # 一般問題 → 串流回應
    def generate():
        full_reply = ""
        try:
            for chunk in ask_anan_stream(message, mode="socratic", 
                                        profile_type=profile_type, 
                                        history=session["chat_history"]):
                if chunk.startswith("[ERROR]"):
                    yield f"data: {chunk}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                
                full_reply += chunk
                yield f"data: {chunk}\n\n"
            
            # 記錄對話
            session["chat_history"].append({"role": "user", "content": message})
            session["chat_history"].append({"role": "assistant", "content": full_reply})
            
            if len(session["chat_history"]) > 20:
                session["chat_history"] = session["chat_history"][-20:]
            
            # 記錄到資料庫
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                "INSERT INTO records (id,user,question,answer,correct,created_at) VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), session["user"], message, full_reply, 1, datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
            
            yield "data: [DONE]\n\n"
        except Exception as e:
            print(f"串流錯誤: {e}")
            yield f"data: [ERROR]發生錯誤: {str(e)}\n\n"
            yield "data: [DONE]\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

# ===== 傳統路由（保留備援，主要用於圖片）=====
@app.route("/", methods=["GET", "POST"])
def home():
    if "user" not in session:
        return redirect("/login")
    
    if request.method == "GET":
        role = session.get("role")
        if role != "admin":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            row = c.execute("SELECT profile_type FROM users WHERE username=?", 
                          (session["user"],)).fetchone()
            conn.close()
            if not row or not row[0]:
                return redirect("/questionnaire")
        
        return render_template("index.html", username=session.get("user"), role=session.get("role"))

    # POST 請求（備援，但前端已改用 /stream）
    if "chat_history" not in session:
        session["chat_history"] = []
    
    msg = (request.form.get("message") or "").strip()
    confusion_count = session.get("confusion_count", 0)

    # 讀取學生風格
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    row = c.execute("SELECT profile_type FROM users WHERE username=?", (session["user"],)).fetchone()
    conn.close()
    profile_type = row[0] if row else None

    # 處理「懂了」
    if "懂了" in msg or "明白" in msg or "了解" in msg:
        reply = random.choice([
            "太棒了！你真的很努力 👍 還有其他數學問題想問我嗎？",
            "安安老師為你鼓掌 👏 有新的題目要挑戰嗎？",
            "很好～你已經掌握這個觀念了！繼續加油 💪",
            "非常好！有其他問題隨時可以問我喔～"
        ])
        session["confusion_count"] = 0
        session["chat_history"] = []
        session.pop("current_problem", None)
        return jsonify({"reply": reply})

    # 處理「不懂」
    if "不懂" in msg:
        if session.get("current_problem"):
            confusion_count += 1
            session["confusion_count"] = confusion_count
            
            if confusion_count == 1:
                followup = "學生說他不太懂，請換個角度、舉例或更簡單的方式再教一次。"
            elif confusion_count == 2:
                followup = "學生第二次說他還是不懂，請再用不同方式簡短解釋，語氣更鼓勵。"
            else:
                reply = "沒關係～學習本來就是一步步來！這題你可以先記下來，明天拿去問老師，安安為你加油 💪"
                return jsonify({"reply": reply})
            
            reply = ask_anan(followup, mode="direct", profile_type=profile_type, history=session["chat_history"])
            
            session["chat_history"].append({"role": "user", "content": followup})
            session["chat_history"].append({"role": "assistant", "content": reply})
            
            if len(session["chat_history"]) > 20:
                session["chat_history"] = session["chat_history"][-20:]
            
            return jsonify({"reply": format_ai_reply(reply)})
        else:
            reply = "沒問題，我們可以換一題或再問別的問題喔～"
            return jsonify({"reply": reply})

    # 一般問題
    reply = ask_anan(msg, mode="socratic", profile_type=profile_type, history=session["chat_history"])
    
    session["chat_history"].append({"role": "user", "content": msg})
    session["chat_history"].append({"role": "assistant", "content": reply})
    
    if len(session["chat_history"]) > 20:
        session["chat_history"] = session["chat_history"][-20:]
    
    session["current_problem"] = msg
    session["confusion_count"] = 0

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO records (id,user,question,answer,correct,created_at) VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), session["user"], msg, reply, 1, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    
    return jsonify({"reply": format_ai_reply(reply)})

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

@app.route("/clear")
def clear():
    if "user" not in session:
        return redirect("/login")
    
    session["chat_history"] = []
    session.pop("current_problem", None)
    session["confusion_count"] = 0
    
    print(f"🧹 已清空 {session.get('user')} 的對話記憶")
    
    return redirect("/")

# ===== 圖片題（Vision 識別）- 不使用串流 =====
@app.route("/analyze_image", methods=["POST"])
@app.route("/upload", methods=["POST"])
def analyze_image():
    if "user" not in session:
        return jsonify({"reply": "⚠️ 請先登入後再上傳題目喔～"})
    
    try:
        file = request.files.get("image") or request.files.get("file") or request.files.get("photo")
        
        if not file:
            available_fields = list(request.files.keys())
            print(f"⚠️ 未收到圖片檔案。收到的欄位: {available_fields}")
            return jsonify({"reply": "⚠️ 沒有收到圖片檔案喔～"})

        img_bytes = file.read()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        
        filename = file.filename.lower()
        if filename.endswith('.png'):
            mime_type = "image/png"
        elif filename.endswith(('.jpg', '.jpeg')):
            mime_type = "image/jpeg"
        elif filename.endswith('.webp'):
            mime_type = "image/webp"
        else:
            mime_type = "image/jpeg"

        print(f"🔍 正在辨識圖片... (格式: {mime_type}, 大小: {len(img_bytes)} bytes)")

        vision_reply = ""
        
        # 讀取學生風格
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        row = c.execute("SELECT profile_type FROM users WHERE username=?", (session["user"],)).fetchone()
        conn.close()
        profile_type = row[0] if row else None
        
        if openai_api_key:
            try:
                print("📸 使用 OpenAI Vision 辨識並解題...")
                headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": build_system_prompt("請用清楚步驟直接講解完整解法。", profile_type)},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "這是一張數學題的照片，請先將題目完整轉成文字，然後用繁體中文詳細解題。\n\n**特別注意**：\n1. 如果是圖形規律題，請仔細觀察每個圖形，數清楚元素數量\n2. 列出前3-4項的具體數值\n3. 找出規律並建立通項公式\n4. 驗證公式的正確性\n\n解題步驟要包含：題目內容、公式、代入、計算、最終答案"
                                },
                                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{img_b64}"}}
                            ]
                        }
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.2
                }
                
                r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=90)
                
                if r.status_code == 200:
                    data = r.json()
                    vision_reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if vision_reply and len(vision_reply.strip()) > 20:
                        print("✅ OpenAI Vision 辨識成功！")
                        # 🆕 加入自動分段處理
                        vision_reply = auto_add_paragraphs(normalize_math_terms(vision_reply))
                    else:
                        vision_reply = ""
                        
            except Exception as e:
                print(f"⚠️ OpenAI Vision 發生錯誤: {e}")
        
        if not vision_reply:
            return jsonify({"reply": "⚠️ 無法辨識這張圖片的內容。請確認圖片清晰度足夠，然後重新上傳。"})
        
        print(f"✅ Vision 辨識完成，回覆長度: {len(vision_reply)} 字元")
        
        final_reply = format_ai_reply(vision_reply)
        
        print(f"✅ 圖片題處理完成，最終回覆長度: {len(final_reply)} 字元")

        # 圖片題也記錄到對話歷史
        if "chat_history" not in session:
            session["chat_history"] = []
        
        session["chat_history"].append({"role": "user", "content": "[學生上傳了一張數學題圖片]"})
        session["chat_history"].append({"role": "assistant", "content": vision_reply})
        
        if len(session["chat_history"]) > 20:
            session["chat_history"] = session["chat_history"][-20:]
        
        # 圖片題也要設定 current_problem
        session["current_problem"] = "[圖片題目]"
        session["confusion_count"] = 0
        print(f"✅ 圖片題已設定 current_problem")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO records (id,user,question,answer,correct,created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), session["user"], "[圖片題上傳]", final_reply, 1, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        return jsonify({"reply": final_reply})
        
    except Exception as e:
        print(f"❌ analyze_image 發生未預期錯誤: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"reply": f"⚠️ 圖片辨識發生錯誤，請稍後再試。\n錯誤類型: {type(e).__name__}"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print("=" * 60)
    print("🚀 安安 v4.9.12 強制分段版啟動完成")
    print("=" * 60)
    print("📸 圖片辨識：OpenAI Vision API")
    print("🎯 教學風格：邏輯戰略家 / 創意視覺家 / 平衡大師")
    print("🧠 對話記憶：已啟用（最多保留 10 輪對話）")
    print("⚡ 串流回應：已啟用（SSE + DeepSeek Stream API）")
    print("🔍 Debug 模式：已啟用（可在 log 看到每個 chunk）")
    print("🆕 強制分段：後端在標點符號後自動加換行")
    print("📝 Prompt 優化：精簡至 500 字")
    print("🔧 數學符號：完全修正（徹底移除所有 LaTeX 語法）")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port)