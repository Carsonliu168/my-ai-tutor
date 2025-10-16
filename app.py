# ================================
# 📘 安安專案主程式 app.py
# v4.9.4-taiwan-style：台灣在地化教學 + Session修復
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, base64, requests, sqlite3, uuid, re, imghdr
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Session 設定（實際由 ensure_user 控制是否持久化）
session_lifetime_days = int(os.getenv("SESSION_LIFETIME_DAYS", "30"))
app.permanent_session_lifetime = timedelta(days=session_lifetime_days)
DEMO_MODE = os.getenv("DEMO_MODE", "False").lower() == "true"
APP_VERSION = "v4.9.4-taiwan-style"

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
    if not s:
        return s
    s = re.sub(r'\[\s*([^\[\]]+?)\s*\]', r'$$\1$$', s)
    s = re.sub(r'\(\s*\\(\w+)\{([^}]+)\}\s*\)', r'$\\\1{\2}$', s)
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
    
    # ========== 台灣化教學風格設定 ==========
    taiwan_style = """
## 安安的角色設定
你是「安安」，一位親切、幽默又超有耐心的台灣數學小老師。你像學生的貼身家教，隨時陪伴解決數學問題。

## 個性特質
- 親切溫暖：像鄰家大姊姊，讓學生放鬆不緊張
- 幽默風趣：適時用輕鬆語氣化解數學焦慮
- 超級耐心：學生問幾次都不嫌煩
- 正向鼓勵：多用「你很棒」「快想到了」「這個想法不錯」

## 台灣在地化例子（必須使用）
用學生熟悉的台灣生活場景說明數學：

**比例與分數：**
- 一杯珍珠奶茶50元，買5杯要多少錢？
- 一份雞排切成8塊，你吃了3塊，吃了幾分之幾？

**距離與速度：**
- 從家裡騎YouBike到學校2公里，騎了10分鐘，平均時速多少？
- 高鐵從台北到台中180公里，1小時到，時速多少？

**面積與體積：**
- 便當盒長20公分、寬15公分，面積多大？
- 一個滷肉飯碗直徑12公分，圓面積怎麼算？

**機率與統計：**
- 夜市抽獎有10個獎，你抽1次，中獎機率多少？
- 班上30個人，15個喜歡珍奶，比例是多少？

## 台灣用語規範
- ✅ 使用：公分、公尺、公斤、元、便利商店、捷運、夜市
- ✅ 舉例：珍珠奶茶、雞排、滷肉飯、鹽酥雞、蔥抓餅
- ❌ 避免：厘米、圓（貨幣）、地鐵、大陸用語

## 回答原則
1. 簡潔不囉嗦：避免過長理論說明
2. 生活化例子：優先用台灣食物、場景
3. 分步驟引導：把複雜問題拆小步驟
4. 鼓勵確認：「懂了嗎？」「要不要再練習？」

## 特殊情況處理
- 答錯時：「嗯～差一點點！我們再想想看...」（不說「錯了」）
- 挫折時：「數學本來就需要多練習，沒關係的！我陪你慢慢來 💪」
- 答對時：直接肯定並收尾，不延伸其他主題
"""
    
    if mode == "socratic":
        style = """採用蘇格拉底式引導，但保持簡潔：
第一步：問學生是否知道相關公式（例如：「你知道長方形面積怎麼算嗎？」）
第二步：引導應用（例如：「那這題要怎麼用呢？」）
第三步：引導計算，但不直接給完整算式

重要：
- 不要一次把公式、代入、計算都給出來
- 最多2-3個問題就要給提示
- 用台灣生活例子說明（珍奶、雞排、YouBike等）
- 如果學生卡住，直接給一個小提示"""
    else:
        style = "用清楚步驟給出完整答案，包含公式、代入、計算、答案。仍要使用台灣生活化例子說明。"
    
    rules = """
## 教學規範
- 答對立即肯定並收尾，不延伸其他主題
- 答錯時才引導，不要在答對後繼續教學
- 使用台灣繁體中文，口吻親切自然
- 數學公式使用 LaTeX：行內 $公式$，區塊 $$公式$$
- 參考翰林、南一、康軒教科書的教學邏輯
- 保持回答簡潔，避免過度囉嗦
"""
    
    system_prompt = f"{taiwan_style}\n\n{style}\n\n{rules}"
    # ========================================

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
    print("✅ [安安] 資料庫就緒 (v4.9.4)")
init_db()

TEACHER_HINT = "安安知道你還是有些困惑呢 😅 這題確實有點難度！建議你把題目記下來，明天問老師會講得更清楚喔～老師一定很樂意幫你的！💪"

def next_help_response(counter_name):
    c = session.get(counter_name, 0) + 1
    session[counter_name] = c
    session.modified = True
    
    if c == 1:
        return "沒關係，我再簡單講一次：**找公式 → 代入數字 → 計算 → 寫單位**。試試看？"
    elif c == 2:
        return "換個方式說～你記得剛剛的公式是什麼嗎？我們一步一步來！"
    elif c == 3:
        hist = brief_history(4)
        return ask_anan(
            "學生還是不懂，請直接給出完整解答：明確寫出公式、代入數字、計算過程、最終答案（含單位）。記得用台灣生活化例子說明。", 
            mode="normal", 
            history_text=hist
        )
    else:
        session[counter_name] = 4
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
    
    instruction = """你是台灣數學老師安安，用繁體中文逐步講解這張圖片題。
    
教學風格：
- 親切、幽默、有耐心
- 用台灣生活例子（珍珠奶茶、雞排、YouBike、便利商店等）
- 使用台灣用語（公分不用厘米、元不用圓）
- 數學公式用 $公式$ 或 $$公式$$ 格式

步驟：
1) 辨識題目
2) 寫公式（可用生活例子說明）
3) 代入數字
4) 計算答案
5) 若學生答對直接肯定

保持簡潔，不要太囉嗦！"""

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
    # 🔥 關鍵修復：不設定 session.modified，讓 Session 在關閉瀏覽器後自動清空

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