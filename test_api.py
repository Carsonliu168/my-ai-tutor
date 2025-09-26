import requests

API_KEY = "sk-b2bbd9aa039f4eed84e7c25f3a14d407"
API_URL = "https://api.deepseek.com/v1/chat/completions"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

data = {
    "model": "deepseek-chat",
    "messages": [
        {"role": "user", "content": "1+1等於多少？"}
    ]
}

try:
    resp = requests.post(API_URL, headers=headers, json=data, timeout=30)
    print("狀態碼:", resp.status_code)
    print("回應內容:", resp.text)
except Exception as e:
    print("❌ 錯誤:", e)
