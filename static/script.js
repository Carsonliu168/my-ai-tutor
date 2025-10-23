// ================================================
// 📘 安安專案前端控制腳本
// v5.0.10-autoformat-final：MathJax 全面防呆版
// ✅ 功能：
// - 自動包裹數學公式
// - 自動清除多餘或未配對的 $
// - 自動修正孤立 \left / \right
// - 完整支援繁體中文字與即時渲染
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
    message.innerHTML = role === "user" ? text : autoFormatMath(text);
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

    appendMessage("user", input);
    userInput.value = "";
    loadingText.style.display = "block";

    try {
      const response = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: input })
      });

      const data = await response.json();
      loadingText.style.display = "none";

      if (data.error) {
        appendMessage("assistant", "⚠️ 系統忙碌，請稍後再試。");
      } else {
        appendMessage("assistant", data.answer);
      }
    } catch (error) {
      loadingText.style.display = "none";
      appendMessage("assistant", "⚠️ 無法連線到伺服器，請稍後重試。");
    }
  });

  // 📷 上傳圖片題
  uploadInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("image", file);
    loadingText.style.display = "block";

    try {
      const response = await fetch("/upload_image", {
        method: "POST",
        body: formData
      });

      const data = await response.json();
      loadingText.style.display = "none";
      appendMessage("assistant", data.answer);
    } catch (error) {
      loadingText.style.display = "none";
      appendMessage("assistant", "⚠️ 圖片上傳或辨識失敗。");
    }
  });
});
