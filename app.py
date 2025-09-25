from flask import Flask, request, render_template, session, redirect, url_for
import requests
import os
from datetime import timedelta
from requests.adapters import HTTPAdapter, Retry

# ====== 版本號 ======
APP_VERSION = "安安 v1.3D"

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.permanent_session_lifetime = timedelta(hours=2)

# ====== API 設定 ======
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

if not DEEPSEEK_API_KEY:
    DEEPSEEK_API_KEY = "sk-2fde4862ca7e43548fe23f4aed4076d5"
    print(f"⚠️ 環境變數沒讀到，改用寫死的 key | {APP_VERSION}")
else:
    print(f"✅ 成功讀到環境變數 | {APP_VERSION}")

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# 建立 requests session + retry 機制
session_req = requests.Session()
retries = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
session_req.mount("https://", HTTPAdapter(max_retries=retries))


# ====== DeepSeek 問答函數 ======
def ask_deepseek(user_message, conversation_history):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }

    system_prompt = """你是數學老師安安，請用蘇格拉底式的引導教學方式協助學生。  
規則如下：  
1. 使用繁體中文回答。  
2. 不直接給完整解答，要先引導學生思考下一步，並提出提示或問題。  
3. 逐步拆解題目，讓學生一步一步回答。  
4. 使用台灣常用的數學術語。  
5. 語氣要親切、鼓勵，像一位耐心的小老師。  
6. 如果需要舉例說明，請使用台灣常見的食物或生活物品（例如：珍珠奶茶、蔥油餅、滷肉飯、刈包、雞排）。  
7. 如果學生多次回答不出來，再給更多提示，最後才提供完整解答。  
8. 在完整解答結束後，請再出一題同樣概念的練習題，鼓勵學生自己嘗試。  
9. 如果學生的問題與數學學習無關（閒聊、歌曲、娛樂等），請用**簡短幽默可愛**的方式回答，並引導學生回到數學學習主題。  
"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    data = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1500
    }

    try:
        response = session_req.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            raw_response = result["choices"][0]["message"]["content"]

            # === 後處理：清理奇怪的 LaTeX 符號 ===
            latex_map = {
                "\\times": "×",
                "\\cdot": "×",
                "\\div": "÷",
                "\\(": "",
                "\\)": "",
                "$": ""
            }
            formatted_response = raw_response
            for k, v in latex_map.items():
                formatted_response = formatted_response.replace(k, v)

            # 去掉我們之前強制加的黑點符號
            formatted_response = formatted_response.replace("• ", "")

            return formatted_response
        else:
            return "安安好像沒聽懂，可以換個方式問嗎？"
    except Exception as e:
        print("❌ API 錯誤:", str(e))
        return "安安出了一點小狀況，先換個數學問題試試吧！"


# ====== 主頁 ======
@app.route('/', methods=['GET', 'POST'])
def home():
    if 'conversation' not in session or not isinstance(session['conversation'], list):
        session['conversation'] = [{'role': 'assistant', 'content': f'我是安安，你的數學小老師'}]

    if request.method == 'POST':
        user_message = request.form.get('message', '').strip()
        if user_message:
            session['conversation'].append({'role': 'user', 'content': user_message})

            ai_response = ask_deepseek(user_message, session['conversation'])

            session['conversation'].append({'role': 'assistant', 'content': ai_response})
            session.modified = True

    return render_template("index.html", conversation=session['conversation'], app_version=APP_VERSION)


# ====== 清除對話 ======
@app.route('/clear')
def clear_conversation():
    session['conversation'] = [{'role': 'assistant', 'content': f'對話已清除，從頭開始吧！'}]
    return redirect(url_for('home'))


# ====== 啟動 ======
if __name__ == '__main__':
    print(f"🚀 {APP_VERSION} 已啟動，準備接受請求！")
    app.run(host='0.0.0.0', port=5000, debug=True)
