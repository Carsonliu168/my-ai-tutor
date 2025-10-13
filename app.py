# ================================
# 📘 安安專案主程式 app.py
# v4.2：保留原功能 + 加入「三層不懂教學回饋機制」
#       DeepSeek 主答 + Gemini 免費圖片辨識 + GPT 備援
#       修正「不懂」只加計數不產生教學行為的問題
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session
import os, json, base64, requests, sqlite3, uuid, re
from datetime import datetime
import random

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制 16MB

# -------------------------------
# ✅ 環境變數與 API 初始化
# -------------------------------
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")
google_api_key = os.getenv("GOOGLE_API_KEY")

# 初始化 Gemini
try:
    import google.generativeai as genai
    if google_api_key:
        genai.configure(api_key=google_api_key)
        print("✅ Gemini API 已就緒 (免費)")
    else:
        print("⚠️ 未設定 GOOGLE_API_KEY")
except Exception as e:
    print(f"⚠️ Gemini 初始化失敗: {e}")


# -------------------------------
# 🧠 DeepSeek 模型（蘇格拉底或正常教學模式）
# -------------------------------
def ask_anan(question: str, mode="socratic"):
    if mode == "socratic":
        style = "採用蘇格拉底式提問法，引導學生思考，不直接給答案。"
    else:
        style = "用正常教學方式清楚給出解題步驟與答案。"

    system_prompt = f"""
你是「數學小老師安安」，一位專業、親切、幽默的數學教學助理。
請使用繁體中文回答。
教學風格：{style}

解題要求：
1. 若是計算題，請務必逐步列出完整計算過程
2. 若是幾何題，請先分析圖形條件，再應用定理
3. 每個步驟都要說明理由
4. 最後要驗證答案的合理性
5. 用溫暖鼓勵的語氣引導學生思考
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
        return r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    except:
        # DeepSeek 失敗則用 GPT 備援
        try:
            backup_headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
            payload["model"] = "gpt-4o-mini"
            r2 = requests.post("https://api.openai.com/v1/chat/completions", headers=backup_headers, json=payload, timeout=40)
            return r2.json().get("choices", [{}])[0].get("message", {}).get("content", "（無回應）")
        except:
            return "（無回應）"


# -------------------------------
# 📊 SQLite 資料庫：紀錄學習
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
    print("✅ [安安] 資料庫就緒 (v4.2)")
init_db()


# -------------------------------
# 🎯 自動判斷答題正確率
# -------------------------------
def evaluate_answer(question, student_answer):
    try:
        if not re.search(r"[0-9=＋×÷\-*/]", question):
            return None
        headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "你是一位數學老師，請判斷學生答案是否正確，只回答「正確」或「錯誤」。"},
                {"role": "user", "content": f"題目：{question}\n學生回答：{student_answer}"}
            ]
        }
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=25)
        reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if "正確" in reply: return 1
        if "錯誤" in reply: return 0
        return None
    except Exception as e:
        print("⚠️ evaluate_answer 錯誤：", e)
        return None


# -------------------------------
# 💬 首頁與對話保存
# -------------------------------
@app.before_request
def ensure_user():
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())
    # 初始化必要狀態（避免 KeyError）
    session.setdefault("conversation", [])
    session.setdefault("confused_count", 0)
    session.setdefault("last_question", None)      # ⬅️ 新增：記錄最新題目（文字或圖片題占位）
    session.setdefault("last_explanation", None)   # ⬅️ 新增：記錄最新的 AI 講解

@app.route("/", methods=["GET", "POST"])
def home():
    conversation = session["conversation"]

    if request.method == "POST":
        user_msg = request.form.get("message", "").strip()
        if user_msg:
            # 記錄最後一道題（文字輸入）
            session["last_question"] = user_msg

            # 根據 confused_count 切換教學模式（保留原邏輯）
            mode = "normal" if session.get("confused_count", 0) >= 2 else "socratic"
            ai_reply = ask_anan(user_msg, mode)

            # 記錄最後一次講解，供「不懂」重教使用
            session["last_explanation"] = ai_reply

            # 更新對話
            conversation.append({"role": "user", "content": user_msg})
            conversation.append({"role": "assistant", "content": ai_reply})
            session["conversation"] = conversation

            # 紀錄正確性
            correctness = evaluate_answer(user_msg, ai_reply)
            conn = get_conn()
            conn.execute(
                "INSERT INTO records (user_id, question, topic, is_correct) VALUES (?, ?, ?, ?)",
                (session["user_id"], user_msg, "一般", correctness)
            )
            conn.commit()
            conn.close()

    return render_template("index.html", conversation=conversation)


# -------------------------------
# 🧭 學生自評回饋（修：加入三層不懂教學邏輯）
# -------------------------------
@app.route("/feedback", methods=["POST"])
def feedback():
    """
    前端：按「我懂了 / 我不懂」會呼叫此端點
    舊行為：只調整 confused_count
    新行為：
      - 懂了：歸零 + 回傳鼓勵語
      - 不懂：計數 + 直接生成下一層教學內容（不用學生再打字）
    """
    data = request.get_json()
    understood = data.get("understood")
    if understood is None:
        return jsonify({"status": "error", "msg": "缺少 understood 參數"})

    # 取用最新題目與講解
    current_question = session.get("last_question")
    previous_explanation = session.get("last_explanation")

    if understood:
        session["confused_count"] = 0
        encouragements = [
            "太棒了！安安老師為你鼓掌 👏",
            "非常好～繼續保持這個思考方式！💪",
            "厲害！你真的越來越懂數學了！🌟"
        ]
        msg = random.choice(encouragements)
        return jsonify({"status": "ok", "confused_count": 0, "reply": msg})

    # 不懂 → 層級 +1，並根據層級生成對應教學
    level = session.get("confused_count", 0) + 1
    session["confused_count"] = level

    # 若找不到題目（例如直接按了不懂），避免亂串舊記憶
    if not current_question and not previous_explanation:
        return jsonify({
            "status": "ok",
            "confused_count": level,
            "reply": "先把題目（或再上傳一次圖片）給我，我會換一種方式重新帶你理解！"
        })

    # 三層不懂回饋邏輯
    if level == 1:
        prompt = f"""
學生第一次表示不懂。
請針對以下題目，換一種教法（舉生活例子、比喻、或更白話的說法）重新講解。
題目：{current_question or "[圖片題目]"}
前一次講解（供你參考，避免重複同樣說法）：{previous_explanation or "(無)"}
請保持條列步驟，避免一次給太多資訊。
"""
        mode = "socratic"
    elif level == 2:
        prompt = f"""
學生第二次仍不懂。
請提供逐步提示，引導他自己推理，不要直接給答案。
題目：{current_question or "[圖片題目]"}
提示方式：每一步只做一個小動作，等待學生回應的口吻。
"""
        mode = "socratic"
    else:
        prompt = f"""
學生第三次仍不懂。
請直接列出完整算式與解題步驟（Step 1/2/3），並用簡短語句說明每一步為什麼這樣做。
題目：{current_question or "[圖片題目]"}
請在最後用一句話幫他檢核答案的合理性。
"""
        mode = "normal"

    ai_reply = ask_anan(prompt, mode)

    # 記錄這次講解，供後續再次「不懂」使用
    session["last_explanation"] = ai_reply

    # 寫入對話（顯示為系統教學追加）
    conv = session.get("conversation", [])
    conv.append({"role": "assistant", "content": ai_reply})
    session["conversation"] = conv

    return jsonify({
        "status": "ok",
        "confused_count": level,
        "reply": f"安安老師：\n{ai_reply}"
    })


# -------------------------------
# 🗑️ 清除對話
# -------------------------------
@app.route("/clear")
def clear():
    session.pop("conversation", None)
    session["confused_count"] = 0
    session["last_question"] = None         # ⬅️ 同步清除
    session["last_explanation"] = None      # ⬅️ 同步清除
    return redirect("/")


# -------------------------------
# 🧮 圖片解題（Gemini 免費主力 + GPT 備援）+ 對話儲存
# -------------------------------
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"result": "⚠️ 沒有收到圖片"}), 400

    image_file = request.files["image"]
    
    # 檢查檔案
    if image_file.filename == '':
        return jsonify({"result": "⚠️ 沒有選擇檔案"}), 400
    
    if not allowed_file(image_file.filename):
        return jsonify({"result": "⚠️ 不支援的圖片格式，請使用 PNG、JPG 或 JPEG"}), 400

    try:
        image_bytes = image_file.read()
        if len(image_bytes) > 10 * 1024 * 1024:
            return jsonify({"result": "⚠️ 圖片太大，請使用小於 10MB 的圖片"}), 400
    except Exception as e:
        return jsonify({"result": f"⚠️ 讀取圖片失敗: {e}"}), 400
    
    # ========================================
    # 第一層：嘗試 Gemini (免費)
    # ========================================
    result = None
    try:
        print("🔵 使用 Gemini 辨識...")
        model_names = ['gemini-1.5-flash-latest', 'gemini-1.5-flash', 'gemini-pro-vision']
        for model_name in model_names:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content([
                    "你是數學老師安安，請看這道數學題目，用親切可愛的語氣逐步解題，條列清楚步驟與答案。如果圖片不清楚請明確說明。",
                    {"mime_type": "image/jpeg", "data": image_bytes}
                ])
                result = response.text
                if len(result) > 30 and not any(x in result for x in ["無法辨識", "看不清", "模糊", "unclear"]):
                    print(f"✅ Gemini 成功! (使用模型: {model_name})")
                    break
                else:
                    print(f"⚠️ Gemini ({model_name}) 品質不佳，嘗試下一個...")
                    result = None
            except Exception as e:
                print(f"⚠️ Gemini ({model_name}) 失敗: {e}")
                continue
    except Exception as e:
        print(f"❌ Gemini 整體失敗: {e}")
    
    # ========================================
    # 第二層：備援用 GPT-4o
    # ========================================
    if not result:
        try:
            print("🟢 使用 GPT-4o 備援...")
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            headers = {
                "Authorization": f"Bearer {openai_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-4o",
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """你是專業的數學老師安安，請仔細解這道數學題：

1. 先仔細觀察並描述圖片中的所有條件（角度、邊長、圖形等）
2. 列出解題需要的數學原理（如：大角對大邊、三角形內角和、正弦定理等）
3. 逐步計算，每一步都要說明理由
4. 驗證答案的合理性
5. 用親切可愛的語氣，條列清楚步驟與最終答案

重要：請務必確保幾何推理和計算的準確性！"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                        }
                    ]
                }],
                "max_tokens": 1000
            }
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
            result = r.json()["choices"][0]["message"]["content"]
            print("✅ GPT 成功!")
        except Exception as e:
            print(f"❌ GPT 也失敗: {e}")
            return jsonify({"result": f"⚠️ 圖片辨識失敗，請確保圖片清晰後重試！"}), 500
    
    # ========================================
    # ✅ 儲存對話到 session 和資料庫
    # ========================================
    conversation = session["conversation"]
    conversation.append({"role": "user", "content": "📷 [上傳了數學題目圖片]"})
    conversation.append({"role": "assistant", "content": result})
    session["conversation"] = conversation
    session.modified = True

    # ⬅️ 重要：為「不懂」回饋準備上下文
    session["last_question"] = "[圖片題目]"         # 圖片題無純文字，先用占位
    session["last_explanation"] = result
    session["confused_count"] = 0                   # 圖片題講解剛產生，重新計算

    # 儲存到資料庫
    conn = get_conn()
    conn.execute(
        "INSERT INTO records (user_id, question, topic, is_correct) VALUES (?, ?, ?, ?)",
        (session["user_id"], "[圖片題目]", "圖片辨識", None)
    )
    conn.commit()
    conn.close()
    
    return jsonify({"result": result, "success": True}), 200


# -------------------------------
# 🩺 健康檢查
# -------------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


# -------------------------------
# 🚀 主程式入口
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"✅ 成功讀到 DEEPSEEK_API_KEY：{bool(deepseek_api_key)}")
    print(f"✅ 成功讀到 OPENAI_API_KEY：{bool(openai_api_key)}")
    print(f"✅ 成功讀到 GOOGLE_API_KEY：{bool(google_api_key)}")
    app.run(host="0.0.0.0", port=port)
