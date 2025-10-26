# ================================
# 📘 數學小老師安安主程式 app.py
# v4.8.12 (修復清除紀錄 + 圖片辨識加入 OpenAI Vision 備援)
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, base64, requests, sqlite3, uuid, re, random, bcrypt
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# ===== API Keys =====
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
openai_api_key   = os.getenv("OPENAI_API_KEY", "")
gemini_api_key   = os.getenv("GEMINI_API_KEY", "")

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

# ===== 內建預設帳號（確保可登入）=====
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
print("✅ [安安] 資料庫就緒（v4.8.12）")

# ===== 文字格式化（<br> 正確渲染）=====
def format_ai_reply(text: str) -> str:
    if not text: return text
    text = re.sub(r'^\s*\d+\.\s*', '', text, flags=re.MULTILINE)
    text = text.replace('\n\n', '<br><br>').replace('\n', '<br>')
    text = re.sub(r'\$([A-Za-z0-9])\$', r'\1', text)
    return text.strip()

def normalize_math_terms(text: str) -> str:
    if not text: return text
    text = text.replace("π", "3.1416")
    text = re.sub(r"(\d+)\s*cm²", r"\1 平方公分", text)
    return text

def build_system_prompt(style: str) -> str:
    return f"""你是「數學小老師安安」，用繁體中文與學生互動教學。
禁止開場寒暄或自我介紹，直接開始教學。

教學風格：
- 溫柔、親切、鼓勵、活潑。
- 蘇格拉底式提問（socratic）或直接講解（direct）。
- 多用台灣生活例子（珍奶、雞排、夜市、便利商店等）讓學生更有共鳴。

教學原則：
1️⃣ 答對→肯定並補上完整算式。
2️⃣ 答錯→鼓勵並引導修正。
3️⃣ 問概念→結合例題與生活情境。
4️⃣ 嚴禁閒聊與自介。
5️⃣ {style}

⚠️ 重要：數學符號與格式規範
**絕對禁止使用任何 LaTeX 語法（$、\\、^、_等特殊符號）**

✅ 必須使用的 Unicode 數學符號：
【基本運算】
  + 加法：「+」
  + 減法：「−」或「-」
  + 乘法：「×」（絕不用 * 或 x）
  + 除法：「÷」（絕不用 /）
  + 等於：「=」

【進階符號】
  + 根號：「√」（例如：√16 = 4）
  + 平方：「²」（例如：5² = 25）
  + 立方：「³」（例如：2³ = 8）
  + 次方：用上標或文字（例如：2⁴ = 16 或「2的4次方」）
  + 分數：用斜線或文字（例如：1/2 或「二分之一」）
  + 括號：「()」「[]」「{{}}」
  + 小於/大於：「<」「>」「≤」「≥」
  + 約等於：「≈」
  + 不等於：「≠」
  + 正負：「±」
  + 角度：「°」（例如：90°）
  + 百分比：「%」
  + 圓周率：「π」或「3.14」

【正確範例】
✓ 面積 = 長 × 寬
✓ √25 = 5
✓ 5² = 25
✓ 2³ = 8
✓ 勾股定理：a² + b² = c²
✓ (3 + 5) × 2 = 16
✓ 圓面積 = π × r²

【錯誤範例（絕對禁止）】
✗ $面積 = 長 \\times 寬$
✗ \\sqrt{{25}} = 5
✗ 5^2 = 25
✗ a^{{2}} + b^{{2}} = c^{{2}}

計算過程要分行清楚列出：
第一步：寫出公式
第二步：代入數字
第三步：計算結果
第四步：標註單位

範例回答格式：
「我們來計算這個長方形的面積！

公式：面積 = 長 × 寬

代入數字：
面積 = 15公分 × 40公分
面積 = 600平方公分

答案是 600平方公分 ✓

就像一張全家便利商店的發票大小，長15公分、寬40公分，面積就是600平方公分喔！」
"""

def ask_anan(question: str, mode="socratic") -> str:
    if len((question or "").strip()) < 5:
        mode = "direct"
    style = (
        "採用蘇格拉底式提問法，引導學生一步步思考。"
        if mode == "socratic"
        else "請用清楚步驟直接講解完整解法，包含公式、代入、計算與答案。"
    )
    system_prompt = build_system_prompt(style)

    # DeepSeek 主模型
    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.2,
        }
        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=40)
        reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if reply:
            return normalize_math_terms(reply)
    except Exception as e:
        print("DeepSeek 失敗:", e)

    # OpenAI 備援
    try:
        if not openai_api_key:
            raise RuntimeError("未設定 OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
        payload2 = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.2,
        }
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload2, timeout=40)
        reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if reply:
            return normalize_math_terms(reply)
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
            
            # ✅ demo_user 每次登入時自動清空問卷（確保可重複測驗）
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
    # ✅ 如果是 demo_user,登出時自動清空問卷記錄
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
    
    # 計算結果
    a_count = answers.count("A")
    b_count = answers.count("B")
    
    if a_count - b_count >= 3:
        profile_type = "邏輯戰略家"
    elif b_count - a_count >= 3:
        profile_type = "創意視覺家"
    else:
        profile_type = "平衡大師"
    
    # 儲存到資料庫
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

# ✅ 新增:手動重新測驗路由
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

# ===== 主互動（守門＋三段式不懂＋問卷檢查）=====
@app.route("/", methods=["GET", "POST"])
def home():
    # ✅ 強制登入檢查
    if "user" not in session:
        return redirect("/login")
    
    # ✅ GET 請求時檢查是否需要填問卷
    if request.method == "GET":
        role = session.get("role")
        if role != "admin":  # 只檢查非管理員
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            row = c.execute("SELECT profile_type FROM users WHERE username=?", 
                          (session["user"],)).fetchone()
            conn.close()
            if not row or not row[0]:  # 沒填過問卷
                return redirect("/questionnaire")
        
        # 已登入且(是管理員 或 填過問卷) → 顯示聊天頁
        return render_template("index.html", username=session.get("user"), role=session.get("role"))

    # ===== POST 請求處理 =====
    msg = (request.form.get("message") or "").strip()
    confusion_count = session.get("confusion_count", 0)

    if "懂了" in msg:
        reply = random.choice([
            "太棒了！你真的很努力 👍",
            "安安老師為你鼓掌 👏",
            "很好～你已經掌握這個觀念了！",
            "非常好！我們繼續挑戰下一題吧 💪"
        ])
        session["confusion_count"] = 0
        return jsonify({"reply": reply})

    if "不懂" in msg:
        if session.get("current_problem"):
            confusion_count += 1
            session["confusion_count"] = confusion_count
            if confusion_count == 1:
                followup = f"學生說他不太懂這題「{session['current_problem']}」，請換個角度、舉例或更簡單的方式再教一次。"
                reply = ask_anan(followup, mode="direct")
            elif confusion_count == 2:
                followup = f"學生第二次說他還是不懂這題「{session['current_problem']}」，請再用不同方式簡短解釋，語氣更鼓勵。"
                reply = ask_anan(followup, mode="direct")
            else:
                reply = "沒關係～學習本來就是一步步來！這題你可以先記下來，明天拿去問老師，安安為你加油 💪"
        else:
            reply = "沒問題，我們可以換一題或再問別的問題喔～"
        return jsonify({"reply": format_ai_reply(reply)})

    # 一般題目 → 模型
    reply = format_ai_reply(ask_anan(msg, mode="socratic"))
    session["current_problem"] = msg
    session["confusion_count"] = 0

    # 寫入紀錄
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO records (id,user,question,answer,correct,created_at) VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), session["user"], msg, reply, 1, datetime.now().isoformat()),
    )
    conn.commit(); conn.close()
    return jsonify({"reply": reply})

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

# ✅ 修改後的清除對話路由（不登出）
@app.route("/clear")
def clear():
    """清除對話紀錄和暫存狀態，但保持登入狀態"""
    if "user" not in session:
        return redirect("/login")
    
    # 只清除對話相關的 session，保留登入資訊
    session.pop("chat_history", None)
    session.pop("current_problem", None)
    session.pop("confusion_count", None)
    
    # 保留以下 session（不清除）：
    # - user（登入帳號）
    # - role（使用者角色）
    # - questionnaire_completed（問卷狀態）
    
    return redirect("/")

# ===== 圖片題（Gemini Vision → OpenAI Vision 備援）=====
@app.route("/analyze_image", methods=["POST"])
@app.route("/upload", methods=["POST"])  # 前端使用的路由
def analyze_image():
    if "user" not in session:
        return jsonify({"reply": "⚠️ 請先登入後再上傳題目喔～"})
    
    try:
        # 嘗試多種可能的欄位名稱
        file = request.files.get("image") or request.files.get("file") or request.files.get("photo")
        
        if not file:
            # Debug: 列出收到的所有欄位
            available_fields = list(request.files.keys())
            print(f"⚠️ 未收到圖片檔案。收到的欄位: {available_fields}")
            return jsonify({"reply": "⚠️ 沒有收到圖片檔案喔～"})

        # 讀取圖片並轉換為 base64
        img_bytes = file.read()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        
        # 自動判斷圖片格式
        filename = file.filename.lower()
        if filename.endswith('.png'):
            mime_type = "image/png"
        elif filename.endswith(('.jpg', '.jpeg')):
            mime_type = "image/jpeg"
        elif filename.endswith('.webp'):
            mime_type = "image/webp"
        else:
            mime_type = "image/jpeg"  # 預設使用 jpeg

        print(f"🔍 正在辨識圖片... (格式: {mime_type}, 大小: {len(img_bytes)} bytes)")

        reply = ""
        
        # ===== 第一步：嘗試用 Gemini 識別 + 解題 =====
        if gemini_api_key:
            try:
                print("📸 使用 Gemini Vision 辨識...")
                headers = {"Content-Type": "application/json"}
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={gemini_api_key}"
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": "這是一張數學題的照片，請先將題目完整轉成文字，然後用繁體中文詳細解題。解題步驟要包含：\n1. 題目內容\n2. 使用的公式\n3. 代入數字的過程\n4. 計算步驟\n5. 最終答案（含單位）\n\n請用清楚易懂的方式說明，讓學生能理解解題邏輯。"},
                            {"inline_data": {"mime_type": mime_type, "data": img_b64}}
                        ]
                    }],
                    "generationConfig": {
                        "temperature": 0.2,
                        "topK": 32,
                        "topP": 1,
                        "maxOutputTokens": 2048,
                    }
                }
                
                r = requests.post(url, headers=headers, json=payload, timeout=90)
                
                if r.status_code == 200:
                    data = r.json()
                    try:
                        reply = data["candidates"][0]["content"]["parts"][0]["text"]
                        if reply and len(reply.strip()) > 20:
                            print("✅ Gemini 辨識成功！")
                            reply = format_ai_reply(normalize_math_terms(reply))
                        else:
                            print("⚠️ Gemini 回應內容太短，嘗試備援...")
                            reply = ""
                    except (KeyError, IndexError, TypeError) as e:
                        print(f"⚠️ Gemini 回應格式異常: {e}")
                        reply = ""
                else:
                    print(f"⚠️ Gemini API 錯誤: Status {r.status_code}")
                    reply = ""
                    
            except requests.Timeout:
                print("⚠️ Gemini 請求超時")
                reply = ""
            except Exception as e:
                print(f"⚠️ Gemini 發生錯誤: {e}")
                reply = ""
        else:
            print("⚠️ 未設定 GEMINI_API_KEY")
        
        # ===== 第二步：如果 Gemini 失敗，使用 OpenAI Vision 備援 =====
        if not reply and openai_api_key:
            try:
                print("🔄 Gemini 無法辨識，切換到 OpenAI Vision 備援...")
                headers = {
                    "Authorization": f"Bearer {openai_api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": build_system_prompt("請用清楚步驟直接講解完整解法，包含公式、代入、計算與答案。")
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "這是一張數學題的照片，請先將題目完整轉成文字，然後用繁體中文詳細解題。解題步驟要包含：\n1. 題目內容\n2. 使用的公式\n3. 代入數字的過程\n4. 計算步驟\n5. 最終答案（含單位）"
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{mime_type};base64,{img_b64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.2
                }
                
                r = requests.post("https://api.openai.com/v1/chat/completions", 
                                headers=headers, json=payload, timeout=90)
                
                if r.status_code == 200:
                    data = r.json()
                    reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if reply and len(reply.strip()) > 20:
                        print("✅ OpenAI Vision 辨識成功！")
                        reply = format_ai_reply(normalize_math_terms(reply))
                    else:
                        reply = ""
                else:
                    print(f"⚠️ OpenAI API 錯誤: Status {r.status_code}")
                    print(f"Response: {r.text}")
                    reply = ""
                    
            except requests.Timeout:
                print("⚠️ OpenAI 請求超時")
                reply = ""
            except Exception as e:
                print(f"⚠️ OpenAI Vision 發生錯誤: {e}")
                reply = ""
        
        # ===== 如果兩個都失敗 =====
        if not reply:
            return jsonify({"reply": "⚠️ 無法辨識這張圖片的內容。請確認：\n1. 圖片清晰度足夠\n2. 題目文字清楚可見\n3. 光線充足，沒有反光\n4. 圖片中確實包含數學題目\n\n建議：可以嘗試重新拍攝後再上傳。"})

        print(f"✅ 圖片辨識成功，回覆長度: {len(reply)} 字元")

        # 寫入紀錄
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO records (id,user,question,answer,correct,created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), session["user"], "[圖片題上傳]", reply, 1, datetime.now().isoformat()),
        )
        conn.commit(); conn.close()
        return jsonify({"reply": reply})
        
    except Exception as e:
        print(f"❌ analyze_image 發生未預期錯誤: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"reply": f"⚠️ 圖片辨識發生錯誤，請稍後再試。\n錯誤類型: {type(e).__name__}"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print("🚀 安安 v4.8.12 啟動完成")
    print("📸 圖片辨識：Gemini Vision (主要) + OpenAI Vision (備援)")
    app.run(host="0.0.0.0", port=port)