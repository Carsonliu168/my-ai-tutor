from flask import Flask, request, render_template_string, session
import requests
import os
from datetime import timedelta

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.permanent_session_lifetime = timedelta(hours=2)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-2fde4862ca7e43548fe23f4aed4076d5")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>AI數學家教老師</title>
    <meta charset="UTF-8">
    <!-- MathJax 數學公式渲染 -->
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        body { 
            font-family: Arial, "Microsoft JhengHei", sans-serif; 
            max-width: 900px; 
            margin: 0 auto; 
            padding: 20px; 
            background-color: #f0f8ff; 
        }
        .chat-container { 
            border: 2px solid #4CAF50; 
            border-radius: 15px; 
            padding: 20px; 
            margin-bottom: 20px; 
            background: white; 
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            height: 500px; 
            overflow-y: auto;
        }
        .user { 
            color: #2c3e50; 
            margin-bottom: 15px; 
            padding: 12px; 
            background: #e3f2fd; 
            border-radius: 12px; 
            text-align: right; 
            margin-left: 20%;
        }
        .ai { 
            color: #1b5e20; 
            margin-bottom: 20px; 
            padding: 15px; 
            background: #e8f5e9; 
            border-radius: 12px; 
            line-height: 1.6; 
            text-align: left; 
            margin-right: 20%;
            white-space: pre-wrap;
        }
        .input-container {
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }
        input[type="text"] { 
            flex: 1;
            padding: 15px; 
            border: 2px solid #4CAF50; 
            border-radius: 8px; 
            font-size: 16px; 
            outline: none;
        }
        input[type="text"]:focus {
            border-color: #2196F3;
            box-shadow: 0 0 5px rgba(33, 150, 243, 0.5);
        }
        input[type="submit"] { 
            padding: 15px 25px; 
            background: #4CAF50; 
            color: white; 
            border: none; 
            border-radius: 8px; 
            cursor: pointer; 
            font-size: 16px; 
            font-weight: bold;
        }
        input[type="submit"]:hover { 
            background: #45a049; 
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }
        h1 { 
            color: #2c3e50; 
            text-align: center; 
            margin-bottom: 30px;
            background: linear-gradient(135deg, #4CAF50, #2196F3);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .button-container {
            display: flex;
            gap: 10px;
            margin-top: 10px;
        }
        .clear-btn, .keep-last-btn {
            padding: 12px 18px;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            flex: 1;
        }
        .clear-btn {
            background: #ff4757;
        }
        .keep-last-btn {
            background: #ffa502;
        }
        .clear-btn:hover {
            background: #ff3742;
        }
        .keep-last-btn:hover {
            background: #e67e22;
        }
        .info-text {
            text-align: center;
            color: #666;
            font-size: 12px;
            margin-top: 5px;
        }
        .loading {
            text-align: center;
            color: #2196F3;
            padding: 10px;
            font-style: italic;
        }
        .math-formula {
            background: #fff3e0;
            padding: 10px;
            border-radius: 8px;
            margin: 10px 0;
            border-left: 4px solid #ff9800;
        }
    </style>
    <script>
        function scrollToBottom() {
            const chatContainer = document.getElementById('chat-container');
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        function handleSubmit() {
            document.querySelector('input[type="submit"]').disabled = true;
            document.querySelector('input[type="submit"]').value = '思考中...';
            return true;
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            scrollToBottom();
        });
    </script>
</head>
<body>
    <h1>🎓 AI數學家教老師</h1>
    
    <div class="chat-container" id="chat-container">
        {% if conversation %}
            {% for message in conversation %}
                {% if message.role == 'user' %}
                    <div class="user"><strong>👦 您：</strong>{{ message.content }}</div>
                {% else %}
                    <div class="ai"><strong>👨‍🏫 AI老師：</strong>{{ message.content | safe }}</div>
                {% endif %}
            {% endfor %}
        {% else %}
            <div class="ai"><strong>👨‍🏫 AI老師：</strong>歡迎！我是您的數學家教老師。請問有什麼數學問題需要幫忙嗎？</div>
        {% endif %}
    </div>

    <form method="POST" onsubmit="return handleSubmit()">
        <div class="input-container">
            <input type="text" name="user_message" placeholder="請輸入您的數學問題..." required autofocus>
            <input type="submit" value="🚀 傳送">
        </div>
    </form>
    
    <div class="button-container">
        <form method="POST" action="/keep_last">
            <input type="submit" value="📋 保留最近對話" class="keep-last-btn">
        </form>
        <form method="POST" action="/clear">
            <input type="submit" value="🧹 清除對話" class="clear-btn">
        </form>
    </div>
    <div class="info-text">對話記錄會暫時保存在瀏覽器中</div>
</body>
</html>
'''

def ask_deepseek(user_message, conversation_history):
    """呼叫 DeepSeek API"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    messages = [
        {
            "role": "system", 
            "content": "你是台灣國小數學老師，用引導方式教學，使用生活化例子。可以用簡單符號：▸ • → 但避免複雜格式。"
        }
    ]
    
    for msg in conversation_history:
        messages.append({"role": msg['role'], "content": msg['content']})
    
    messages.append({"role": "user", "content": user_message})
    
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "max_tokens": 1000,
        "temperature": 0.7
    }
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except:
        return "⚠️ 暫時無法回應，請稍後再試。"

@app.route('/', methods=['GET', 'POST'])
def home():
    if 'conversation' not in session:
        session['conversation'] = []
    
    if request.method == 'POST':
        user_message = request.form['user_message']
        if user_message.strip():
            session['conversation'].append({"role": "user", "content": user_message})
            try:
                ai_response = ask_deepseek(user_message, session['conversation'])
                session['conversation'].append({"role": "assistant", "content": ai_response})
                session.modified = True
            except Exception as e:
                session['conversation'].append({"role": "assistant", "content": f"⚠️ 發生錯誤：{str(e)}"})
    
    return render_template_string(HTML_TEMPLATE, conversation=session['conversation'])

@app.route('/clear', methods=['POST'])
def clear_conversation():
    session['conversation'] = []
    session.modified = True
    return render_template_string(HTML_TEMPLATE, conversation=[])

@app.route('/keep_last', methods=['POST'])
def keep_last_conversation():
    if 'conversation' in session and len(session['conversation']) > 6:
        session['conversation'] = session['conversation'][-6:]
    session.modified = True
    return render_template_string(HTML_TEMPLATE, conversation=session['conversation'])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)