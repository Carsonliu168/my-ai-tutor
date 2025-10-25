// ================================
// 📘 安安前端互動邏輯 script.js
// v4.8.0-restored (POST "/") + Vision upload
// ================================

document.addEventListener("DOMContentLoaded", function () {
  const chatBox = document.getElementById("chat-box");
  const input = document.getElementById("user-input");
  const sendBtn = document.getElementById("send-btn");
  const uploadBtn = document.getElementById("upload-btn");
  const understoodBtn = document.getElementById("understood-btn");
  const confusedBtn = document.getElementById("confused-btn");

  function appendMessage(sender, message) {
    const div = document.createElement("div");
    div.className = "msg " + sender;
    div.innerHTML = message;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
    if (window.MathJax) MathJax.typesetPromise();
  }

  async function sendToBackend(text) {
    appendMessage("user", `<b>👤 你：</b> ${text}`);
    input.value = "";
    appendMessage("anan", `<i>安安正在思考中...</i>`);

    try {
      const body = new URLSearchParams();
      body.append("message", text);

      const res = await fetch("/", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body
      });
      const data = await res.json();
      chatBox.lastChild.remove();
      appendMessage("anan", `<b>🧮 安安：</b> ${data.reply}`);
    } catch (e) {
      chatBox.lastChild.remove();
      appendMessage("anan", `<b>⚠️ 系統忙碌，請稍後再試。</b>`);
    }
  }

  // 送出
  sendBtn.addEventListener("click", () => {
    const msg = (input.value || "").trim();
    if (msg) sendToBackend(msg);
  });

  // Enter 快捷送出
  input.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendBtn.click();
    }
  });

  // 懂了 / 不懂
  understoodBtn.addEventListener("click", () => sendToBackend("我懂了"));
  confusedBtn.addEventListener("click", () => sendToBackend("我不懂"));

  // 圖片上傳（/analyze_image）
  uploadBtn.addEventListener("click", async () => {
    const picker = document.createElement("input");
    picker.type = "file";
    picker.accept = "image/*";
    picker.onchange = async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;

      appendMessage("user", `📷 上傳圖片：${file.name}`);
      appendMessage("anan", `<i>安安正在看這張圖片題喔...</i>`);

      const formData = new FormData();
      formData.append("image", file);

      try {
        const res = await fetch("/analyze_image", { method: "POST", body: formData });
        const data = await res.json();
        chatBox.lastChild.remove();
        appendMessage("anan", `<b>🧮 安安：</b> ${data.reply}`);
      } catch (err) {
        chatBox.lastChild.remove();
        appendMessage("anan", `<b>⚠️ 圖片辨識失敗，請稍後再試。</b>`);
      }
    };
    picker.click();
  });

  // 前端歡迎詞（非模型）
  appendMessage("anan", "👋 安安：已登入成功。直接輸入題目，或點「不懂 / 懂了 / 上傳圖片題」。");
});
