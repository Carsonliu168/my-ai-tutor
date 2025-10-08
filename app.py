# ================================
# 📘 安安專案主程式 app.py
# 終極繁體版 v2.0：Vision OCR + GPT 幾何講解 + DeepSeek 備援 + 安安人格
# ================================

from flask import Flask, render_template, request, jsonify
import os, json, base64, requests
from google.cloud import vision

app = Flask(__name__)

# -------------------------------
# ✅ 啟動時檢查環境變數
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
        print("✅ 成功讀到 GOOGLE_APPLICATION_CREDENTIALS_JSON")
        with open("google_cred.json", "w", encoding="utf-8") as f:
            f.write(creds_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_cred.json"
        vision_client = vision.ImageAnnotatorClient()
    else:
        print("❌ 找不到 GOOGLE_APPLICATION_CREDENTIALS_JSON")
        vision_client = None
except Exception as e:
    print("⚠️ 啟動時環境檢查出錯：", e)
    vision_client = None


# -------------------------------
# 📄 首頁
# -------------------------------
@app.route("/", methods=["GET", "POST"])
def home():
    conversation = []
    if request.method == "POST":
        user_message = request.form.get("message", "")
        if user_message:
            ai_response = ask_anan(user_message)
            conversation.append({"role": "user", "content": user_message})
            conversation.append({"role": "assistant", "content": ai_response})
    return render_template("index.html", conversation=conversation)


# -------------------------------
# 💬 文字問答（安安人格 + DeepSeek 備援）
# -------------------------------
def ask_anan(question: str):
    system_prompt = """
你是一位名叫「安安」的數學小老師，個性溫柔、幽默又有耐心。
請用繁體中文回答，語氣要像在陪國小學生聊天，
回答要親切、有趣、互動性高。
但要記得：
- 每次回應不要超過 20 句。
- 即使學生聊偏題，也要用幽默方式慢慢拉回數學主題。
- 若是數學題，要先用簡單口語幫助他理解題意，再逐步引導解題。
- 回答時可使用 Markdown 公式格式（如 \\( a^2 + b^2 = c^2 \\) ）。
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
        result = r.json().get("choices", [{}])[0].get("message", {}).get("content", "（沒有回應）")
        return result
    except Exception as e:
        print("⚠️ DeepSeek 錯誤，改用 GPT 備援：", e)
        # 備援 → GPT-4o-mini
        backup_payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
        }
        backup_headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"}
        try:
            r2 = requests.post("https://api.openai.com/v1/chat/completions", headers=backup_headers, json=backup_payload, timeout=40)
            return r2.json().get("choices", [{}])[0].get("message", {}).get("content", "（GPT 備援無回應）")
        except Exception as e2:
            return f"⚠️ 系統錯誤，暫時無法取得回應：{e2}"


# -------------------------------
# 🧮 圖片解題（Vision + GPT 幾何分析）
# -------------------------------
@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"result": "沒有收到圖片"}), 400

    image_file = request.files["image"]
    image_bytes = image_file.read()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    # --- Google Vision OCR ---
    ocr_text = ""
    try:
        if vision_client:
            image = vision.Image(content=image_bytes)
            response = vision_client.text_detection(image=image)
            ocr_text = response.text_annotations[0].description if response.text_annotations else ""
            print(f"📝 OCR 辨識結果：{ocr_text[:80]}...")
        else:
            ocr_text = "(Vision API 尚未初始化)"
    except Exception as e:
        print("⚠️ Vision OCR 發生錯誤：", e)
        ocr_text = "(OCR 失敗)"

    # --- GPT 幾何分析 ---
    gpt_prompt = f"""
你現在是「安安老師」，是一位專精幾何與圖形推理的數學小老師。
請根據下列 OCR 文字內容與圖片（若有圖形），詳細推理題意並逐步講解。
請使用繁體中文、口語化方式講解，語氣可愛、有互動感，
並可用 Markdown 呈現公式。
題目內容如下：
{ocr_text}
"""

    try:
        headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "你是安安老師，請用親切、可愛、幽默的方式講解數學。"},
                {"role": "user", "content": [
                    {"type": "text", "text": gpt_prompt},
                    {"type": "image_base64", "image_base64": image_base64}
                ]}
            ]
        }
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
        result = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        return jsonify({"result": result}), 200, {"Content-Type": "application/json; charset=utf-8"}

    except Exception as e:
        print("⚠️ GPT 幾何分析錯誤：", e)
        return jsonify({"result": f"⚠️ 系統錯誤：{e}"}), 500


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
