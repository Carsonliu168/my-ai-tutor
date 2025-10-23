// ================================================
// 📘 安安專案前端控制腳本
// v5.0.16-complete：完整修訂版 + 思考中提示
// ✅ 功能：
// - student(藍色) + anan(粉紅色) 對話框
// - 文字題和圖片題都顯示「安安思考中...」
// - 自動包裹數學公式
// - 自動清除多餘或未配對的 $
// - 自動修正孤立 \left / \right
// - 完整支援繁體中文字與即時渲染
// - 圖片上傳功能
// - 懂了/不懂按鈕(保持原樣)
// ================================================
document.addEventListener("DOMContentLoaded", () => {
  const chatForm = document.getElementById("chat-form");
  const userInput = document.getElementById("user-input");
  const chatBox = document.getElementById("chat-box");
  const loadingText = document.getElementById("loading-text");
  const uploadInput = document.getElementById("image-upload");

  // 🧩 自動格式化公式文字
  function autoFormatMath(text) {
    if (!text) return text;

    // ---------- 🧹 1️⃣ 清理多餘符號 ----------
    // 移除重複或孤立的 $ 符號
    text = text.replace(/\$\$\$/g, "$$");
    text = text.replace(/\$\s*\$/g, "$");

    // 修正多餘 $$...$$$$ 的狀況
    text = text.replace(/\$\$([^\$]+)\$\$\$/g, "$$$1$$");

    // ---------- 🧱 2️⃣ 修正未配對的 \left / \right ----------
    // 將孤立的 \left / \right 改為普通括號，防止報錯
    text = text.replace(/\\left(?![({[])/g, "(");
    text = text.replace(/\\right(?![)}\]])/g, ")");

    // ---------- 🧮 3️⃣ 自動包裹公式 ----------
    // 把 [ ... ] 包成 $...$
    text = text.replace(/\[([^\[\]]+)\]/g, "\$$1\$");

    // 把未包起來的 \frac、\sqrt、自動加上 $
    text = text.replace(/([^$])((?:\\frac|\\sqrt|\\sin|\\cos|\\tan)[^$ ]+)/g, "$1\$$2\$");

    // 把簡單的 a + b / c × d 自動包起來
    text = text.replace(/([=：])([\d\w\s\\\+\-\*\/\(\)\.]+)([。；\)])/g, "$1\$$2\$$3");

    return text;
  }

  // 🧠 輸出訊息至畫面
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

  // ✉️ 傳送訊息
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = userInput.value.trim();
    if (!input) return;

    appendMessage("student", input);
    userInput.value = "";
    
    // ✅ 立即在對話框顯示「安安思考中...」
    const thinkingMsg = document.createElement("div");
    thinkingMsg.className = "anan";
    thinkingMsg.innerHTML = "🤔 安安思考中...";
    thinkingMsg.id = "thinking-message";
    chatBox.appendChild(thinkingMsg);
    chatBox.scrollTop = chatBox.scrollHeight;
    
    loadingText.style.display = "block";

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: input })
      });
      const data = await response.json();
      loadingText.style.display = "none";

      // ✅ 移除「思考中」訊息
      const thinkingElement = document.getElementById("thinking-message");
      if (thinkingElement) {
        thinkingElement.remove();
      }

      if (data.reply) {
        appendMessage("anan", data.reply);
      } else {
        appendMessage("anan", "⚠️ 系統忙碌，請稍後再試。");
      }
    } catch (error) {
      loadingText.style.display = "none";
      
      // ✅ 移除「思考中」訊息
      const thinkingElement = document.getElementById("thinking-message");
      if (thinkingElement) {
        thinkingElement.remove();
      }
      
      appendMessage("anan", "⚠️ 無法連線到伺服器，請稍後重試。");
    }
  });

  // 📷 上傳圖片題
  uploadInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    // ✅ 立即在對話框顯示「安安思考中...」
    const thinkingMsg = document.createElement("div");
    thinkingMsg.className = "anan";
    thinkingMsg.innerHTML = "🤔 安安思考中...";
    thinkingMsg.id = "thinking-message-upload";
    chatBox.appendChild(thinkingMsg);
    chatBox.scrollTop = chatBox.scrollHeight;

    loadingText.style.display = "block";

    try {
      const response = await fetch("/upload", {
        method: "POST",
        body: formData
      });
      const data = await response.json();
      loadingText.style.display = "none";

      // ✅ 移除「思考中」訊息
      const thinkingElement = document.getElementById("thinking-message-upload");
      if (thinkingElement) {
        thinkingElement.remove();
      }

      if (data.reply) {
        appendMessage("anan", data.reply);
      } else {
        appendMessage("anan", "⚠️ 圖片辨識失敗。");
      }
    } catch (error) {
      loadingText.style.display = "none";
      
      // ✅ 移除「思考中」訊息
      const thinkingElement = document.getElementById("thinking-message-upload");
      if (thinkingElement) {
        thinkingElement.remove();
      }
      
      appendMessage("anan", "⚠️ 圖片上傳或辨識失敗。");
    }

    // 清空檔案選擇器，允許重複上傳同一檔案
    uploadInput.value = "";
  });
});

// ✉️ 供 HTML onclick 使用的全域函數（給「懂了」「不懂」按鈕用）
function sendMessage(presetText) {
  const userInput = document.getElementById("user-input");
  const chatBox = document.getElementById("chat-box");
  const loadingText = document.getElementById("loading-text");
  const input = presetText || userInput.value.trim();
  
  if (!input) return;

  // 顯示學生訊息（藍色）
  const studentMsg = document.createElement("div");
  studentMsg.className = "student";
  studentMsg.innerHTML = input;
  chatBox.appendChild(studentMsg);
  chatBox.scrollTop = chatBox.scrollHeight;

  userInput.value = "";
  
  // ✅ 立即在對話框顯示「安安思考中...」
  const thinkingMsg = document.createElement("div");
  thinkingMsg.className = "anan";
  thinkingMsg.innerHTML = "🤔 安安思考中...";
  thinkingMsg.id = "thinking-message-preset";
  chatBox.appendChild(thinkingMsg);
  chatBox.scrollTop = chatBox.scrollHeight;
  
  loadingText.style.display = "block";

  fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: input })
  })
  .then(res => res.json())
  .then(data => {
    loadingText.style.display = "none";
    
    // ✅ 移除「思考中」訊息
    const thinkingElement = document.getElementById("thinking-message-preset");
    if (thinkingElement) {
      thinkingElement.remove();
    }
    
    // 顯示安安回覆（粉紅色）
    const ananMsg = document.createElement("div");
    ananMsg.className = "anan";
    
    // 自動格式化公式
    let formattedText = data.reply || "⚠️ 系統忙碌，請稍後再試。";
    formattedText = formattedText.replace(/\$\$\$/g, "$$");
    formattedText = formattedText.replace(/\$\s*\$/g, "$");
    formattedText = formattedText.replace(/\\left(?![({[])/g, "(");
    formattedText = formattedText.replace(/\\right(?![)}\]])/g, ")");
    
    ananMsg.innerHTML = formattedText;
    chatBox.appendChild(ananMsg);
    chatBox.scrollTop = chatBox.scrollHeight;

    if (window.MathJax && window.MathJax.typesetPromise) {
      MathJax.typesetPromise([ananMsg]);
    }
  })
  .catch(error => {
    loadingText.style.display = "none";
    
    // ✅ 移除「思考中」訊息
    const thinkingElement = document.getElementById("thinking-message-preset");
    if (thinkingElement) {
      thinkingElement.remove();
    }
    
    const errMsg = document.createElement("div");
    errMsg.className = "anan";
    errMsg.innerHTML = "⚠️ 無法連線到伺服器，請稍後重試。";
    chatBox.appendChild(errMsg);
    chatBox.scrollTop = chatBox.scrollHeight;
  });
}

function uploadImage(input) {
  const file = input.files[0];
  if (!file) return;

  const chatBox = document.getElementById("chat-box");
  const loadingText = document.getElementById("loading-text");
  const formData = new FormData();
  formData.append("file", file);

  // ✅ 立即在對話框顯示「安安思考中...」
  const thinkingMsg = document.createElement("div");
  thinkingMsg.className = "anan";
  thinkingMsg.innerHTML = "🤔 安安思考中...";
  thinkingMsg.id = "thinking-message-upload-func";
  chatBox.appendChild(thinkingMsg);
  chatBox.scrollTop = chatBox.scrollHeight;

  loadingText.style.display = "block";

  fetch("/upload", {
    method: "POST",
    body: formData
  })
  .then(res => res.json())
  .then(data => {
    loadingText.style.display = "none";
    
    // ✅ 移除「思考中」訊息
    const thinkingElement = document.getElementById("thinking-message-upload-func");
    if (thinkingElement) {
      thinkingElement.remove();
    }
    
    const ananMsg = document.createElement("div");
    ananMsg.className = "anan";
    ananMsg.innerHTML = data.reply || "⚠️ 圖片辨識失敗。";
    chatBox.appendChild(ananMsg);
    chatBox.scrollTop = chatBox.scrollHeight;

    if (window.MathJax && window.MathJax.typesetPromise) {
      MathJax.typesetPromise([ananMsg]);
    }
  })
  .catch(error => {
    loadingText.style.display = "none";
    
    // ✅ 移除「思考中」訊息
    const thinkingElement = document.getElementById("thinking-message-upload-func");
    if (thinkingElement) {
      thinkingElement.remove();
    }
    
    const errMsg = document.createElement("div");
    errMsg.className = "anan";
    errMsg.innerHTML = "⚠️ 圖片上傳或辨識失敗。";
    chatBox.appendChild(errMsg);
    chatBox.scrollTop = chatBox.scrollHeight;
  });

  input.value = "";
}