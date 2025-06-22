from flask import Flask, jsonify, request
import time
import threading

app = Flask(__name__)
_leak_data = []

@app.route('/')
def index():
    return jsonify({"status": "ok", "time": time.time()})

@app.route('/error')
def error():
    # Simulate an exception
    raise RuntimeError("Triggered failure for demo")

@app.route('/leak')
def leak():
    # Simulate memory leak by appending bytes
    _leak_data.append('x' * 10_000_00)  # ~1MB per call
    return jsonify({"leaked_mb": len(_leak_data)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)