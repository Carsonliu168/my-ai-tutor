# ================================
# 📘 安安專案主程式 app.py
# v4.3.3 – 修正圖片題「我不懂」卡住問題 + Gemini 模型更新
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os, json, base64, requests, sqlite3, uuid, re
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制 16MB

# -------------------------------
# ✅ 環境變數
# -------------------------------
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
openai_api_key  = os.getenv("OPENAI_API_KEY")
google_api_key  = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

# 初始化 Gemini
genai = None
try:
    import google.generativeai as genai_mod
    if google_api_key:
        genai_mod.configure(api_key=google_api_key)
        genai = genai_mod
        print("✅ Gemini API 已就緒")
    else:
        print("⚠️ 未設定 GOOGLE_API_KEY（或 GEMINI_API_KEY）")
except Exception as e:
    print(f"⚠️ Gemini 初始化失敗: {e}")

# -------------------------------
# 📊 SQLite 初始化
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
    print("✅ [安安] 資料庫就緒 (v4.3.3)")
init_db()

# -------------------------------
# 🧠 DeepSeek / GPT 文字問答
# -------------------------------
def ask_anan(question: str, mode="socratic"):
    style = "採用蘇格拉底式提問法，引導學生思考，不直接給答案。" if mode == "socratic" \
        else "用正常教學方式清楚給出解題步驟與答案。"
    system_prompt = f"""
你是「數學小老師安安」，請使用繁體中文。
教學風格：{style}
解題要求：
1. 逐步列出完整計算過程
2. 幾何題需分析圖形條件並應用定理
3. 每步都要說明理由
4. 最後驗證答案合理性
5. 用溫暖鼓勵的語氣引導學生思考
"""
    try:
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat",
                   "messages": [{"role": "system", "content": system_prompt},
                                {"role": "user", "content": question}]}
        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=40)
        return r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        print("⚠️ DeepSeek 失敗：", e)
        try:
            backup_headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            payload["model"] = "gpt-4o-mini"
            r2 = requests.post("https://api.openai.com/v1/chat/completions",
                               headers=backup_headers, json=payload, timeout=40)
            return r2.json().get("choices", [{}])[0].get("message", {}).get("content", "（無回應）")
        except Exception as e2:
            print("❌ GPT 備援失敗：", e2)
            return "（無回應）"

# -------------------------------
# 💬 首頁與對話
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
        user_msg = request.form.get("message", "").strip()
        if not user_msg:
            return render_template("index.html", conversation=conversation)

        mode = "normal" if session.get("confused_count", 0) >= 2 else "socratic"
        ai_reply = ask_anan(user_msg, mode)
        conversation.append({"role": "user", "content": user_msg})
        conversation.append({"role": "assistant", "content": ai_reply})
        session["conversation"] = conversation
    return render_template("index.html", conversation=conversation)

# -------------------------------
# 🧭 學生自評回饋（圖片題修正版）
# -------------------------------
@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json()
    understood = data.get("understood")
    if understood is None:
        return jsonify({"status": "error"})

    convo = session.get("conversation", [])
    last_q = next((m["content"] for m in reversed(convo) if m["role"] == "user"), "")

    if understood:
        session["confused_count"] = 0
        reply = "太棒了～安安替你開心 💪 你真的越來越厲害了！"
    else:
        session["confused_count"] = session.get("confused_count", 0) + 1
        count = session["confused_count"]

        # 🔹 檢查是否為圖片題
        is_image = "[圖片題目]" in last_q

        if count == 1:
            reply = "沒關係～老師換個說法試試看 👇" if not is_image \
                else "這張圖的題目有點難，我換個方式幫你想一次 📷"
        elif count == 2:
            reply = "我再給一個提示，看看能不能幫上忙 💡" if not is_image \
                else "我來強調圖片題的重點部分：看看角度、比例或對稱關係 🔍"
        else:
            # 🔸 第三次：重新講解上一題
            if is_image:
                reply = "我們一起重新解這道圖片題 👇\n"
                try:
                    # 取出上一張圖片的 AI 結果
                    img_ans = next((m["content"] for m in reversed(convo)
                                   if m["role"] == "assistant" and "📷" in convo[convo.index(m)-1]["content"]), "")
                    # 再用 GPT 重講一次
                    prompt = f"請用更簡單的方式重新講解以下數學題：\n{img_ans}"
                    headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
                    payload = {
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "system", "content": "你是親切的台灣數學老師，請用繁體中文一步步講解。"},
                                     {"role": "user", "content": prompt}]
                    }
                    r = requests.post("https://api.openai.com/v1/chat/completions",
                                      headers=headers, json=payload, timeout=40)
                    reply += r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                except Exception as e:
                    print("⚠️ 圖片題重講失敗：", e)
                    reply += "⚠️ 系統暫時無法重新講解這張圖，請稍後再試。"
            else:
                reply = "第三次了，我直接一步步列出完整算式與理由 🧮"
                full_q = next((m["content"] for m in reversed(convo) if m["role"] == "user"), "")
                reply += "\n" + ask_anan(f"請直接詳細解這題：{full_q}", "normal")
            session["confused_count"] = 0

    convo.append({"role": "assistant", "content": reply})
    session["conversation"] = convo
    session.modified = True
    return jsonify({"status": "ok", "reply": reply})

# -------------------------------
# 🧮 圖片辨識（Gemini 模型更新）
# -------------------------------
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
def allowed_file(filename): return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"result": "⚠️ 沒有收到圖片"}), 400
    image_file = request.files["image"]
    if not allowed_file(image_file.filename):
        return jsonify({"result": "⚠️ 不支援的圖片格式"}), 400
    image_bytes = image_file.read()
    result = None

    if genai and google_api_key:
        model_names = ["gemini-1.5-pro", "gemini-1.0-pro"]
        for model_name in model_names:
            try:
                model = genai.GenerativeModel(model_name)
                resp = model.generate_content([
                    "你是台灣數學老師安安，請完整解這道圖片數學題（繁體中文、逐步講解）",
                    {"mime_type": "image/jpeg", "data": image_bytes}
                ])
                if resp.text and len(resp.text) > 60:
                    result = resp.text.strip()
                    break
            except Exception as e:
                print(f"⚠️ {model_name} 失敗：{e}")
                continue

    # GPT 備援
    if not result:
        try:
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-4o",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "請解釋這張數學題圖片，繁體中文逐步講解："},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                    ]
                }]
            }
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=80)
            result = r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"❌ GPT 備援失敗：{e}")
            return jsonify({"result": "⚠️ 圖片辨識失敗"}), 500

    if "conversation" not in session:
        session["conversation"] = []
    convo = session["conversation"]
    convo.append({"role": "user", "content": "[圖片題目]"})
    convo.append({"role": "assistant", "content": result})
    session["conversation"] = convo
    session.modified = True
    return jsonify({"result": result, "success": True})

# -------------------------------
# 清除對話 / 健康檢查
# -------------------------------
@app.route("/clear")
def clear(): session.clear(); return redirect("/")
@app.route("/health")
def health(): return jsonify({"status": "ok"}), 200

# -------------------------------
# 🚀 主程式
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"✅ 啟動 | DeepSeek={bool(deepseek_api_key)} | OpenAI={bool(openai_api_key)} | Gemini={bool(google_api_key)} | PORT={port}")
    app.run(host="0.0.0.0", port=port)
