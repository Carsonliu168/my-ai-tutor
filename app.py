# ================================
# 📘 安安專案主程式 app.py
# v4.9.0-FINAL：完全修復所有問題
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, base64, requests, sqlite3, uuid, re, imghdr
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

session_lifetime_days = int(os.getenv("SESSION_LIFETIME_DAYS", "30"))
app.permanent_session_lifetime = timedelta(days=session_lifetime_days)
DEMO_MODE = os.getenv("DEMO_MODE", "False").lower() == "true"
APP_VERSION = "v4.9.1-teaching-improved"

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

def normalize_math_terms(s):
    if not s:
        return s
    s = re.sub(r'\blcm\b', '最小公倍數', s, flags=re.IGNORECASE)
    s = re.sub(r'\bgcd\b', '最大公因數', s, flags=re.IGNORECASE)
    s = re.sub(r'\bmod\b', '模（取餘數）', s, flags=re.IGNORECASE)
    s = (s.replace("质","質").replace("余数","餘數").replace("约数","約數")
           .replace("这","這").replace("个","個").replace("写","寫").replace("为","為"))
    return s

def clean_latex_format(s):
    """修復錯誤的 LaTeX 格式 - 這個函數很重要！"""
    if not s:
        return s
    # 修復 [ xxx ] -> $$xxx$$
    s = re.sub(r'\[\s*([^\[\]]+?)\s*\]', r'$$\1$$', s)
    # 修復 ( \xxx{yyy} ) -> $\xxx{yyy}$
    s = re.sub(r'\(\s*\\(\w+)\{([^}]+)\}\s*\)', r'$\\\1{\2}$', s)
    # 修復 ( ADEF ) -> $ADEF$
    s = re.sub(r'\(\s*([A-Z]{1,4})\s*\)', r'$\1$', s)
    return s

def is_pure_help_phrase(msg):
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

def safe_json(resp):
    try:
        data = resp.json()
        print(f"[API] 狀態碼: {resp.status_code}")
        return data
    except Exception as e:
        print(f"[API] JSON 解析失敗: {e}")
        return {}

def fallback_generate_reply(user_text):
    t = (user_text or "").replace(" ", "")
    
    simple_calc = re.match(r'^(\d+)\s*([\+\-\*\/])\s*(\d+)\s*=?\s*$', user_text.strip())
    if simple_calc:
        num1 = float(simple_calc.group(1))
        op = simple_calc.group(2)
        num2 = float(simple_calc.group(3))
        
        if op == '+':
            result = num1 + num2
            return f"很好的問題！{num1} + {num2} = **{result}**\n\n你算對了嗎？"
        elif op == '-':
            result = num1 - num2
            return f"來算減法！{num1} - {num2} = **{result}**"
        elif op == '*':
            result = num1 * num2
            return f"乘法題！{num1} × {num2} = **{result}**"
        elif op == '/':
            if num2 != 0:
                result = num1 / num2
                return f"除法題！{num1} ÷ {num2} = **{result}**"
    
    m = re.search(r"長(是)?(\d+(\.\d+)?)\D+寬(是)?(\d+(\.\d+)?)", t)
    if m:
        L = float(m.group(2)); W = float(m.group(5))
        area = L * W
        return normalize_math_terms(f"先用備援解法：**長方形面積 = 長 × 寬 = {L} × {W} = {area}（平方公分）**。")

    return normalize_math_terms(f"我收到你的問題了：「{user_text[:50]}」\n\n請告訴我更多資訊。")

def trim_conversation_history():
    convo = session.get("conversation", [])
    MAX_HISTORY = 10
    if len(convo) > MAX_HISTORY:
        session["conversation"] = convo[-MAX_HISTORY:]
        session.modified = True

def ask_anan(question, mode="socratic", history_text=""):
    if not deepseek_api_key and not openai_api_key:
        return fallback_generate_reply(question)
    
    if mode == "socratic":
        style = """採用蘇格拉底式提問法，分階段引導學生：
第一階段：先問學生是否知道相關公式或概念（例如：「你知道長方形面積怎麼算嗎？」）
第二階段：等學生回答後，再引導他們如何應用（例如：「那你覺得這題要怎麼用這個公式呢？」）
第三階段：引導計算過程，但不要直接列出完整算式
重要：不要一次就把公式、代入、計算都給出來，要讓學生有思考空間。"""
    else:
        style = "用清楚步驟給出完整答案，包含公式、代入、計算、答案。"
    
    rules = """
教學規範：
- 答對立即肯定並收尾，不延伸其他主題。
- 答錯時才引導，不要在答對後繼續教學。
- 使用台灣繁體中文，口吻親切。
- 數學公式使用 LaTeX：行內 $公式$，區塊 $公式$
"""
    system_prompt = f"你是數學老師安安。{style}\n{rules}"

    messages = [{"role":"system","content":system_prompt}]
    if history_text:
        messages.append({"role":"user","content":f"[history]\n{history_text}"})
        messages.append({"role":"assistant","content":"（收到上方脈絡）"})
    messages.append({"role":"user","content":question})

    if deepseek_api_key:
        try:
            headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
            payload = {"model": "deepseek-chat","messages": messages,"temperature":0.3}
            
            r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=35)
            r.raise_for_status()
            data = safe_json(r)
            
            if data and "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    reply = choice["message"]["content"].strip()
                    if reply:
                        print(f"[DeepSeek] ✅ 成功")
                        # 🔥 關鍵：清理 LaTeX 格式
                        reply = clean_latex_format(reply)
                        return normalize_math_terms(reply)
        except Exception as e:
            print(f"[DeepSeek] ❌ {e}")

    if openai_api_key:
        try:
            headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            payload2 = {"model":"gpt-4o-mini","messages":messages,"temperature":0.3}
            
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload2, timeout=35)
            r.raise_for_status()
            data = safe_json(r)
            
            if data and "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    reply = choice["message"]["content"].strip()
                    if reply:
                        print(f"[OpenAI] ✅ 成功")
                        # 🔥 關鍵：清理 LaTeX 格式
                        reply = clean_latex_format(reply)
                        return normalize_math_terms(reply)
        except Exception as e:
            print(f"[OpenAI] ❌ {e}")

    return fallback_generate_reply(question)

DB_PATH = "data/anan.db"
os.makedirs("data", exist_ok=True)
def get_conn(): return sqlite3.connect(DB_PATH, check_same_thread=False)
def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, question TEXT, topic TEXT,
        is_correct INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit(); conn.close()
    print("✅ [安安] 資料庫就緒 (v4.9.0)")
init_db()

TEACHER_HINT = "安安發現你還是有點困惑，建議明天問老師！"
def next_help_response(counter_name):
    c = session.get(counter_name, 0) + 1
    session[counter_name] = c
    session.modified = True
    if c == 1:
        return "沒關係，我再簡單講一次：找公式→代入→計算→加單位。"
    elif c == 2:
        return "我們換個說法試試～你記得剛剛的公式是哪一個嗎？"
    elif c == 3:
        hist = brief_history(4)
        return ask_anan("請用最簡單方式重講上一題，清楚列出公式、代入與答案。", mode="normal", history_text=hist)
    else:
        session[counter_name] = 3
        session.modified = True
        return TEACHER_HINT

ALLOWED = {'png','jpg','jpeg'}
def allow(filename): return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED

def detect_mime_by_bytes(b):
    kind = imghdr.what(None, h=b)
    if kind == "png": return "image/png"
    return "image/jpeg"

@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"result":"⚠️ 沒有收到圖片"}),400
    img = request.files["image"]
    if img.filename=='' or not allow(img.filename):
        return jsonify({"result":"⚠️ 圖片格式錯誤"}),400

    data = img.read()
    mime = detect_mime_by_bytes(data)
    
    instruction = "你是台灣數學老師安安，用繁體中文逐步講解這張圖片題。數學公式用 $公式$ 或 $$公式$$ 格式。步驟：1)辨識題目；2)寫公式；3)代入；4)算答案；5)若答對直接肯定。"

    res = None

    try:
        if google_api_key and genai:
            model = genai.GenerativeModel("gemini-1.5-flash")
            r = model.generate_content(
                [instruction, {"mime_type": mime, "data": data}],
                generation_config={"max_output_tokens":1024}
            )
            res = getattr(r, "text", None)
            if res: 
                res = clean_latex_format(normalize_math_terms(res))
                print(f"[Gemini] ✅")
    except Exception as e:
        print(f"[Gemini] ❌ {e}")

    if not res and openai_api_key:
        try:
            b64 = base64.b64encode(data).decode()
            headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            payload = {
                "model":"gpt-4o",
                "messages":[{"role":"user","content":[
                    {"type":"text","text":instruction},
                    {"type":"image_url","image_url":{"url":f"data:{mime};base64,{b64}"}}
                ]}],
                "temperature":0.2
            }
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            data_json = safe_json(r)
            res = (data_json.get("choices",[{}])[0].get("message",{}) or {}).get("content","")
            if res: 
                res = clean_latex_format(normalize_math_terms(res))
                print(f"[OpenAI-image] ✅")
        except Exception as e:
            return jsonify({"result":f"⚠️ {e}"}),500

    convo = session.get("conversation", [])
    convo.append({"role":"user","content":"📷 [圖片題]"})
    convo.append({"role":"assistant","content": res or "無法解讀"})
    
    if len(convo) > 10:
        session["conversation"] = convo[-10:]
    else:
        session["conversation"] = convo
    
    session.modified = True
    return jsonify({"result": res, "success": True}), 200

@app.before_request
def ensure_user():
    if "user_id" not in session:
        session["user_id"]=str(uuid.uuid4())
        session.modified = True
    session.permanent = True

@app.route("/", methods=["GET","POST"])
def home():
    convo = session.setdefault("conversation", [])
    if request.method=="POST":
        msg = (request.form.get("message","") or "").strip()
        if not msg:
            return render_template("index.html",conversation=convo)

        if is_pure_help_phrase(msg):
            key = "image_confused_count" if session.get("guided_topic")=="image_explain" else "confused_count"
            reply = next_help_response(key)
            convo.append({"role":"user","content":msg})
            convo.append({"role":"assistant","content":reply})
            session["conversation"] = convo
            session.modified = True
            trim_conversation_history()
            return render_template("index.html",conversation=convo)

        session["confused_count"] = 0
        session["image_confused_count"] = 0
        hist = brief_history(6)
        
        reply = ask_anan(msg, "socratic", hist)

        convo.append({"role":"user","content":msg})
        convo.append({"role":"assistant","content":reply})
        session["conversation"] = convo
        session.modified = True
        trim_conversation_history()

    return render_template("index.html", conversation=convo)

@app.route("/feedback", methods=["POST"])
def feedback():
    d = request.get_json(silent=True) or {}
    under = d.get("understood")
    if under is None:
        return jsonify({"status":"error"})
    if under:
        session["confused_count"]=0; session["image_confused_count"]=0
        session.modified = True
        return jsonify({"status":"ok","reply":"太棒了～💪"})
    key = "image_confused_count" if session.get("guided_topic")=="image_explain" else "confused_count"
    reply = next_help_response(key)
    return jsonify({"status":"ok","reply":reply})

@app.route("/clear")
def clear():
    for k in ["conversation","confused_count","guided_topic","image_confused_count"]:
        session.pop(k, None)
    session.modified = True
    return redirect(url_for("home"))

@app.route("/health")
def health():
    keys = {"deepseek": bool(deepseek_api_key), "openai": bool(openai_api_key), "google": bool(google_api_key)}
    return jsonify({"ok": True, "keys": keys, "version": APP_VERSION}), 200

if __name__=="__main__":
    port=int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0",port=port)