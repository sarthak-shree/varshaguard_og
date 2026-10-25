import asyncio
import base64
import json
import os
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request, send_from_directory, make_response
from flask_cors import CORS

try:
    from .model import load_model
    from .prediction import (
        REGIONS,
        get_flood_risk_map,
        get_history,
        get_rainfall_series,
        get_stations,
        predict_probability,
    )
    from .risk import get_risk, get_warning
    from .bihar_live.api import bp as bihar_live_bp
except ImportError:
    from model import load_model
    from prediction import (
        REGIONS,
        get_flood_risk_map,
        get_history,
        get_rainfall_series,
        get_stations,
        predict_probability,
    )
    from risk import get_risk, get_warning
    from bihar_live.api import bp as bihar_live_bp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DATA_PATH = os.path.join(BASE_DIR, "data", "processed", "flood_warning_ml_ready_v2.csv")

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 4_000_000
app.register_blueprint(bihar_live_bp)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def error_response(message, status_code=400):
    response = jsonify({"success": False, "error": message, "timestamp": now_iso()})
    response.status_code = status_code
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


def no_store_json(payload):
    response = make_response(jsonify(payload))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


class AssistantAPIError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def request_assistant_answer(message, context, response_language=None):
    """Get a dashboard-grounded answer from the same Groq model as text chat."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise AssistantAPIError("Groq API key is not configured on the backend", 503)

    system_prompt = """You are VarshaGuard Assistant, the official AI assistant for VarshaGuard, a flood-risk early-warning prototype built by Freshcode, a six-person student team.

TEAM CANON — use this when asked who built the project, who does what, or to introduce the team:
- Sarthak — main developer and technical lead; the primary person building and integrating the project.
- Tanmay — research lead; contributes research, investigation, and background analysis.
- Mohit — feedback and review; gives feedback that helps improve the project.
- Rupali — moral support; encourages the team and helps keep morale up.
- Ayushi — moral support; encourages the team and helps keep morale up.
- Partik — listed as a team member. The team's running joke is that his contribution has been hard to spot so far; describe him as "the mysterious team member" or "the name-on-the-roster specialist" in a clearly playful, friendly roast. Do not invent technical contributions or present the joke as a verified performance assessment. If asked seriously, say the team has not specified a concrete responsibility for Partik.

VOICE AND PERSONALITY:
Be lively, confident, witty, and a little "spicy" when talking about the Freshcode team. Use tasteful punchlines, friendly teasing, and memorable wording rather than bland corporate language. Celebrate the people doing the work, while keeping jokes affectionate rather than abusive. Never claim you personally trained or fine-tuned the model; say these are the project's team facts and response instructions.
If a user asks for a team intro, a suitable style is: "Freshcode: six names, one flood-warning mission, and enough teamwork to keep the dashboard alive. Sarthak is shipping the code, Tanmay is digging through the research, Mohit is catching rough edges with feedback, and Rupali and Ayushi are the morale department—keeping the humans running while the code runs. Then there's Partik: the mysterious entry in the credits, currently bringing premium 'classified contribution' energy. We're keeping the roast friendly; he can still unlock his character-development arc."
Do not reuse that exact intro every time; vary the wording naturally.

PROJECT SAFETY AND ACCURACY:
Explain only what is supported by the dashboard context provided by the application.
The dashboard prototype may use historical data, so never describe it as live unless the context explicitly says so.
Help users understand flood probability, risk level, rainfall, river level, model features, forecast horizon, station information, and dashboard sections in clear operational language.
Do not invent measurements, causes, alerts, locations, or forecasts.
When discussing a risk prediction, clearly distinguish model output from certainty. This is a prototype and not a substitute for official warnings.
Keep responses concise and practical. If asked about subjects outside the dashboard or Freshcode team, say that they are outside your available project context, then help if possible within that context."""

    if response_language == "hi":
        system_prompt += "\nReply in simple Hindi. Keep it to 1-3 short sentences suitable for listening. Avoid markdown, lists, and symbols."
    elif response_language == "en":
        system_prompt += "\nReply in simple English. Keep it to 1-3 short sentences suitable for listening. Avoid markdown, lists, and symbols."

    user_prompt = f"Dashboard context:\n{json.dumps(context, ensure_ascii=False)}\n\nUser question:\n{message}"
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
    try:
        groq_response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_completion_tokens": 250 if response_language else 500,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise AssistantAPIError("Could not reach the Groq assistant service", 502) from exc

    if not groq_response.ok:
        try:
            details = groq_response.json().get("error", {}).get("message", groq_response.text)
        except Exception:
            details = groq_response.text
        raise AssistantAPIError(f"Groq API error: {details}", 502)

    try:
        answer = groq_response.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise AssistantAPIError("Groq returned an empty assistant response", 502) from exc
    if not answer:
        raise AssistantAPIError("Groq returned an empty assistant response", 502)
    return answer


async def synthesize_edge_tts(text, voice):
    """Generate an MP3 with the same edge-tts project used by MoodySong."""
    import edge_tts

    audio = bytearray()
    # A +25% rate keeps spoken answers brisk while remaining intelligible.
    rate = os.environ.get("EDGE_TTS_RATE", "+25%")
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            audio.extend(chunk["data"])
    if not audio:
        raise RuntimeError("The speech service returned no audio")
    return bytes(audio)


def get_region_from_request():
    region = request.args.get("region", "Assam").strip()
    if region not in REGIONS:
        return None, None, "Unsupported region"
    station = request.args.get("station", "").strip() or None
    return region, station, None


@app.route("/api/health")
def health():
    model_info = load_model()
    data_available = os.path.exists(DATA_PATH)
    ready = model_info["ok"] and data_available
    return no_store_json({
        "status": "ok" if ready else "error",
        "service": "VARSHAGUARD API",
        "model": "LOADED" if model_info["ok"] else "ERROR",
        "model_error": model_info["error"],
        "data": "AVAILABLE" if data_available else "ERROR",
        "prediction": "READY" if ready else "ERROR",
    })


@app.route("/api/regions")
def regions():
    return no_store_json({"success": True, "regions": REGIONS})


@app.route("/api/flood-risk")
def flood_risk():
    region, station, error = get_region_from_request()
    if error:
        return error_response(error, 400)
    model_info = load_model()
    probability, record, error = predict_probability(model_info, region, station)
    if error:
        return error_response(error, 500)
    risk = get_risk(probability, model_info["decision_threshold"])
    important_features = {
        "rainfall_1h": float(record.get("rainfall_1h", 0)),
        "rainfall_3h": float(record.get("rainfall_3h", 0)),
        "rainfall_6h": float(record.get("rainfall_6h", 0)),
        "rainfall_12h": float(record.get("rainfall_12h", 0)),
        "rainfall_24h": float(record.get("rainfall_24h", 0)),
        "rainfall_72h": float(record.get("rainfall_72h", 0)),
        "is_monsoon": int(record.get("is_monsoon", 0)),
    }
    return no_store_json({
        "success": True,
        "region": region,
        "station": record.get("station", "Prototype station"),
        "prediction_horizon_hours": model_info["prediction_horizon_hours"],
        "flood_probability": round(float(probability), 4),
        "risk": risk,
        "warning": get_warning(risk),
        "timestamp": now_iso(),
        "data_timestamp": str(record.get("timestamp", "")),
        "latitude": float(record.get("latitude", 0)),
        "longitude": float(record.get("longitude", 0)),
        "features": important_features,
    })


@app.route("/api/flood-risk-map")
def flood_risk_map():
    region = request.args.get("region", "Assam").strip()
    if region not in REGIONS:
        return error_response("Unsupported region", 400)
    model_info = load_model()
    results, error = get_flood_risk_map(model_info, region)
    if error:
        return error_response(error, 500)
    return no_store_json({
        "success": True,
        "region": region,
        "prediction_horizon_hours": model_info["prediction_horizon_hours"],
        "stations": results,
        "count": len(results),
        "generated_at": now_iso(),
    })


@app.route("/api/rainfall")
def rainfall():
    region, station, error = get_region_from_request()
    if error:
        return error_response(error, 400)
    rows, error = get_rainfall_series(region, station)
    if error:
        return error_response(error, 500)
    return no_store_json({"success": True, "region": region, "station": station, "rainfall": rows})


@app.route("/api/history")
def history():
    region, station, error = get_region_from_request()
    if error:
        return error_response(error, 400)
    rows, error = get_history(region, station)
    if error:
        return error_response(error, 500)
    return no_store_json({"success": True, "region": region, "station": station, "history": rows})


@app.route("/api/stations")
def stations():
    region = request.args.get("region", "Assam").strip()
    if region not in REGIONS:
        return error_response("Unsupported region", 400)
    rows, error = get_stations(region)
    if error:
        return error_response(error, 500)
    return no_store_json({"success": True, "region": region, "stations": rows})


@app.route("/api/assistant", methods=["POST"])
def assistant():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    context = payload.get("context") or {}

    if not message:
        return error_response("Message is required", 400)

    try:
        answer = request_assistant_answer(message, context)
        return no_store_json({"success": True, "answer": answer})
    except AssistantAPIError as exc:
        return error_response(str(exc), exc.status_code)
    except Exception:
        return error_response("Assistant request failed", 502)


@app.route("/api/assistant/voice", methods=["POST"])
def assistant_voice():
    """Transcribe one short recording, answer with the dashboard LLM, and speak it."""
    audio_file = request.files.get("audio")
    if audio_file is None or not audio_file.filename:
        return error_response("Record a short question before sending it", 400)

    audio_bytes = audio_file.read(3_800_001)
    if not audio_bytes:
        return error_response("The recording was empty. Please try again", 400)
    if len(audio_bytes) > 3_800_000:
        return error_response("The recording is too large. Keep it under 20 seconds and try again", 413)
    if not (audio_file.mimetype or "").lower().startswith("audio/"):
        return error_response("Please send a browser-recorded audio file", 415)

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return error_response("Groq API key is not configured on the backend", 503)

    try:
        raw_context = request.form.get("context", "{}")
        context = json.loads(raw_context)
        if not isinstance(context, dict) or len(raw_context) > 16_000:
            return error_response("Dashboard context is invalid", 400)
    except (TypeError, json.JSONDecodeError):
        return error_response("Dashboard context is invalid", 400)

    reply_language = "hi" if request.form.get("reply_language") == "hi" else "en"
    filename = os.path.basename(audio_file.filename) or "question.webm"
    mime_type = audio_file.mimetype or "audio/webm"

    try:
        transcription_response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            data={
                "model": os.environ.get("GROQ_STT_MODEL", "whisper-large-v3"),
                "response_format": "json",
                "prompt": "VarshaGuard, Bihar, Patna, Muzaffarpur, CWC, IMD, flood risk, rainfall, river gauge.",
            },
            files={"file": (filename, audio_bytes, mime_type)},
            timeout=45,
        )
        if not transcription_response.ok:
            try:
                details = transcription_response.json().get("error", {}).get("message", transcription_response.text)
            except Exception:
                details = transcription_response.text
            return error_response(f"Speech transcription failed: {details}", 502)

        transcript = str(transcription_response.json().get("text", "")).strip()
        if not transcript:
            return error_response("I could not hear a question. Please speak clearly and try again", 422)
        transcript = transcript[:500]
        answer = request_assistant_answer(transcript, context, reply_language)

        voice = "hi-IN-SwaraNeural" if reply_language == "hi" else "en-IN-NeerjaNeural"
        audio_output = asyncio.run(synthesize_edge_tts(answer, voice))
        return no_store_json({
            "success": True,
            "transcript": transcript,
            "answer": answer,
            "audio_base64": base64.b64encode(audio_output).decode("ascii"),
            "audio_mime_type": "audio/mpeg",
        })
    except AssistantAPIError as exc:
        return error_response(str(exc), exc.status_code)
    except Exception:
        return error_response("Voice reply could not be created. Please try again", 502)


@app.errorhandler(413)
def request_too_large(_error):
    return error_response("The recording is too large. Keep it under 20 seconds and try again", 413)


@app.route("/")
def dashboard():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:file_name>")
def frontend_files(file_name):
    return send_from_directory(FRONTEND_DIR, file_name)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
