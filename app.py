# ================================
# 📘 安安專案主程式 app.py
# v4.3.4：繁體中文鎖定 + 術語正規化（mod/lcm/gcd/簡體）
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session
import os, json, base64, requests, sqlite3, uuid, re
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制 16MB

# -------------------------------
# ✅ 環境變數與 API 初始化
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

# -------------------------------
# 🧩 術語與繁體正規化
# -------------------------------
def normalize_math_terms(s: str) -> str:
    if not s:
        return s
    try:
        # 英文術語 → 中文
        s = re.sub(r'\blcm\b', '最小公倍數', s, flags=re.IGNORECASE)
        s = re.sub(r'\bgcd\b', '最大公因數', s, flags=re.IGNORECASE)
        s = re.sub(r'\bmod\b', '模（取餘數）', s, flags=re.IGNORECASE)
        # 常見簡體字 → 繁體
        s = s.replace("质数", "質數").replace("质因数", "質因數").replace("余数", "餘數")
        s = s.replace("最小公倍数", "最小公倍數").replace("最大公约数", "最大公因數")
        s = s.replace("这", "這").replace("个", "個").replace("写", "寫").replace("为", "為")
    except Exception:
        pass
    return s

# -------------------------------
# 🧠 DeepSeek 模型
# -------------------------------
def ask_anan(question: str, mode="socratic"):
    style = "採用蘇格拉底式提問法，引導學生思考，不直接給答案。" if mode == "socratic" else "用正常教學方式清楚給出解題步驟與答案。"

    system_prompt = f"""
你是「數學小老師安安」，一位專業、親切、幽默的數學教學助理。
請務必使用「繁體中文（臺灣用語）」回答。
若題目是簡體或英文，請先轉成繁體再解說。

解題規範：
- 術語請用中文為主（例如：最小公倍數、最大公因數、模運算），避免使用 lcm/gcd/mod 等縮寫。
- 若出現模運算，請說明它代表取餘數的意思。
- 用親切、鼓勵的語氣引導學生。
"""

    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
        }
        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=40)
        reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        return normalize_math_terms(reply)
    except:
        try:
            backup_headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            payload["model"] = "gpt-4o-mini"
            r2 = requests.post("https://api.openai.com/v1/chat/completions", headers=backup_headers, json=payload, timeout=40)
            reply = r2.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            return normalize_math_terms(reply)
        except:
            return "（無回應）"

# -------------------------------
# 📊 SQLite 紀錄
# -------------------------------
DB_PATH = "data/anan.db"
os.makedirs("data", exist_ok=True)

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        question TEXT,
        topic TEXT,
        is_correct INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()
    print("✅ [安安] 資料庫就緒 (v4.3.4)")
init_db()

# -------------------------------
# 💬 主頁與回饋
# -------------------------------
@app.before_request
def ensure_user():
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())

@app.route("/", methods=["GET", "POST"])
def home():
    if "conversation" not in session:
        session["conversation"] = []
        session["confused_count"] = 0
    conversation = session["conversation"]

    if request.method == "POST":
        user_msg = request.form.get("message", "")
        if user_msg:
            mode = "normal" if session.get("confused_count", 0) >= 2 else "socratic"
            ai_reply = ask_anan(user_msg, mode)
            conversation.append({"role": "user", "content": user_msg})
            conversation.append({"role": "assistant", "content": ai_reply})
            session["conversation"] = conversation

            conn = get_conn()
            conn.execute("INSERT INTO records (user_id, question, topic, is_correct) VALUES (?, ?, ?, ?)",
                         (session["user_id"], user_msg, "一般", None))
            conn.commit()
            conn.close()

    return render_template("index.html", conversation=conversation)

# -------------------------------
# 🧭 學生回饋邏輯
# -------------------------------
@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json()
    understood = data.get("understood")
    if understood is None:
        return jsonify({"status": "error"})
    if understood:
        session["confused_count"] = 0
        reply = "太棒了～安安替你開心 💪"
    else:
        session["confused_count"] = session.get("confused_count", 0) + 1
        count = session["confused_count"]
        if count == 1:
            reply = "沒關係，我先用更簡單的方式說一次，跟著我一步步來 👇"
        elif count == 2:
            reply = "好喔，我再舉個不同的例子幫你理解看看 💡"
        else:
            reply = ask_anan("請直接用最簡單明確的方式重講上一題，列出算式與答案。", mode="normal")
    return jsonify({"status": "ok", "reply": normalize_math_terms(reply)})

# -------------------------------
# 🧮 圖片解題（Gemini + GPT 備援）
# -------------------------------
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"result": "⚠️ 沒有收到圖片"}), 400
    image_file = request.files["image"]
    if image_file.filename == '' or not allowed_file(image_file.filename):
        return jsonify({"result": "⚠️ 圖片格式錯誤"}), 400
    image_bytes = image_file.read()

    result = None
    try:
        print("🔵 嘗試使用 Gemini 模型中...")
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content([
            "你是台灣數學老師安安，請用『繁體中文（臺灣用語）』逐步講解這張圖片題。"
            "先整理條件→指出概念→逐步計算→驗證答案。"
            "術語請用中文為主（例如：最小公倍數、最大公因數、模運算），不要用英文縮寫。",
            {"mime_type": "image/jpeg", "data": image_bytes}
        ])
        result = response.text
    except Exception as e:
        print(f"⚠️ Gemini 失敗：{e}")

    if not result:
        try:
            print("🟢 使用 GPT-4o 備援中...")
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-4o",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "你是台灣數學老師安安，請用繁體中文詳細逐步解這張圖片題。"
                                                  "先整理條件→指出概念→逐步計算→驗證答案；"
                                                  "術語以中文為主，不要出現英文縮寫（lcm/gcd/mod）。"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                    ]
                }],
                "max_tokens": 1000
            }
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
            result = r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return jsonify({"result": f"⚠️ 辨識失敗：{e}"}), 500

    result = normalize_math_terms(result)

    if "conversation" not in session:
        session["conversation"] = []
    conversation = session["conversation"]
    conversation.append({"role": "user", "content": "📷 [上傳了數學題目圖片]"})
    conversation.append({"role": "assistant", "content": result})
    session["conversation"] = conversation
    session.modified = True

    return jsonify({"result": result, "success": True}), 200

# -------------------------------
# 🚀 啟動
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
