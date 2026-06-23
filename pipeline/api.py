"""
Flask API wrapper around the pipeline.
Deployed on Render — n8n calls POST /run weekly to trigger the pipeline.
"""

import logging
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

app = Flask(__name__)

API_SECRET = os.getenv("PIPELINE_API_SECRET", "")


def _authorized() -> bool:
    if not API_SECRET:
        return True
    return request.headers.get("X-Api-Secret") == API_SECRET


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/run", methods=["POST"])
def run_pipeline():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401

    import run_pipeline as rp
    exit_code = rp.main()

    if exit_code == 0:
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "failed", "exit_code": exit_code}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
