import json
import os
from flask import Flask, render_template, request, jsonify

from sandbox import execute_sandboxed
from explainer import explain_trace, get_example_prompt

app = Flask(__name__)

MAX_CODE_LENGTH = 5000


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/trace", methods=["POST"])
def api_trace():
    data = request.get_json()
    if not data or "code" not in data:
        return jsonify({"error": "Missing 'code' field in request body"}), 400

    code = data["code"].strip()
    if not code:
        return jsonify({"error": "Code cannot be empty"}), 400

    if len(code) > MAX_CODE_LENGTH:
        return jsonify({"error": f"Code exceeds maximum length of {MAX_CODE_LENGTH} characters"}), 400

    trace = execute_sandboxed(code)
    return jsonify(trace)


@app.route("/api/explain", methods=["POST"])
def api_explain():
    data = request.get_json()
    if not data or "code" not in data:
        return jsonify({"error": "Missing 'code' field in request body"}), 400

    code = data["code"].strip()
    if not code:
        return jsonify({"error": "Code cannot be empty"}), 400

    if len(code) > MAX_CODE_LENGTH:
        return jsonify({"error": f"Code exceeds maximum length of {MAX_CODE_LENGTH} characters"}), 400

    depth = data.get("depth", "intermediate")
    if depth not in ("beginner", "intermediate", "advanced"):
        return jsonify({"error": "depth must be 'beginner', 'intermediate', or 'advanced'"}), 400

    trace = execute_sandboxed(code)

    explanation = None
    prompt_preview = None
    error_msg = None

    if trace["steps"]:
        prompt_preview = get_example_prompt(trace, depth)
        try:
            explanation = explain_trace(trace, depth=depth)
        except ValueError as e:
            error_msg = str(e)
        except RuntimeError as e:
            error_msg = f"AI explanation failed: {e}"
    elif trace.get("error"):
        prompt_preview = get_example_prompt(trace, depth)
        try:
            explanation = explain_trace(trace, depth=depth)
        except Exception as e:
            error_msg = f"AI explanation failed: {e}"

    response = {
        "trace": trace,
        "explanation": explanation,
        "prompt_preview": prompt_preview,
    }

    if error_msg:
        response["ai_error"] = error_msg

    return jsonify(response)


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
