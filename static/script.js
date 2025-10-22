// 追加訊息到對話框
function appendMessage(role, content) {
  const box = document.getElementById("chat-box");
  const div = document.createElement("div");
  div.className = role; // "anan" 或 "student"
  try {
    div.innerHTML = marked.parse(content || "");
  } catch (e) {
    div.textContent = content || "";
  }
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise();
}

// 傳送純文字訊息
function sendMessage(preset) {
  const input = document.getElementById("user-input");
  const text = (preset || input.value || "").trim();
  if (!text) return;

  appendMessage("student", text);
  if (!preset) input.value = "";

  appendMessage("anan", "安安正在思考中...");

  fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text })
  })
    .then(r => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(data => {
      const msgs = document.getElementsByClassName("anan");
      const last = msgs[msgs.length - 1];
      last.innerHTML = marked.parse(data.reply || "（沒有回覆內容）");
      if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise();
    })
    .catch(err => {
      const msgs = document.getElementsByClassName("anan");
      const last = msgs[msgs.length - 1];
      last.textContent = "⚠️ 系統忙碌，請稍後再試。";
      console.error(err);
    });
}

// 上傳圖片執行 OCR
function uploadImage(inputEl) {
  const f = inputEl.files && inputEl.files[0];
  if (!f) return;
  appendMessage("student", `（已選擇圖片：${f.name}）`);
  appendMessage("anan", "安安正在辨識圖片與文字...");

  const fd = new FormData();
  fd.append("file", f);

  fetch("/upload", { method: "POST", body: fd })
    .then(r => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(data => {
      const msgs = document.getElementsByClassName("anan");
      const last = msgs[msgs.length - 1];
      last.innerHTML = marked.parse(data.reply || "（沒有回覆內容）");
      if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise();
      inputEl.value = ""; // 重置選擇
    })
    .catch(err => {
      const msgs = document.getElementsByClassName("anan");
      const last = msgs[msgs.length - 1];
      last.textContent = "⚠️ 圖片上傳/辨識失敗，請稍後再試。";
      console.error(err);
    });
}
