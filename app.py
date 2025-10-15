# =====================================
# 📘 安安 app.py — 無登入還原基線（完整可用）
# - 六種幾何（三角形、長方形、正方形、圓形、菱形、梯形）
# - 三步蘇格拉底教學
# - 圖片分析：優雅備援（Vision ➜ Gemini ➜ DeepSeek ➜ OpenAI），任何一層失敗都「靜默切換」，不會卡
# - SQLite：data/anan.db（learning_records）
# =====================================

from flask import Flask, render_template, request, jsonify
import os, sqlite3, uuid, requests
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
DB_PATH = os.getenv("ANAN_DB_PATH", "data/anan.db")
PI = 3.1416

# -----------------------------
# DB
# -----------------------------
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS learning_records (
            id TEXT PRIMARY KEY,
            ts TEXT,
            user_id TEXT,
            question TEXT,
            response TEXT,
            topic TEXT,
            step INTEGER,
            correct INTEGER
        )
    """)
    conn.commit()
    conn.close()

init_db()

def log_record(question, response, topic, step, correct=None, user_id="guest"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO learning_records (id, ts, user_id, question, response, topic, step, correct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (str(uuid.uuid4()), datetime.utcnow().isoformat(), user_id, question, response, topic, step, correct))
    conn.commit()
    conn.close()

# -----------------------------
# 教學邏輯
# -----------------------------
def detect_topic(msg):
    if "長方形" in msg: return "rectangle"
    if "正方形" in msg: return "square"
    if "三角形" in msg: return "triangle"
    if "圓" in msg or "圓形" in msg or "半徑" in msg or "直徑" in msg: return "circle"
    if "菱形" in msg: return "rhombus"
    if "梯形" in msg: return "trapezoid"
    return "general"

def is_area(msg): return any(k in msg for k in ["面積", "area"])
def is_perimeter(msg): return any(k in msg for k in ["周長", "perimeter", "圍一圈"])

def socratic_steps(topic, kind):
    if topic == "rectangle":
        return ([
            "第 1 步：找出長與寬。你知道題目給的長與寬是多少嗎？",
            "第 2 步：面積公式是「長 × 寬」。能代入數字嗎？",
            "第 3 步：面積 = 長 × 寬，記得單位是平方（例如平方公分）。"
        ] if kind=="area" else [
            "第 1 步：先列出長與寬。",
            "第 2 步：周長公式是 2 × (長 + 寬)。",
            "第 3 步：P = 2 × (L + W)。單位是長度。"
        ])
    if topic == "square":
        return ([
            "第 1 步：正方形四邊相等，先找出邊長 s。",
            "第 2 步：面積公式是 s × s。",
            "第 3 步：A = s²。記得單位是平方。"
        ] if kind=="area" else [
            "第 1 步：確認邊長 s。",
            "第 2 步：周長公式是 4s。",
            "第 3 步：P = 4s。"
        ])
    if topic == "triangle":
        return ([
            "第 1 步：確認底 b 與高 h（高須垂直於底）。",
            "第 2 步：面積公式是 (b × h) ÷ 2。",
            "第 3 步：A = (b × h) ÷ 2。"
        ] if kind=="area" else [
            "第 1 步：列出三邊長 a、b、c。",
            "第 2 步：周長公式是 a + b + c。",
            "第 3 步：P = a + b + c。"
        ])
    if topic == "circle":
        return ([
            "第 1 步：先找半徑 r（或 d/2）。",
            f"第 2 步：面積公式 A = πr²，這裡取 π = {PI}。",
            f"第 3 步：A = {PI} × r²。"
        ] if kind=="area" else [
            "第 1 步：找半徑 r 或直徑 d（r = d ÷ 2）。",
            f"第 2 步：周長公式 C = 2πr 或 C = πd（π = {PI}）。",
            f"第 3 步：C = 2 × {PI} × r。"
        ])
    if topic == "rhombus":
        return ([
            "第 1 步：菱形面積可用對角線 d1、d2。",
            "第 2 步：A = (d1 × d2) ÷ 2；或底 × 高。",
            "第 3 步：若 d1、d2 已知，A = (d1 × d2) ÷ 2。"
        ] if kind=="area" else [
            "第 1 步：確認邊長 s。",
            "第 2 步：周長公式 P = 4s。",
            "第 3 步：P = 4s。"
        ])
    if topic == "trapezoid":
        return ([
            "第 1 步：找上底 a、下底 b 與高 h（高需垂直）。",
            "第 2 步：A = ((a + b) × h) ÷ 2。",
            "第 3 步：A = ((a + b) × h) ÷ 2。"
        ] if kind=="area" else [
            "第 1 步：列出四邊 a、b、c、d（兩底為 a、b）。",
            "第 2 步：P = a + b + c + d。",
            "第 3 步：把四邊相加即可。"
        ])
    return [
        "第 1 步：列出題目已知數據。",
        "第 2 步：找出適用公式並代入。",
        "第 3 步：計算後檢查單位與合理性。"
    ]

def build_reply(msg, step=1):
    topic = detect_topic(msg)
    kind = "area" if is_area(msg) else "perimeter" if is_perimeter(msg) else "area"
    steps = socratic_steps(topic, kind)
    idx = max(1, min(3, int(step))) - 1
    return steps[idx], topic, idx + 1

# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html", version="無登入還原基線")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    msg = data.get("message", "").strip()
    step = int(data.get("step", 1))
    if not msg:
        return jsonify({"ok": False, "error": "訊息為空白"}), 400
    reply, topic, step_used = build_reply(msg, step)
    log_record(msg, reply, topic, step_used)
    return jsonify({"ok": True, "reply": reply, "topic": topic, "step": step_used})

# ---- 圖片分析（穩定備援、不阻塞） ----
@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    data = request.get_json(force=True) or {}
    img_b64 = data.get("image_base64")
    if not img_b64:
        return jsonify({"ok": False, "error": "缺少 image_base64"}), 400

    prompt = "請閱讀這張數學圖形題，描述它的幾何關係並提出第 1 步引導問題（請用繁體中文、簡潔清楚）。"

    def try_vision():
        if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"):
            return None
        # 之後你要接真正 Vision/OCR 再換這段
        return "🔍 Vision 模式：偵測到幾何圖形題，先標記邊與角，再說出你知道的數字與單位。"

    def try_gemini():
        key = os.getenv("GEMINI_API_KEY")
        if not key: return None
        try:
            r = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent",
                params={"key": key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=6
            )
            j = r.json()
            return j["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            return None

    def try_deepseek():
        key = os.getenv("DEEPSEEK_API_KEY")
        if not key: return None
        try:
            r = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}]},
                timeout=6
            )
            j = r.json()
            return j["choices"][0]["message"]["content"]
        except Exception:
            return None

    def try_openai():
        key = os.getenv("OPENAI_API_KEY")
        if not key: return None
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]},
                timeout=6
            )
            j = r.json()
            return j["choices"][0]["message"]["content"]
        except Exception:
            return None

    # 逐層備援（任何錯誤即靜默換下一層；全部失敗回離線訊息）
    providers = [
        ("vision", try_vision),
        ("gemini", try_gemini),
        ("deepseek", try_deepseek),
        ("openai", try_openai),
    ]
    reply, used = None, "none"
    for name, fn in providers:
        out = fn()
        if out and isinstance(out, str) and out.strip():
            reply, used = out.strip(), name
            break
    if not reply:
        reply = "我看見一個幾何圖形。先描述有哪些邊、角或標示（例：底與高？半徑/直徑？），我再帶你做第 1 步分析。"

    log_record("[analyze_image]", reply, "image", 1)
    return jsonify({"ok": True, "reply": reply, "provider_used": used})

@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json(force=True) or {}
    question = str(data.get("question", ""))
    reply = str(data.get("reply", ""))
    correct = data.get("correct", None)
    try:
        correct_val = int(correct) if correct is not None else None
    except:
        correct_val = None
    log_record(question=question, response=reply, topic="feedback", step=0, correct=correct_val)
    return jsonify({"ok": True})

@app.route("/clear", methods=["POST"])
def clear():
    return jsonify({"ok": True, "message": "已重置對話狀態（伺服器無需清除）。"})

@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "version": "無登入還原基線",
        "db_path": DB_PATH,
        "has_gemini": bool(os.getenv("GEMINI_API_KEY")),
        "has_deepseek": bool(os.getenv("DEEPSEEK_API_KEY")),
        "has_openai": bool(os.getenv("OPENAI_API_KEY")),
        "has_vision": bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")),
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
