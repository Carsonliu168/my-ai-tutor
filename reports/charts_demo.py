# reports/charts_demo.py
# ------------------------------------------
# 安安專案用：生成個人學習分析圖表（繁體中文正常顯示）
# 不會影響 app.py，也不會啟動 Flask，只會輸出圖片到 reports/images/
# ------------------------------------------

import platform
from pathlib import Path
import numpy as np
import matplotlib
import matplotlib.pyplot as plt

# ---------- A. 中文字型設定（避免亂碼） ----------
# Windows 系統使用「微軟正黑體」；Mac / Linux 使用 Noto Sans TC
if platform.system() == "Windows":
    matplotlib.rcParams['font.sans-serif'] = ['Microsoft JhengHei']
else:
    matplotlib.rcParams['font.sans-serif'] = ['Noto Sans CJK TC', 'Noto Sans TC', 'Arial Unicode MS']
matplotlib.rcParams['axes.unicode_minus'] = False  # 負號正常顯示

# ---------- B. 固定輸出資料夾（使用你的實際絕對路徑） ----------
ROOT = Path(r"C:\Users\user\my-ai-tutor\reports")
OUT = ROOT / "images"
OUT.mkdir(parents=True, exist_ok=True)

# ---------- C. 模擬一位學生的學習資料 ----------
student_name = "學生A"
topics = ['分數運算', '代數方程', '幾何圖形', '應用題', '邏輯推理']
correct_rates = [0.85, 0.73, 0.55, 0.68, 0.79]  # 五大主題正確率（0~1）
weeks = np.arange(1, 9)
weekly_scores = [58, 61, 64, 69, 72, 76, 80, 85]  # 8 週平均正確率（%）
radar_labels = np.array(['概念理解', '運算速度', '幾何空間', '應用題', '邏輯推理'])
radar_scores = np.array([80, 70, 55, 65, 75])     # 0~100

# ---------- D. 各章節正確率（長條圖） ----------
plt.figure(figsize=(8,5))
bars = plt.bar(topics, [r*100 for r in correct_rates], color='#4E79A7')
plt.title(f'安安小老師學習報告 - {student_name}\n各章節正確率', fontsize=16)
plt.xlabel('數學主題'); plt.ylabel('正確率 (%)'); plt.ylim(0, 100)
for bar, rate in zip(bars, correct_rates):
    plt.text(bar.get_x()+bar.get_width()/2, rate*100-3, f"{rate*100:.0f}%", ha='center', va='top', color='white', fontsize=12)
plt.tight_layout()
plt.savefig(OUT / "各章節正確率.png", dpi=180)
plt.close()

# ---------- E. 學習成長曲線（折線圖） ----------
plt.figure(figsize=(8,5))
plt.plot(weeks, weekly_scores, marker='o', color='#F28E2B', linewidth=3)
plt.title(f'安安小老師學習報告 - {student_name}\n學習成長曲線', fontsize=16)
plt.xlabel('週次'); plt.ylabel('平均正確率 (%)')
plt.grid(True, linestyle='--', alpha=0.6)
for x, y in zip(weeks, weekly_scores):
    plt.text(x, y+1, f"{y}%", ha='center', fontsize=10)
plt.tight_layout()
plt.savefig(OUT / "學習成長曲線.png", dpi=180)
plt.close()

# ---------- F. 學習能力雷達圖 ----------
labels = radar_labels
scores = radar_scores
angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False).tolist()
scores = np.concatenate((scores, [scores[0]]))
angles += [angles[0]]

plt.figure(figsize=(6,6))
ax = plt.subplot(111, polar=True)
ax.plot(angles, scores, 'o-', linewidth=2, color='#59A14F')
ax.fill(angles, scores, alpha=0.25, color='#59A14F')
ax.set_thetagrids(np.degrees(angles[:-1]), labels)
ax.set_ylim(0, 100)
plt.title(f'安安小老師學習報告 - {student_name}\n學習能力雷達圖', fontsize=15, pad=20)
plt.tight_layout()
plt.savefig(OUT / "學習能力雷達圖.png", dpi=180)
plt.close()

print(f"✅ 已完成！繁體中文學習分析圖表已輸出到：{OUT}")
