# ================================
# 📘 安安專案主程式 app.py
# v4.3.6：加入互動式教學模板（長方形面積）；引導不超過 3 次，第 3 次直接給出標準完整解答
# 同步保留：全面繁體化 + 術語正規化 + 修復 /clear 路由 + 圖片備援
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
# 🧠 DeepSeek / GPT 文本模型（一般題用）
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
- {style}
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
    print("✅ [安安] 資料庫就緒 (v4.3.6)")
init_db()

# -------------------------------
# 🎯 專題：長方形面積 3 步互動引導（第 3 步直接給標準解答）
# -------------------------------
RECTANGLE_TOPIC = "rectangle_area_v436"

def detect_rectangle_area(q: str):
    """
    嘗試從文字中抓出「長方形 長=.. 寬=..」的數字；若抓到回傳 (L, W) int，否則 None
    """
    if not q:
        return None
    text = q.replace("：", ":").replace("，", ",").replace("。", ".")
    # 常見敘述：長 12 公分、寬 8 公分 / 長是12、寬是8 / 長=12 寬=8
    m = re.search(r'長方形.*?長[是為=]?\s*(\d+)\s*公?\s*分?.*?[,、與和及。\s]*寬[是為=]?\s*(\d+)\s*公?\s*分?', text)
    if not m:
        # 另一種順序：寬在前
        m = re.search(r'長方形.*?寬[是為=]?\s*(\d+)\s*公?\s*分?.*?[,、與和及。\s]*長[是為=]?\s*(\d+)\s*公?\s*分?', text)
        if m:
            w, l = m.group(1), m.group(2)
            return int(l), int(w)
        return None
    l, w = m.group(1), m.group(2)
    return int(l), int(w)

def rectangle_step_prompt(stage: int, L: int, W: int):
    """
    第 1～3 步的回覆文案
    - 第 1 步：問概念（加法 or 乘法），不給答案
    - 第 2 步：帶入公式與數字，請學生算 12×8，不給最終句
    - 第 3 步：直接給完整標準解答（你先前貼的語氣）
    """
    if stage == 1:
        return normalize_math_terms(f"""安安老師：我們一起來想想這題吧～ 😊  
題目說：一個長方形的長是 **{L} 公分**，寬是 **{W} 公分**。  
那你還記得長方形的**面積要怎麼算**嗎？是用**加法**還是**乘法**呢？🤔""")
    if stage == 2:
        return normalize_math_terms(f"""太好了～長方形的面積要用**乘法**！  
公式是：**面積 = 長 × 寬**。  
把數字帶進去：**{L} × {W} = ?**  
你來算算看是多少呢？😉""")
    # stage 3：標準完整解答（直接給出最終答案與單位）
    area = L * W
    return normalize_math_terms(f"""安安來幫你算這個長方形的面積喔！  

長方形的面積公式是：  
**面積 = 長 × 寬**

題目給的長是 **{L} 公分**，寬是 **{W} 公分**，  
所以我們來算一下：  
**{L} × {W} = {area}**

答案就是 **{area} 平方公分**～  

很簡單對吧？記得面積的單位是「平方公分」喔！如果有其他問題，隨時問我～ 😊""")

def start_rectangle_flow(L: int, W: int):
    session["guided_topic"] = RECTANGLE_TOPIC
    session["guided_params"] = {"L": L, "W": W}
    session["guided_stage"] = 1
    return rectangle_step_prompt(1, L, W)

def continue_rectangle_flow(user_text: str):
    """
    根據目前 stage 往下推進；不超過 3 步
    """
    stage = int(session.get("guided_stage", 1))
    params = session.get("guided_params", {})
    L, W = int(params.get("L", 0)), int(params.get("W", 0))
    if not L or not W:
        # 安全回落
        session.pop("guided_topic", None)
        session.pop("guided_params", None)
        session.pop("guided_stage", None)
        return ask_anan(user_text, mode="socratic")

    if stage <= 1:
        session["guided_stage"] = 2
        return rectangle_step_prompt(2, L, W)

    if stage == 2:
        session["guided_stage"] = 3
        return rectangle_step_prompt(3, L, W)

    # stage >=3：已給標準解答，結束此導引
    session.pop("guided_topic", None)
    session.pop("guided_params", None)
    session.pop("guided_stage", None)
    # 若學生再追問，回到一般回答
    return ask_anan(user_text, mode="normal")

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
            reply_text = None

            # ① 若目前在引導「長方形面積」主題中，就走引導流程（最多 3 步）
            if session.get("guided_topic") == RECTANGLE_TOPIC:
                reply_text = continue_rectangle_flow(user_msg)

            # ② 嘗試偵測是否為新的「長方形面積」題目，若是，啟動 3 步引導
            if reply_text is None:
                params = detect_rectangle_area(user_msg)
                if params:
                    L, W = params
                    reply_text = start_rectangle_flow(L, W)

            # ③ 其他一般題目 → 走既有的 Socratic/normal 策略
            if reply_text is None:
                mode = "normal" if session.get("confused_count", 0) >= 2 else "socratic"
                reply_text = ask_anan(user_msg, mode)

            # 記錄對話
            conversation.append({"role": "user", "content": user_msg})
            conversation.append({"role": "assistant", "content": reply_text})
            session["conversation"] = conversation

            # 紀錄 DB
            conn = get_conn()
            conn.execute("INSERT INTO records (user_id, question, topic, is_correct) VALUES (?, ?, ?, ?)",
                         (session["user_id"], user_msg,
                          "長方形面積" if session.get("guided_topic") == RECTANGLE_TOPIC else "一般",
                          None))
            conn.commit()
            conn.close()

    return render_template("index.html", conversation=conversation)

# -------------------------------
# 🧭 學生回饋邏輯（保留）
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
# 🗑️ 清除對話（修復 404）
# -------------------------------
@app.route("/clear")
def clear():
    session.pop("conversation", None)
    session["confused_count"] = 0
    # 結束任何正在進行的引導
    session.pop("guided_topic", None)
    session.pop("guided_params", None)
    session.pop("guided_stage", None)
    return redirect("/")

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
