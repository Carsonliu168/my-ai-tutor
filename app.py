from flask import Flask, request, render_template_string, session
import requests
import json
import os
import time
from datetime import timedelta

app = Flask(__name__)
app.secret_key = os.urandom(24)  # 隨機生成密鑰
app.permanent_session_lifetime = timedelta(hours=2)  # 會話有效期2小時

# 從環境變數獲取 API Key
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-2fde4862ca7e43548fe23f4aed4076d5")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# HTML 界面 - 支援更好的排版和簡單圖形
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>AI家教老師</title>
    <meta charset="UTF-8">
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
            white-space: pre-wrap; /* 保留空白和換行 */
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
        input[type="submit"]:disabled {
            background: #cccccc;
            cursor: not-allowed;
            transform: none;
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
        .loading-dots::after {
            content: '';
            animation: dots 1.5s infinite;
        }
        @keyframes dots {
            0%, 20% { content: '.'; }
            40% { content: '..'; }
            60%, 100% { content: '...'; }
        }
        .status-message {
            text-align: center;
            padding: 10px;
            margin: 10px 0;
            border-radius: 5px;
        }
        .status-error {
            background-color: #ffebee;
            color: #c62828;
            border: 1px solid #ffcdd2;
        }
        .status-success {
            background-color: #e8f5e9;
            color: #2e7d32;
            border: 1px solid #c8e6c9;
        }
        .math-diagram {
            background: #fff3e0;
            padding: 15px;
            border-radius: 10px;
            border-left: 4px solid #ff9800;
            margin: 10px 0;
            font-family: 'Courier New', monospace;
            white-space: pre;
            overflow-x: auto;
        }
        .step {
            background: #e8f5e9;
            padding: 10px;
            border-radius: 8px;
            margin: 5px 0;
            border-left: 3px solid #4CAF50;
        }
        .formula {
            background: #e3f2fd;
            padding: 10px;
            border-radius: 8px;
            margin: 5px 0;
            border-left: 3px solid #2196F3;
        }
    </style>
    <script>
        function scrollToBottom() {
            const chatContainer = document.getElementById('chat-container');
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        function handleSubmit() {
            document.querySelector('input[type="submit"]').disabled = true;
            document.querySelector('input[type="submit"]').value = '⏳ 處理中...';
            
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'loading';
            loadingDiv.id = 'loading-message';
            loadingDiv.innerHTML = '👨‍🏫 AI老師思考中<span class="loading-dots"></span>';
            
            document.getElementById('chat-container').appendChild(loadingDiv);
            scrollToBottom();
            
            return true;
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            scrollToBottom();
            
            document.querySelector('form[action="/clear"]').addEventListener('submit', function(e) {
                if (!confirm('確定要清除所有對話記錄嗎？')) {
                    e.preventDefault();
                }
            });
            
            document.querySelector('form[action="/keep_last"]').addEventListener('submit', function(e) {
                if (!confirm('確定要只保留最近3組對話嗎？')) {
                    e.preventDefault();
                }
            });
        });
    </script>
</head>
<body>
    <h1>🎓 AI數學家教老師（五年級）</h1>
    
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
            <input type="text" name="user_message" placeholder="請輸入您的問題或回答..." required autofocus>
            <input type="submit" value="🚀 傳送">
        </div>
    </form>
    
    <div class="button-container">
        <form method="POST" action="/keep_last">
            <input type="submit" value="📋 保留最近對話" class="keep-last-btn">
        </form>
        <form method="POST" action="/clear">
            <input type="submit" value="🧹 清除所有對話" class="clear-btn">
        </form>
    </div>
    <div class="info-text">對話記錄會保存在瀏覽器中，關閉頁面後仍然存在</div>
</body>
</html>
'''

def ask_deepseek(user_message, conversation_history):
    """呼叫 DeepSeek API，並帶上之前的對話歷史"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 優化的系統提示詞
    messages = [
        {
            "role": "system",
            "content": """你是一個台灣國小五年級數學老師，使用蘇格拉底教學法。請用引導式、生活化的方式回答問題。

重要指導原則：
🎯 可以用這些符號來排版：▸ • ☆ → ╱╲ ▲ ● ◯ ▢
🎯 可以用簡單的文字圖形來解釋幾何概念
🎯 公式計算要逐步解釋，不要跳步
🎯 可以用數字編號但不要用Markdown格式
🎯 重要概念可以重複強調
🎯 鼓勵學生動手畫圖

圖形範例：
三角形：▲    圓形：◯    方形：▢
分數：可以用披薩🍕、蛋糕🎂來比喻
數線：可以用文字描述位置

請用繁體中文回答，並使用台灣常用的數學術語。"""
        }
    ]
    
    # 加入之前的所有對話歷史
    for msg in conversation_history:
        messages.append({"role": msg['role'], "content": msg['content']})
    
    # 加入用戶最新的訊息
    messages.append({"role": "user", "content": user_message})
    
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "max_tokens": 1000,  # 增加回應長度
        "temperature": 0.7,
        "timeout": 30
    }
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except requests.exceptions.Timeout:
        return "⚠️ 回應超時，請稍後再試或重新發送問題。"
    except requests.exceptions.ConnectionError:
        return "⚠️ 網路連線錯誤，請檢查您的網路連線。"
    except Exception as e:
        return f"⚠️ 發生錯誤：{str(e)}"

@app.route('/', methods=['GET', 'POST'])
def home():
    if 'conversation' not in session:
        session['conversation'] = []
    
    status_message = None
    status_type = None
    
    if request.method == 'POST':
        user_message = request.form['user_message']
        
        if user_message.strip():
            session['conversation'].append({"role": "user", "content": user_message})
            
            try:
                ai_response = ask_deepseek(user_message, session['conversation'])
                session['conversation'].append({"role": "assistant", "content": ai_response})
                session.modified = True
            except Exception as e:
                status_message = f"系統錯誤：{str(e)}"
                status_type = "error"
    
    return render_template_string(
        HTML_TEMPLATE, 
        conversation=session['conversation'],
        status_message=status_message or "None",
        status_type=status_type or "None"
    )

@app.route('/clear', methods=['POST'])
def clear_conversation():
    session['conversation'] = []
    session.modified = True
    return render_template_string(
        HTML_TEMPLATE, 
        conversation=[],
        status_message="對話記錄已清除",
        status_type="success"
    )

@app.route('/keep_last', methods=['POST'])
def keep_last_conversation():
    if 'conversation' in session and len(session['conversation']) > 6:
        session['conversation'] = session['conversation'][-6:]
        status_msg = "已保留最近3組對話"
    else:
        status_msg = "對話記錄不足3組，保持原樣"
    
    session.modified = True
    return render_template_string(
        HTML_TEMPLATE, 
        conversation=session['conversation'],
        status_message=status_msg,
        status_type="success"
    )

if __name__ == '__main__':
    print("🎯 AI家教服務啟動中...")
    print("🌐 請在瀏覽器打開: http://localhost:5000")
    print("⏹️ 按 Ctrl+C 可停止服務")
    print("🔒 建議設置環境變數: export DEEPSEEK_API_KEY=您的金鑰")
    print("💡 現在支援更好的數學圖形顯示！")
    app.run(debug=True, host='0.0.0.0', port=5000)