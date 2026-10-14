import io
import json
import logging
import os
import re
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from server.process.llm_funcs.llm_scr import llm_response
from server.process.tts_func.sovits_ping import sovits_gen


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "client"
AUDIO_DIR = ROOT / "audio"
MAX_REQUEST_BYTES = 32 * 1024
MAX_AUDIO_BYTES = 4 * 1024 * 1024
CHAT_LOCK = threading.Lock()
AUDIO_MAX_AGE_SEC = 10 * 60
# Whisper often spells the name a few different ways.
WAKE_WORD_RE = re.compile(r"\b(?:riko|rico|reeko|rieko)\b", re.IGNORECASE)

PUNCTUATION = " ,.!?;:-"
GREETINGS = {"hey", "hi", "hello", "ok", "okay", "yo", "hey there", "hi there", "oh", "so"}

_whisper_model = None
_whisper_lock = threading.Lock()


def transcribe_wav(data):
    global _whisper_model
    from faster_whisper import WhisperModel

    with _whisper_lock:
        if _whisper_model is None:
            _whisper_model = WhisperModel("base.en", device="cpu", compute_type="float32")
        # The VAD filter stops Whisper from inventing text ("Thank you.") on noise.
        segments, _ = _whisper_model.transcribe(io.BytesIO(data), language="en", vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments).strip()


def cleanup_old_audio():
    cutoff = time.time() - AUDIO_MAX_AGE_SEC
    for old in AUDIO_DIR.glob("web_output_*.wav"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


class WebAppHandler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path in ("/", "/index.html"):
            self._send_file(CLIENT_DIR / "index.html", "text/html; charset=utf-8")
            return

        if path == "/manifest.webmanifest":
            self._send_file(CLIENT_DIR / "manifest.webmanifest", "application/manifest+json")
            return
        if path in ("/icon.png", "/apple-touch-icon.png"):
            self._send_file(CLIENT_DIR / "icon.png", "image/png")
            return

        audio_match = re.fullmatch(r"/audio/(web_output_[0-9a-f]{32}\.wav)", path)
        if audio_match:
            self._send_file(AUDIO_DIR / audio_match.group(1), "audio/wav")
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def _read_body(self, limit):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length"})
            return None

        if content_length <= 0 or content_length > limit:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Request body is empty or too large"})
            return None
        return self.rfile.read(content_length)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/api/listen":
            self._handle_listen()
        elif path == "/api/chat":
            self._handle_chat()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _handle_chat(self):
        body = self._read_body(MAX_REQUEST_BYTES)
        if body is None:
            return

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Request body must be valid JSON"})
            return

        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "A non-empty text value is required"})
            return

        self._respond_to(text.strip())

    def _handle_listen(self):
        """Transcribe an uploaded WAV utterance and answer it if it addresses Riko."""
        body = self._read_body(MAX_AUDIO_BYTES)
        if body is None:
            return

        # The client sets ?wake=1 when the previous utterance was only the wake word.
        already_awake = parse_qs(urlsplit(self.path).query).get("wake") == ["1"]

        try:
            transcript = transcribe_wav(body)
        except Exception:
            logging.exception("Failed to transcribe audio")
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Failed to transcribe audio"})
            return

        logging.info("Heard: %r", transcript)
        if already_awake:
            request = transcript
        else:
            match = WAKE_WORD_RE.search(transcript)
            if not match:
                self._send_json(HTTPStatus.OK, {"status": "ignored"})
                return
            after = transcript[match.end():].strip(PUNCTUATION)
            before = transcript[:match.start()].strip(PUNCTUATION)
            # "What's the weather, Riko?" puts the request before the name.
            request = after or ("" if before.lower() in GREETINGS else before)

        if not request.strip(PUNCTUATION):
            self._send_json(HTTPStatus.OK, {"status": "awake"})
            return

        self._respond_to(request, status="reply", heard=request)

    def _respond_to(self, text, **extra):
        try:
            with CHAT_LOCK:
                reply = llm_response(text)
                AUDIO_DIR.mkdir(parents=True, exist_ok=True)
                cleanup_old_audio()
                audio_name = f"web_output_{uuid.uuid4().hex}.wav"
                audio_path = sovits_gen(reply, AUDIO_DIR / audio_name)
        except Exception:
            logging.exception("Failed to process web chat request")
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Failed to process the chat request"})
            return

        if audio_path is None:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"error": "Riko responded, but speech generation failed", "reply": reply, **extra},
            )
            return

        self._send_json(
            HTTPStatus.OK,
            {"reply": reply, "audio_url": f"/audio/{audio_name}", **extra},
        )

    def _send_file(self, path, content_type):
        try:
            contents = path.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        total = len(contents)
        status = HTTPStatus.OK
        content_range = None
        range_match = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
        # iOS Safari refuses to play media from servers that ignore Range requests.
        if range_match and (range_match.group(1) or range_match.group(2)):
            if range_match.group(1):
                start = int(range_match.group(1))
                end = int(range_match.group(2)) if range_match.group(2) else total - 1
            else:
                start = max(total - int(range_match.group(2)), 0)
                end = total - 1
            end = min(end, total - 1)
            if start > end or start >= total:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{total}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT
            content_range = f"bytes {start}-{end}/{total}"
            contents = contents[start:end + 1]

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        if content_range:
            self.send_header("Content-Range", content_range)
        self.send_header("Content-Length", str(len(contents)))
        self.end_headers()
        self.wfile.write(contents)

    def log_message(self, format_string, *args):
        logging.info("%s - %s", self.address_string(), format_string % args)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host = os.environ.get("RIKO_HOST", "127.0.0.1")
    port = int(os.environ.get("RIKO_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), WebAppHandler)
    print(f"Riko web app: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Riko web app...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
