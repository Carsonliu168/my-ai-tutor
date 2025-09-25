# app.py
# -*- coding: utf-8 -*-

import os
import json
import logging
from datetime import timedelta

from flask import (
    Flask, request, render_template, session, redirect, url_for, jsonify
)
from werkzeug.middleware.proxy_fix import ProxyFix

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ====== 版本號 ======
APP_VERSION = "安安 v1.3D"

# ====== 基本設定 ======
def str2bool(v: str) -> bool:
    return str(v).lower() in {"1", "true", "yes", "y", "on"}

DEBUG = str2bool(os.getenv("DEBUG", "0"))

app = Flask(__name__, template_folder="templates", static_folder="static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# 重要：Production 請設定固定的 SECRET_KEY，避免多進程/多機 session 失效
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))
app.permanent_session_lifetime = timedelta(hours=2)
app.config["JSON_AS_ASCII"] = False

# ====== Logging ======
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)
logger.info("啟動版本：%s，DEBUG=%s", APP_VERSION, DEBUG)

# ====== API 設定 ======
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

if DEEPSEEK_API_KEY:
    logger.info("✅ 成功讀到 DEEPSEEK_API_KEY | %s", APP_VERSION)
else:
    # 不要在程式裡硬寫金鑰（安全風險），請在 Railway 變數設定 DEEPSEEK_API_KEY
    logger.warning("⚠️ 沒有讀到 DEEPSEEK_API_KEY，請在環境變數中設定。")

# ====== requests session + retry 機制 ======
session_req = requests.Session()
retries = Retry(
    total=3,
    connect=3,
    read=3,
    backoff_factor=1.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["GET", "POST"]),
)
adapter = HTTPAdapter(max_retries=retries)
session_req.mount("https://", adapter)
session_req.mount("http://", adapter)
DEFAULT_TIMEOUT = 30  # 秒

# ====== before_request：讓 session 採用「滑動式」過期 ======
@app.before_request
def make_session_permanent():
    session.permanent = True

# ====== 健康檢查（Railway 用） ======
@app.route("/health")
def health_check():
    return jsonify({"status": "healthy", "version": APP_VERSION})

@app.route("/favicon.ico")
def favicon():
    # 避免 404 汙染 log
    return ("", 204)

# ====== DeepSeek 問答函數 ======
def ask_deepseek(user_message: str, conversation_history: list) -> str:
    if not DEEPSEEK_API_KEY:
        return "系統尚未設定 DEEPSEEK_API_KEY，請在 Railway 變數中加入後再試一次。"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }

    system_prompt = (
        "你是數學老師安安，請用蘇格拉底式的引導教學方式協助學生。\n"
        "規則如下：\n"
        "1. 使用繁體中文回答。\n"
        "2. 不直接給完整解答，要先引導學生思考下一步，並提出提示或問題。\n"
        "3. 逐步拆解題目，讓學生一步一步回答。\n"
        "4. 使用台灣常用的數學術語。\n"
        "5. 語氣要親切、鼓勵，像一位耐心的小
