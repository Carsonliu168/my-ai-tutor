# ================================
# 📘 安安專案主程式 app.py
# v3.7：DeepSeek 主答 + GPT 備援 + Vision OCR + 學習紀錄 + 自動正確率 +
#       蘇格拉底次數調整 + 對話保存 + 清除對話 + 學生自評功能修正
#       ＋ analyze_image 強化（不會卡住，永遠回 JSON）
# ================================

from flask import Flask, render_template, request, jsonify, redirect, session
import os, json, base64, requests, sqlite3, uuid, re
from datetime import datetime
from google.cloud import vision

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "anan-secret-key")

# -------------------------------
# ✅ 環境與 Vision 初始化
# -------------------------------
try:
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
    creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if creds_json:
        json.loads(creds_json)
        with open("google_cred.json", "w", encoding="utf-8") as f:
            f.write(creds_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_cred.json"
        vision_client = vision.ImageAnnotatorClient()
        print("✅ 成功啟用 Google Vision")
    else:
        vision_client = None
except Exception as e:
    print("⚠️ Vision 初始化錯誤：", e)
    vision_client = None


# -------------------------------
# 🧠 DeepSeek / GPT 模型（蘇格拉底或正常教學模式）
# -------------------------------
def ask_anan(question: str, mode="socratic"):
    if mode == "socratic":
        style = "採用蘇格拉底式提問法，引導學生思考，不直接給答案。"
    else:
        style = "用正常教學方式清楚給出解題步驟與答案。"

    system_prompt = f"""
你是「數學小老師安安」，一位親切、幽默、溫柔的教學助理。
請使用繁體中文回答。
教學風格：{style}
若題目中有算式，請條列步驟並清楚說明。
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
        backup_headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"}
        payload["model"] = "gpt-4o-mini"
        r2 = requests.post("https://api.openai.com/v1/chat/completions", headers=backup_headers, json=payload, timeout=40)
        return r2.json().get("choices", [{}])[0].get("message", {}).get("content", "（無回應）")


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
    print("✅ [安安] 資料庫就緒 (v3.7)")
init_db()


# -------------------------------
# 🎯 自動判斷答題正確率
# -------------------------------
def evaluate_answer(question, student_answer):
    try:
        if not re.search(r"[0-9=＋×÷\-*/]", question):
            return None
        headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"}
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

@app.route("/", methods=["GET", "POST"])
def home():
    if "conversation" not in session:
        session["conversation"] = []
        session["confused_count"] = 0
    conversation = session["conversation"]

    if request.method == "POST":
        user_msg = request.form.get("message", "")
        if user_msg:
            mode = "normal" if session.get("confused_count", 0) >= 2 else "socratic"
            ai_reply = ask_anan(user_msg, mode)

            conversation.append({"role": "user", "content": user_msg})
            conversation.append({"role": "assistant", "content": ai_reply})
            session["conversation"] = conversation

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
# 🧭 學生自評回饋
# -------------------------------
@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json()
    understood = data.get("understood")
    if understood is None:
        return jsonify({"status": "error"})
    if understood:
        session["confused_count"] = 0
    else:
        session["confused_count"] = session.get("confused_count", 0) + 1
    return jsonify({"status": "ok", "confused_count": session["confused_count"]})


# -------------------------------
# 🗑️ 清除對話
# -------------------------------
@app.route("/clear")
def clear():
    session.pop("conversation", None)
    session["confused_count"] = 0
    return redirect("/")


# -------------------------------
# 🧮 圖片解題（Vision + GPT 備援，強化穩定性）
# -------------------------------
@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"result": "⚠️ 沒有收到圖片"}), 400

    image_file = request.files["image"]
    image_bytes = image_file.read()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    ocr_text = ""
    try:
        if vision_client:
            image = vision.Image(content=image_bytes)
            response = vision_client.text_detection(image=image)
            ocr_text = response.text_annotations[0].description if response.text_annotations else ""
            print(f"📝 OCR 辨識結果：{(ocr_text or '')[:80]}...")
        else:
            ocr_text = "(Vision API 尚未初始化)"
    except Exception as e:
        print("⚠️ Vision OCR 發生錯誤：", e)
        ocr_text = "(OCR 失敗)"

    try:
        if not ocr_text.strip() or ocr_text == "(OCR 失敗)":
            user_prompt = "這是一題數學圖形題，請根據圖片推測題意並解題，條列清楚步驟與答案。"
        else:
            user_prompt = f"題目內容：{ocr_text}\n請幫學生逐步解釋，條列清楚步驟與答案。"

        headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "你是安安老師，用親切可愛的語氣一步步解釋數學題，必要時給出答案。"},
                {"role": "user", "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_base64", "image_base64": image_base64}
                ]}
            ]
        }

        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        result = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not result:
            result = "⚠️ GPT 沒有回應，可能圖片太複雜或 API 出錯。"
        return jsonify({"result": result}), 200, {"Content-Type": "application/json; charset=utf-8"}

    except Exception as e:
        print("⚠️ analyze_image 例外：", e)
        return jsonify({"result": f"⚠️ 圖片分析失敗：{e}"}), 500


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
    app.run(host="0.0.0.0", port=port)
