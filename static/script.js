function appendMessage(role, content) {
  const box = document.getElementById("chat-box");
  const div = document.createElement("div");
  div.className = role;
  try {
    div.innerHTML = marked.parse(content || "");
  } catch (e) {
    div.textContent = content || "";
  }
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;

  if (window.MathJax) {
    if (MathJax.typesetPromise) {
      MathJax.typesetPromise([div]).catch((err) => console.log("MathJax error:", err));
    }
  } else {
    setTimeout(() => {
      if (window.MathJax && MathJax.typesetPromise) {
        MathJax.typesetPromise([div]).catch((err) => console.log("MathJax error:", err));
      }
    }, 1000);
  }
}

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
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
      const msgs = document.getElementsByClassName("anan");
      const last = msgs[msgs.length - 1];

      try {
        let reply = data.reply || "(沒有回覆內容)";

        // ✅ 自動把中括號裡的 LaTeX 語法包進 $...$，讓 MathJax 可辨識
        reply = reply.replace(/\[([^\]]+)\]/g, "$$$1$$");

        last.innerHTML = marked.parse(reply);
      } catch (e) {
        last.textContent = data.reply || "(沒有回覆內容)";
      }

      setTimeout(() => {
        if (window.MathJax && MathJax.typesetPromise) {
          MathJax.typesetPromise([last]).catch((err) => console.log("MathJax error:", err));
        }
      }, 300);
    })
    .catch((err) => {
      const msgs = document.getElementsByClassName("anan");
      const last = msgs[msgs.length - 1];
      last.textContent = "系統忙碌，請稍後再試。";
      console.error(err);
    });
}

function uploadImage(inputEl) {
  const f = inputEl.files && inputEl.files[0];
  if (!f) return;
  appendMessage("student", "(已選擇圖片：" + f.name + ")");
  appendMessage("anan", "安安正在辨識圖片與文字...");

  const fd = new FormData();
  fd.append("file", f);

  fetch("/upload", { method: "POST", body: fd })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
      const msgs = document.getElementsByClassName("anan");
      const last = msgs[msgs.length - 1];

      try {
        let reply = data.reply || "(沒有回覆內容)";
        reply = reply.replace(/\[([^\]]+)\]/g, "$$$1$$"); // ✅ 同步處理圖片回覆的公式
        last.innerHTML = marked.parse(reply);
      } catch (e) {
        last.textContent = data.reply || "(沒有回覆內容)";
      }

      setTimeout(() => {
        if (window.MathJax && MathJax.typesetPromise) {
          MathJax.typesetPromise([last]).catch((err) => console.log("MathJax error:", err));
        }
      }, 300);

      inputEl.value = "";
    })
    .catch((err) => {
      const msgs = document.getElementsByClassName("anan");
      const last = msgs[msgs.length - 1];
      last.textContent = "圖片上傳/辨識失敗，請稍後再試。";
      console.error(err);
    });
}
