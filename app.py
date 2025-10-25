<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>數學小老師安安</title>
  <style>
    body{font-family:"Microsoft JhengHei",Arial,sans-serif;max-width:900px;margin:0 auto;padding:20px;background:#f7fbff;line-height:1.6}
    .header{background:#fff;padding:16px 20px;border-radius:12px;box-shadow:0 6px 20px rgba(0,0,0,.06);margin-bottom:16px}
    .header h1{margin:0;font-size:24px}
    .badge{display:inline-block;background:#ff7aa2;color:#fff;border-radius:999px;padding:2px 10px;font-size:12px;margin-left:8px}
    .bar{display:flex;gap:8px;margin-top:8px}
    #chat{background:#fff;border-radius:12px;box-shadow:0 6px 20px rgba(0,0,0,.06);padding:16px;height:420px;overflow:auto}
    #input{display:flex;gap:8px;margin-top:12px}
    #input textarea{flex:1;padding:10px;border-radius:8px;border:1px solid #cfd9e6;resize:vertical;min-height:60px}
    #input button{padding:10px 14px;border:0;border-radius:10px;background:#4c8bf5;color:#fff;cursor:pointer}
    .ghost{background:#e8eefc;color:#2b4ea3}
    .small{font-size:12px;color:#607089}
    .msg{margin:8px 0}
    .you{color:#2b4ea3}
    .anan{color:#0b5;white-space:pre-wrap}
  </style>
</head>
<body>
  <div class="header">
    <h1>🧮 數學小老師安安 <span class="badge">已登入</span></h1>
    <div class="small">歡迎，<b>{{ username }}</b>！直接輸入題目，或用下方快捷按鈕。</div>
    <div class="bar">
      <button class="ghost" onclick="quick('我不懂')">不懂</button>
      <button class="ghost" onclick="quick('我懂了')">懂了</button>
      <button class="ghost" onclick="location.href='/reset'">清除紀錄</button>
      <button class="ghost" onclick="location.href='/logout'">登出</button>
      {% if role == 'admin' %}
      <button class="ghost" onclick="location.href='/admin'">後台</button>
      {% endif %}
    </div>
  </div>

  <div id="chat"></div>

  <div id="input">
    <textarea id="message" placeholder="例如：9870 ÷ 6 = ?，或輸入 3+5="></textarea>
    <button onclick="send()">送出</button>
  </div>

  <script src="/static/script.js"></script>
</body>
</html>
