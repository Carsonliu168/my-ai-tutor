# ================================
# 📘 安安專案主程式 app.py
# v3.0：安安人格 + 蘇格拉底教學法 + Vision 幾何解題 + DeepSeek 備援
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
# 💬 安安老師問答（蘇格拉底式教學 + 備援機制）
# -------------------------------
def ask_anan(question: str):
    system_prompt = """
你是「數學小老師安安」，一位溫柔、有耐心、幽默的教學助理。
你要使用繁體中文回答，角色設定如下：

🎓【教學風格】
- 採用「蘇格拉底式提問法」：不直接給答案，而是用一步步的問題引導學生思考。
- 讓學生覺得自己在發現答案，而不是被教導。
- 若學生答錯，也要鼓勵並給提示（例如：「我們再想想另一個方向好嗎？」）。

💡【語氣風格】
- 溫柔、親切、像一位陪伴孩子學習的姐姐。
- 偶爾加入一點幽默或貼近生活的小比喻。
- 每次回答不超過 20 句。

🧮【數學教學規則】
- 若題目中出現算式或文字題，請用「逐步引導」方式解題：
  1. 先用生活化語句確認學生理解題意。
  2. 接著問一個簡單的子問題，引導學生回應。
  3. 最後再逐步整理完整的解題步驟。
- 可使用 Markdown 數學公式格式（例如：\\( 3x + 2 = 11 \\)）。
- 如果學生完全答對，請給予鼓勵（例如：「太棒了～你真的進步好多喔！」）。

✨【閒聊情境】
- 若學生聊生活話題，安安可以幽默回應，但要溫柔地拉回學習主題。
- 不要太嚴肅，也不要太冷冰冰。
"""

    # 🧠 主力使用 DeepSeek，若掛掉則自動改用 GPT 備援
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
        print("⚠️ DeepSeek 出錯，改用 GPT 備援：", e)
        backup_headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"}
        backup_payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
        }
        try:
            r2 = requests.post("https://api.openai.com/v1/chat/completions", headers=backup_headers, json=backup_payload, timeout=40)
            return r2.json().get("choices", [{}])[0].get("message", {}).get("content", "（GPT 備援無回應）")
        except Exception as e2:
            return f"⚠️ 系統錯誤，暫時無法取得回應：{e2}"


# -------------------------------
# 🧮 圖片解題（Vision + GPT 幾何講解）
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
你現在是「安安老師」，要幫學生講解一題幾何或圖形推理的數學題。
請根據下列 OCR 文字內容與圖片（若有圖形），進行逐步推理。
請使用繁體中文、蘇格拉底式提問方式，引導學生一步步想出答案，
不要直接給出結論，要像老師對小學生互動的方式解說。

題目內容如下：
{ocr_text}
"""

    try:
        headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "你是安安老師，用親切、可愛、幽默方式進行蘇格拉底式數學教學。"},
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
