// ================================================
// 📘 安安專案前端控制腳本
// v5.0.20-securefix
// - 修正 $1$ 顯示亂碼
// - 避免重複包裹已有公式
// - 防止連點「不懂」造成重複請求
// ================================================

let lastQuestion = "";
let confusionCount = 0;
let isWaiting = false;

document.addEventListener("DOMContentLoaded", () => {
  const chatForm = document.getElementById("chat-form");
  const userInput = document.getElementById("user-input");
  const chatBox = document.getElementById("chat-box");
  const loadingText = document.getElementById("loading-text");
  const uploadInput = document.getElementById("image-upload");

  // 🧮 自動格式化公式文字
  function autoFormatMath(text) {
    if (!text) return text;
    // 🔹 若已有 $$ 或 $...$，不再重複包裹
    if (text.includes("$$") || text.match(/\$[^$]+\$/)) return text;
    // 🔹 清理孤立符號
    text = text.replace(/\$\s*\$/g, "");
    text = text.replace(/\$([A-Za-z0-9])\$/g, "$1");
    // 🔹 自動包公式
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
    if (window.MathJax?.typesetPromise) MathJax.typesetPromise([message]);
  }

  // ✉️ 傳送訊息
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = userInput.value.trim();
    if (!input || isWaiting) return;
    isWaiting = true;

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
      const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: input })
      });
      const data = await res.json();
      thinkingMsg.remove();
      loadingText.style.display = "none";
      appendMessage("anan", data.reply || "⚠️ 系統忙碌，請稍後再試。");
    } catch {
      thinkingMsg.remove();
      loadingText.style.display = "none";
      appendMessage("anan", "⚠️ 無法連線到伺服器，請稍後重試。");
    } finally {
      isWaiting = false;
    }
  });

  // 📷 上傳圖片題
  uploadInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file || isWaiting) return;
    isWaiting = true;

    lastQuestion = "[圖片題目]";
    confusionCount = 0;

    const thinkingMsg = document.createElement("div");
    thinkingMsg.className = "anan";
    thinkingMsg.innerHTML = "🤔 安安思考中...";
    chatBox.appendChild(thinkingMsg);
    chatBox.scrollTop = chatBox.scrollHeight;
    loadingText.style.display = "block";

    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/upload", { method: "POST", body: formData });
      const data = await res.json();
      thinkingMsg.remove();
      loadingText.style.display = "none";
      appendMessage("anan", data.reply || "⚠️ 圖片辨識失敗。");
    } catch {
      thinkingMsg.remove();
      loadingText.style.display = "none";
      appendMessage("anan", "⚠️ 圖片上傳或辨識失敗。");
    } finally {
      uploadInput.value = "";
      isWaiting = false;
    }
  });
});

// ✉️ 供「懂了／不懂」按鈕用
async function sendMessage(presetText) {
  if (isWaiting) return;
  const chatBox = document.getElementById("chat-box");
  const loadingText = document.getElementById("loading-text");
  const userInput = document.getElementById("user-input");

  let actualMessage = presetText;
  if (!actualMessage) return;
  isWaiting = true;

  // 🎯 不懂邏輯
  if (actualMessage === "我不懂") {
    confusionCount++;
    if (confusionCount === 1)
      actualMessage = `關於這題「${lastQuestion}」，我有些地方不太懂。`;
    else if (confusionCount === 2)
      actualMessage = `這題「${lastQuestion}」我還是不太懂，可以換一個方法再教我一次嗎？`;
    else
      actualMessage = "我已經問了三次還是不懂了，請你建議我明天問老師，並給我一點鼓勵就好～";
  } else if (actualMessage === "我懂了") {
    confusionCount = 0;
  } else {
    lastQuestion = actualMessage;
    confusionCount = 0;
  }

  appendMessage("student", presetText);
  const thinkingMsg = document.createElement("div");
  thinkingMsg.className = "anan";
  thinkingMsg.innerHTML = "🤔 安安思考中...";
  chatBox.appendChild(thinkingMsg);
  chatBox.scrollTop = chatBox.scrollHeight;
  loadingText.style.display = "block";

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: actualMessage })
    });
    const data = await res.json();
    thinkingMsg.remove();
    loadingText.style.display = "none";
    appendMessage("anan", data.reply || "⚠️ 系統忙碌，請稍後再試。");
  } catch {
    thinkingMsg.remove();
    loadingText.style.display = "none";
    appendMessage("anan", "⚠️ 無法連線到伺服器，請稍後重試。");
  } finally {
    isWaiting = false;
  }
}
