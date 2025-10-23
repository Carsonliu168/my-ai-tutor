// ================================================
// 📘 安安專案前端控制腳本
// v5.0.19-final：修正第三次不懂邏輯
// ✅ 功能：完整保留,只修正第三次「不懂」建議
// ================================================

// 🧠 全域變數：記住上一題和困惑次數
let lastQuestion = "";
let confusionCount = 0;

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
    text = text.replace(/\$\$\$/g, "$$");
    text = text.replace(/\$\s*\$/g, "$");
    text = text.replace(/\$\$([^\$]+)\$\$\$/g, "$$$1$$");

    // ---------- 🧱 2️⃣ 修正未配對的 \left / \right ----------
    text = text.replace(/\\left(?![({[])/g, "(");
    text = text.replace(/\\right(?![)}\]])/g, ")");

    // ---------- 🧮 3️⃣ 自動包裹公式 ----------
    text = text.replace(/\[([^\[\]]+)\]/g, "\$$1\$");
    text = text.replace(/([^$])((?:\\frac|\\sqrt|\\sin|\\cos|\\tan)[^$ ]+)/g, "$1\$$2\$");
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

    // 🔄 記住這個問題,並重置困惑計數
    lastQuestion = input;
    confusionCount = 0;

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

    // 🔄 圖片題也要記住,重置困惑計數
    lastQuestion = "[圖片題目]";
    confusionCount = 0;

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
  
  let actualMessage = presetText || userInput.value.trim();
  
  if (!actualMessage) return;

  // 🎯 智能「不懂」按鈕邏輯
  if (actualMessage === "我不懂") {
    confusionCount++;
    
    if (confusionCount === 1) {
      // 第1次按「不懂」→ 問哪個步驟不懂
      if (lastQuestion && lastQuestion !== "[圖片題目]") {
        actualMessage = `關於這題「${lastQuestion}」,我有些地方不太懂`;
      } else if (lastQuestion === "[圖片題目]") {
        actualMessage = "剛才那題我有些地方不太懂";
      } else {
        actualMessage = "我不懂";
      }
    } else if (confusionCount === 2) {
      // 第2次按「不懂」→ 請求換個方法
      if (lastQuestion && lastQuestion !== "[圖片題目]") {
        actualMessage = `這題「${lastQuestion}」我還是不太懂,可以換一個方法再教我一次嗎?`;
      } else if (lastQuestion === "[圖片題目]") {
        actualMessage = "剛才那題我還是不太懂,可以換一個方法再教我一次嗎?";
      } else {
        actualMessage = "我還是不懂,可以換個方法嗎?";
      }
    } else if (confusionCount >= 3) {
      // ✅ 第3次以上按「不懂」→ 明確建議問老師,不要再解題
      actualMessage = "我已經問了三次還是不懂了,請你用親切的口氣建議我把這題記下來,明天去問學校老師。請不要再繼續解題了,只要給我鼓勵和建議就好";
    }
  } else if (actualMessage === "我懂了") {
    // 「懂了」按鈕 → 重置困惑計數
    confusionCount = 0;
  } else {
    // 其他訊息 → 視為新問題,重置困惑計數並記住問題
    lastQuestion = actualMessage;
    confusionCount = 0;
  }

  // 顯示學生訊息（藍色）- 顯示原始的「我懂了」或「我不懂」
  const studentMsg = document.createElement("div");
  studentMsg.className = "student";
  studentMsg.innerHTML = presetText || actualMessage;
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

  // 🚀 發送實際訊息給後端
  fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: actualMessage })
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

  // 🔄 圖片題也要記住,重置困惑計數
  lastQuestion = "[圖片題目]";
  confusionCount = 0;

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