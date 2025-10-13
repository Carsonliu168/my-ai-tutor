# ================================
# 📘 安安專案主程式 app.py
# v4.4.0：幾何導引完整版（長方形/正方形/三角形/圓形/菱形/梯形）
# - 各題型三步互動：第3步直接標準完整解答（台灣繁體、生活化例子）
# - π = 3.1416、單位預設「平方公分」
# - 不懂/feedback：三步封頂（前兩次本地即時，第三次定稿），圖+文皆適用
# - 保留：繁體正規化、Gemini→GPT 備援、/clear、SQLite 紀錄
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
    print("✅ [安安] 資料庫就緒 (v4.4.0)")
init_db()

# =========================================================
# 🎯 幾何題型：偵測 + 三步互動（第3步標準完整解答）
#    題型：長方形、正方形、三角形、圓形、菱形、梯形
# =========================================================

PI = 3.1416  # 國中常用 π

# ---- 通用引導管理 ----
GUIDED_TOPICS = {"rectangle","square","triangle","circle","rhombus","trapezoid"}

def start_flow(topic: str, params: dict, step1_text: str):
    session["guided_topic"] = topic
    session["guided_params"] = params
    session["guided_stage"] = 1
    return normalize_math_terms(step1_text)

def next_step_or_finish(topic: str, make_step_text_fn):
    stage = int(session.get("guided_stage", 1))
    params = session.get("guided_params", {})
    if not params:
        # 安全回落
        session.pop("guided_topic", None)
        session.pop("guided_params", None)
        session.pop("guided_stage", None)
        return ask_anan("請用最簡單的方式解釋上一題。", mode="normal")

    if stage <= 1:
        session["guided_stage"] = 2
        return normalize_math_terms(make_step_text_fn(stage=2, **params))
    if stage == 2:
        session["guided_stage"] = 3
        return normalize_math_terms(make_step_text_fn(stage=3, **params))

    # 完成 → 清空導引狀態
    session.pop("guided_topic", None)
    session.pop("guided_params", None)
    session.pop("guided_stage", None)
    return ask_anan("請用最簡單的方式解釋上一題。", mode="normal")

# ---- 長方形 ----
def detect_rectangle(q: str):
    if not q: return None
    t = q.replace("：", ":").replace("，", ",").replace("。", ".")
    m = re.search(r'長方形.*?長[是為=]?\s*(\d+).*寬[是為=]?\s*(\d+)', t)
    if m: return {"L": int(m.group(1)), "W": int(m.group(2))}
    m = re.search(r'長方形.*?寬[是為=]?\s*(\d+).*長[是為=]?\s*(\d+)', t)
    if m: return {"L": int(m.group(2)), "W": int(m.group(1))}
    return None

def rectangle_step(stage:int, L:int, W:int):
    if stage==1:
        return f"安安老師：我們來看長方形吧～像是課桌面的形狀！😉\n已知 **長 {L} 公分**、**寬 {W} 公分**。\n你覺得要用**加法**還是**乘法**來算面積呢？🤔"
    if stage==2:
        return f"長方形的面積公式是：**面積 = 長 × 寬**。\n把數字帶進去：**{L} × {W} = ?**\n想像把桌面分成 {W} 列、每列 {L} 個 1×1 小方格，把它們乘起來就行囉！"
    area = L*W
    return f"安安幫你結算一下：\n**{L} × {W} = {area}**\n所以長方形的面積是 **{area} 平方公分**！\n記得喔，面積要用「平方公分」。👏"

# ---- 正方形 ----
def detect_square(q: str):
    if not q: return None
    t = q.replace("：", ":").replace("，", ",").replace("。", ".")
    m = re.search(r'正方形.*?(邊|邊長)[是為=]?\s*(\d+)', t)
    if m: return {"S": int(m.group(2))}
    return None

def square_step(stage:int, S:int):
    if stage==1:
        return f"安安老師：正方形就像**便利貼**或**棋盤的小格子**～每條邊都一樣長！\n邊長是 **{S} 公分**，你覺得面積要怎麼算呢？🤔"
    if stage==2:
        return f"正方形的面積公式：**面積 = 邊長 × 邊長**。\n帶入：**{S} × {S} = ?**\n就像把一條邊當『一排方格』，疊上去 {S} 排～"
    area = S*S
    return f"算出來是：**{S} × {S} = {area}**。\n所以正方形的面積是 **{area} 平方公分**！很像 {S}×{S} 的方格填滿整張紙～📄"

# ---- 三角形 ----
def detect_triangle(q: str):
    if not q: return None
    t = q.replace("：", ":").replace("，", ",").replace("。", ".")
    m = re.search(r'三角形.*?底[是為=]?\s*(\d+).*高[是為=]?\s*(\d+)', t)
    if m: return {"B": int(m.group(1)), "H": int(m.group(2))}
    m = re.search(r'三角形.*?高[是為=]?\s*(\d+).*底[是為=]?\s*(\d+)', t)
    if m: return {"B": int(m.group(2)), "H": int(m.group(1))}
    return None

def triangle_step(stage:int, B:int, H:int):
    if stage==1:
        return f"想像把三角形當作被對半切的**蛋糕**！🍰\n已知 **底 {B} 公分**、**高 {H} 公分**。\n你覺得面積要用到『對半』的概念嗎？😉"
    if stage==2:
        return f"三角形面積：**面積 = 底 × 高 ÷ 2**。\n代入：**{B} × {H} ÷ 2 = ?**\n因為三角形大約是『同底同高長方形的一半』～"
    area = B*H/2
    # 確保整數或小數顯示合理
    area_str = f"{area:.2f}".rstrip('0').rstrip('.') if isinstance(area, float) else str(area)
    return f"算一算：**{B} × {H} ÷ 2 = {area_str}**。\n所以三角形面積是 **{area_str} 平方公分**！🥳"

# ---- 圓形 ----
def detect_circle(q: str):
    if not q: return None
    t = q.replace("：", ":").replace("，", ",").replace("。", ".")
    # 半徑優先
    m = re.search(r'(圓|圓形).*?半徑[是為=]?\s*(\d+)', t)
    if m: return {"r": float(m.group(2))}
    # 直徑
    m = re.search(r'(圓|圓形).*?直徑[是為=]?\s*(\d+)', t)
    if m: return {"r": float(m.group(2))/2}
    return None

def circle_step(stage:int, r:float):
    if stage==1:
        return f"想像一個**披薩**🍕！半徑是 **{r} 公分**。\n你覺得圓的面積會跟『半徑的平方』有關嗎？"
    if stage==2:
        return f"圓面積：**面積 = π × r²**（用 π=3.1416）。\n帶入：**3.1416 × {r}² = 3.1416 × {r*r} = ?**"
    area = PI * (r*r)
    area_str = f"{area:.4f}".rstrip('0').rstrip('.')
    return f"計算結果：**3.1416 × {r*r} = {area_str}**。\n所以圓的面積是 **{area_str} 平方公分**！像把披薩整片都吃光～😋"

# ---- 菱形 ----
def detect_rhombus(q: str):
    if not q: return None
    t = q.replace("：", ":").replace("，", ",").replace("。", ".")
    # 對角線 a、b
    # 關鍵字：對角線、對角線一、對角線二、d1/d2/長
    m = re.search(r'菱形.*?對角線[一1]?[^0-9]*(\d+).*?(對角線[二2]?|另一條對角線)[^0-9]*(\d+)', t)
    if m: return {"d1": int(re.sub(r'[^0-9]','',m.group(1))), "d2": int(re.sub(r'[^0-9]','',m.group(3)))}
    # 若寫成兩個「對角線長」也抓一下
    nums = re.findall(r'菱形.*?對角線(?:長)?[是為=]?\s*(\d+)', t)
    if len(nums) >= 2: return {"d1": int(nums[0]), "d2": int(nums[1])}
    return None

def rhombus_step(stage:int, d1:int, d2:int):
    if stage==1:
        return f"想像窗戶上那種**菱格窗**🔷！\n已知兩條對角線長：**{d1} 公分** 和 **{d2} 公分**。\n你覺得面積跟『兩條對角線』的乘積有關嗎？"
    if stage==2:
        return f"菱形面積：**面積 = (對角線1 × 對角線2) ÷ 2**。\n帶入：**({d1} × {d2}) ÷ 2 = ?**"
    area = d1*d2/2
    area_str = f"{area:.2f}".rstrip('0').rstrip('.') if isinstance(area, float) else str(area)
    return f"算出來是：**({d1} × {d2}) ÷ 2 = {area_str}**。\n所以菱形面積是 **{area_str} 平方公分**！像把兩條『窗格十字』鋪滿的一半～🌟"

# ---- 梯形 ----
def detect_trapezoid(q: str):
    if not q: return None
    t = q.replace("：", ":").replace("，", ",").replace("。", ".")
    # 上底、下底、高
    m = re.search(r'梯形.*?上底[是為=]?\s*(\d+).*?下底[是為=]?\s*(\d+).*?高[是為=]?\s*(\d+)', t)
    if m: return {"a": int(m.group(1)), "b": int(m.group(2)), "h": int(m.group(3))}
    m = re.search(r'梯形.*?下底[是為=]?\s*(\d+).*?上底[是為=]?\s*(\d+).*?高[是為=]?\s*(\d+)', t)
    if m: return {"a": int(m.group(2)), "b": int(m.group(1)), "h": int(m.group(3))}
    # 若高不在最後，做寬鬆匹配
    m = re.search(r'梯形.*?上底[是為=]?\s*(\d+).*?下底[是為=]?\s*(\d+).*?(?:高|高度)[是為=]?\s*(\d+)', t)
    if m: return {"a": int(m.group(1)), "b": int(m.group(2)), "h": int(m.group(3))}
    return None

def trapezoid_step(stage:int, a:int, b:int, h:int):
    if stage==1:
        return f"把梯形想成**斜斜的舞台**或**斜坡**～上面窄、下面寬！\n已知 **上底 {a} 公分**、**下底 {b} 公分**、**高 {h} 公分**。\n你覺得面積會跟『上下兩底的平均』有關嗎？"
    if stage==2:
        return f"梯形面積：**面積 = (上底 + 下底) × 高 ÷ 2**。\n帶入：**({a} + {b}) × {h} ÷ 2 = ?**"
    area = (a + b) * h / 2
    area_str = f"{area:.2f}".rstrip('0').rstrip('.') if isinstance(area, float) else str(area)
    return f"算一算：**({a} + {b}) × {h} ÷ 2 = {area_str}**。\n所以梯形面積是 **{area_str} 平方公分**！就像平均一下上下兩邊，再乘上高度～💡"

# ---- 啟動/延續導引（統一接口）----
def try_start_guided_flow(user_msg: str):
    """
    依序嘗試六種圖形偵測，命中即啟動導引。
    回傳文字或 None（None 表示沒命中）
    """
    # 1) 長方形
    p = detect_rectangle(user_msg)
    if p:
        return start_flow("rectangle", p, rectangle_step(1, **p))
    # 2) 正方形
    p = detect_square(user_msg)
    if p:
        return start_flow("square", p, square_step(1, **p))
    # 3) 三角形
    p = detect_triangle(user_msg)
    if p:
        return start_flow("triangle", p, triangle_step(1, **p))
    # 4) 圓形
    p = detect_circle(user_msg)
    if p:
        return start_flow("circle", p, circle_step(1, **p))
    # 5) 菱形
    p = detect_rhombus(user_msg)
    if p:
        return start_flow("rhombus", p, rhombus_step(1, **p))
    # 6) 梯形
    p = detect_trapezoid(user_msg)
    if p:
        return start_flow("trapezoid", p, trapezoid_step(1, **p))

    return None

def continue_guided_flow(user_msg: str):
    topic = session.get("guided_topic")
    params = session.get("guided_params", {})
    if topic == "rectangle":
        return next_step_or_finish(topic, lambda stage, **kw: rectangle_step(stage, **kw))
    if topic == "square":
        return next_step_or_finish(topic, lambda stage, **kw: square_step(stage, **kw))
    if topic == "triangle":
        return next_step_or_finish(topic, lambda stage, **kw: triangle_step(stage, **kw))
    if topic == "circle":
        return next_step_or_finish(topic, lambda stage, **kw: circle_step(stage, **kw))
    if topic == "rhombus":
        return next_step_or_finish(topic, lambda stage, **kw: rhombus_step(stage, **kw))
    if topic == "trapezoid":
        return next_step_or_finish(topic, lambda stage, **kw: trapezoid_step(stage, **kw))
    # 萬一 topic 已丟失，安全回落
    return ask_anan(user_msg, mode="socratic")

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

            # A) 若目前在導引中 → 繼續三步流程
            if session.get("guided_topic") in GUIDED_TOPICS:
                reply_text = continue_guided_flow(user_msg)

            # B) 嘗試新啟動導引
            if reply_text is None:
                reply_text = try_start_guided_flow(user_msg)

            # C) 其他一般題目 → 走 Socratic/normal 策略
            if reply_text is None:
                mode = "normal" if session.get("confused_count", 0) >= 2 else "socratic"
                reply_text = ask_anan(user_msg, mode)
                session["last_mode"] = "text"

            # 記錄對話
            conversation.append({"role": "user", "content": user_msg})
            conversation.append({"role": "assistant", "content": reply_text})
            session["conversation"] = conversation

            # 給 feedback 用的上下文
            session["last_question"] = user_msg
            session["last_answer"] = reply_text
            if session.get("guided_topic") not in GUIDED_TOPICS:
                session.setdefault("last_mode", "text")

            # 紀錄 DB
            conn = get_conn()
            topic_name = session.get("guided_topic") if session.get("guided_topic") in GUIDED_TOPICS else "一般"
            conn.execute("INSERT INTO records (user_id, question, topic, is_correct) VALUES (?, ?, ?, ?)",
                         (session["user_id"], user_msg, topic_name, None))
            conn.commit()
            conn.close()

    return render_template("index.html", conversation=conversation)

# -------------------------------
# 🧭 不懂（圖片題/文字題皆三步封頂，本地即時）
# -------------------------------
def simplify_text_answer_base(question: str, answer: str) -> str:
    q = (question or "").strip()
    a = normalize_math_terms((answer or "").strip())
    blocks = []
    if q:
        blocks.append(f"【題目重點】{q}")
    concept = "先判斷要用哪種運算或公式（例如：乘法、面積公式、比例、方程）。"
    if any(k in a for k in ["面積", "長 × 寬", "乘法", "平方公分", "π"]):
        concept = "這題是『面積思路』：先找正確公式，再把數字帶入。"
    blocks.append(f"【做法提示】{concept}")
    blocks.append("【計算步驟】1) 列條件 2) 套公式 3) 代數字 4) 寫單位。")
    blocks.append("如果你願意，我可以針對你卡住的那一步，再用更慢的節奏講一次～")
    return "\n".join(blocks)

@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json()
    understood = data.get("understood")
    if understood is None:
        return jsonify({"status": "error"})

    if understood:
        session["confused_count"] = 0
        for k in ["last_mode", "last_question", "last_answer"]:
            session.pop(k, None)
        return jsonify({"status": "ok", "reply": "太棒了～安安替你開心 💪"})

    session["confused_count"] = session.get("confused_count", 0) + 1
    count = session["confused_count"]

    last_q = session.get("last_question", "")
    last_a = session.get("last_answer", "")

    if count == 1:
        if session.get("last_mode") == "image":
            reply = "沒關係，我再用更簡單的方式說一次，跟著我一步步來 👇\n" + (last_a.split("\n")[0] if last_a else "先列條件→找對概念→代入數字→寫單位。")
        else:
            reply = "沒關係，我先用更簡單的方式說一次，跟著我一步步來 👇\n" + simplify_text_answer_base(last_q, last_a)
    elif count == 2:
        reply = "我們再壓縮重點：\n1) 找出題目要算的量；2) 用正確的公式或性質；3) 代入數字計算；4) 檢查單位。\n你卡在「找公式」還是「代入計算」呢？"
    else:
        if session.get("last_mode") == "image":
            reply = "好的，我直接給最簡單定稿版：把條件列清楚 → 找對公式 → 代入數字 → 檢查單位。這樣照做就能得到正確答案～"
        else:
            reply = ask_anan("請直接用最簡單明確的方式重講上一題，列出算式與答案。", mode="normal")
        session["confused_count"] = 0

    return jsonify({"status": "ok", "reply": normalize_math_terms(reply)})

# -------------------------------
# 🗑️ 清除對話（重置所有狀態）
# -------------------------------
@app.route("/clear")
def clear():
    for k in ["conversation", "confused_count",
              "guided_topic", "guided_params", "guided_stage",
              "last_mode", "last_question", "last_answer"]:
        session.pop(k, None)
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

    # 標記圖片題上下文，供 /feedback 使用
    session["last_mode"] = "image"
    session["last_question"] = "📷 [上傳了數學題目圖片]"
    session["last_answer"] = result

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
