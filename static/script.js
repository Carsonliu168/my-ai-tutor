// 基本聊天功能
function appendMessage(role, content) {
  const box = document.getElementById("chat-box");
  const div = document.createElement("div");
  div.className = role;
  div.innerHTML = marked.parse(content);
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function sendMessage() {
  const input = document.getElementById("user-input");
  const text = input.value.trim();
  if (!text) return;

  appendMessage("student", text);
  input.value = "";

  appendMessage("anan", "安安正在思考中...");
  fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text })
  })
  .then(r => r.json())
  .then(data => {
    const responses = document.getElementsByClassName("anan");
    const last = responses[responses.length - 1];
    last.innerHTML = marked.parse(data.reply);
    MathJax.typesetPromise();
  })
  .catch(err => {
    appendMessage("anan", "⚠️ 系統忙碌，請稍後再試。");
    console.error(err);
  });
}
