// ===== Math 文字自動格式化（給 MathJax 用） =====
function autoFormatMath(text) {
  if (!text) return text;

  let t = String(text);

  // 1) [ ... ] → $...$  （原始後端格式）
  t = t.replace(/\[([^\]]+)\]/g, (_, g1) => `$${g1}$`);

  // 2) ( ... \times ... ) / ( ... \div ... ) 等整段包進 $...$
  //   目的：開頭敘述中常出現的「( 46 \times 5 ) 與 ( 23 \div 2 )」
  const opPattern = '\\\\(?:times|div|frac|sqrt|pi|le|ge)';
  const parenRegex = new RegExp(`\\(([^()]*${opPattern}[^()]*)\\)`, 'g');
  t = t.replace(parenRegex, (_, inner) => `$(${inner})$`);

  // 3) 保底：在「非 $...$ 區塊」裡遇到單顆 LaTeX 符號就包 $...$
  //   方法：先用 $...$ 切段，僅處理非數學片段
  const tokenRegex = /(\\frac\{[^}]+\}\{[^}]+\}|\\sqrt\{[^}]*\}|\\times|\\div|\\pi|\\le|\\ge)/g;
  const parts = t.split(/(\$[^$]+\$)/g); // 保留分隔符
  for (let i = 0; i < parts.length; i++) {
    const seg = parts[i];
    if (!seg) continue;
    // 跳過已是 $...$ 的數學片段
    if (seg.startsWith('$') && seg.endsWith('$')) continue;

    // 只處理非數學片段：把殘留的 LaTeX 符號包起來
    parts[i] = seg.replace(tokenRegex, (m) => `$${m}$`);
  }
  t = parts.join('');

  return t;
}

// ====== 以下為 UI 與聊天流程 ======
function appendMessage(role, content) {
  const box = document.getElementById("chat-box");
  const div = document.createElement("div");
  div.className = role;
  try {
    // 對動態插入內容也先做數學自動格式化
    const formatted = autoFormatMath(content || "");
    div.innerHTML = marked.parse(formatted);
  } catch (e) {
    div.textContent = content || "";
  }
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;

  // 重新渲染 MathJax
  if (window.MathJax && MathJax.typesetPromise) {
    MathJax.typesetPromise([div]).catch((err) => console.log("MathJax error:", err));
  } else {
    setTimeout(() => {
      if (window.MathJax && MathJax.typesetPromise) {
        MathJax.typesetPromise([div]).catch((err) => console.log("MathJax error:", err));
      }
    }, 600);
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
        reply = autoFormatMath(reply); // ✅ 關鍵：回覆先做數學自動格式化
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
        reply = autoFormatMath(reply); // ✅ 圖片回覆也一併處理
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
