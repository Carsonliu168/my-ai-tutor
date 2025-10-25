// ================================================
// 📘 安安專案前端控制腳本
// v5.0.20-dialogsync：修正懂了/不懂同步 & 分段顯示
// ================================================

let lastQuestion = "";
let confusionCount = 0;

document.addEventListener("DOMContentLoaded", () => {
  const chatForm = document.getElementById("chat-form");
  const userInput = document.getElementById("user-input");
  const chatBox = document.getElementById("chat-box");
  const loadingText = document.getElementById("loading-text");
  const uploadInput = document.getElementById("image-upload");

  function autoFormatMath(text) {
    if (!text) return text;
    text = text.replace(/\$\$\$/g, "$$");
    text = text.replace(/\$\s*\$/g, "$");
    text = text.replace(/\$\$([^\$]+)\$\$\$/g, "$$$1$$");
    text = text.replace(/\\left(?![({[])/g, "(");
    text = text.replace(/\\right(?![)}\]])/g, ")");
    text = text.replace(/\[([^\[\]]+)\]/g, "\$$1\$");
    text = text.replace(/([^$])((?:\\frac|\\sqrt|\\sin|\\cos|\\tan)[^$ ]+)/g, "$1\$$2\$");
    text = text.replace(/([=：])([\d\w\s\\\+\-\*\/\(\)\.]+)([。；\)])/g, "$1\$$2\$$3");
    return text;
  }

  function appendMessage(role, text) {
    const message = document.createElement("div");
    message.className = role;
    message.innerHTML = role === "student" ? text : autoFormatMath(text);
    chatBox.appendChild(message);
    chatBox.scrollTop = chatBox.scrollHeight;
    if (window.MathJax && window.MathJax.typesetPromise) {
      MathJax.typesetPromise([message]);
    }
  }

  // ✉️ 送出自輸入的訊息
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = userInput.value.trim();
    if (!input) return;

    lastQuestion = input;
    confusionCount = 0;

    appendMessage("student", input);
    userInput.value = "";

    const thinkingMsg = document.createElement("div");
    thinkingMsg.className = "anan";
    thinkingMsg.innerHTML = "🤔 安安思考中...";
    thinkingMsg.id = "thinking-message";
    chatBox.appendChild(thinkingMsg);
    chatBox.scrollTop = chatBox.scrollHeight;
    loadingText.style.display = "block";

    try {
      const response = await fetch("/", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: `message=${encodeURIComponent(input)}`
      });
      const data = await response.json();
      loadingText.style.display = "none";
      document.getElementById("thinking-message")?.remove();

      appendMessage("anan", data.reply || "⚠️ 系統忙碌，請稍後再試。");
    } catch (error) {
      loadingText.style.display = "none";
      document.getElementById("thinking-message")?.remove();
      appendMessage("anan", "⚠️ 無法連線到伺服器，請稍後重試。");
    }
  });

  // ✉️ 給「我懂了」「我不懂」按鈕
  window.sendMessage = async function (presetText) {
    let message = presetText;
    if (!message) return;

    // 智能「不懂」邏輯
    if (message === "我不懂") {
      confusionCount++;
      if (confusionCount === 1) {
        message = lastQuestion ? `這題「${lastQuestion}」我有點不太懂。` : "我不懂";
      } else if (confusionCount === 2) {
        message = lastQuestion ? `「${lastQuestion}」我還是不太懂，能換個方法再教一次嗎？` : "我還是不太懂。";
      } else if (confusionCount >= 3) {
        message = "我已經問了三次還是不懂，請你親切地建議我記下這題去問老師，不要再繼續講解。";
      }
    } else if (message === "我懂了") {
      confusionCount = 0;
    } else {
      lastQuestion = message;
      confusionCount = 0;
    }

    appendMessage("student", presetText);
    const thinking = document.createElement("div");
    thinking.className = "anan";
    thinking.innerHTML = "🤔 安安思考中...";
    thinking.id = "thinking-message-btn";
    chatBox.appendChild(thinking);
    chatBox.scrollTop = chatBox.scrollHeight;
    loadingText.style.display = "block";

    try {
      const res = await fetch("/", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: `message=${encodeURIComponent(message)}`
      });
      const data = await res.json();
      loadingText.style.display = "none";
      document.getElementById("thinking-message-btn")?.remove();

      appendMessage("anan", data.reply || "⚠️ 系統忙碌，請稍後再試。");
    } catch (error) {
      loadingText.style.display = "none";
      document.getElementById("thinking-message-btn")?.remove();
      appendMessage("anan", "⚠️ 無法連線到伺服器，請稍後重試。");
    }
  };

  // 📷 上傳圖片題
  uploadInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    lastQuestion = "[圖片題目]";
    confusionCount = 0;

    const thinking = document.createElement("div");
    thinking.className = "anan";
    thinking.innerHTML = "🤔 安安思考中...";
    thinking.id = "thinking-upload";
    chatBox.appendChild(thinking);
    chatBox.scrollTop = chatBox.scrollHeight;
    loadingText.style.display = "block";

    try {
      const res = await fetch("/upload", { method: "POST", body: formData });
      const data = await res.json();
      loadingText.style.display = "none";
      document.getElementById("thinking-upload")?.remove();
      appendMessage("anan", data.reply || "⚠️ 圖片辨識失敗。");
    } catch (err) {
      loadingText.style.display = "none";
      document.getElementById("thinking-upload")?.remove();
      appendMessage("anan", "⚠️ 圖片上傳或辨識失敗。");
    }
    uploadInput.value = "";
  });
});
