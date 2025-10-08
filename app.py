# ================================
# 📘 安安專案主程式 app.py
# 升級版：加入 /analyze_image (Vision + GPT 幾何解題)
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
        # 初始化 Vision API
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
# 📄 首頁 - 修正版：支持 GET 和 POST
# -------------------------------
@app.route("/", methods=["GET", "POST"])
def home():
    conversation = []
    
    if request.method == "POST":
        user_message = request.form.get("message", "")
        if user_message:
            # 呼叫 DeepSeek API
            headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": user_message}]
            }
            
            try:
                r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=30)
                ai_response = r.json().get("choices", [{}])[0].get("message", {}).get("content", "沒有回應")
                
                conversation.append({"role": "user", "content": user_message})
                conversation.append({"role": "assistant", "content": ai_response})
            except Exception as e:
                conversation.append({"role": "assistant", "content": f"錯誤：{e}"})
    
    return render_template("index.html", conversation=conversation)

# -------------------------------
# 💬 一般問答 (原功能)
# -------------------------------
@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    question = data.get("question", "")
    if not question:
        return jsonify({"result": "請輸入問題內容"}), 400

    # 呼叫 DeepSeek / GPT API（這裡用 DeepSeek 範例）
    headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": question}]
    }

    try:
        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=30)
        result = r.json().get("choices", [{}])[0].get("message", {}).get("content", "（沒有回應）")
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"result": f"⚠️ 伺服器錯誤：{e}"}), 500

# -------------------------------
# 🧮 新功能：上傳圖片 → Vision OCR + GPT 幾何解題
# -------------------------------
@app.route("/analyze_image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"result": "沒有收到圖片"}), 400

    image_file = request.files["image"]
    image_bytes = image_file.read()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    # --- 用 Google Vision OCR ---
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

    # --- 將圖片 + OCR 結果交給 GPT 做幾何分析 ---
    headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
    prompt = f"""
請閱讀下列 OCR 文字內容,並同時觀察圖片（若有圖形）。
這是一道幾何圖形相關的數學題,請推理題意並詳細講解解題步驟。

題目文字：
{ocr_text}
"""

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_base64", "image_base64": image_base64}
            ]}
        ]
    }

    try:
        r = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=60)
        result = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        return jsonify({"result": result}), 200, {"Content-Type": "application/json; charset=utf-8"}
    except Exception as e:
        print("⚠️ analyze_image 發生錯誤：", e)
        return jsonify({"result": f"⚠️ 系統錯誤：{e}"}), 500

# -------------------------------
# 🩺 健康檢查（可選）
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