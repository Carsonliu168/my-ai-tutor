// ================================================
// 📘 安安專案前端控制腳本
// v5.0.13-final：完整修正版
// ✅ student(藍色) + anan(粉紅色) + 圖片上傳
// ================================================

// 🎨 顯示訊息到聊天框
function appendMessage(role, text) {
  const chatBox = document.getElementById("chat-box");
  const message = document.createElement("div");
  
  // ✅ 正確的 class 名稱
  message.className = role;  // "student" 或 "anan"
  message.innerHTML = text;
  chatBox.appendChild(message);
  chatBox.scrollTop = chatBox.scrollHeight;

  // 渲染數學公式
  if (window.MathJax && window.MathJax.typesetPromise) {
    MathJax.typesetPromise([message]);
  }
}

// ✉️ 送出文字訊息
function sendMessage(presetText) {
  const userInput = document.getElementById("user-input");
  const loadingText = document.getElementById("loading-text");
  const input = presetText || userInput.value.trim();
  
  if (!input) return;

  // 顯示學生訊息(藍色)
  appendMessage("student", input);
  userInput.value = "";
  loadingText.style.display = "block";

  fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: input })
  })
  .then(res => res.json())
  .then(data => {
    loadingText.style.display = "none";
    // 顯示安安的回覆(粉紅色)
    appendMessage("anan", data.reply || "⚠️ 系統忙碌，請稍後再試。");
  })
  .catch(error => {
    loadingText.style.display = "none";
    appendMessage("anan", "⚠️ 無法連線到伺服器，請稍後重試。");
  });
}

// 📷 上傳圖片
function uploadImage(input) {
  const file = input.files[0];
  if (!file) return;

  const loadingText = document.getElementById("loading-text");
  const formData = new FormData();
  formData.append("file", file);

  loadingText.style.display = "block";

  fetch("/upload", {
    method: "POST",
    body: formData
  })
  .then(res => res.json())
  .then(data => {
    loadingText.style.display = "none";
    appendMessage("anan", data.reply || "⚠️ 圖片辨識失敗。");
  })
  .catch(error => {
    loadingText.style.display = "none";
    appendMessage("anan", "⚠️ 圖片上傳或辨識失敗。");
  });

  // 清空檔案選擇器
  input.value = "";
}

// 🚀 頁面載入時綁定表單送出事件
document.addEventListener("DOMContentLoaded", () => {
  const chatForm = document.getElementById("chat-form");
  if (chatForm) {
    chatForm.addEventListener("submit", (e) => {
      e.preventDefault();
      sendMessage();
    });
  }
});