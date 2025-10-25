// ================================
// 📘 安安前端互動邏輯 script.js
// ================================

document.addEventListener("DOMContentLoaded", function () {
  const chatBox = document.getElementById("chat-box");
  const input = document.getElementById("user-input");
  const sendBtn = document.getElementById("send-btn");
  const clearBtn = document.getElementById("clear-btn");
  const uploadBtn = document.getElementById("upload-btn");
  const understoodBtn = document.getElementById("understood-btn");
  const confusedBtn = document.getElementById("confused-btn");

  function appendMessage(sender, message) {
    const div = document.createElement("div");
    div.className = sender;
    div.innerHTML = message;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
    if (window.MathJax) MathJax.typesetPromise();
  }

  async function sendMessage(message) {
    appendMessage("user", `<b>👤 你：</b> ${message}`);
    input.value = "";
    appendMessage("anan", `<i>安安正在思考中...</i>`);

    try {
      const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: `message=${encodeURIComponent(message)}`
      });
      const data = await res.json();
      chatBox.lastChild.remove();
      appendMessage("anan", `<b>🧮 安安：</b> ${data.reply}`);
    } catch (e) {
      chatBox.lastChild.remove();
      appendMessage("anan", `<b>⚠️ 系統忙碌，請稍後再試。</b>`);
    }
  }

  sendBtn.addEventListener("click", () => {
    const msg = input.value.trim();
    if (msg) sendMessage(msg);
  });

  input.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendBtn.click();
    }
  });

  clearBtn.addEventListener("click", () => {
    window.location.href = "/clear";
  });

  uploadBtn.addEventListener("click", () => {
    alert("📷 圖片上傳功能暫未啟用（待 Vision 模組重新串接）");
  });

  understoodBtn.addEventListener("click", () => sendMessage("我懂了"));
  confusedBtn.addEventListener("click", () => sendMessage("我不懂"));

  appendMessage("anan", "👋 安安：你好呀～今天想學什麼數學題呢？");
});
