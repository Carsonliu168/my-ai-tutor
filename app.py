from flask import Flask, request, render_template, session, redirect, url_for
import requests
import os
from datetime import timedelta

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.permanent_session_lifetime = timedelta(hours=2)

# ====== API 設定 ======
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

if not DEEPSEEK_API_KEY:
    # fallback，避免 Railway 沒吃到變數
    DEEPSEEK_API_KEY = "sk-2fde4862ca7e43548fe23f4aed4076d5"
    print("⚠️ 環境變數沒讀到，改用寫死的 key")
else:
    print("✅ 成功讀到環境變數")

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# ====== DeepSeek 問答函數 ======
def ask_deepseek(user_message, conversation_history):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }

    system_prompt = """你是數學老師安安，請遵守以下要求：
1. 使用繁體中文回答
2. 不要使用 - 符號，改用 • 符號或數字編號
3. 用台灣常用的數學術語
4. 回答要清晰易懂"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    data = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2000
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            raw_response = result["choices"][0]["message"]["content"]
            formatted_response = raw_response.replace('- ', '• ')
            return formatted_response
        else:
            return "安安好像沒聽懂，可以換個方式問嗎？"
    except Exception as e:
        print("❌ API 錯誤:", str(e))
        return f"安安出現錯誤：{str(e)}"

# ====== 主頁 ======
@app.route('/', methods=['GET', 'POST'])
def home():
    if 'conversation' not in session:
        session['conversation'] = [{'role': 'assistant', 'content': '我是安安，你的數學小老師'}]

    if request.method == 'POST':
        user_message = request.form.get('message', '').strip()
        if user_message:
            session['conversation'].append({'role': 'user', 'content': user_message})
            ai_response = ask_deepseek(user_message, session['conversation'])
            session['conversation'].append({'role': 'assistant', 'content': ai_response})
            session.modified = True

    return render_template("index.html", conversation=session['conversation'])

# ====== 清除對話 ======
@app.route('/clear')
def clear_conversation():
    session['conversation'] = [{'role': 'assistant', 'content': '對話已清除'}]
    return redirect(url_for('home'))

# ====== 啟動 ======
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
