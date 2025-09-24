from flask import Flask, request, render_template, session, redirect, url_for
import requests
import os
from datetime import timedelta

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.permanent_session_lifetime = timedelta(hours=2)

# ====== API 設定 ======
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "你的預設APIKEY")
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
            simplified_to_traditional = {
                '质因数': '質因數', '约数': '因數', '这个': '這個',
                '个体': '個體', '数量': '數量', '问题': '問題',
                '计算': '計算', '答案': '答案', '结果': '結果'
            }
            for simp, trad in simplified_to_traditional.items():
                formatted_response = formatted_response.replace(simp, trad)
            return formatted_response
        else:
            return "安安正在思考中..."
    except:
        return "安安正在思考中..."

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
