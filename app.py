# ================================
# 📘 安安專案主程式 app.py
# v4.5.0：幾何導引＋周長導引完整版（共六型）
# - 面積：長方形、正方形、三角形、圓形、菱形、梯形
# - 周長：長方形、正方形、三角形、圓形
# - 三步互動式引導 + 生活化例子 + π=3.1416
# - 全繁體、備援模型、清除/feedback 正常
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
    s = re.sub(r'\blcm\b', '最小公倍數', s, flags=re.IGNORECASE)
    s = re.sub(r'\bgcd\b', '最大公因數', s, flags=re.IGNORECASE)
    s = re.sub(r'\bmod\b', '模（取餘數）', s, flags=re.IGNORECASE)
    s = s.replace("质数","質數").replace("质因数","質因數").replace("余数","餘數")
    s = s.replace("最小公倍数","最小公倍數").replace("最大公约数","最大公因數")
    s = s.replace("这","這").replace("个","個").replace("写","寫").replace("为","為")
    return s

# -------------------------------
# 🧠 DeepSeek / GPT 文本模型
# -------------------------------
def ask_anan(question, mode="socratic"):
    style = "採用蘇格拉底式提問法，引導學生思考。" if mode=="socratic" else "用清楚步驟給出答案。"
    system_prompt = f"""你是台灣數學小老師安安。
請使用繁體中文（臺灣用語），親切、幽默地教學。
教學規範：
- 術語用中文（最小公倍數、最大公因數、模運算等）。
- 用鼓勵的語氣引導學生。
- {style}
"""
    try:
        headers={"Authorization":f"Bearer {deepseek_api_key}","Content-Type":"application/json"}
        payload={"model":"deepseek-chat","messages":[{"role":"system","content":system_prompt},{"role":"user","content":question}]}
        r=requests.post("https://api.deepseek.com/chat/completions",headers=headers,json=payload,timeout=40)
        reply=r.json().get("choices",[{}])[0].get("message",{}).get("content","")
        return normalize_math_terms(reply)
    except:
        try:
            headers={"Authorization":f"Bearer {openai_api_key}","Content-Type":"application/json"}
            payload["model"]="gpt-4o-mini"
            r=requests.post("https://api.openai.com/v1/chat/completions",headers=headers,json=payload,timeout=40)
            reply=r.json().get("choices",[{}])[0].get("message",{}).get("content","")
            return normalize_math_terms(reply)
        except:
            return "（無回應）"

# -------------------------------
# 📊 SQLite 紀錄
# -------------------------------
DB_PATH="data/anan.db"
os.makedirs("data",exist_ok=True)
def get_conn(): return sqlite3.connect(DB_PATH,check_same_thread=False)
def init_db():
    conn=get_conn();c=conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS records(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT, question TEXT, topic TEXT,
    is_correct INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit();conn.close()
    print("✅ [安安] 資料庫就緒 (v4.5.0)")
init_db()

# =========================================================
# 🎯 幾何導引＋周長導引
# =========================================================
PI=3.1416
GUIDED_TOPICS={"rectangle","square","triangle","circle","rhombus","trapezoid",
               "rectangle_p","square_p","triangle_p","circle_p"}

def start_flow(topic,params,text):
    session["guided_topic"]=topic
    session["guided_params"]=params
    session["guided_stage"]=1
    return normalize_math_terms(text)

def next_step(topic,make_text):
    stage=int(session.get("guided_stage",1))
    params=session.get("guided_params",{})
    if not params:
        for k in ["guided_topic","guided_params","guided_stage"]:
            session.pop(k,None)
        return ask_anan("請重講上一題。",mode="normal")
    if stage<=1:
        session["guided_stage"]=2;return normalize_math_terms(make_text(2,**params))
    if stage==2:
        session["guided_stage"]=3;return normalize_math_terms(make_text(3,**params))
    for k in ["guided_topic","guided_params","guided_stage"]:
        session.pop(k,None)
    return ask_anan("請重講上一題。",mode="normal")

# ------------------- 面積六型 -------------------
def rect(q):
    m=re.search(r'長方形.*?長[是為=]?\s*(\d+).*寬[是為=]?\s*(\d+)',q)
    if m: return {"L":int(m.group(1)),"W":int(m.group(2))}
    m=re.search(r'長方形.*?寬[是為=]?\s*(\d+).*長[是為=]?\s*(\d+)',q)
    if m: return {"L":int(m.group(2)),"W":int(m.group(1))}
    return None
def rect_step(stage,L,W):
    if stage==1: return f"像課桌一樣的長方形，長 {L}、寬 {W}。面積要用加法還是乘法呢？"
    if stage==2: return f"面積 = 長 × 寬。帶入：{L} × {W} = ?"
    return f"算出：{L}×{W}={L*W}，面積是 {L*W} 平方公分！"

def square(q):
    m=re.search(r'正方形.*?(邊|邊長)[是為=]?\s*(\d+)',q)
    return {"S":int(m.group(2))} if m else None
def square_step(stage,S):
    if stage==1:return f"像棋盤格一樣的正方形，邊長 {S}。你覺得面積要怎麼算？"
    if stage==2:return f"面積 = 邊長 × 邊長 → {S}×{S}=?"
    return f"算出 {S}×{S}={S*S}，所以面積是 {S*S} 平方公分～"

def triangle(q):
    m=re.search(r'三角形.*?底[是為=]?\s*(\d+).*高[是為=]?\s*(\d+)',q)
    if not m:m=re.search(r'三角形.*?高[是為=]?\s*(\d+).*底[是為=]?\s*(\d+)',q)
    if m:return {"B":int(m.group(1)),"H":int(m.group(2))}
def tri_step(stage,B,H):
    if stage==1:return f"想像一片被切一半的蛋糕🍰，底 {B} 高 {H}。面積要不要除以 2 呢？"
    if stage==2:return f"面積 = 底×高÷2 → {B}×{H}÷2=?"
    area=B*H/2;return f"結果是 {area} 平方公分。"

def circle(q):
    m=re.search(r'圓.*?半徑[是為=]?\s*(\d+)',q)
    if m:return {"r":float(m.group(1))}
    m=re.search(r'圓.*?直徑[是為=]?\s*(\d+)',q)
    if m:return {"r":float(m.group(1))/2}
def cir_step(stage,r):
    if stage==1:return f"像披薩🍕，半徑 {r}。面積會用到 π 嗎？"
    if stage==2:return f"面積 = π×r²=3.1416×{r}²=?"
    a=PI*r*r;return f"答案：{a:.4f} 平方公分～"

def rhombus(q):
    m=re.findall(r'菱形.*?對角線(?:長)?[是為=]?\s*(\d+)',q)
    return {"d1":int(m[0]),"d2":int(m[1])} if len(m)>=2 else None
def rhom_step(stage,d1,d2):
    if stage==1:return f"像菱格窗🔷，對角線 {d1}、{d2}。面積會用到它們的乘積嗎？"
    if stage==2:return f"面積 = (d1×d2)÷2 = ({d1}×{d2})÷2=?"
    return f"面積 {d1*d2/2} 平方公分～"

def trape(q):
    m=re.search(r'梯形.*?上底[是為=]?\s*(\d+).*下底[是為=]?\s*(\d+).*高[是為=]?\s*(\d+)',q)
    if m:return {"a":int(m.group(1)),"b":int(m.group(2)),"h":int(m.group(3))}
def trap_step(stage,a,b,h):
    if stage==1:return f"像斜坡一樣的梯形，上底 {a} 下底 {b} 高 {h}。要不要取平均？"
    if stage==2:return f"面積 = (上底+下底)×高÷2 = ({a}+{b})×{h}÷2=?"
    return f"結果 {(a+b)*h/2} 平方公分。"

# ------------------- 周長四型 -------------------
def rect_p(q):
    m=re.search(r'長方形.*?長[是為=]?\s*(\d+).*寬[是為=]?\s*(\d+)',q)
    if m and re.search("周長|繞|圍",q):return {"L":int(m.group(1)),"W":int(m.group(2))}
def rectp_step(stage,L,W):
    if stage==1:return f"像桌子的外框線要貼邊，長 {L} 寬 {W}，你覺得要加幾次呢？"
    if stage==2:return f"周長 = (長+寬)×2 = ({L}+{W})×2=?"
    return f"算出 ({L}+{W})×2={(L+W)*2}，周長 {(L+W)*2} 公分。"

def square_p(q):
    m=re.search(r'正方形.*?邊長[是為=]?\s*(\d+)',q)
    if m and re.search("周長|圍|邊|繞",q):return {"S":int(m.group(1))}
def squarep_step(stage,S):
    if stage==1:return f"像便利貼邊框，邊 {S}。四條邊一樣長，要加幾次呢？"
    if stage==2:return f"周長 = 4×邊長 = 4×{S}=?"
    return f"算出 4×{S}={4*S}，周長 {4*S} 公分～"

def triangle_p(q):
    m=re.findall(r'三角形.*?邊[一二三]?[^0-9]*(\d+)',q)
    if len(m)>=3 and re.search("周長|繞|邊",q):return {"a":int(m[0]),"b":int(m[1]),"c":int(m[2])}
def trip_step(stage,a,b,c):
    if stage==1:return f"三角旗🎏的三邊 {a}、{b}、{c}。要算周長要怎麼做？"
    if stage==2:return f"周長 = 三邊相加 = {a}+{b}+{c}=?"
    return f"結果 {a+b+c} 公分～"

def circle_p(q):
    if re.search("圓.*半徑",q) and re.search("周長|圓周|繞",q):
        r=int(re.search(r'半徑[是為=]?\s*(\d+)',q).group(1));return {"r":r}
    if re.search("圓.*直徑",q) and re.search("周長|圓周|繞",q):
        d=int(re.search(r'直徑[是為=]?\s*(\d+)',q).group(1));return {"r":d/2}
def circp_step(stage,r):
    if stage==1:return f"想像繞著披薩邊走一圈🍕，半徑 {r}。要用 π 嗎？"
    if stage==2:return f"周長 = 2×π×r = 2×3.1416×{r}=?"
    return f"結果 {2*PI*r:.4f} 公分。"

# ------------------- 啟動與延續 -------------------
def try_start(msg):
    for f,topic,step in [
        (rect,"rectangle",rect_step),(square,"square",square_step),
        (triangle,"triangle",tri_step),(circle,"circle",cir_step),
        (rhombus,"rhombus",rhom_step),(trape,"trapezoid",trap_step),
        (rect_p,"rectangle_p",rectp_step),(square_p,"square_p",squarep_step),
        (triangle_p,"triangle_p",trip_step),(circle_p,"circle_p",circp_step)
    ]:
        p=f(msg)
        if p:return start_flow(topic,p,step(1,**p))
    return None

def continue_flow(msg):
    t=session.get("guided_topic");p=session.get("guided_params",{})
    mapping={
        "rectangle":rect_step,"square":square_step,"triangle":tri_step,
        "circle":cir_step,"rhombus":rhom_step,"trapezoid":trap_step,
        "rectangle_p":rectp_step,"square_p":squarep_step,
        "triangle_p":trip_step,"circle_p":circp_step
    }
    if t in mapping:return next_step(t,lambda s,**kw:mapping[t](s,**kw))
    return ask_anan(msg,mode="socratic")

# -------------------------------
# 💬 主頁與回饋
# -------------------------------
@app.before_request
def ensure_user():
    if "user_id" not in session:session["user_id"]=str(uuid.uuid4())

@app.route("/",methods=["GET","POST"])
def home():
    if "conversation" not in session:session["conversation"]=[];session["confused_count"]=0
    convo=session["conversation"]
    if request.method=="POST":
        msg=request.form.get("message","")
        if msg:
            reply=None
            if session.get("guided_topic") in GUIDED_TOPICS:
                reply=continue_flow(msg)
            if reply is None: reply=try_start(msg)
            if reply is None:
                mode="normal" if session.get("confused_count",0)>=2 else "socratic"
                reply=ask_anan(msg,mode)
            convo.append({"role":"user","content":msg})
            convo.append({"role":"assistant","content":reply})
            session["conversation"]=convo
            conn=get_conn()
            conn.execute("INSERT INTO records (user_id,question,topic,is_correct) VALUES (?,?,?,?)",
                         (session["user_id"],msg,session.get("guided_topic","一般"),None))
            conn.commit();conn.close()
    return render_template("index.html",conversation=session["conversation"])

# -------------------------------
# 🧭 feedback
# -------------------------------
@app.route("/feedback",methods=["POST"])
def feedback():
    d=request.get_json();under=d.get("understood")
    if under is None:return jsonify({"status":"error"})
    if under:
        session["confused_count"]=0;return jsonify({"status":"ok","reply":"太棒了～安安替你開心 💪"})
    session["confused_count"]=session.get("confused_count",0)+1;c=session["confused_count"]
    if c==1:reply="沒關係，我再簡單講一次：找對公式→代數字→算→加單位。"
    elif c==2:reply="我們換個說法試試～你記得剛剛的公式是哪一個嗎？"
    else:
        reply=ask_anan("請直接用最簡單方式重講上一題。",mode="normal");session["confused_count"]=0
    return jsonify({"status":"ok","reply":normalize_math_terms(reply)})

# -------------------------------
# 🗑️ clear
# -------------------------------
@app.route("/clear")
def clear():
    for k in ["conversation","confused_count","guided_topic","guided_params","guided_stage"]:
        session.pop(k,None)
    return redirect("/")

# -------------------------------
# 🧮 analyze_image (保留)
# -------------------------------
ALLOWED={'png','jpg','jpeg'}
def allow(f):return '.' in f and f.rsplit('.',1)[1].lower() in ALLOWED

@app.route("/analyze_image",methods=["POST"])
def analyze_image():
    if "image" not in request.files:return jsonify({"result":"⚠️ 沒有收到圖片"}),400
    img=request.files["image"]
    if img.filename==''or not allow(img.filename):return jsonify({"result":"⚠️ 圖片格式錯誤"}),400
    data=img.read();res=None
    try:
        model=genai.GenerativeModel("gemini-1.5-flash")
        r=model.generate_content([
            "你是台灣數學老師安安，用繁體中文逐步解圖片題。",
            {"mime_type":"image/jpeg","data":data}])
        res=r.text
    except Exception as e:print("Gemini 失敗",e)
    if not res:
        try:
            b64=base64.b64encode(data).decode()
            h={"Authorization":f"Bearer {openai_api_key}","Content-Type":"application/json"}
            p={"model":"gpt-4o","messages":[{"role":"user","content":[
                {"type":"text","text":"你是台灣數學老師安安，用繁體中文詳細逐步講解這張圖片題。"},
                {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}]}]}
            r=requests.post("https://api.openai.com/v1/chat/completions",headers=h,json=p,timeout=60)
            res=r.json()["choices"][0]["message"]["content"]
        except Exception as e:return jsonify({"result":f"⚠️ 辨識失敗:{e}"}),500
    res=normalize_math_terms(res)
    if "conversation" not in session:session["conversation"]=[]
    session["conversation"].append({"role":"user","content":"📷 [圖片題]"})
    session["conversation"].append({"role":"assistant","content":res})
    session.modified=True
    return jsonify({"result":res,"success":True}),200

# -------------------------------
# 🚀 run
# -------------------------------
if __name__=="__main__":
    port=int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0",port=port)
