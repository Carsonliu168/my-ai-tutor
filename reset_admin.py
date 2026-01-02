# reset_admin.py - 自動修復 users 表並重置管理員
import sqlite3, bcrypt, os
DB_PATH = os.path.join("data", "xiangyu.db")
if not os.path.exists(DB_PATH):
    print("❌ 找不到資料庫 data/xiangyu.db，請確認目前目錄正確。")
    exit()
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
# 取得現有欄位
cur.execute("PRAGMA table_info(users)")
columns = [col[1] for col in cur.fetchall()]
# 若沒有 password 欄位，就修正表結構
if "password" not in columns:
    print("⚙️ 檢測到舊版 users 表，正在修正欄位結構...")
    cur.execute("ALTER TABLE users RENAME TO users_old;")
    cur.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            password TEXT,
            role TEXT,
            profile_type TEXT
        )
    """)
    # 複製舊資料（如果有 username 就保留）
    try:
        cur.execute("INSERT INTO users (username, role) SELECT username, role FROM users_old;")
        print("✅ 已保留舊用戶資料。")
    except Exception as e:
        print("⚠️ 無法保留舊資料：", e)
    cur.execute("DROP TABLE users_old;")
    conn.commit()
    print("✅ 已修復 users 表結構。")
# 刪除舊管理員帳號
cur.execute("DELETE FROM users WHERE username='admin'")
# 建立新密碼
hashed = bcrypt.hashpw("Carson@2025".encode('utf-8'), bcrypt.gensalt())
cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ('admin', hashed, 'admin'))
conn.commit()
conn.close()
print("✅ 已重置管理員帳號：admin / 密碼 Carson@2025")