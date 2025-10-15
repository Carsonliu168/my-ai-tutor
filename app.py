# ================================
# 📘 安安專案主程式 app.py
# v4.7.8b：UTF-8 修復 + /analyze_image + 舊版 records 相容寫入 + 更穩的 /feedback
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session
import os, json, base64, requests, sqlite3, uuid, re
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# API Keys
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
openai_api_key   = os.getenv("OPENAI_API_KEY", "")
gemini_api_key   = os.getenv("GEMINI_API_KEY", "")

# SQLite
DB_PATH = "data/anan.db"
os.makedirs("data", exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 使用者表（登入）
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        created_at TEXT
    )""")
    # 新版 records 表（不會覆蓋既有舊表）
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

def seed_admin():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE username='anan_admin'")
    if not c.fetchone():
        c.execute(
            "INSERT INTO users (username, password, role, created_at) VALUES ('anan_admin','1234','admin',datetime('now'))"
        )
        conn.commit()
        print("✅ 已自動建立管理員帳號：anan_admin / 密碼 1234")
    conn.close()

seed_admin()
print("✅ [安安] 資料庫就緒，含 users 登入表 (v4.7.8b)")

# ---------------- 工具 ----------------
def normalize_math_terms(text):
    if not text:
        return text
    # π 正規化
    text = text.replace("π", "3.1416")
    # 單位正規化
    text = re.sub(r"(\d+)\s*cm²", r"\1 平方公分", text)
    return text

def ask_anan(question, mode="socratic"):
    """主教學回答：DeepSeek > OpenAI 備援；全繁中、可蘇格拉底或直接講解"""
    if len((question or "").strip()) < 5:
        mode = "direct"
    style = ("採用蘇格拉底式提問法，引導學生一步步思考，但不要閒聊。"
             if mode == "socratic"
             else "請用清楚步驟直接講解完整解法，包含公式、代入、計算與答案。")
    system_prompt = f"""你是台灣國中數學助教「安安」，用繁體中文教學。
風格：親切、有耐心，但不寒暄、不離題。
原則：
- 若學生回答正確，先肯定再補上完整算式。
- 若學生答錯，請用鼓勵語氣引導。
- 若學生輸入簡短詞（如公式或關鍵字），請直接用「公式應用 + 範例 + 最後答案」教學。
- {style}
"""

    # DeepSeek 主模型
    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            "temperature": 0.2
        }
        r = requests.post("https://api.deepseek.com/chat/completions",
                          headers=headers, json=payload, timeout=40)
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
                {"role": "user", "content": question}
            ],
            "temperature": 0.2
        }
        r = requests.post("https://api.openai.com/v1/chat/completions",
                          headers=headers, json=payload2, timeout=40)
        reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if reply:
            return normalize_math_terms(reply)
    except Exception as e:
        print("OpenAI 備援失敗:", e)

    return "（安安暫時沒回應，請稍後再試一次）"

def write_record_compat(user_name, question, answer, is_correct=1):
    """同時相容新舊 records 結構寫入"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # 先試新版表
        c.execute(
            "INSERT INTO records (id,user,question,answer,correct,created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), user_name, question, answer, is_correct, datetime.now().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.OperationalError as e:
        # 相容舊表（常見欄位：user_id / question / topic / is_correct）
        try:
            c.execute(
                "INSERT INTO records (user_id,question,topic,is_correct) VALUES (?,?,?,?)",
                (user_name, question, "一般", is_correct)
            )
            conn.commit()
            print("ℹ️ 已自動使用舊版 records 結構寫入成功")
            return True
        except Exception as e2:
            print("⚠️ 寫入 records 失敗：", e, "/ fallback:", e2)
            return False
    finally:
        conn.close()

# ---------------- 登入/登出 ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session["user"] = username
            session.permanent = True
            return redirect("/")
        return render_template("login.html", error="帳號或密碼錯誤，請再試一次。")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

# ---------------- 首頁互動 ----------------
@app.route("/", methods=["GET", "POST"])
def home():
    if "user" not in session:
        return redirect("/login")

    # 確保模板可安全迭代
    conversation = session.get("conversation", [])

    if request.method == "POST":
        msg = (request.form.get("message", "")).strip()
        reply = ask_anan(msg, mode="socratic")
        # 記錄（相容新舊表）
        write_record_compat(session["user"], msg, reply, is_correct=1)

        # 可選：把訊息放到 session 對話（供模板顯示）
        conversation.append({"role": "user", "content": msg})
        conversation.append({"role": "assistant", "content": reply})
        session["conversation"] = conversation

        # 維持你原本流程：直接回 JSON（前端目前是表單提交，會重新導向；保留行為）
        return jsonify({"reply": reply})

    return render_template("index.html", conversation=conversation)

# ---------------- 圖片辨識 ----------------
@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    try:
        image = request.files.get("image")
        if not image:
            return jsonify({"result": "⚠️ 沒有收到圖片"})

        # 轉 base64
        img_b64 = base64.b64encode(image.read()).decode("utf-8")

        # 先用 Gemini OCR （Google AI Studio REST）
        text = ""
        try:
            if not gemini_api_key:
                raise RuntimeError("未設定 GEMINI_API_KEY")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_api_key}"
            payload = {
                "contents": [{
                    "role": "user",
                    "parts": [
                        {"text": "請讀取這張數學題圖片內容，抽取清楚的題目文字。"},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                    ]
                }]
            }
            r = requests.post(url, json=payload, timeout=60)
            data = r.json()
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            ) or ""
        except Exception as e:
            print("Gemini 圖片讀取失敗:", e)

        if not text:
            text = "⚠️ 無法從圖片辨識出清楚文字，請再拍清楚一點。"

        answer = ask_anan(text, mode="direct")
        return jsonify({"result": answer})

    except Exception as e:
        print("❌ analyze_image 失敗:", e)
        return jsonify({"result": "⚠️ 圖片分析發生錯誤"})

# ---------------- 清除對話（只清 session） ----------------
@app.route("/clear")
def clear():
    session.pop("conversation", None)
    return redirect("/")

# ---------------- 學生回饋 ----------------
@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json(silent=True) or {}
    # 兼容兩種傳法：{understood: true/false} 或 {feedback: "understood"/"confused"}
    if "understood" in data:
        understood = bool(data.get("understood"))
    else:
        fb = str(data.get("feedback", "")).lower()
        understood = (fb == "understood")

    if understood is True:
        return jsonify({"reply": "太棒了～安安替你開心 💪"})
    elif understood is False:
        return jsonify({"reply": "沒關係，我再簡單講一次：記得公式與步驟才是關鍵喔～"})
    return jsonify({"reply": "收到你的回饋，謝謝！"})

# ---------------- 啟動 ----------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
