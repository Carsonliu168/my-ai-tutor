# ================================
# 📘 安安專案主程式 app.py
# v4.3.7：
# - 統一「不懂」三步封頂邏輯：文字題與圖片題皆本地即時簡化前兩步，第3步定稿
# - 保留：繁體化 + 術語正規化 + 長方形三步導引 + 圖片備援 + /clear 修復 + SQLite 紀錄
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
        s = re.sub(r'\blcm\b', '最小公倍數', s, flags=re.IGNORECASE)
        s = re.sub(r'\bgcd\b', '最大公因數', s, flags=re.IGNORECASE)
        s = re.sub(r'\bmod\b', '模（取餘數）', s, flags=re.IGNORECASE)
        s = s.replace("质数", "質數").replace("质因数", "質因數").replace("余数", "餘數")
        s = s.replace("最小公倍数", "最小公倍數").replace("最大公约数", "最大公因數")
        s = s.replace("这", "這").replace("个", "個").replace("写", "寫").replace("为", "為")
    except Exception:
        pass
    return s

# -------------------------------
# 🧠 DeepSeek / GPT 模型
# -------------------------------
def ask_anan(question: str, mode="socratic"):
    style = "採用蘇格拉底式提問法，引導學生思考，不直接給答案。" if mode == "socratic" else "用正常教學方式清楚給出解題步驟與答案。"
    system_prompt = f"""
你是「數學小老師安安」，一位專業、親切、幽默的數學教學助理。
請務必使用「繁體中文（臺灣用語）」回答。
若題目是簡體或英文，請先轉成繁體再解說。
解題規範：
- 術語請用中文為主（例如：最小公倍數、最大公因數、模運算）
- 若出現模運算，請說明它代表取餘數的意思。
- 用親切、鼓勵的語氣引導學生。
- {style}
"""
    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat","messages":[{"role":"system","content":system_prompt},{"role":"user","content":question}]}
        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=40)
        return normalize_math_terms(r.json().get("choices",[{}])[0].get("message",{}).get("content",""))
    except:
        try:
            backup_headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            payload["model"] = "gpt-4o-mini"
            r2 = requests.post("https://api.openai.com/v1/chat/completions", headers=backup_headers, json=payload, timeout=40)
            return normalize_math_terms(r2.json().get("choices",[{}])[0].get("message",{}).get("content",""))
        except:
            return "（無回應）"

# -------------------------------
# 📊 SQLite 初始化
# -------------------------------
DB_PATH = "data/anan.db"
os.makedirs("data", exist_ok=True)
def get_conn(): return sqlite3.connect(DB_PATH, check_same_thread=False)
def init_db():
    conn = get_conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, question TEXT, topic TEXT,
        is_correct INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit(); conn.close()
    print("✅ [安安] 資料庫就緒 (v4.3.7)")
init_db()

# -------------------------------
# 🎯 長方形三步互動導引
# -------------------------------
RECTANGLE_TOPIC = "rectangle_area_v437"
def detect_rectangle_area(q: str):
    if not q: return None
    t = q.replace("：",":").replace("，",",").replace("。",".")
    m = re.search(r'長方形.*?長[是為=]?\s*(\d+).*寬[是為=]?\s*(\d+)',t)
    if not m:
        m = re.search(r'長方形.*?寬[是為=]?\s*(\d+).*長[是為=]?\s*(\d+)',t)
        if m: return int(m.group(2)),int(m.group(1))
        return None
    return int(m.group(1)),int(m.group(2))

def rectangle_step_prompt(stage,L,W):
    if stage==1: return f"安安老師：我們一起來想想這題吧～ 😊\n題目說：一個長方形的長是 **{L} 公分**，寬是 **{W} 公分**。\n那你還記得長方形的**面積要怎麼算**嗎？是用**加法**還是**乘法**呢？🤔"
    if stage==2: return f"太好了～長方形的面積要用**乘法**！\n公式是：**面積 = 長 × 寬**。\n把數字帶進去：**{L} × {W} = ?**\n你來算算看是多少呢？😉"
    area=L*W
    return f"安安來幫你算這個長方形的面積喔！\n\n長方形的面積公式是：\n**面積 = 長 × 寬**\n\n題目給的長是 **{L} 公分**，寬是 **{W} 公分**，\n所以我們來算一下：\n**{L} × {W} = {area}**\n\n答案就是 **{area} 平方公分**～\n\n很簡單對吧？記得面積的單位是「平方公分」喔！如果有其他問題，隨時問我～ 😊"

def start_rectangle_flow(L,W):
    session["guided_topic"]=RECTANGLE_TOPIC;session["guided_params"]={"L":L,"W":W};session["guided_stage"]=1
    return rectangle_step_prompt(1,L,W)

def continue_rectangle_flow(txt):
    s=int(session.get("guided_stage",1));p=session.get("guided_params",{})
    L,W=int(p.get("L",0)),int(p.get("W",0))
    if not L or not W: session.clear();return ask_anan(txt)
    if s<=1: session["guided_stage"]=2;return rectangle_step_prompt(2,L,W)
    if s==2: session["guided_stage"]=3;return rectangle_step_prompt(3,L,W)
    session.pop("guided_topic",None);session.pop("guided_params",None);session.pop("guided_stage",None)
    return ask_anan(txt)

# -------------------------------
# 💬 主頁
# -------------------------------
@app.before_request
def ensure_user():
    if "user_id" not in session: session["user_id"]=str(uuid.uuid4())

@app.route("/",methods=["GET","POST"])
def home():
    if "conversation" not in session:
        session["conversation"]=[];session["confused_count"]=0
    conv=session["conversation"]
    if request.method=="POST":
        msg=request.form.get("message","")
        if msg:
            reply=None
            if session.get("guided_topic")==RECTANGLE_TOPIC: reply=continue_rectangle_flow(msg)
            if reply is None:
                p=detect_rectangle_area(msg)
                if p: reply=start_rectangle_flow(*p)
            if reply is None:
                mode="normal" if session.get("confused_count",0)>=2 else "socratic"
                reply=ask_anan(msg,mode);session["last_mode"]="text"
            conv.append({"role":"user","content":msg});conv.append({"role":"assistant","content":reply})
            session["conversation"]=conv
            session["last_question"]=msg;session["last_answer"]=reply
            conn=get_conn();conn.execute("INSERT INTO records (user_id,question,topic,is_correct) VALUES (?,?,?,?)",
                (session["user_id"],msg,"長方形面積" if session.get("guided_topic")==RECTANGLE_TOPIC else "一般",None))
            conn.commit();conn.close()
    return render_template("index.html",conversation=conv)

# -------------------------------
# 🧭 統一三步封頂「不懂」邏輯
# -------------------------------
@app.route("/feedback",methods=["POST"])
def feedback():
    data=request.get_json();understood=data.get("understood")
    if understood is None: return jsonify({"status":"error"})
    if understood:
        session["confused_count"]=0
        for k in ["last_mode","last_question","last_answer"]: session.pop(k,None)
        return jsonify({"status":"ok","reply":"太棒了～安安替你開心 💪"})
    session["confused_count"]=session.get("confused_count",0)+1;count=session["confused_count"]
    last_q=session.get("last_question","");last_a=session.get("last_answer","")
    # 簡化文字題重述
    def simplify_text(q,a):
        a=normalize_math_terms(a or "");return f"沒關係，我先用更簡單的方式說一次，跟著我一步步來 👇\n【題目重點】{q}\n【做法提示】先判斷要用哪種運算/公式（例如：乘法、加法、面積公式等）。\n【步驟建議】1) 列條件 2) 套公式 3) 代數字 4) 寫單位。"
    # 簡化圖片題重述
    def simplify_image(a):
        a=normalize_math_terms(a or "");return "沒關係，我再用更簡單的方式說一次，跟著我一步步來 👇\n" + a.split("\n")[0]
    if count==1:
        if session.get("last_mode")=="image": reply=simplify_image(last_a)
        else: reply=simplify_text(last_q,last_a)
    elif count==2:
        reply="我們再壓縮重點：\n1) 找出題目要算的量；2) 用正確的公式或性質；3) 代入數字計算；4) 檢查單位。你卡在哪一步呢？"
    else:
        if session.get("last_mode")=="image":
            reply="好的，我直接給最簡單定稿版：條件列清楚 → 找對公式 → 代入數字 → 檢查單位。這樣照做就能得到正確答案～"
        else:
            reply=ask_anan("請直接用最簡單明確的方式重講上一題，列出算式與答案。",mode="normal")
        session["confused_count"]=0
    return jsonify({"status":"ok","reply":normalize_math_terms(reply)})

# -------------------------------
# 🗑️ 清除對話
# -------------------------------
@app.route("/clear")
def clear():
    for k in ["conversation","confused_count","guided_topic","guided_params","guided_stage",
              "last_mode","last_question","last_answer"]:
        session.pop(k,None)
    return redirect("/")

# -------------------------------
# 🧮 圖片解題（Gemini + GPT 備援）
# -------------------------------
ALLOWED_EXTENSIONS={'png','jpg','jpeg','gif','bmp','webp'}
def allowed_file(f): return '.' in f and f.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS
@app.route("/analyze_image",methods=["POST"])
def analyze_image():
    if "image" not in request.files: return jsonify({"result":"⚠️ 沒有收到圖片"}),400
    f=request.files["image"]
    if f.filename=='' or not allowed_file(f.filename): return jsonify({"result":"⚠️ 圖片格式錯誤"}),400
    b=f.read();result=None
    try:
        print("🔵 嘗試使用 Gemini 模型中...")
        m=genai.GenerativeModel("gemini-1.5-flash")
        r=m.generate_content(["你是台灣數學老師安安，請用繁體中文逐步講解圖片題。"
            "先整理條件→指出概念→逐步計算→驗證答案。術語請用中文。",{"mime_type":"image/jpeg","data":b}])
        result=r.text
    except Exception as e: print(f"⚠️ Gemini 失敗：{e}")
    if not result:
        try:
            print("🟢 使用 GPT-4o 備援中...")
            b64=base64.b64encode(b).decode("utf-8")
            h={"Authorization":f"Bearer {openai_api_key}","Content-Type":"application/json"}
            p={"model":"gpt-4o","messages":[{"role":"user","content":[
                {"type":"text","text":"你是台灣數學老師安安，請用繁體中文詳細逐步解這張圖片題。"},
                {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}]}],"max_tokens":1000}
            r=requests.post("https://api.openai.com/v1/chat/completions",headers=h,json=p,timeout=60)
            result=r.json()["choices"][0]["message"]["content"]
        except Exception as e: return jsonify({"result":f"⚠️ 辨識失敗：{e}"}),500
    result=normalize_math_terms(result)
    session["last_mode"]="image";session["last_question"]="📷 [上傳了數學題目圖片]";session["last_answer"]=result
    if "conversation" not in session: session["conversation"]=[]
    session["conversation"].append({"role":"user","content":"📷 [上傳了數學題目圖片]"})
    session["conversation"].append({"role":"assistant","content":result})
    session.modified=True
    return jsonify({"result":result,"success":True}),200

# -------------------------------
# 🚀 啟動
# -------------------------------
if __name__=="__main__":
    port=int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0",port=port)
