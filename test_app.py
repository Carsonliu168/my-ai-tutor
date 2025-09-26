from flask import Flask 
app = Flask(__name__) 
@app.route("/") 
def home(): return "數學小老師安安 - 基本測試成功！" 
@app.route("/healthz") 
def healthz(): return "ok", 200 
if __name__ == "__main__": app.run(host="0.0.0.0", port=5000) 
