# ================================
# 📘 安安專案主程式 app.py
# v4.8.3-stable：
# - 自動健康檢查 /health /smoke
# - Session 容量預警
# - Gemini 模型更新 gemini-1.5-flash-latest
# - 全面繁體化、教學邏輯不變
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, base64, requests, sqlite3, uuid, re
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# -------------------------------
# ✅ Session 與模式設定
# -------------------------------
session_lifetime_days = int(os.getenv("SESSION_LIFETIME_DAYS", "30"))
app.permanent_session_lifetime = timedelta(days=session_lifetime_days)
DEMO_MODE = os.getenv("DEMO_MODE", "False").lower() == "true"

# -------------------------------
# ✅ 環境變數檢查
# -------------------------------
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")
google_api_key = os.getenv("GOOGLE_API_KEY")

print("🔍 環境變數檢查：")
print("✅ DEEPSEEK_API_KEY" if deepseek_api_key else "⚠️ 未設定 DeepSeek")
print("✅ OPENAI_API_KEY" if openai_api_key else "⚠️ 未設定 OpenAI")
print("✅ GOOGLE_API_KEY" if google_api_key else "⚠️ 未設定 Google")

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
    s = s.replace("质","質").replace("余数","餘數").replace("约数","約數")
    s = s.replace("这","這").replace("个","個").replace("写","寫").replace("为","為")
    return s

def is_pure_help_phrase(msg: str) -> bool:
    return bool(re.fullmatch(r'\s*(我不會|不會|不懂|看不懂)\s*', msg or ""))

def brief_history(max_items=4):
    convo = session.get("conversation", [])
    if not convo: return ""
    tail = convo[-max_items:]
    lines = []
    for m in tail:
        role = "學生" if m.get("role") == "user" else "安安"
        content = (m.get("content") or "").strip()
        content = re.sub(r'\s+', ' ', content)
        lines.append(f"{role}：{content}")
    return "\n".join(lines)

# -------------------------------
# 🧠 DeepSeek / GPT 備援邏輯
# -------------------------------
def ask_anan(question, mode="socratic", history_text=""):
    style = "採用蘇格拉底式提問法，引導學生思考。" if mode=="socratic" else "用清楚步驟給出答案。"
    rules = """
教學規範：
- 答對立即肯定並收尾。
- 答錯或說「不懂」時才引導。
- 使用台灣繁體中文，口吻親切。
"""
    system_prompt = f"你是數學老師安安。{style}\n{rules}"

    messages = [{"role":"system","content":system_prompt}]
    if history_text:
        messages.append({"role":"user","content":f"[history]\n{history_text}"})
        messages.append({"role":"assistant","content":"（收到上方脈絡）"})
    messages.append({"role":"user","content":question})

    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat","messages": messages,"temperature":0.3}
        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=35)
        reply = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
        if reply: return normalize_math_terms(reply)
    except Exception as e:
        print("DeepSeek 失敗:", e)

    try:
        if not openai_api_key: raise RuntimeError("未設定 OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
        payload2 = {"model":"gpt-4o-mini","messages":messages,"temperature":0.3}
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload2, timeout=35)
        reply = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
        if reply: return normalize_math_terms(reply)
    except Exception as e:
        print("OpenAI 備援失敗:", e)

    return "（目前伺服器忙碌，稍後再試 🙏）"

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
    print("✅ [安安] 資料庫就緒 (v4.8.3)")
init_db()

# -------------------------------
# 💬 不懂邏輯
# -------------------------------
TEACHER_HINT = "安安發現你還是有點困惑，建議明天問老師，他一定會幫你解釋得更仔細！"
def next_help_response(counter_name):
    c = session.get(counter_name, 0) + 1
    session[counter_name] = c
    if c == 1:
        return "沒關係，我再簡單講一次：找公式→代入→計算→加單位。"
    elif c == 2:
        return "我們換個說法試試～你記得剛剛的公式是哪一個嗎？"
    elif c == 3:
        hist = brief_history(4)
        return ask_anan("請用最簡單方式重講上一題，清楚列出公式、代入與答案。", mode="normal", history_text=hist)
    else:
        session[counter_name] = 3
        return TEACHER_HINT

# -------------------------------
# 🖼️ analyze_image
# -------------------------------
ALLOWED = {'png','jpg','jpeg'}
def allow(f): return '.' in f and f.rsplit('.',1)[1].lower() in ALLOWED

@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"result":"⚠️ 沒有收到圖片"}),400
    img = request.files["image"]
    if img.filename=='' or not allow(img.filename):
        return jsonify({"result":"⚠️ 圖片格式錯誤"}),400
    data = img.read(); res = None

    instruction = (
        "你是台灣數學老師安安，用繁體中文逐步講解這張圖片題："
        "1) 辨識題目；2) 寫公式；3) 代入；4) 算答案與單位；"
        "5) 若學生答對，直接肯定，不延伸其他主題。"
    )
    try:
        if not google_api_key or genai is None:
            raise RuntimeError("未設定 GOOGLE_API_KEY")
        model = genai.GenerativeModel("gemini-1.5-flash-latest")
        r = model.generate_content([instruction, {"mime_type":"image/jpeg","data":data}],
            generation_config={"max_output_tokens":1024})
        res = r.text
    except Exception as e:
        print("Gemini 失敗：", e)

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
            return jsonify({"result":f"⚠️ 圖片辨識不可用：{e}"}),500

    res = normalize_math_terms(res)
    session["guided_topic"] = "image_explain"
    session["image_b64"] = base64.b64encode(data).decode()
    session["image_confused_count"] = 0
    convo = session.setdefault("conversation", [])
    convo.append({"role":"user","content":"📷 [圖片題]（已上傳）請講解。"})
    convo.append({"role":"assistant","content":res})
    session.modified = True
    return jsonify({"result":res,"success":True}),200

# -------------------------------
# 💬 主要對話邏輯
# -------------------------------
@app.before_request
def ensure_user():
    if "user_id" not in session: session["user_id"]=str(uuid.uuid4())
    session.permanent = True

@app.route("/", methods=["GET","POST"])
def home():
    convo=session.setdefault("conversation",[])
    if request.method=="POST":
        msg=request.form.get("message","").strip()
        if not msg: return render_template("index.html",conversation=convo)
        if is_pure_help_phrase(msg):
            key="image_confused_count" if session.get("guided_topic")=="image_explain" else "confused_count"
            reply=next_help_response(key)
            convo.append({"role":"user","content":msg})
            convo.append({"role":"assistant","content":normalize_math_terms(reply)})
            session["conversation"]=convo
            return render_template("index.html",conversation=convo)

        session["confused_count"]=0; session["image_confused_count"]=0
        hist=brief_history(6)
        reply=ask_anan(msg,"socratic",hist)
        convo.append({"role":"user","content":msg})
        convo.append({"role":"assistant","content":reply})
        session["conversation"]=convo

        try:
            conn=get_conn()
            conn.execute("INSERT INTO records (user_id,question,topic,is_correct) VALUES (?,?,?,?)",
                (session["user_id"],msg,session.get("guided_topic","一般"),None))
            conn.commit(); conn.close()
        except Exception as e:
            print("寫入 records 失敗：", e)

    # Session 大小警告
    try:
        size=len(json.dumps(session,ensure_ascii=False).encode())
        if size>3000: print(f"⚠️ Session 逼近上限：{size} bytes")
    except: pass

    return render_template("index.html",conversation=convo)

# -------------------------------
# 📩 feedback
# -------------------------------
@app.route("/feedback", methods=["POST"])
def feedback():
    d=request.get_json(); under=d.get("understood")
    if under is None: return jsonify({"status":"error"})
    if under:
        session["confused_count"]=0; session["image_confused_count"]=0
        return jsonify({"status":"ok","reply":"太棒了～安安替你開心 💪 下次挑戰更難一點！"})
    key="image_confused_count" if session.get("guided_topic")=="image_explain" else "confused_count"
    reply=next_help_response(key)
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
# 🩺 健康檢查與煙霧測試
# -------------------------------
@app.route("/health")
def health():
    keys={"deepseek":bool(deepseek_api_key),"openai":bool(openai_api_key),"google":bool(google_api_key)}
    db_ok=True
    try:
        conn=get_conn(); conn.execute("SELECT 1"); conn.close()
    except: db_ok=False
    return jsonify({"ok":all(keys.values()) and db_ok,"keys":keys,"db_ok":db_ok,"version":"v4.8.3-stable"}),200

@app.route("/smoke")
def smoke():
    session["smoke"]=datetime.utcnow().isoformat()
    return jsonify({"ok":True,"session":session.get("smoke")}),200

# -------------------------------
# 🚀 run
# -------------------------------
if __name__=="__main__":
    port=int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0",port=port)
