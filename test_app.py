from flask import Flask

application = Flask(__name__)

@application.route("/")
def home():
    return "Math Tutor AnAn - Fixed WSGI Interface"

@application.route("/healthz")
def healthz():
    return "ok", 200

@application.route("/debug")
def debug():
    import os, sys
    return {
        "python_version": sys.version,
        "files": os.listdir("."),
        "env_vars": {k: v for k, v in os.environ.items() if 'KEY' not in k}
    }

if __name__ == "__main__":
    application.run(host="0.0.0.0", port=5000)
