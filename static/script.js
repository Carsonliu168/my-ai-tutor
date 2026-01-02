// ================================================
// 📘 解題小幫手專案前端控制腳本
// v5.4.4：修復步驟編號格式問題
// ================================================

document.addEventListener("DOMContentLoaded", () => {
  const chatForm = document.getElementById("chat-form");
  const userInput = document.getElementById("user-input");
  const chatBox = document.getElementById("chat-box");
  const loadingText = document.getElementById("loading-text");
  const uploadInput = document.getElementById("image-upload");

  // ===== 數學公式自動格式化（v5.4.2 修正版）=====
  function autoFormatMath(text) {
    if (!text) return text;
    
    // 清理多餘的 $ 符號
    text = text.replace(/\$\$\$/g, "$$");
    text = text.replace(/\$\s*\$/g, "$");
    text = text.replace(/\$\$([^\$]+)\$\$\$/g, "$$$1$$");
    
    // 處理 LaTeX 括號
    text = text.replace(/\\left(?![({[])/g, "(");
    text = text.replace(/\\right(?![)}\]])/g, ")");
    
    // 方括號轉數學模式
    text = text.replace(/\[([^\[\]]+)\]/g, "\$$1\$");
    
    // 常見數學函數自動包 $
    text = text.replace(/([^$])((?:\\frac|\\sqrt|\\sin|\\cos|\\tan|\\log|\\ln|\\arcsin|\\arccos|\\arctan)[^$ ]+)/g, "$1\$$2\$");
    
    // ✅ 已移除有問題的規則
    
    return text;
  }

  // ===== 添加訊息到聊天室 =====
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

  // 🆕 創建可更新的訊息容器（用於串流）
  function createStreamMessage(role) {
    const message = document.createElement("div");
    message.className = role;
    message.innerHTML = "";
    chatBox.appendChild(message);
    chatBox.scrollTop = chatBox.scrollHeight;
    return message;
  }

  // 🔥 v5.4.4 修復版：加強步驟編號格式處理
  function updateStreamMessage(messageElement, text) {
    // 📝 步驟 1：處理換行符號
    let result = text
      .replace(/\n\n/g, '<br><br>')  // 雙換行
      .replace(/\n/g, '<br>');        // 單換行
    
    // 🆕 步驟 1.5：強制處理步驟編號格式
    // 確保每個【步驟X】都有足夠的換行
    result = result.replace(/(【步驟\d+】)/g, '<br><br>$1<br>');
    
    // 📝 步驟 2：處理列表符號 (- 開頭的行)
    result = result.replace(/(^|\<br\>)-\s+(.+?)(?=\<br\>|$)/g, '$1<li>$2</li>');
    
    // 📝 步驟 3：如果有 <li>，包在 <ul> 裡
    if (result.includes('<li>')) {
      result = result.replace(/(<li>.*?<\/li>)+/g, '<ul>$&</ul>');
    }
    
    // 📝 步驟 4：套用數學公式格式化
    result = autoFormatMath(result);
    
    // 📝 步驟 5：設定內容
    messageElement.innerHTML = result;
    chatBox.scrollTop = chatBox.scrollHeight;
    
    // 📝 步驟 6：觸發 MathJax 渲染數學符號
    if (window.MathJax && window.MathJax.typesetPromise) {
      MathJax.typesetPromise([messageElement]).catch(err => {
        console.warn("MathJax 渲染警告:", err);
      });
    }
  }

  // 🆕 圖片燈箱（點擊放大）
  function createImageLightbox(imageSrc) {
    const lightbox = document.createElement("div");
    lightbox.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.9);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 9999;
      cursor: pointer;
    `;
    
    const img = document.createElement("img");
    img.src = imageSrc;
    img.style.cssText = `
      max-width: 90%;
      max-height: 90%;
      border-radius: 8px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    `;
    
    lightbox.appendChild(img);
    
    // 點擊關閉
    lightbox.addEventListener("click", () => {
      document.body.removeChild(lightbox);
    });
    
    document.body.appendChild(lightbox);
  }

  // ===== 🆕 串流接收函數 =====
  function streamChat(message) {
    return new Promise((resolve, reject) => {
      // 創建串流訊息容器
      const thinkingMsg = createStreamMessage("xiangyu");
      thinkingMsg.innerHTML = "🤔 解題小幫手思考中...";
      
      let fullReply = "";
      let hasStarted = false;

      // 建立 SSE 連線
      const eventSource = new EventSource(`/stream?message=${encodeURIComponent(message)}`);
      
      eventSource.onmessage = function(event) {
        const data = event.data;
        
        // 收到完成信號
        if (data === "[DONE]") {
          eventSource.close();
          loadingText.style.display = "none";
          resolve(fullReply);
          return;
        }
        
        // 收到錯誤信號
        if (data.startsWith("[ERROR]")) {
          eventSource.close();
          loadingText.style.display = "none";
          thinkingMsg.innerHTML = "⚠️ " + data.replace("[ERROR]", "");
          reject(new Error(data));
          return;
        }
        
        // 首次收到內容，清除「思考中」
        if (!hasStarted) {
          hasStarted = true;
          fullReply = "";
        }
        
        // 累積內容
        fullReply += data;
        
        // 🔥 v5.4.4：使用修復版處理函數
        updateStreamMessage(thinkingMsg, fullReply);
      };
      
      eventSource.onerror = function(error) {
        console.error("SSE 錯誤:", error);
        eventSource.close();
        loadingText.style.display = "none";
        
        if (!hasStarted) {
          thinkingMsg.innerHTML = "⚠️ 連線失敗，請重試";
        }
        reject(error);
      };
    });
  }

  // ===== 送出文字訊息（表單提交）=====
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = userInput.value.trim();
    if (!input) return;

    // 顯示學生訊息
    appendMessage("student", input);
    userInput.value = "";
    loadingText.style.display = "block";

    try {
      await streamChat(input);
    } catch (error) {
      console.error("送出訊息失敗:", error);
    }
  });

  // ===== 🆕 按鈕快捷訊息（我懂了 / 我不懂）=====
  window.sendMessage = async function (presetText) {
    if (!presetText) return;

    // 顯示學生訊息
    appendMessage("student", presetText);
    loadingText.style.display = "block";

    try {
      await streamChat(presetText);
    } catch (error) {
      console.error("送出訊息失敗:", error);
    }
  };

  // ===== 🆕 圖片上傳（含預覽和點擊放大）=====
  uploadInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // 🆕 步驟 1：讀取並顯示圖片預覽
    const reader = new FileReader();
    reader.onload = async function(event) {
      const imageSrc = event.target.result;
      
      // 創建圖片預覽（可點擊放大）
      const imgContainer = document.createElement("div");
      imgContainer.className = "student";
      imgContainer.style.cssText = "cursor: pointer;";
      
      const img = document.createElement("img");
      img.src = imageSrc;
      img.style.cssText = `
        max-width: 300px;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        transition: transform 0.2s;
      `;
      
      // 滑鼠懸停效果
      img.addEventListener("mouseenter", () => {
        img.style.transform = "scale(1.05)";
      });
      img.addEventListener("mouseleave", () => {
        img.style.transform = "scale(1)";
      });
      
      // 點擊放大
      img.addEventListener("click", () => {
        createImageLightbox(imageSrc);
      });
      
      const caption = document.createElement("p");
      caption.style.cssText = "color: #666; font-size: 14px; margin-top: 8px;";
      caption.textContent = "📷 上傳了一張數學題（點擊圖片可放大）";
      
      imgContainer.appendChild(img);
      imgContainer.appendChild(caption);
      chatBox.appendChild(imgContainer);
      chatBox.scrollTop = chatBox.scrollHeight;

      // 🆕 步驟 2：顯示思考中
      const thinkingMsg = document.createElement("div");
      thinkingMsg.className = "xiangyu";
      thinkingMsg.innerHTML = "🤔 解題小幫手正在辨識圖片...";
      thinkingMsg.id = "thinking-upload";
      chatBox.appendChild(thinkingMsg);
      chatBox.scrollTop = chatBox.scrollHeight;
      loadingText.style.display = "block";

      // 🆕 步驟 3：上傳圖片
      try {
        const formData = new FormData();
        formData.append("file", file);

        const res = await fetch("/upload", { 
          method: "POST", 
          body: formData 
        });
        
        const data = await res.json();
        
        loadingText.style.display = "none";
        document.getElementById("thinking-upload")?.remove();

        // 顯示 AI 回應
        appendMessage("xiangyu", data.reply || "⚠️ 圖片辨識失敗。");
        
      } catch (err) {
        console.error("圖片上傳失敗:", err);
        loadingText.style.display = "none";
        document.getElementById("thinking-upload")?.remove();
        appendMessage("xiangyu", "⚠️ 圖片上傳或辨識失敗，請重試。");
      }
    };

    // 開始讀取圖片
    reader.readAsDataURL(file);
    uploadInput.value = ""; // 清空 input，允許重複上傳同一張圖
  });
});