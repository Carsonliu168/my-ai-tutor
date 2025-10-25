(function(){
  const chat = document.getElementById('chat');
  const messageEl = document.getElementById('message');

  function append(role, text){
    const div = document.createElement('div');
    div.className = 'msg ' + (role === 'you' ? 'you' : 'anan');
    div.innerHTML = (role === 'you' ? '你：' : '安安：') + text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
  }

  window.quick = function(txt){
    messageEl.value = txt;
    send();
  }

  window.send = async function(){
    const msg = (messageEl.value || '').trim();
    if(!msg) return;
    append('you', msg);
    messageEl.value = '';
    append('anan', '安安正在思考中...');

    try{
      const form = new FormData();
      form.append('message', msg);
      const res = await fetch('/chat', { method: 'POST', body: form });
      const data = await res.json();
      const last = chat.querySelectorAll('.msg.anan');
      if(last.length){
        last[last.length - 1].innerHTML = '安安：' + (data.reply || '（沒有內容）');
      }
    }catch(e){
      const last = chat.querySelectorAll('.msg.anan');
      if(last.length){
        last[last.length - 1].innerHTML = '安安：系統忙碌，請稍後再試。';
      }
    }
  };

  // 初始提示（前端的問候語，不靠模型）
  append('anan', '嗨～已登入成功。直接輸入題目，或點「不懂 / 懂了 / 清除紀錄」。');
})();
