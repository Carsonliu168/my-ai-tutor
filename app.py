# ================================
# 📘 安安專案主程式 app.py
# v4.8-fixes：
# 1) 對話教學邏輯修正：答對就肯定與總結，不再無關延伸（仍保留蘇格拉底引導於答錯/不懂時）
# 2) 圖片題承接記憶：把圖片題指示與回覆寫入同一段 conversation，後續問題帶入精簡歷史
# 3) 容錯訊息更清楚；備援順序維持：文字 DeepSeek→OpenAI；圖片 Gemini→OpenAI
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, base64, requests, sqlite3, uuid, re
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制 16MB

# -------------------------------
# ✅ 登入/Session 設定
# -------------------------------
session_lifetime_days = int(os.getenv("SESSION_LIFETIME_DAYS", "30"))
app.permanent_session_lifetime = timedelta(days=session_lifetime_days)
DEMO_MODE = os.getenv("DEMO_MODE", "False").lower() == "true"

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
    genai = None

# -------------------------------
# 🧩 工具函式
# -------------------------------
def normalize_math_terms(s: str) -> str:
    if not s:
        return s
    s = re.sub(r'\blcm\b', '最小公倍數', s, flags=re.IGNORECASE)
    s = re.sub(r'\bgcd\b', '最大公因數', s, flags=re.IGNORECASE)
    s = re.sub(r'\bmod\b', '模（取餘數）', s, flags=re.IGNORECASE)
    s = s.replace("质数","質數").replace("质因数","質因數").replace("余数","餘數")
    s = s.replace("最小公倍数","最小公倍數").replace("最大公约数","最大公因數")
    s = s.replace("这","這").replace("个","個").replace("写","寫").replace("为","為")
    return s

def is_pure_help_phrase(msg: str) -> bool:
    """判斷是否為純粹『我不懂／我不會／看不懂』"""
    return bool(re.fullmatch(r'\s*(我不會|不會|不懂|看不懂)\s*', msg or ""))

def brief_history(max_items=4):
    """從 session.conversation 擷取最近對話，壓縮為乾淨的純文字，提供 LLM 當精簡脈絡"""
    convo = session.get("conversation", [])
    if not convo: return ""
    # 取最近 N 則訊息（user/assistant 混合），轉成短行文字
    tail = convo[-max_items:]
    lines = []
    for m in tail:
        role = "學生" if m.get("role") == "user" else "安安"
        content = (m.get("content") or "").strip()
        content = re.sub(r'\s+', ' ', content)
        lines.append(f"{role}：{content}")
    return "\n".join(lines)

# -------------------------------
# 🧠 DeepSeek / GPT（備援：文字 → DeepSeek → OpenAI）
# -------------------------------
def ask_anan(question, mode="socratic", history_text=""):
    """
    mode:
      - "socratic": 蘇格拉底引導（預設）
      - "normal": 清楚步驟講解
    history_text: 傳入最近幾輪對話，讓模型知道學生是否剛剛已答對
    """
    style = "採用蘇格拉底式提問法，引導學生思考。" if mode=="socratic" else "用清楚步驟給出答案。"
    rules = """
教學規範補充（極重要）：
- 如果學生的最新回覆已是正確答案，請「立即」肯定、重述關鍵公式與單位，簡短收尾，不要再延伸到無關主題。
- 只有在學生答錯、概念混淆或回覆『我不懂/不會』時，才使用蘇格拉底式追問與引導。
- 文字風格用臺灣繁體中文、口吻親切鼓勵、重點條列清楚。
"""
    system_prompt = f"""你是台灣數學小老師安安。
請使用繁體中文（臺灣用語），親切、幽默地教學。
- 術語用中文（最小公倍數、最大公因數、模運算等）。
- 用鼓勵的語氣引導學生。
- {style}
{rules}
若提供了對話脈絡 history，請先判斷學生是否剛剛已答對，並遵守上述規則。
"""

    # 構建 messages，附帶精簡歷史（讓模型能判斷上一輪是否答對）
    messages = [{"role":"system","content":system_prompt}]
    if history_text:
        messages.append({"role":"user","content":f"[history]\n{history_text}"})
        messages.append({"role":"assistant","content":"（收到上方脈絡）"})
    messages.append({"role":"user","content":question})

    # 先試 DeepSeek
    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat","messages": messages,"temperature":0.3}
        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=35)
        reply = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
        if reply: return normalize_math_terms(reply)
    except Exception as e:
        print("DeepSeek 失敗:", e)

    # 備援 OpenAI
    try:
        if not openai_api_key: raise RuntimeError("未設定 OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
        payload2 = {"model":"gpt-4o-mini","messages":messages,"temperature":0.3}
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload2, timeout=35)
        reply = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
        if reply: return normalize_math_terms(reply)
    except Exception as e:
        print("OpenAI 備援失敗:", e)

    return "（目前連線較忙碌，稍後再試一次或換個說法提問喔 🙏）"

# -------------------------------
# 📊 SQLite 初始化
# -------------------------------
DB_PATH = "data/anan.db"
os.makedirs("data", exist_ok=True)
def get_conn(): return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS records(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT, question TEXT, topic TEXT,
    is_correct INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit(); conn.close()
    print("✅ [安安] 資料庫就緒 (v4.8-fixes)")
init_db()

# -------------------------------
# 💬 不懂邏輯共用：三次後建議請教老師
# -------------------------------
TEACHER_HINT = "安安發現你還是有點困惑，這很正常喔。建議你把這題抄下來，明天上課時問老師，他一定會替你解釋得更仔細！"

def next_help_response(counter_name):
    """控制第1~4次不懂的回應"""
    c = session.get(counter_name, 0) + 1
    session[counter_name] = c
    if c == 1:
        return "沒關係，我再簡單講一次：找對公式→代入數字→計算→加單位。"
    elif c == 2:
        return "我們換個說法試試～你記得剛剛的公式是哪一個嗎？"
    elif c == 3:
        # 第三次改為『直接再講一次重點步驟』
        hist = brief_history(4)
        return ask_anan("請用最簡單方式重講上一題，清楚列出公式、代入與答案。", mode="normal", history_text=hist)
    else:
        session[counter_name] = 3
        return TEACHER_HINT

# -------------------------------
# 🧮 analyze_image（含圖片記憶；圖片 → Gemini →（備援）OpenAI）
# -------------------------------
ALLOWED = {'png','jpg','jpeg'}
def allow(f): return '.' in f and f.rsplit('.',1)[1].lower() in ALLOWED

@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files: return jsonify({"result":"⚠️ 沒有收到圖片"}),400
    img = request.files["image"]
    if img.filename=='' or not allow(img.filename): return jsonify({"result":"⚠️ 圖片格式錯誤（支援 png/jpg/jpeg）"}),400
    data = img.read(); res = None

    instruction = (
        "你是台灣數學老師安安，請用繁體中文逐步講解這張圖片題："
        "1) 先辨識題目要做什麼；2) 寫出公式；3) 代入數字；4) 算出答案與單位；"
        "5) 若學生之後回覆的數字正確，請直接肯定與總結，不要延伸到不相干主題。"
    )

    # 先試 Gemini
    try:
        if not google_api_key or genai is None:
            raise RuntimeError("未設定 GOOGLE_API_KEY")
        model = genai.GenerativeModel("gemini-1.5-flash")
        r = model.generate_content(
            [instruction, {"mime_type":"image/jpeg","data":data}],
            generation_config={"max_output_tokens":1024}
        )
        res = r.text
    except Exception as e:
        print("Gemini 失敗：", e)

    # 備援 OpenAI
    if not res:
        try:
            if not openai_api_key: raise RuntimeError("未設定 OPENAI_API_KEY")
            b64 = base64.b64encode(data).decode()
            h = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            p = {"model":"gpt-4o","messages":[{"role":"user","content":[
                {"type":"text","text":instruction},
                {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}]}],"temperature":0.2}
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=h, json=p, timeout=60)
            res = r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return jsonify({"result":f"⚠️ 圖片辨識目前不可用：{e}"}),500

    res = normalize_math_terms(res)

    # 🩷 關鍵：把圖片題訊息 & 回覆寫入 conversation，並標記 guided_topic
    session["guided_topic"] = "image_explain"
    session["image_b64"] = base64.b64encode(data).decode()
    session["image_confused_count"] = 0
    if "conversation" not in session: session["conversation"]=[]
    session["conversation"].append({"role":"user","content":"📷 [圖片題]（已上傳）請講解。"})
    session["conversation"].append({"role":"assistant","content":res})
    session.modified = True

    return jsonify({"result":res,"success":True}),200

# -------------------------------
# 🧠 主要對話邏輯（帶精簡歷史給模型）
# -------------------------------
@app.before_request
def ensure_user():
    if "user_id" not in session: session["user_id"]=str(uuid.uuid4())
    session.permanent = True  # 讓 session 依照上方設定自動延長

@app.route("/", methods=["GET","POST"])
def home():
    if "conversation" not in session: session["conversation"]=[]; session["confused_count"]=0
    convo=session["conversation"]

    if request.method=="POST":
        msg=request.form.get("message","").strip()
        if not msg: return render_template("index.html",conversation=convo)

        # 純「不懂」→ 走不懂計數邏輯（圖片題/一般題各自累計）
        if is_pure_help_phrase(msg):
            if session.get("guided_topic")=="image_explain":
                reply = next_help_response("image_confused_count")
            else:
                reply = next_help_response("confused_count")
            convo.append({"role":"user","content":msg})
            convo.append({"role":"assistant","content":normalize_math_terms(reply)})
            session["conversation"]=convo
            return render_template("index.html",conversation=convo)

        # 重置困惑計數
        session["confused_count"]=0
        session["image_confused_count"]=0

        # 帶入最近對話歷史，讓模型判斷「學生是否已答對」
        hist = brief_history(6)
        reply = ask_anan(msg, mode="socratic", history_text=hist)

        convo.append({"role":"user","content":msg})
        convo.append({"role":"assistant","content":reply})
        session["conversation"]=convo

        # 記錄到 DB
        try:
            conn=get_conn()
            conn.execute("INSERT INTO records (user_id,question,topic,is_correct) VALUES (?,?,?,?)",
                        (session["user_id"],msg,session.get("guided_topic","一般"),None))
            conn.commit(); conn.close()
        except Exception as e:
            print("寫入 records 失敗：", e)

    return render_template("index.html",conversation=session["conversation"])

# -------------------------------
# 🧭 feedback 按鈕版
# -------------------------------
@app.route("/feedback", methods=["POST"])
def feedback():
    d=request.get_json(); under=d.get("understood")
    if under is None: return jsonify({"status":"error"})
    if under:
        session["confused_count"]=0; session["image_confused_count"]=0
        return jsonify({"status":"ok","reply":"太棒了～安安替你開心 💪 下次換你挑戰更難一點！"})
    if session.get("guided_topic")=="image_explain":
        reply = next_help_response("image_confused_count")
    else:
        reply = next_help_response("confused_count")
    return jsonify({"status":"ok","reply":normalize_math_terms(reply)})

# -------------------------------
# 🗑️ clear
# -------------------------------
@app.route("/clear")
def clear():
    for k in ["conversation","confused_count","guided_topic","image_b64","image_confused_count"]:
        session.pop(k,None)
    return redirect(url_for("home"))

# -------------------------------
# 🚀 run
# -------------------------------
if __name__=="__main__":
    port=int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0",port=port)
