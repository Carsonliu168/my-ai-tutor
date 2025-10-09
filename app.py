# ================================
# 📘 安安專案主程式 app.py
# v3.6：DeepSeek 主答 + GPT 圖像備援 + Vision OCR +
#       後台統計（圖表/篩選/匯出/週報）+ 自評回饋 + 使用時間追蹤 +
#       ✅ 新增自動判斷答題正確率 evaluate_answer()
# ================================

from flask import (
    Flask, render_template, request, jsonify, session,
    render_template_string, send_file
)
import os, json, base64, requests, sqlite3, uuid, csv, re
from datetime import datetime
from google.cloud import vision

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
ADMIN_KEY = os.getenv("ADMIN_KEY", "anan123")

# -------------------------------
# ✅ 啟動環境變數與 Vision
# -------------------------------
try:
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
    creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if deepseek_api_key:
        print("✅ 成功讀到 DEEPSEEK_API_KEY")
    else:
        print("❌ 找不到 DEEPSEEK_API_KEY")
    if creds_json:
        json.loads(creds_json)
        with open("google_cred.json", "w", encoding="utf-8") as f:
            f.write(creds_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_cred.json"
        vision_client = vision.ImageAnnotatorClient()
        print("✅ 成功啟用 Google Vision")
    else:
        vision_client = None
        print("⚠️ 未啟用 Vision API")
except Exception as e:
    print("⚠️ 啟動錯誤：", e)
    vision_client = None

# -------------------------------
# 🗂️ SQLite 初始化
# -------------------------------
os.makedirs("data", exist_ok=True)
DB_PATH = "data/anan.db"
def get_conn(): return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, question TEXT, topic TEXT,
        is_correct INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS daily_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL, date TEXT NOT NULL,
        seconds_active INTEGER DEFAULT 0,
        last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, date)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS feedbacks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL, record_id INTEGER,
        understood INTEGER, note TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit(); conn.close()
    print("✅ [安安] 資料庫就緒 (v3.6)")
init_db()

@app.before_request
def ensure_user():
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())

# -------------------------------
# 🧮 主題偵測
# -------------------------------
def detect_topic(text):
    t = (text or "").lower()
    if any(k in t for k in ["角","邊","面積","圖形","幾何","內角","外角"]): return "幾何"
    if any(k in t for k in ["分數","倍數","因數","fraction"]): return "分數/因數"
    if any(k in t for k in ["代數","方程","x","y","代號","解","變數"]): return "代數"
    if any(k in t for k in ["比例","百分比","%"]): return "比例/百分比"
    return "未分類"

# -------------------------------
# 💾 紀錄互動
# -------------------------------
def log_record(user_id, question, topic, is_correct=None):
    try:
        conn = get_conn(); c = conn.cursor()
        c.execute("INSERT INTO records (user_id, question, topic, is_correct) VALUES (?,?,?,?)",
                  (user_id, question, topic, is_correct))
        conn.commit(); rid = c.lastrowid; conn.close()
        return rid
    except Exception as e:
        print("⚠️ 紀錄失敗：", e)
        return None

# -------------------------------
# 💓 使用時間追蹤
# -------------------------------
@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    user_id = session.get("user_id")
    if not user_id: return jsonify({"status":"no_user"}), 400
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn(); c = conn.cursor()
    c.execute("""
      INSERT INTO daily_usage (user_id,date,seconds_active)
      VALUES(?,?,15)
      ON CONFLICT(user_id,date) DO UPDATE SET
        seconds_active=seconds_active+15,
        last_seen=CURRENT_TIMESTAMP
    """,(user_id,today))
    conn.commit(); conn.close()
    return jsonify({"status":"ok"})

@app.after_request
def inject_tracker(res):
    try:
        if res.headers.get("Content-Type","").startswith("text/html"):
            html = res.get_data(as_text=True)
            tag = '<script src="/tracker.js"></script>'
            res.set_data(html.replace("</body>",f"{tag}</body>"))
    except: pass
    return res

@app.route("/tracker.js")
def tracker_js():
    js = """
(function(){
 var t=null;
 function beat(){fetch('/heartbeat',{method:'POST',credentials:'same-origin'});}
 function start(){if(!t){beat();t=setInterval(beat,15000);}}
 function stop(){if(t){clearInterval(t);t=null;}}
 document.addEventListener('visibilitychange',()=>{(document.visibilityState==='visible')?start():stop();});
 window.addEventListener('pageshow',start);window.addEventListener('pagehide',stop);
 if(document.visibilityState==='visible'){start();}
})();"""
    return js,200,{"Content-Type":"application/javascript"}

# -------------------------------
# 🎯 自動判斷答題正確率
# -------------------------------
def evaluate_answer(question, student_answer):
    """
    自動用 GPT 判斷學生答案是否正確（僅數學題觸發）。
    回傳 1=正確, 0=錯誤, None=無法判斷。
    """
    try:
        # 只在題目像數學題時啟動
        if not re.search(r"[0-9=＋×÷\-*/]", question):
            return None

        headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                   "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "你是一位數學老師，請判斷學生答案是否正確，只回答「正確」或「錯誤」。"},
                {"role": "user", "content": f"題目：{question}\n學生回答：{student_answer}"}
            ]
        }
        r = requests.post("https://api.openai.com/v1/chat/completions",
                          headers=headers, json=payload, timeout=25)
        reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if "正確" in reply: return 1
        if "錯誤" in reply: return 0
        return None
    except Exception as e:
        print("⚠️ evaluate_answer 錯誤：", e)
        return None

# -------------------------------
# 💬 DeepSeek 主答 + 備援
# -------------------------------
def ask_anan(q):
    system_prompt = "你是「數學小老師安安」，使用繁體中文、蘇格拉底式提問法引導學生思考。"
    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}",
                   "Content-Type":"application/json"}
        payload = {"model":"deepseek-chat",
                   "messages":[{"role":"system","content":system_prompt},
                               {"role":"user","content":q}]}
        r = requests.post("https://api.deepseek.com/chat/completions",
                          headers=headers,json=payload,timeout=40)
        return r.json().get("choices",[{}])[0].get("message",{}).get("content","")
    except Exception as e:
        print("⚠️ DeepSeek 出錯，改用 GPT 備援：", e)
        try:
            h2={"Authorization":f"Bearer {os.getenv('OPENAI_API_KEY')}",
                "Content-Type":"application/json"}
            p2={"model":"gpt-4o-mini",
                "messages":[{"role":"system","content":system_prompt},
                            {"role":"user","content":q}]}
            r2=requests.post("https://api.openai.com/v1/chat/completions",
                             headers=h2,json=p2,timeout=40)
            return r2.json().get("choices",[{}])[0].get("message",{}).get("content","")
        except Exception as e2:
            return f"⚠️ 系統錯誤：{e2}"

# -------------------------------
# 🏠 首頁（答題＋自動正確率）
# -------------------------------
@app.route("/", methods=["GET","POST"])
def home():
    conversation=[]
    if request.method=="POST":
        msg=request.form.get("message","")
        if msg:
            ans=ask_anan(msg)
            conversation.append({"role":"user","content":msg})
            conversation.append({"role":"assistant","content":ans})
            topic=detect_topic(msg)
            rid=log_record(session.get("user_id"),msg,topic,None)
            # 自動評估答題正確率
            correctness=evaluate_answer(msg,ans)
            if rid and correctness is not None:
                conn=get_conn()
                conn.execute("UPDATE records SET is_correct=? WHERE id=?",(correctness,rid))
                conn.commit(); conn.close()
    return render_template("index.html",conversation=conversation)

# -------------------------------
# 🧮 圖片解題（Vision + GPT 備援）
# -------------------------------
@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"result":"沒有收到圖片"}),400
    img=request.files["image"].read()
    b64=base64.b64encode(img).decode("utf-8")

    # OCR 辨識
    ocr_text=""
    try:
        if vision_client:
            image=vision.Image(content=img)
            res=vision_client.text_detection(image=image)
            ocr_text=res.text_annotations[0].description if res.text_annotations else ""
            print("📝 OCR 辨識結果：",ocr_text[:100])
    except Exception as e:
        print("⚠️ Vision OCR 錯誤：",e)

    # 若 OCR 無結果 → 圖形備援
    if not ocr_text.strip():
        print("⚠️ OCR 無結果 → GPT 圖像備援")
        prompt="你是安安老師，根據圖片推測數學題，用蘇格拉底式提問法引導學生思考。"
        headers={"Authorization":f"Bearer {os.getenv('OPENAI_API_KEY')}","Content-Type":"application/json"}
        payload={"model":"gpt-4o-mini",
                 "messages":[{"role":"system","content":prompt},
                             {"role":"user","content":[{"type":"image_base64","image_base64":b64}]}]}
        r=requests.post("https://api.openai.com/v1/chat/completions",headers=headers,json=payload,timeout=60)
        ans=r.json().get("choices",[{}])[0].get("message",{}).get("content","")
        log_record(session.get("user_id"),"(圖形題無文字)","幾何/圖形",None)
        return jsonify({"result":ans}),200,{"Content-Type":"application/json; charset=utf-8"}

    # 有文字 → 正常講解
    gpt_prompt=f"請用繁體中文、蘇格拉底式引導法講解以下題目：\n{ocr_text}"
    headers={"Authorization":f"Bearer {os.getenv('OPENAI_API_KEY')}","Content-Type":"application/json"}
    payload={"model":"gpt-4o-mini",
             "messages":[
                 {"role":"system","content":"你是安安老師，用可愛親切方式教學。"},
                 {"role":"user","content":[{"type":"text","text":gpt_prompt},{"type":"image_base64","image_base64":b64}]}
             ]}
    r=requests.post("https://api.openai.com/v1/chat/completions",headers=headers,json=payload,timeout=60)
    ans=r.json().get("choices",[{}])[0].get("message",{}).get("content","")
    log_record(session.get("user_id"),ocr_text[:200],"幾何/圖形",None)
    return jsonify({"result":ans}),200,{"Content-Type":"application/json; charset=utf-8"}

# -------------------------------
# 🩺 健康檢查
# -------------------------------
@app.route("/health")
def health(): return jsonify({"status":"ok"}),200

# -------------------------------
# 🚀 主程式入口
# -------------------------------
if __name__=="__main__":
    port=int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0",port=port)
