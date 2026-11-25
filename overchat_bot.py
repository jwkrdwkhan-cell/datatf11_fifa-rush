"""
overchat_bot.py — بوت تليجرام احترافي (يعمل بالأزرار) لـ Overchat.

الميزات:
- واجهة أزرار (inline) بالكامل: محادثة / صورة / فيديو / النماذج / الحسابات / الدعوة / الرصيد.
- حسابات Overchat متعددة لكل مستخدم، تبديل تلقائي عند نفاد الرصيد (وإنشاء حساب جديد).
- نظام دعوة: كل دعوة (مستخدم جديد يبدأ عبر رابطك) تمنحك حسابًا جديدًا = 100 رصيد.
- تخزين محلي JSON — فقط requests + python-telegram-bot + Pillow.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import html
import io
import json
import logging
import os
import re
import threading
import time
import uuid
from typing import Any
from urllib.parse import quote

import requests
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, ".telegram_state.json")
TOKEN_PATH = os.path.join(BASE_DIR, ".telegram.json")
PERSONAS_PATH = os.path.join(BASE_DIR, ".overchat-personas.json")
PERSONAS_TTL = 6 * 60 * 60

DEFAULT_TELEGRAM_TOKEN = "8807749461:AAHy_xwZw6fBSPS_QhmQN-9I96FFaqZglHU"
DEFAULT_OWNER_ID = 8178993130

OC_BASE = (os.environ.get("OVERCHAT_BASE_URL") or "https://api.overchat.ai").rstrip("/")
OC_VERSION = os.environ.get("OVERCHAT_DEVICE_VERSION", "1.0.44")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

MAIL_BASE = (os.environ.get("OVERCHAT_MAIL_BASE") or "https://mail-server.1timetech.com/api").rstrip("/")
MAIL_APP_KEY = os.environ.get("OVERCHAT_MAIL_APP_KEY", "b9db03078622")

DEFAULT_TEXT_PERSONA = "gpt-5-6-luna"
DEFAULT_IMAGE_PERSONA = "flux-3-klein"
DEFAULT_VIDEO_PERSONA = "grok-imagine-lite"

BOT_DISPLAY_NAME = "3mh ai"

CURATED_TEXT_MODELS = (
    "gpt-5-6-luna",
    "deepseek-v-3-2-landing",
    "deepseek-4-landing",
    "claude-haiku-4-5-landing",
    "claude-opus-4-7-landing",
    "gemini-3-5-flash",
    "gpt-5-5-landing",
    "gpt-4o-landing",
    "grok-4-2-landing",
    "qwen-3-landing",
    "gemma-4-landing",
)
MAX_MODEL_PRICE = 100
DEFAULT_PERSONAS = {
    "text": DEFAULT_TEXT_PERSONA,
    "image": DEFAULT_IMAGE_PERSONA,
    "video": DEFAULT_VIDEO_PERSONA,
}
MODEL_NAME_OVERRIDES = {
    "gpt-5-6-luna": "GPT-6 Luna",
    "deepseek-v-3-2-landing": "DeepSeek V3.2",
    "claude-haiku-4-5-landing": "Claude Haiku 5.5",
    "gemini-3-5-flash": "Gemini 3.8 Flash",
    "gpt-5-5-landing": "GPT-5.5",
    "gpt-4o-landing": "GPT-4o",
    "claude-opus-4-7-landing": "Claude Opus 4.7",
    "deepseek-4-landing": "DeepSeek 4",
    "grok-4-2-landing": "Grok 4.2",
    "qwen-3-landing": "Qwen 3",
    "gemma-4-landing": "Gemma 4",
    "Nano-Banana-2": "Nano Banana 2",
    "Nano-Banana-2.1": "Nano Banana 2.1",
    "seedram-4": "Seedream 4",
    "flux-3-klein": "Flux 3 Klein",
    "flux-3-image": "Flux 3 Image",
    "flux-2-max": "Flux 2 Max",
    "gpt-image-2-5-flare": "GPT Image 2.5 Flare",
    "gpt-image-2-5-sunburst": "GPT Image 2.5 Sunburst",
    "gpt-image-2-6-flare": "GPT Image 2.6 Flare",
    "gpt-image-2-6-sunburst": "GPT Image 2.6 Sunburst",
    "grok-imagine-image": "Grok Imagine Image",
    "grok-imagine-image-2": "Grok Imagine Image 2",
    "grok-imagine-lite": "Grok Imagine Lite",
    "qwen-image-2": "Qwen Image 2",
    "qwen-image-3": "Qwen Image 3",
}
MODEL_DESCRIPTIONS = {
    "gpt-5-6-luna": "سريع واقتصادي للمحادثة والمهام اليومية",
    "deepseek-v-3-2-landing": "قوي في البرمجة والاستدلال وبسعر اقتصادي",
    "claude-haiku-4-5-landing": "سريع وخفيف من Anthropic",
    "gemini-3-5-flash": "أداء متقدم وسرعة عالية من Google",
    "flux-3-klein": "أسرع نموذج صور من Flux — اقتصادي ومناسب للتجربة",
    "flux-3-image": "أحدث نموذج صور من Black Forest Labs",
    "flux-2-max": "أقوى نماذج Flux لتوليد الصور",
    "nano-banana": "توليد وتعديل الصور من Google",
    "Nano-Banana-2": "أحدث نماذج Nano Banana — جودة عالية وتعديل ذكي",
    "Nano-Banana-2.1": "إصدار أحدث من Nano Banana بجودة وتعديل محسّنين",
    "gpt-image-2-5-flare": "جودة عالية وإضاءة طبيعية من OpenAI",
    "gpt-image-2-5-sunburst": "دقة عالية مخصصة للأعمال البصرية المميزة",
    "gpt-image-2-6-flare": "أحدث نماذج OpenAI للصور — جودة وإضاءة طبيعية",
    "gpt-image-2-6-sunburst": "أحدث نماذج OpenAI للصور — دقة وتفاصيل عالية",
    "grok-imagine-image": "صور جمالية من xAI",
    "grok-imagine-image-2": "الجيل الثاني من Grok Imagine للصور",
    "seedram-4": "توليد وتعديل الصور من ByteDance",
    "qwen-image-2": "توليد وتعديل الصور من Alibaba",
    "qwen-image-3": "أحدث نماذج Qwen للصور من Alibaba",
    "grok-imagine-lite": "فيديو 480p مع صوت من نص أو صورة",
}
TYPE_TITLES = {"text": "المحادثة", "image": "الصور", "video": "الفيديو"}
TYPE_PROMPTS = {
    "text": "✍️ اكتب رسالتك وأرسلها في رسالة واحدة:",
    "image": "✍️ اكتب وصف الصورة بالتفصيل وأرسله في رسالة واحدة:",
    "video": "✍️ اكتب وصف المشهد والحركة وأرسله في رسالة واحدة:",
}
TYPE_EXAMPLES = {
    "text": "مثال: «اشرح لي الفرق بين الذكاء الاصطناعي وتعلّم الآلة ببساطة»",
    "image": "مثال: «منظر جبلي عند الغروب، ضباب خفيف، تصوير سينمائي»",
    "video": "مثال: «موجة تتكسر على صخرة عند الغروب، حركة بطيئة»",
}


SUCCESS_STATES = {"completed", "succeeded", "success", "done", "finished"}
FAILURE_STATES = {"failed", "failure", "error", "cancelled", "canceled"}

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                    level=logging.INFO)
log = logging.getLogger("overchat-bot")

app: Application | None = None
_BG_TASKS: set[asyncio.Task] = set()


def spawn(coro):
    """يشغّل مهمة خلفية ويحتفظ بمرجع لها حتى لا يجمعها الـ GC."""
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_bg_done)
    return task


def _bg_done(task: asyncio.Task) -> None:
    _BG_TASKS.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error:
        log.warning("فشلت مهمة خلفية: %s", error)


_DEC_SW = {"*": "4", "=": "x", "B": "z", "z": "B", "5": "b", "b": "5",
           "a": "o", "o": "a", "q": "s", "s": "q"}
_ENC_SW = {v: k for k, v in _DEC_SW.items()}


def tm_decode(s: str) -> Any:
    n = len(s) - len(s.lstrip("x"))
    t = "=" * n + s[n:]
    rev = t[::-1]
    m = len(rev) - len(rev.rstrip("="))
    body = rev[: len(rev) - m] if m else rev
    std = "".join(_DEC_SW.get(c, c) for c in body) + "=" * m
    raw = base64.b64decode(std + "==").decode("utf-8", "replace")
    try:
        obj = json.loads(raw)
    except Exception:
        obj = json.loads(base64.b64decode(std + "==").decode("latin-1"))
    return json.loads(obj) if isinstance(obj, str) else obj


def tm_encode(obj: Any) -> str:
    s = obj if isinstance(obj, str) else json.dumps(obj, separators=(",", ":"))
    b64 = base64.b64encode(s.encode()).decode()
    custom = "".join(_ENC_SW.get(c, c) for c in b64)
    rev = custom[::-1]
    n = len(rev) - len(rev.lstrip("="))
    return "x" * n + rev[n:]


def load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


_SAVE_LOCK = threading.Lock()


def save_json(path: str, data: Any) -> None:
    tmp = path + ".tmp"
    with _SAVE_LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def esc(value: Any) -> str:
    """تهريب النصوص الديناميكية قبل إرسالها بـ HTML."""
    return html.escape(str(value if value is not None else ""), quote=False)


def chunk_escaped(text: str, size: int = 3800) -> list[str]:
    """تقسيم نص طويل بعد تهريبه دون قطع أي كيان HTML في المنتصف."""
    parts: list[str] = []
    current: list[str] = []
    length = 0
    for char in text:
        piece = esc(char)
        if current and length + len(piece) > size:
            parts.append("".join(current))
            current = []
            length = 0
        current.append(piece)
        length += len(piece)
    if current:
        parts.append("".join(current))
    return parts or [""]


def shorten(text: Any, limit: int = 30) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: max(1, limit - 1)].rstrip() + "…"


def fmt_points(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    return f"{number:.0f}" if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")


def points_word(value: Any) -> str:
    """صيغة عربية سليمة لكلمة نقاط حسب العدد."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "نقطة"
    if number.is_integer():
        n = abs(int(number))
        if n == 1:
            return "نقطة"
        if n == 2:
            return "نقطتان"
        if 3 <= n <= 10:
            return "نقاط"
    return "نقطة"


def fmt_price(value: Any) -> str:
    """مثال: «3 نقاط» بدل «3 نقطة»."""
    return f"{fmt_points(value)} {points_word(value)}"


def download(url: str) -> bytes:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.content


def compress_image(data: bytes, max_side: int = 1280, quality: int = 85) -> bytes:
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGB")
        im.thumbnail((max_side, max_side))
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception:
        return data


class OverchatError(Exception):
    def __init__(self, status: int, message: str, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


def is_quota_error(err: OverchatError) -> bool:
    msg = (err.body or str(err) or "").lower()
    if "paid plans" in msg or "paid plan" in msg:
        return False
    return bool(re.search(r"quota|limit reached|insufficient|not enough|takos|credit|"
                          r"balance|reached your|plan limit", msg))


class Overchat:
    def __init__(self) -> None:
        self._local = threading.local()
        self._personas: list[dict] = []
        self._personas_lock = threading.Lock()

    @property
    def session(self) -> requests.Session:
        sess = getattr(self._local, "session", None)
        if sess is None:
            sess = requests.Session()
            self._local.session = sess
        return sess

    def headers(self, device_uuid: str, token: str | None = None,
                auth: bool = True, json_body: bool = False) -> dict:
        h = {
            "accept": "application/json, text/plain, */*",
            "x-device-platform": "web",
            "x-device-version": OC_VERSION,
            "x-device-language": "en",
            "x-device-uuid": device_uuid,
            "origin": "https://overchat.ai",
            "referer": "https://overchat.ai/",
            "User-Agent": UA,
        }
        if json_body:
            h["content-type"] = "application/json"
        if auth and token:
            h["authorization"] = f"Bearer {token}"
        return h

    def _request(self, path: str, *, method: str = "GET", device_uuid: str,
                 token: str | None = None, auth: bool = True, body: Any = None,
                 stream: bool = False, allow: tuple[int, ...] = ()) -> requests.Response:
        h = self.headers(device_uuid, token, auth, json_body=body is not None)
        url = OC_BASE + path
        data = json.dumps(body).encode() if body is not None else None
        r = self.session.request(method, url, headers=h, data=data, stream=stream, timeout=60)
        r.encoding = "utf-8"
        if r.status_code >= 400 and r.status_code not in allow:
            text = r.text[:500]
            raise OverchatError(r.status_code, f"HTTP {r.status_code}: {text}", text)
        return r

    def me(self, device_uuid: str, token: str) -> dict:
        return self._request("/v1/auth/me", device_uuid=device_uuid, token=token).json()

    def send_code(self, device_uuid: str, email: str) -> None:
        r = self._request("/v1/auth/email/send-code", method="POST", device_uuid=device_uuid,
                          auth=False, body={"email": email},
                          allow=(400, 403, 429, 500, 502, 503))
        if r.status_code in (403, 429):
            raise OverchatError(r.status_code, "rate limited", r.text[:200])

    def verify_code(self, device_uuid: str, email: str, code: str) -> dict:
        r = self._request("/v1/auth/email/verify", method="POST", device_uuid=device_uuid,
                          auth=False, body={"email": email, "code": code},
                          allow=(400, 401, 403, 409, 410, 422, 429))
        data = r.json() if r.text.strip() else {}
        if r.status_code >= 400:
            raise OverchatError(r.status_code, data.get("message", "verify failed"), r.text)
        if not data.get("access_token"):
            raise OverchatError(r.status_code, "no access_token", r.text)
        return data

    def personas(self, device_uuid: str, force: bool = False) -> list[dict]:
        with self._personas_lock:
            cached = load_json(PERSONAS_PATH, None)
            if (not force and cached and isinstance(cached.get("personas"), list)
                    and time.time() - cached.get("fetchedAt", 0) < PERSONAS_TTL):
                self._personas = cached["personas"]
                return self._personas
            r = self._request("/v1/personas?view=list", device_uuid=device_uuid)
            data = r.json()
            items = data if isinstance(data, list) else (
                data.get("data") or data.get("items") or data.get("personas") or [])
            if items:
                save_json(PERSONAS_PATH, {"fetchedAt": time.time(), "personas": items})
                self._personas = items
            return self._personas

    def find_persona(self, pid: str) -> dict | None:
        for p in self._personas:
            if p.get("id") == pid:
                return p
        low = str(pid).lower()
        for p in self._personas:
            if str(p.get("id", "")).lower() == low or str(p.get("name", "")).lower() == low:
                return p
        return None

    def chat(self, device_uuid: str, token: str, persona_id: str, prompt: str) -> str:
        persona = self.find_persona(persona_id) or {}
        body = {
            "chatId": str(uuid.uuid4()),
            "model": persona.get("model") or persona_id,
            "personaId": persona_id,
            "messages": [{"id": str(uuid.uuid4()), "role": "user", "content": prompt}],
            "links": [],
            "frequency_penalty": 0,
            "max_tokens": 4000,
            "presence_penalty": 0,
            "stream": True,
            "temperature": 0.5,
            "top_p": 0.95,
        }
        r = self._request("/v1/chat/completions", method="POST", device_uuid=device_uuid,
                          token=token, body=body, stream=True)
        if "text/event-stream" not in r.headers.get("content-type", ""):
            raise OverchatError(r.status_code, f"unexpected: {r.text[:300]}", r.text)
        r.encoding = "utf-8"
        out: list[str] = []
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            data = raw[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                obj = json.loads(data)
            except Exception:
                continue
            if isinstance(obj, dict):
                if obj.get("error"):
                    raise OverchatError(200, str(obj["error"]), data)
                ch = obj.get("choices") or []
                if ch:
                    d = (ch[0].get("delta") or {}).get("content")
                    if d:
                        out.append(d)
        text = "".join(out)
        if not text:
            raise OverchatError(200, "empty response")
        return text

    @staticmethod
    def _extract_url(obj: Any) -> str | None:
        if isinstance(obj, str):
            return obj if obj.startswith("http") else None
        if isinstance(obj, list):
            for it in obj:
                u = Overchat._extract_url(it)
                if u:
                    return u
            return None
        if not isinstance(obj, dict):
            return None
        for k in ("videoUrl", "video_url", "audioUrl", "url", "resultUrl", "imageUrl",
                  "fileUrl", "downloadUrl", "outputUrl", "link", "video", "image"):
            v = obj.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
        for k in ("result", "data", "output", "files", "file", "media", "generation",
                  "images", "image", "video", "videos"):
            if k in obj:
                u = Overchat._extract_url(obj[k])
                if u:
                    return u
        return None

    @staticmethod
    def _state(obj: dict) -> str:
        raw = obj.get("status") or obj.get("state") or ""
        if isinstance(obj.get("data"), dict):
            raw = obj["data"].get("status") or raw
        return str(raw).lower()

    def image(self, device_uuid: str, token: str, persona_id: str, prompt: str,
              aspect: str | None = None) -> str:
        persona = self.find_persona(persona_id) or {}
        params = dict((persona.get("config") or {}).get("params") or {})
        body = {
            "chatId": str(uuid.uuid4()),
            "prompt": prompt,
            "userMessageText": prompt,
            "model": persona.get("model") or persona_id,
            "personaId": persona_id,
            "output_format": "png",
            "params": params,
            "metadata": {"flow_type": "image"},
            "userMessageId": str(uuid.uuid4()),
            "assistantMessageId": str(uuid.uuid4()),
        }
        if aspect:
            body["metadata"]["aspect_ratio"] = aspect
        r = self._request("/v1/images/generation", method="POST", device_uuid=device_uuid,
                          token=token, body=body)
        wf = r.json().get("id") or r.json().get("workflowId")
        if not wf:
            raise OverchatError(200, "no workflow id", r.text)
        log.info("image workflow %s", wf)
        return self._poll(device_uuid, token, f"/v1/images/generation/{wf}", timeout=300)

    def video(self, device_uuid: str, token: str, persona_id: str, prompt: str,
              aspect: str | None = None) -> str:
        persona = self.find_persona(persona_id) or {}
        params = dict((persona.get("config") or {}).get("params") or {})
        body = {
            "chatId": str(uuid.uuid4()),
            "prompt": prompt,
            "userMessageText": prompt,
            "personaId": persona_id,
            "metadata": {"flow_type": "video"},
            "params": params,
            "userMessageId": str(uuid.uuid4()),
            "assistantMessageId": str(uuid.uuid4()),
        }
        if aspect:
            body["metadata"]["aspect_ratio"] = aspect
        r = self._request("/v1/videos/generations", method="POST", device_uuid=device_uuid,
                          token=token, body=body)
        wf = r.json().get("id") or r.json().get("workflowId")
        if not wf:
            raise OverchatError(200, "no workflow id", r.text)
        log.info("video workflow %s", wf)
        return self._poll(device_uuid, token, f"/v1/videos/generations/{wf}",
                          interval=5, timeout=1200)

    def _poll(self, device_uuid: str, token: str, path: str,
              interval: int = 3, timeout: int = 300) -> str:
        start = time.time()
        last = None
        while time.time() - start < timeout:
            r = self._request(path, device_uuid=device_uuid, token=token, allow=(422,))
            data = r.json() if r.text.strip() else {}
            state = self._state(data)
            if state != last:
                log.info("poll %s -> %s", path.split("/")[-1], state or "(no status)")
                last = state
            if state in SUCCESS_STATES:
                url = self._extract_url(data)
                if not url:
                    raise OverchatError(200, "done but no url", json.dumps(data)[:400])
                return url
            if state in FAILURE_STATES:
                raise OverchatError(200, f"generation failed: {state}")
            time.sleep(interval)
        raise OverchatError(200, "generation timeout")


class TempMail:
    def __init__(self) -> None:
        self._local = threading.local()

    @property
    def session(self) -> requests.Session:
        sess = getattr(self._local, "session", None)
        if sess is None:
            sess = requests.Session()
            self._local.session = sess
        return sess

    def _headers(self, with_type: bool = True) -> dict:
        h = {"accept": "application/json", "x-app-key": MAIL_APP_KEY,
             "User-Agent": "okhttp/4.12.0"}
        if with_type:
            h["Content-Type"] = "application/json"
        return h

    def create(self) -> dict:
        token = tm_encode({})
        r = self.session.post(f"{MAIL_BASE}/g-mail", headers=self._headers(),
                              data=json.dumps({"data": token}), timeout=30)
        r.raise_for_status()
        data = tm_decode(r.json()["data"])
        return {"email": data["email"], "id": data["id"],
                "token": tm_encode({"email": data["email"]})}

    def list_messages(self, inbox: dict) -> list[dict]:
        r = self.session.get(f"{MAIL_BASE}/email/{inbox['id']}/messages",
                             params={"params": inbox["token"]},
                             headers=self._headers(False), timeout=30)
        r.raise_for_status()
        data = tm_decode(r.json()["data"])
        return data if isinstance(data, list) else []

    def get_message(self, inbox: dict, mid: str) -> dict:
        r = self.session.get(f"{MAIL_BASE}/email/{inbox['id']}/messages/{mid}",
                             params={"params": inbox["token"]},
                             headers=self._headers(False), timeout=30)
        r.raise_for_status()
        return tm_decode(r.json()["data"]) or {}

    @staticmethod
    def extract_code(msg: dict) -> str | None:
        subject = str(msg.get("subject", ""))
        body = f"{subject}\n{msg.get('text','')}\n{msg.get('html','')}"
        m = re.search(r"\b(\d{4})\b", subject) or re.search(r"\b(\d{4})\b", body)
        return m.group(1) if m else None

    @staticmethod
    def looks_like_overchat(msg: dict) -> bool:
        frm = str(msg.get("from", "")).lower()
        subj = str(msg.get("subject", "")).lower()
        return "overchat" in frm or "overchat" in subj or "verif" in subj

    def wait_for_code(self, inbox: dict, timeout: int = 180, interval: int = 4,
                      since: float = 0) -> str:
        start = time.time()
        while time.time() - start < timeout:
            for msg in self.list_messages(inbox):
                ts = float(msg.get("createdAt") or 0) / 1000.0
                if ts and ts < since - 5:
                    continue
                if not self.looks_like_overchat(msg):
                    continue
                code = self.extract_code(self.get_message(inbox, msg["id"]))
                if code:
                    return code
            time.sleep(interval)
        raise TimeoutError("no verification code")


oc = Overchat()
mail = TempMail()


def cached_personas() -> list[dict]:
    """يعيد النماذج من الذاكرة أو من ملف الكاش دون أي طلب شبكة."""
    if oc._personas:
        return oc._personas
    cached = load_json(PERSONAS_PATH, None)
    if isinstance(cached, dict) and isinstance(cached.get("personas"), list):
        oc._personas = cached["personas"]
    return oc._personas


def personas_fresh() -> bool:
    cached = load_json(PERSONAS_PATH, None)
    if not isinstance(cached, dict) or not isinstance(cached.get("personas"), list):
        return False
    try:
        return time.time() - float(cached.get("fetchedAt") or 0) < PERSONAS_TTL
    except (TypeError, ValueError):
        return False


def canonical_model(persona: dict) -> str:
    """اسم الموديل الأساسي بعد إزالة بادئة المزوّد، لمقارنة النسخ المكررة."""
    model = str(persona.get("model") or "").strip().lower()
    model = re.sub(
        r"^(?:openai|anthropic|google|meta|meta-llama|mistralai|x-ai|xai|deepseek|"
        r"qwen|bytedance|blackforestlabs|fal-ai|minimax|alibaba|moonshotai|z-ai|"
        r"tencent|baidu|recursive)/",
        "",
        model,
    )
    return model.rstrip(":")


def is_base_model(persona: dict) -> bool:
    config = persona.get("config")
    if not isinstance(config, dict):
        return False
    if config.get("isAIModel") is True:
        return True
    ui = config.get("ui")
    if not isinstance(ui, dict):
        return False
    return bool(ui.get("imageGenModel") or ui.get("videoGenModel"))


def _is_bad_model_id(persona: dict) -> bool:
    value = str(persona.get("id") or "").lower()
    return any(token in value for token in ("pregen", "spec-test", "-test", "probe", "internal"))


def _price(persona: dict) -> int:
    try:
        return int(float(persona.get("price") or 0))
    except (TypeError, ValueError):
        return 0


def curated_personas(typ: str, items: list[dict] | None = None) -> list[dict]:
    """قائمة النماذج الأساسية القابلة للاستخدام لكل قسم."""
    items = items if items is not None else cached_personas()

    def usable(p: dict) -> bool:
        return (
            str(p.get("type")) == typ
            and p.get("freeAccess") is True
            and _price(p) <= MAX_MODEL_PRICE
            and not _is_bad_model_id(p)
        )

    if typ == "text":
        selected: list[dict] = []
        by_id = {str(p.get("id")): p for p in items}
        for pid in CURATED_TEXT_MODELS:
            p = by_id.get(pid)
            if p and usable(p):
                selected.append(p)
        if selected:
            return selected

        junk = ("landing", "widget", "scan", "tool", "generator", "summarizer",
                "detector", "solver", "rater", "looksmax", "answer")
        seen: set[str] = set()
        fallback: list[dict] = []
        for p in items:
            if not usable(p):
                continue
            label = f"{p.get('id')} {p.get('name')}".lower()
            if any(word in label for word in junk):
                continue
            config = p.get("config")
            if not isinstance(config, dict):
                config = {}
            if not (p.get("isDefault") or config.get("apiVersion") or p.get("isAgentEnabled")):
                continue
            key = canonical_model(p)
            if not key or key in seen:
                continue
            seen.add(key)
            fallback.append(p)
        fallback.sort(key=lambda p: (_price(p), str(p.get("name"))))
        return fallback[:12]

    models = [p for p in items if usable(p) and is_base_model(p)]
    unique: dict[str, dict] = {}
    for p in models:
        key = canonical_model(p) or str(p.get("id"))
        previous = unique.get(key)
        if previous is None or _price(p) < _price(previous):
            unique[key] = p
    result = sorted(unique.values(), key=lambda p: (_price(p), str(p.get("name"))))
    if result:
        return result

    return sorted((p for p in items if usable(p)), key=lambda p: _price(p))[:12]


def model_display_name(persona: dict) -> str:
    pid = str(persona.get("id") or "")
    if pid in MODEL_NAME_OVERRIDES:
        return MODEL_NAME_OVERRIDES[pid]
    name = " ".join(str(persona.get("name") or "").split())
    lowered = name.lower()
    if not name or lowered == pid.lower() or "landing" in lowered or "widget" in lowered:
        model = canonical_model(persona)
        labels = {
            "gpt-6-luna": "GPT-6 Luna",
            "deepseek-non-thinking-v3.2-exp": "DeepSeek V3.2",
            "claude-haiku-5.5": "Claude Haiku 5.5",
            "gemini-3.8-flash": "Gemini 3.8 Flash",
            "nano-banana": "Nano Banana",
            "nano-banana-2": "Nano Banana 2",
            "nano-banana-2.1": "Nano Banana 2.1",
            "seedream/v4": "Seedream 4",
            "flux-3/klein": "Flux 3 Klein",
            "gpt-image-2.5/flare": "GPT Image 2.5 Flare",
            "gpt-image-2.5/sunburst": "GPT Image 2.5 Sunburst",
            "gpt-image-2.6/flare": "GPT Image 2.6 Flare",
            "gpt-image-2.6/sunburst": "GPT Image 2.6 Sunburst",
        }
        if model in labels:
            return labels[model]
        tail = model.split("/")[-1]
        if tail:
            return re.sub(r"[-_]+", " ", tail).strip().title()
        return pid or "نموذج"
    return name


def model_description(persona: dict) -> str:
    pid = str(persona.get("id") or "")
    if pid in MODEL_DESCRIPTIONS:
        return MODEL_DESCRIPTIONS[pid]
    for key in ("displayPrompt", "description"):
        value = " ".join(str(persona.get(key) or "").split())
        if value and value not in (".", "-"):
            return shorten(value, 150)
    return ""


def model_button_label(persona: dict) -> str:
    return f"{shorten(model_display_name(persona), 28)} · {fmt_price(_price(persona))}"


def resolve_model_id(typ: str, pid: str | None, u: dict | None = None) -> str:
    """يحوّل أي معرّف قديم/قالب إلى نموذج أساسي معروف من القائمة."""
    pid = str(pid or "").strip()
    items = cached_personas()
    models = curated_personas(typ, items)
    ids = {str(p.get("id")) for p in models}
    if pid in ids:
        return pid
    by_id = {str(p.get("id")): p for p in items}
    old = by_id.get(pid)
    if old:
        old_model = canonical_model(old)
        for p in models:
            if canonical_model(p) == old_model:
                return str(p.get("id"))
    default = DEFAULT_PERSONAS.get(typ, "")
    if default in ids:
        return default
    if models:
        return str(models[0].get("id"))
    return default or pid


def model_count(typ: str) -> int:
    return len(curated_personas(typ))


def new_user(uid: int) -> dict:
    return {"uid": uid, "device_uuid": str(uuid.uuid4()), "accounts": [],
            "active": 0, "invites": [], "referred_by": None, "created": time.time()}


def seed_settings(st: dict) -> None:
    """تهيئة إعدادات البوت بدون قنوات اشتراك إجباري."""
    s = st.get("settings")
    if not isinstance(s, dict):
        s = {}
        st["settings"] = s
    s.pop("channel", None)
    s.pop("channel_url", None)
    if not isinstance(s.get("channels"), list):
        s["channels"] = []


_STATE: dict | None = None
_STATE_LOCK = threading.RLock()


def load_state() -> dict:
    """حالة مشتركة واحدة في الذاكرة حتى لا يضيع تحديث مستخدم بسبب تحديث آخر."""
    global _STATE
    if _STATE is None:
        st = load_json(STATE_PATH, None)
        if not isinstance(st, dict):
            st = {"users": {}}
        if not isinstance(st.get("users"), dict):
            st["users"] = {}
        st.setdefault("users", {})
        seed_settings(st)
        _STATE = st
    return _STATE


def save_state(st: dict | None = None) -> None:
    global _STATE
    if st is not None:
        _STATE = st
    if _STATE is None:
        return
    with _STATE_LOCK:
        snapshot = copy.deepcopy(_STATE)
    save_json(STATE_PATH, snapshot)


def get_user(st: dict, uid: int) -> dict:
    u = st["users"].get(str(uid))
    if not isinstance(u, dict):
        u = new_user(uid)
        st["users"][str(uid)] = u
    return u


def active_account(u: dict) -> dict | None:
    accs = u.get("accounts") or []
    if not accs:
        return None
    try:
        i = int(u.get("active") or 0)
    except (TypeError, ValueError):
        i = 0
    if i < 0 or i >= len(accs):
        i = 0
    return accs[i]


_ACCOUNT_LOCK = threading.Lock()


def create_account_blocking(u: dict, attempts: int = 5) -> dict:
    with _ACCOUNT_LOCK:
        return _create_account_locked(u, attempts)


def _create_account_locked(u: dict, attempts: int = 5) -> dict:
    last_err: Exception | None = None
    created: list[dict] = []
    best: tuple[int, dict] | None = None
    chosen: dict | None = None
    chosen_inbox: dict | None = None
    try:
        for i in range(attempts):
            try:
                inbox = mail.create()
            except Exception as e:
                last_err = e
                log.warning("إنشاء حساب: تعذر تجهيز بريد مؤقت (%s)", e)
                break
            try:
                oc.send_code(u["device_uuid"], inbox["email"])
                code = mail.wait_for_code(inbox, timeout=150, since=time.time())
                data = oc.verify_code(u["device_uuid"], inbox["email"], code)
            except OverchatError as e:
                last_err = e
                log.warning("إنشاء حساب: محاولة %s فشلت (%s)", i + 1, e)
                if e.status in (403, 429):
                    time.sleep(20)
                continue
            except TimeoutError as e:
                last_err = e
                log.warning("إنشاء حساب: لم يصل الكود (محاولة %s)", i + 1)
                continue
            except Exception as e:
                last_err = e
                log.warning("إنشاء حساب: خطأ غير متوقع في المحاولة %s (%s)", i + 1, e)
                continue

            acc = {"email": inbox["email"], "accessToken": data["access_token"],
                   "createdAt": time.time(), "mailInboxId": inbox["id"],
                   "mailToken": inbox["token"]}
            try:
                me = oc.me(u["device_uuid"], acc["accessToken"])
                bal = int(me.get("takosCoin") or 0)
            except Exception:
                bal = 100
            acc["balance"] = bal
            acc["balanceAt"] = time.time()
            created.append(acc)
            if best is None or bal > best[0]:
                best = (bal, acc)
            if bal >= 100:
                chosen, chosen_inbox = acc, inbox
                break
            log.warning("حساب %s رصيده %s فقط — محاولة أخرى", acc["email"], bal)
    finally:
        if created:
            final = chosen or (best[1] if best else created[-1])
            _store_new_accounts(u, created, final, chosen_inbox)

    if chosen:
        return chosen
    if best:
        return best[1]
    raise last_err or TimeoutError("create account failed")


def _store_new_accounts(u: dict, created: list[dict], chosen: dict,
                        inbox: dict | None) -> None:
    with _STATE_LOCK:
        accounts = u.setdefault("accounts", [])
        for acc in created:
            if acc not in accounts:
                accounts.append(acc)
        u["active"] = accounts.index(chosen)
        if inbox:
            u["mailInboxId"] = inbox["id"]
            u["mailToken"] = inbox["token"]
            u["mailEmail"] = inbox["email"]


def rotate_blocking(st: dict, u: dict) -> dict:
    with _STATE_LOCK:
        accs = list(u.get("accounts") or [])
        cur = active_account(u)
        if cur:
            cur["exhaustedAt"] = time.time()
        for a in accs:
            if a is not cur and not a.get("exhaustedAt"):
                u["active"] = accs.index(a)
                return a
    return create_account_blocking(u)


def account_balance(u: dict, acc: dict, max_age: int = 120) -> int:
    """رصيد الحساب (Takos) مع كاش قصير."""
    now = time.time()
    if acc.get("balance") is not None and now - float(acc.get("balanceAt") or 0) < max_age:
        return int(acc.get("balance") or 0)
    try:
        me = oc.me(u["device_uuid"], acc["accessToken"])
        bal = int(me.get("takosCoin") or 0)
    except Exception:
        bal = int(acc.get("balance") or 0)
    with _STATE_LOCK:
        acc["balance"] = bal
        acc["balanceAt"] = now
    return bal


def pick_account(u: dict, cost: int) -> dict:
    """
    يختار حسابًا رصيده >= التكلفة (أفضل ملاءمة: أصغر رصيد يكفي)،
    وإلا ينشئ حسابًا جديدًا (100 رصيد).
    """
    accs = u.get("accounts") or []
    best = None
    best_bal = None
    for a in accs:
        if a.get("exhaustedAt"):
            continue
        bal = account_balance(u, a)
        if bal >= cost and (best_bal is None or bal < best_bal):
            best, best_bal = a, bal
    if best:
        with _STATE_LOCK:
            u["active"] = accs.index(best)
        return best
    return create_account_blocking(u)


STARTER_POINTS = 20.0
INVITE_POINTS = 100.0


def settings(st: dict) -> dict:
    return st.setdefault("settings", {})


def owner_id(st: dict | None = None) -> int:
    if st is None:
        st = load_state()
    s = st.get("settings") or {}
    cfg = load_json(TOKEN_PATH, {})
    for raw in (s.get("owner_id"),
                cfg.get("owner_id") if isinstance(cfg, dict) else None,
                os.environ.get("BOT_OWNER_ID"),
                DEFAULT_OWNER_ID):
        try:
            if raw:
                return int(raw)
        except (TypeError, ValueError):
            continue
    return DEFAULT_OWNER_ID


def is_owner(uid: int, st: dict | None = None) -> bool:
    oid = owner_id(st)
    return bool(oid) and uid == oid


def user_points(u: dict) -> float:
    return float(u.get("points") or 0.0)


def add_points(u: dict, n: float) -> None:
    u["points"] = max(0.0, user_points(u) + float(n))


def charge_points(u: dict, n: float) -> None:
    u["points"] = max(0.0, user_points(u) - float(n))


async def ensure_access(update, context, st: dict, u: dict) -> bool:
    """بوابة الحظر + وضع الصيانة."""
    if is_owner(update.effective_user.id, st):
        return True
    if u.get("banned"):
        await update.effective_message.reply_text(
            "⛔ <b>تم حظرك من استخدام البوت.</b>\n"
            "إذا كنت تعتقد أن هذا خطأ، تواصل مع مالك البوت.",
            parse_mode="HTML")
        return False
    s = settings(st)
    if s.get("maintenance"):
        await update.effective_message.reply_text(
            "🚧 <b>صيانة مؤقتة</b>\n"
            "البوت قيد التحديث حاليًا. حاول مرة أخرى بعد قليل.",
            parse_mode="HTML")
        return False
    return True


async def broadcast_all(bot, text: str) -> tuple[int, int]:
    st = load_state()
    ok = fail = 0
    for uid in list(st.get("users", {}).keys()):
        try:
            await bot.send_message(int(uid), text)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    return ok, fail


def btn(text: str, data: str, style: str | None = None,
        disabled: bool = False) -> InlineKeyboardButton:
    kwargs: dict[str, Any] = {}
    if disabled:
        kwargs["api_kwargs"] = {"disabled": {}}
    return InlineKeyboardButton(text, callback_data=data, style=style, **kwargs)


def main_menu(admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [btn("💬 محادثة", "menu:chat", style="primary"),
         btn("🎨 صور", "menu:image", style="success")],
        [btn("🎬 فيديو", "menu:video", style="danger"),
         btn("📚 النماذج", "menu:models", style="primary")],
        [btn("🎁 دعوة الأصدقاء", "menu:invite", style="success"),
         btn("💰 رصيدي", "menu:balance", style="success")],
        [btn("👤 حسابات Overchat", "menu:accounts", style="primary"),
         btn("⚙️ الإعدادات", "menu:settings", style="primary")],
        [btn("ℹ️ المساعدة", "menu:help", style="primary")],
    ]
    if admin:
        rows.append([btn("👑 لوحة التحكم", "admin:panel", style="danger")])
    return InlineKeyboardMarkup(rows)


def pref_label(u: dict, typ: str) -> str:
    pid = resolve_model_id(typ, (u.get("prefs") or {}).get(typ), u)
    persona = oc.find_persona(pid)
    return model_display_name(persona) if persona else "الافتراضي"


def welcome_text(u: dict, admin: bool = False) -> str:
    name = esc(u.get("name") or "صديقي")
    points = user_points(u)
    balance_line = (
        "👑 <b>مالك البوت</b> — الاستخدام مجاني"
        if admin else
        f"💎 رصيدك الحالي: <b>{fmt_price(points)}</b>"
    )
    return (
        f"👋 <b>مرحبًا {name}</b>\n"
        f"<b>{esc(BOT_DISPLAY_NAME)}</b> — مساعدك للمحادثة والصور والفيديو.\n\n"
        f"{balance_line}\n\n"
        f"💬 المحادثة: {esc(pref_label(u, 'text'))}\n"
        f"🎨 الصور: {esc(pref_label(u, 'image'))}\n"
        f"🎬 الفيديو: {esc(pref_label(u, 'video'))}\n\n"
        f"اختر ما تريد من الأزرار بالأسفل 👇"
    )


HELP_TEXT = (
    "ℹ️ <b>دليل الاستخدام</b>\n\n"
    "<b>1)</b> اختر القسم: 💬 محادثة / 🎨 صور / 🎬 فيديو.\n"
    "<b>2)</b> اختر النموذج المناسب — السعر ظاهر أمام كل نموذج.\n"
    "<b>3)</b> أرسل سؤالك أو وصفك في رسالة واحدة.\n"
    "<b>4)</b> انتظر النتيجة؛ الفيديو قد يستغرق عدة دقائق.\n\n"
    "<b>أوامر سريعة:</b>\n"
    "• /cancel — إلغاء العملية والعودة للقائمة.\n"
    "• /help — عرض هذه المساعدة.\n\n"
    "<b>ملاحظات مهمة:</b>\n"
    "• كل طلب يخصم نقاطًا حسب سعر النموذج المختار.\n"
    "• نقاط البوت منفصلة عن رصيد Takos الموجود في كل حساب Overchat.\n"
    "• عند نفاد رصيد حساب Overchat يتم التبديل لحساب آخر تلقائيًا.\n"
    "• كل صديق جديد يبدأ عبر رابط دعوتك = <b>100 نقطة</b> + حساب جديد.\n"
    "• يمكنك تثبيت نموذج افتراضي لكل قسم من ⚙️ الإعدادات.\n"
    "• لإدارة حسابات Overchat افتح 👤 حسابات Overchat."
)


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[btn("⬅️ القائمة الرئيسية", "menu:main")]])


def result_kb(typ: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [btn("🔁 طلب جديد", f"again:{typ}", style="success"),
         btn("🎛️ تغيير النموذج", f"models:{typ}:0", style="primary")],
        [btn("⬅️ القائمة الرئيسية", "menu:main")],
    ])


async def safe_edit(query, text: str, keyboard=None) -> None:
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception:
            pass


async def send_long(bot, chat_id: int, text: str, keyboard=None) -> None:
    """يرسل نصًا عاديًا طويلًا بعد تهريبه إلى HTML وتقسيمه بأمان."""
    parts = chunk_escaped(text)
    for i, part in enumerate(parts):
        kb = keyboard if i == len(parts) - 1 else None
        try:
            await bot.send_message(chat_id, part, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await bot.send_message(chat_id, html.unescape(part), reply_markup=kb)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    st = load_state()
    uid = update.effective_user.id
    u = get_user(st, uid)
    context.user_data.pop("state", None)
    context.user_data.pop("admin_state", None)
    if update.effective_user.first_name:
        u["name"] = update.effective_user.first_name

    if u.get("banned") and not is_owner(uid, st):
        await update.message.reply_text(
            "⛔ <b>تم حظرك من استخدام البوت.</b>", parse_mode="HTML")
        return

    first_time = not u.get("started")
    if first_time:
        u["started"] = True
        add_points(u, STARTER_POINTS)

    prefs = u.setdefault("prefs", {})
    for typ in ("text", "image", "video"):
        old = prefs.get(typ)
        if old:
            new = resolve_model_id(typ, old, u)
            if new and new != old:
                prefs[typ] = new

    note = ""
    payload = (context.args[0] if context.args else "") or ""
    m = re.match(r"ref_(\d+)", payload)
    if m:
        inviter_id = int(m.group(1))
        if inviter_id != uid and not u.get("referred_by") and first_time:
            u["referred_by"] = inviter_id
            inv = get_user(st, inviter_id)
            if uid not in inv["invites"]:
                inv["invites"].append(uid)
            add_points(inv, INVITE_POINTS)
            spawn(grant_invite_async(inviter_id))
            note = (
                "🎉 <b>وصلت عبر دعوة صديق</b>\n"
                f"حصل صديقك على <b>{fmt_price(INVITE_POINTS)}</b>، "
                f"وحصلت أنت على <b>{fmt_price(STARTER_POINTS)}</b> للبداية.\n\n")

    save_state(st)

    if not await ensure_access(update, context, st, u):
        return

    await update.message.reply_text(
        note + welcome_text(u, is_owner(uid, st)), parse_mode="HTML",
        reply_markup=main_menu(is_owner(uid, st)))


async def grant_invite_async(inviter_id: int) -> None:
    st = load_state()
    u = get_user(st, inviter_id)
    try:
        await asyncio.to_thread(create_account_blocking, u)
        save_state(st)
        text = (
            "🎉 <b>دعوة جديدة!</b>\n\n"
            "بدأ صديق جديد عبر رابطك.\n"
            f"💎 +{fmt_price(INVITE_POINTS)}\n"
            "🆕 تم تجهيز حساب Overchat جديد تلقائيًا.\n"
            f"💳 رصيدك الآن: <b>{fmt_price(user_points(u))}</b>.")
    except Exception as e:
        log.warning("grant invite failed: %s", e)
        text = (
            "🎉 <b>دعوة جديدة!</b>\n\n"
            "بدأ صديق جديد عبر رابطك.\n"
            f"💎 +{fmt_price(INVITE_POINTS)}\n"
            "⚠️ تعذّر تجهيز حساب Overchat جديد تلقائيًا، "
            "ويمكنك إضافته من 👤 حسابات Overchat.")
    try:
        if app:
            await app.bot.send_message(inviter_id, text, parse_mode="HTML")
    except Exception as e:
        log.warning("grant invite notify failed: %s", e)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    st = load_state()
    context.user_data.pop("state", None)
    context.user_data.pop("admin_state", None)
    await update.message.reply_text(
        HELP_TEXT, parse_mode="HTML",
        reply_markup=main_menu(is_owner(update.effective_user.id, st)))


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in list(context.user_data):
        if key.startswith("preferred_") or key in ("state", "admin_state"):
            context.user_data.pop(key, None)
    st = load_state()
    await update.message.reply_text(
        "✅ <b>تم إلغاء العملية الحالية.</b>\n"
        "يمكنك اختيار قسم جديد من الأزرار بالأسفل.",
        parse_mode="HTML",
        reply_markup=main_menu(is_owner(update.effective_user.id, st)))


async def unsupported_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    st = load_state()
    await update.message.reply_text(
        "📎 <b>هذا النوع من الرسائل غير مدعوم.</b>\n"
        "أرسل سؤالك أو وصفك كنص مكتوب فقط، "
        "وسيتولى البوت توليد الصورة أو الفيديو.",
        parse_mode="HTML",
        reply_markup=main_menu(is_owner(update.effective_user.id, st)))


async def unknown_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "❓ <b>أمر غير معروف.</b>\n"
        "استخدم /help لعرض دليل الاستخدام، أو /start للقائمة الرئيسية.",
        parse_mode="HTML")


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    st = load_state()
    if not is_owner(update.effective_user.id, st):
        await update.message.reply_text(
            "⛔ <b>هذه اللوحة مخصصة لمالك البوت فقط.</b>", parse_mode="HTML")
        return
    await update.message.reply_text(
        "👑 <b>لوحة التحكم</b>\nاختر الإجراء المطلوب:",
        parse_mode="HTML", reply_markup=admin_panel_kb(st))


async def ensure_access_cb(query, context, st: dict, uid: int) -> bool:
    u = get_user(st, uid)
    if is_owner(uid, st):
        return True
    if u.get("banned"):
        await safe_edit(
            query,
            "⛔ <b>تم حظرك من استخدام البوت.</b>\n"
            "إذا كنت تعتقد أن هذا خطأ، تواصل مع مالك البوت.")
        return False
    s = settings(st)
    if s.get("maintenance"):
        await safe_edit(
            query,
            "🚧 <b>صيانة مؤقتة</b>\n"
            "البوت قيد التحديث حاليًا. حاول مرة أخرى بعد قليل.")
        return False
    return True


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    data = query.data or ""
    uid = update.effective_user.id
    st = load_state()
    u = get_user(st, uid)
    dev = u["device_uuid"]
    admin = is_owner(uid, st)

    if data.startswith("admin:") and not admin:
        await safe_edit(query, "⛔ <b>لا تملك صلاحية الوصول إلى هذه اللوحة.</b>")
        return

    if data.startswith(("menu:", "admin:")):
        context.user_data.pop("state", None)
    if data.startswith(("menu:", "admin:", "models:", "set:")):
        context.user_data.pop("admin_state", None)

    if data == "menu:main":
        context.user_data.pop("state", None)
        await safe_edit(query, welcome_text(u, admin), main_menu(admin))
        return

    if data == "menu:help":
        context.user_data.pop("state", None)
        await safe_edit(query, HELP_TEXT, back_menu())
        return

    if data not in ("menu:main", "menu:help") and not data.startswith("admin:"):
        if not await ensure_access_cb(query, context, st, uid):
            return

    if data in ("menu:chat", "menu:image", "menu:video"):
        kind = data.split(":")[1]
        typ = "text" if kind == "chat" else kind
        context.user_data.pop("state", None)
        selected = (context.user_data.get(f"preferred_{typ}")
                    or (u.get("prefs") or {}).get(typ))
        await show_models(query, typ, 0, dev, mode="use", selected=selected)
        return

    if data == "menu:models":
        context.user_data.pop("state", None)
        await show_categories(query, dev)
        return

    if data.startswith("models:"):
        parts = data.split(":")
        if len(parts) in (3, 4) and parts[1] in TYPE_TITLES:
            try:
                page = int(parts[2])
            except ValueError:
                page = 0
            mode = parts[3] if len(parts) == 4 and parts[3] == "set" else "use"
            selected = ((u.get("prefs") or {}).get(parts[1]) if mode == "set"
                        else context.user_data.get(f"preferred_{parts[1]}")
                        or (u.get("prefs") or {}).get(parts[1]))
            await show_models(query, parts[1], page, dev, mode=mode, selected=selected)
        return

    if data.startswith("pick:"):
        parts = data.split(":", 2)
        if len(parts) == 3 and parts[1] in TYPE_TITLES:
            await choose_model(update, context, st, u, parts[1], parts[2], as_default=False)
        return

    if data == "menu:settings":
        context.user_data.pop("state", None)
        await show_settings(query, st, u)
        return

    if data.startswith("set:"):
        parts = data.split(":")
        if len(parts) == 2 and parts[1] in TYPE_TITLES:
            selected = (u.get("prefs") or {}).get(parts[1])
            await show_models(query, parts[1], 0, dev, mode="set", selected=selected)
        return

    if data.startswith("pickset:"):
        parts = data.split(":", 2)
        if len(parts) == 3 and parts[1] in TYPE_TITLES:
            await choose_model(update, context, st, u, parts[1], parts[2], as_default=True)
        return

    if data == "prefs:reset":
        u["prefs"] = {}
        for key in list(context.user_data):
            if key.startswith("preferred_"):
                context.user_data.pop(key, None)
        save_state(st)
        await show_settings(query, st, u)
        return

    if data == "menu:invite":
        context.user_data.pop("state", None)
        await show_invite(query, uid)
        return

    if data == "menu:balance":
        context.user_data.pop("state", None)
        await show_balance(query, st, u)
        return

    if data == "menu:accounts":
        context.user_data.pop("state", None)
        await show_accounts(query, st, u)
        return

    if data.startswith("acct:"):
        await handle_accounts_cb(update, context, st, u, data)
        return

    if data.startswith("again:"):
        parts = data.split(":")
        if len(parts) == 2 and parts[1] in TYPE_TITLES:
            await start_generation_prompt(query, context, st, u, parts[1])
        return

    if data.startswith("admin:"):
        if not admin:
            await safe_edit(query, "⛔ <b>لا تملك صلاحية الوصول إلى هذه اللوحة.</b>")
            return
        await handle_admin_cb(update, context, st, u, data)


async def handle_admin_cb(update, context, st, u, data: str) -> None:
    query = update.callback_query
    s = settings(st)

    if data == "admin:panel":
        await show_admin_panel(query, st)
        return

    if data == "admin:stats":
        users = st.get("users", {})
        total = len(users)
        banned = sum(1 for x in users.values() if x.get("banned"))
        gens = sum(int(x.get("gen_count") or 0) for x in users.values())
        pts = sum(user_points(x) for x in users.values())
        await safe_edit(
            query,
            f"📊 <b>إحصائيات البوت</b>\n\n"
            f"👥 إجمالي المستخدمين: <b>{total}</b>\n"
            f"⛔ المحظورون: <b>{banned}</b>\n"
            f"⚙️ مرات التوليد: <b>{gens}</b>\n"
            f"💎 مجموع النقاط: <b>{fmt_points(pts)}</b>",
            InlineKeyboardMarkup([[btn("⬅️ لوحة التحكم", "admin:panel")]]))
        return

    if data == "admin:broadcast":
        context.user_data["admin_state"] = "broadcast"
        await safe_edit(
            query,
            "📢 <b>بث رسالة</b>\n\n"
            "أرسل نص الرسالة الآن وسيتم إرسالها لكل المستخدمين.\n"
            "اكتب /cancel للإلغاء.",
            InlineKeyboardMarkup([[btn("⬅️ لوحة التحكم", "admin:panel")]]))
        return

    if data == "admin:users":
        await show_users_list(query, st)
        return

    if data.startswith("admin:ban:"):
        try:
            target = int(data.split(":", 2)[2])
        except (IndexError, ValueError):
            return
        tu = get_user(st, target)
        tu["banned"] = not bool(tu.get("banned"))
        save_state(st)
        await show_users_list(query, st)
        return

    if data == "admin:toggle_maint":
        s["maintenance"] = not s.get("maintenance")
        save_state(st)
        await show_admin_panel(query, st)
        return

    if data == "admin:addpoints":
        context.user_data["admin_state"] = "addpoints"
        await safe_edit(
            query,
            "💎 <b>منح نقاط</b>\n\n"
            "أرسل بالصيغة التالية:\n"
            "<code>USER_ID AMOUNT</code>\n\n"
            "مثال: <code>123456789 100</code>\n"
            "استخدم رقمًا سالبًا للخصم.",
            InlineKeyboardMarkup([[btn("⬅️ لوحة التحكم", "admin:panel")]]))
        return


async def show_users_list(query, st: dict) -> None:
    users = st.get("users", {})
    rows: list[list[InlineKeyboardButton]] = []
    ordered = sorted(users.items(),
                     key=lambda kv: float((kv[1] or {}).get("created") or 0),
                     reverse=True)
    for uid, x in ordered[:20]:
        tag = "⛔" if x.get("banned") else "✅"
        label = f"{tag} {shorten(x.get('name') or uid, 24)} · {fmt_points(user_points(x))}"
        rows.append([btn(label, f"admin:ban:{uid}",
                         style="success" if x.get("banned") else "danger")])
    rows.append([btn("⬅️ لوحة التحكم", "admin:panel")])
    note = "\n(تظهر أحدث 20 مستخدمًا)" if len(users) > 20 else ""
    await safe_edit(
        query,
        "👥 <b>المستخدمون</b>\n"
        "اضغط على المستخدم لحظره أو فك الحظر عنه." + note,
        InlineKeyboardMarkup(rows))


def admin_panel_kb(st: dict) -> InlineKeyboardMarkup:
    s = settings(st)
    return InlineKeyboardMarkup([
        [btn("📊 الإحصائيات", "admin:stats", style="primary")],
        [btn("📢 بث رسالة", "admin:broadcast", style="danger")],
        [btn("👥 المستخدمون", "admin:users", style="primary")],
        [btn(f"🚧 الصيانة: {'مفعّلة' if s.get('maintenance') else 'متوقفة'}",
             "admin:toggle_maint",
             style="danger" if s.get("maintenance") else "success")],
        [btn("➕ منح نقاط", "admin:addpoints", style="success")],
        [btn("⬅️ القائمة الرئيسية", "menu:main")],
    ])


async def show_admin_panel(query, st: dict) -> None:
    s = settings(st)
    users = st.get("users", {})
    total = len(users)
    banned = sum(1 for x in users.values() if x.get("banned"))
    gens = sum(int(x.get("gen_count") or 0) for x in users.values())
    pts = sum(user_points(x) for x in users.values())
    await safe_edit(
        query,
        f"👑 <b>لوحة التحكم</b>\n\n"
        f"👥 المستخدمون: <b>{total}</b>\n"
        f"⛔ المحظورون: <b>{banned}</b>\n"
        f"⚙️ مرات التوليد: <b>{gens}</b>\n"
        f"💎 مجموع النقاط: <b>{fmt_points(pts)}</b>\n\n"
        f"🚧 الصيانة: <b>{'مفعّلة' if s.get('maintenance') else 'متوقفة'}</b>",
        admin_panel_kb(st))


async def show_categories(query, device_uuid: str = "") -> None:
    if not cached_personas() and device_uuid:
        await safe_edit(query, "⏳ <b>جارٍ تحميل مكتبة النماذج...</b>")
        try:
            await asyncio.to_thread(oc.personas, device_uuid)
        except Exception as e:
            log.warning("تعذر تحميل فئات النماذج: %s", e)
    text, image, video = (model_count(t) for t in ("text", "image", "video"))
    rows = [
        [btn(f"💬 نماذج المحادثة ({text})", "models:text:0", style="primary")],
        [btn(f"🎨 نماذج الصور ({image})", "models:image:0", style="success")],
        [btn(f"🎬 نماذج الفيديو ({video})", "models:video:0", style="danger")],
        [btn("⬅️ القائمة الرئيسية", "menu:main")],
    ]
    await safe_edit(
        query,
        "📚 <b>مكتبة النماذج</b>\n\n"
        "اختر الفئة التي تريد استعراض نماذجها.\n"
        "💎 سعر كل نموذج ظاهر أمامه ويُخصم عند الطلب فقط.",
        InlineKeyboardMarkup(rows))


async def start_generation_prompt(query, context, st: dict, u: dict, typ: str) -> None:
    if typ not in TYPE_TITLES:
        return
    pid = (context.user_data.get(f"preferred_{typ}")
           or (u.get("prefs") or {}).get(typ)
           or DEFAULT_PERSONAS[typ])
    pid = resolve_model_id(typ, pid, u)
    persona = oc.find_persona(pid)
    if not persona:
        await safe_edit(
            query,
            "⚠️ <b>النموذج المحدد لم يعد متاحًا.</b>\n"
            "اختر نموذجًا آخر من القائمة.",
            InlineKeyboardMarkup([
                [btn("📚 اختيار نموذج", f"models:{typ}:0", style="primary")],
                [btn("⬅️ القائمة الرئيسية", "menu:main")],
            ]))
        return

    context.user_data[f"preferred_{typ}"] = pid
    target = "chat" if typ == "text" else typ
    context.user_data["state"] = f"await_{target}"

    name = model_display_name(persona)
    price = _price(persona)
    description = model_description(persona)
    points = user_points(u)
    heading = {
        "text": "💬 <b>محادثة جديدة</b>",
        "image": "🎨 <b>توليد صورة</b>",
        "video": "🎬 <b>توليد فيديو</b>",
    }[typ]

    lines = [
        heading,
        f"النموذج: <b>{esc(name)}</b>",
    ]
    owner = is_owner(u.get("uid") or 0, st)
    lines.append(
        f"💎 التكلفة: <b>{'مجانًا' if owner else fmt_price(price)}</b> · "
        f"رصيدك: <b>{fmt_price(points)}</b>")
    if description:
        lines.append(f"<i>{esc(description)}</i>")
    if owner:
        lines.append("👑 الاستخدام مجاني لك كمالك للبوت.")
    elif points < price:
        lines.append(
            f"⚠️ رصيدك أقل من تكلفة هذا النموذج. "
            f"ادعُ صديقًا من 🎁 أو اختر نموذجًا أرخص.")
    if typ == "video":
        lines.append("⏳ قد يستغرق توليد الفيديو من دقيقة إلى عدة دقائق.")
    lines.extend(["", TYPE_PROMPTS[typ], TYPE_EXAMPLES[typ], "",
                  "💡 يمكنك تغيير النموذج من الزر بالأسفل، أو إرسال /cancel."])

    await safe_edit(
        query,
        "\n".join(lines),
        InlineKeyboardMarkup([
            [btn("🎛️ تغيير النموذج", f"models:{typ}:0", style="primary")],
            [btn("⬅️ القائمة الرئيسية", "menu:main")],
        ]))


async def choose_model(update, context, st, u, typ, pid, as_default) -> None:
    if typ not in TYPE_TITLES:
        return
    pid = resolve_model_id(typ, pid, u)
    persona = oc.find_persona(pid)
    if not persona:
        await safe_edit(
            update.callback_query,
            "⚠️ <b>هذا النموذج غير متاح حاليًا.</b>\n"
            "جرّب نموذجًا آخر من القائمة.",
            InlineKeyboardMarkup([
                [btn("📚 العودة للنماذج", f"models:{typ}:0", style="primary")],
                [btn("⬅️ القائمة الرئيسية", "menu:main")],
            ]))
        return

    if as_default:
        u.setdefault("prefs", {})[typ] = pid
        save_state(st)
        await show_settings(update.callback_query, st, u)
        return

    context.user_data[f"preferred_{typ}"] = pid
    await start_generation_prompt(update.callback_query, context, st, u, typ)


async def show_models(query, typ: str, page: int, device_uuid: str,
                      mode: str = "use", selected: str | None = None) -> None:
    if typ not in TYPE_TITLES:
        return
    current = resolve_model_id(typ, selected or DEFAULT_PERSONAS.get(typ))
    if not personas_fresh():
        await safe_edit(query, "⏳ <b>جارٍ تحميل النماذج...</b>")
    try:
        items = await asyncio.to_thread(oc.personas, device_uuid)
    except Exception as e:
        log.warning("تعذر تحميل النماذج: %s", e)
        items = cached_personas()

    models = curated_personas(typ, items)
    if not models:
        await safe_edit(
            query,
            "⚠️ <b>تعذر تحميل النماذج</b>\n\n"
            "حدث خطأ مؤقت أثناء جلب قائمة النماذج. حاول مرة أخرى.",
            InlineKeyboardMarkup([
                [btn("🔄 إعادة المحاولة", f"models:{typ}:0:{mode}",
                     style="success")],
                [btn("⬅️ القائمة الرئيسية", "menu:main")],
            ]))
        return

    per = 6
    pages = max(1, (len(models) + per - 1) // per)
    page = max(0, min(page, pages - 1))
    rows: list[list[InlineKeyboardButton]] = []
    for p in models[page * per:(page + 1) * per]:
        pid = str(p.get("id"))
        selected_now = pid == current
        mark = "✅ " if selected_now else ""
        rows.append([
            btn(mark + model_button_label(p),
                f"{'pickset' if mode == 'set' else 'pick'}:{typ}:{pid}",
                style="success" if selected_now else "primary")
        ])

    nav = []
    if page > 0:
        nav.append(btn("◀ السابق", f"models:{typ}:{page - 1}:{mode}",
                       style="primary"))
    nav.append(btn(f"صفحة {page + 1}/{pages}", f"models:{typ}:{page}:{mode}",
                   style="primary", disabled=True))
    if page < pages - 1:
        nav.append(btn("التالي ▶", f"models:{typ}:{page + 1}:{mode}",
                       style="primary"))
    rows.append(nav)
    rows.append([btn("⬅️ رجوع", "menu:settings" if mode == "set" else "menu:models")])

    title = TYPE_TITLES[typ]
    if mode == "set":
        head = (
            f"⭐ <b>اختر النموذج الافتراضي — {title}</b>\n"
            "سيُستخدم تلقائيًا عند فتح هذا القسم."
        )
    else:
        head = (
            f"📚 <b>نماذج {title}</b>\n"
            "اختر النموذج المناسب — السعر ظاهر أمام كل خيار."
        )
    await safe_edit(
        query,
        f"{head}\n"
        f"عدد النماذج: <b>{len(models)}</b> · صفحة <b>{page + 1}/{pages}</b>\n"
        f"💎 السعر يُخصم من نقاطك عند كل طلب.",
        InlineKeyboardMarkup(rows))


async def show_settings(query, st: dict, u: dict) -> None:
    if not cached_personas():
        await safe_edit(query, "⏳ <b>جارٍ تجهيز الإعدادات...</b>")
        try:
            await asyncio.to_thread(oc.personas, u.get("device_uuid") or str(uuid.uuid4()))
        except Exception as e:
            log.warning("تعذر تحميل النماذج في الإعدادات: %s", e)
    prefs = u.setdefault("prefs", {})
    changed = False
    for typ in ("text", "image", "video"):
        old = prefs.get(typ)
        if old:
            new = resolve_model_id(typ, old, u)
            if new and new != old:
                prefs[typ] = new
                changed = True
    if changed:
        save_state(st)

    def label(typ: str, default_suffix: bool = True) -> str:
        pid = prefs.get(typ)
        is_default = not pid
        pid = pid or DEFAULT_PERSONAS[typ]
        persona = oc.find_persona(pid)
        name = model_display_name(persona) if persona else "—"
        return f"{name} (افتراضي)" if (is_default and default_suffix) else name

    rows = [
        [btn(f"💬 المحادثة: {shorten(label('text', False), 20)}", "set:text",
             style="primary")],
        [btn(f"🎨 الصور: {shorten(label('image', False), 20)}", "set:image",
             style="success")],
        [btn(f"🎬 الفيديو: {shorten(label('video', False), 20)}", "set:video",
             style="danger")],
        [btn("♻️ إعادة ضبط الافتراضيات", "prefs:reset", style="danger")],
        [btn("⬅️ القائمة الرئيسية", "menu:main")],
    ]
    await safe_edit(
        query,
        "⚙️ <b>الإعدادات</b>\n\n"
        "النماذج الافتراضية التي ستُستخدم تلقائيًا:\n\n"
        f"💬 المحادثة: <b>{esc(label('text'))}</b>\n"
        f"🎨 الصور: <b>{esc(label('image'))}</b>\n"
        f"🎬 الفيديو: <b>{esc(label('video'))}</b>\n\n"
        "اختر القسم لتغيير نموذجه الافتراضي.",
        InlineKeyboardMarkup(rows))


async def show_accounts(query, st: dict, u: dict) -> None:
    accs = u.get("accounts") or []
    rows: list[list[InlineKeyboardButton]] = []
    for i, acc in enumerate(accs):
        mark = "● " if i == u.get("active", 0) else "○ "
        email = str(acc.get("email") or f"حساب {i + 1}")
        extra = " · منتهي" if acc.get("exhaustedAt") else ""
        balance = acc.get("balance")
        if balance is not None and not acc.get("exhaustedAt"):
            extra += f" · {fmt_points(balance)} Takos"
        rows.append([btn(shorten(f"{mark}{email}{extra}", 46), f"acct:use:{i}",
                         style="success" if i == u.get("active", 0) else "primary")])
    rows.append([btn("⬅️ القائمة الرئيسية", "menu:main")])

    active = active_account(u)
    active_email = esc(active.get("email") or "—") if active else "—"
    text = (
        "👤 <b>حسابات Overchat</b>\n\n"
        f"عدد الحسابات: <b>{len(accs)}</b>\n"
        f"الحساب النشط: <code>{active_email}</code>\n\n"
        "اختر حسابًا لتفعيله.\n"
        "💡 نقاط البوت منفصلة عن رصيد Takos لكل حساب.\n"
        "⚙️ عند نفاد رصيد الحساب يتم التبديل تلقائيًا لحساب آخر."
    )
    await safe_edit(query, text, InlineKeyboardMarkup(rows))


async def handle_accounts_cb(update, context, st, u, data: str) -> None:
    query = update.callback_query
    accs = u.get("accounts") or []

    if data.startswith("acct:use:"):
        try:
            index = int(data.split(":", 2)[2])
        except (IndexError, ValueError):
            return
        if 0 <= index < len(accs):
            u["active"] = index
            save_state(st)
            await show_accounts(query, st, u)
        return

    if data == "acct:new":
        await safe_edit(
            query,
            "⏳ <b>جارٍ إنشاء حساب Overchat جديد...</b>\n\n"
            "قد يستغرق هذا بعض الوقت. لا تغلق المحادثة.",
            back_menu())
        try:
            await asyncio.to_thread(create_account_blocking, u)
            save_state(st)
            await show_accounts(query, st, u)
        except Exception as e:
            log.exception("account create failed: %s", e)
            await safe_edit(
                query,
                "⚠️ <b>تعذر إنشاء حساب جديد</b>\n\n"
                "حدث خطأ مؤقت. حاول مرة أخرى بعد قليل، "
                "أو تواصل مع مالك البوت.",
                InlineKeyboardMarkup([
                    [btn("⬅️ القائمة الرئيسية", "menu:main")],
                ]))


async def show_invite(query, uid: int) -> None:
    bot_username = (app.bot.username if app and app.bot else None) or "bot"
    link = f"https://t.me/{bot_username}?start=ref_{uid}"
    u = get_user(load_state(), uid)
    n = len(u.get("invites") or [])
    share_text = "جرّب بوت Overchat الذكي للمحادثة والصور والفيديو:"
    share_url = (
        "https://t.me/share/url"
        f"?url={quote(link, safe='')}&text={quote(share_text, safe='')}"
    )
    await safe_edit(
        query,
        "🎁 <b>دعوة الأصدقاء</b>\n\n"
        "شارك رابطك — كل صديق جديد يبدأ عبره يمنحك "
        f"<b>{fmt_price(INVITE_POINTS)}</b> وحساب Overchat جديد.\n\n"
        f"🔗 رابطك:\n<code>{esc(link)}</code>\n\n"
        f"📨 عدد دعواتك: <b>{n}</b>\n"
        f"💎 نقاط الدعوات: <b>{fmt_points(n * INVITE_POINTS)}</b>",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 مشاركة الرابط", url=share_url,
                                  style="success")],
            [btn("⬅️ القائمة الرئيسية", "menu:main")],
        ]))


async def show_balance(query, st: dict, u: dict) -> None:
    acc = active_account(u)
    takos: Any = "—"
    plan = "—"
    if acc:
        await safe_edit(query, "⏳ <b>جارٍ جلب الرصيد...</b>")
        try:
            me = await asyncio.to_thread(oc.me, u["device_uuid"], acc["accessToken"])
            takos = me.get("takosCoin", 0)
            subscription = me.get("subscription") or {}
            plan = subscription.get("planName") or "مجاني"
        except Exception as e:
            log.warning("تعذر جلب رصيد Overchat: %s", e)
            takos = acc.get("balance", "—")
            plan = "غير متاح"
    active = active_account(u)
    email = esc(active.get("email") or "—") if active else "لا يوجد حساب"
    takos_text = fmt_points(takos) if isinstance(takos, (int, float)) else "—"
    await safe_edit(
        query,
        "💰 <b>رصيدك</b>\n\n"
        f"💎 نقاط البوت: <b>{fmt_price(user_points(u))}</b>\n"
        f"🪙 رصيد Overchat: <b>{takos_text}</b> Takos\n"
        f"📦 الخطة: <b>{esc(plan)}</b>\n"
        f"👤 الحسابات: <b>{len(u.get('accounts') or [])}</b> · "
        f"النشط: <code>{email}</code>\n\n"
        "💡 عند نفاد رصيد الحساب يتم التبديل تلقائيًا.\n"
        f"🎁 كل دعوة صديق = <b>{fmt_price(INVITE_POINTS)}</b>.",
        InlineKeyboardMarkup([
            [btn("🎁 دعوة الأصدقاء", "menu:invite", style="success"),
             btn("👤 الحسابات", "menu:accounts", style="primary")],
            [btn("⬅️ القائمة الرئيسية", "menu:main")],
        ]))


_seen_msgs: set[str] = set()
_gen_locks: dict[int, asyncio.Lock] = {}


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    key = f"{update.effective_chat.id}:{update.message.message_id}"
    if key in _seen_msgs:
        return
    _seen_msgs.add(key)
    if len(_seen_msgs) > 5000:
        _seen_msgs.clear()

    st = load_state()
    u = get_user(st, uid)
    admin = is_owner(uid, st)
    prompt = (update.message.text or "").strip()
    if not prompt:
        return

    astate = context.user_data.get("admin_state")
    if astate:
        context.user_data.pop("admin_state", None)
        if not admin:
            return
        if astate == "broadcast":
            ok, fail = await broadcast_all(context.bot, prompt)
            if ok == 0 and fail == 0:
                result = "📢 لا يوجد مستخدمون لإرسال الرسالة إليهم."
            else:
                result = (
                    "📢 <b>اكتمل البث</b>\n\n"
                    f"✅ تم الإرسال: <b>{ok}</b>\n"
                    f"❌ فشل الإرسال: <b>{fail}</b>")
            await update.message.reply_text(
                result, parse_mode="HTML", reply_markup=main_menu(admin))
            return
        if astate == "addpoints":
            parts = prompt.replace("،", " ").split()
            try:
                if len(parts) < 2:
                    raise ValueError
                target = int(parts[0])
                amount = float(parts[1])
            except ValueError:
                context.user_data["admin_state"] = "addpoints"
                await update.message.reply_text(
                    "⚠️ <b>صيغة غير صحيحة.</b>\n"
                    "أرسل: <code>USER_ID AMOUNT</code>\n"
                    "مثال: <code>123456789 100</code>",
                    parse_mode="HTML", reply_markup=main_menu(admin))
                return
            tu = get_user(st, target)
            add_points(tu, amount)
            save_state(st)
            action = "منح" if amount >= 0 else "خصم"
            await update.message.reply_text(
                f"💎 <b>تم {action} النقاط</b>\n\n"
                f"المستخدم: <code>{target}</code>\n"
                f"المبلغ: <b>{fmt_price(abs(amount))}</b>\n"
                f"الرصيد الجديد: <b>{fmt_price(user_points(tu))}</b>.",
                parse_mode="HTML", reply_markup=main_menu(admin))
            return
        return

    if not u.get("started"):
        if u.get("banned") and not admin:
            await update.message.reply_text(
                "⛔ <b>تم حظرك من استخدام البوت.</b>", parse_mode="HTML")
            return
        u["started"] = True
        if update.effective_user.first_name:
            u["name"] = update.effective_user.first_name
        add_points(u, STARTER_POINTS)
        save_state(st)
        if not await ensure_access(update, context, st, u):
            return
        await update.message.reply_text(
            welcome_text(u, admin), parse_mode="HTML", reply_markup=main_menu(admin))
        return

    if not admin:
        if u.get("banned"):
            await update.message.reply_text(
                "⛔ <b>تم حظرك من استخدام البوت.</b>", parse_mode="HTML")
            return
        s = settings(st)
        if s.get("maintenance"):
            await update.message.reply_text(
                "🚧 <b>صيانة مؤقتة</b>\n"
                "البوت قيد التحديث حاليًا. حاول مرة أخرى بعد قليل.",
                parse_mode="HTML")
            return

    state = context.user_data.get("state")
    if not state:
        await update.message.reply_text(
            "👋 اختر القسم الذي تريده من القائمة بالأسفل، "
            "أو أرسل /help لعرض الدليل.",
            parse_mode="HTML", reply_markup=main_menu(admin))
        return
    if state not in ("await_chat", "await_image", "await_video"):
        context.user_data.pop("state", None)
        await update.message.reply_text(
            "تمت إعادة ضبط الجلسة. اختر القسم من جديد.",
            reply_markup=main_menu(admin))
        return

    lock = _gen_locks.setdefault(uid, asyncio.Lock())
    if lock.locked():
        await update.message.reply_text(
            "⏳ <b>لديك طلب قيد التنفيذ بالفعل.</b>\n"
            "انتظر حتى ينتهي، أو أرسل /cancel لإلغاء الوضع الحالي.",
            parse_mode="HTML")
        return

    async with lock:
        action = ChatAction.TYPING
        if state == "await_image":
            action = ChatAction.UPLOAD_PHOTO
        elif state == "await_video":
            action = ChatAction.RECORD_VIDEO
        try:
            await context.bot.send_chat_action(update.effective_chat.id, action)
        except Exception:
            pass

        try:
            if state == "await_chat":
                await do_chat(update, context, st, u, prompt)
            elif state == "await_image":
                await do_image(update, context, st, u, prompt)
            elif state == "await_video":
                await do_video(update, context, st, u, prompt)
        except OverchatError as e:
            if is_quota_error(e):
                try:
                    await asyncio.to_thread(rotate_blocking, st, u)
                    save_state(st)
                    if state == "await_chat":
                        await do_chat(update, context, st, u, prompt)
                    elif state == "await_image":
                        await do_image(update, context, st, u, prompt)
                    elif state == "await_video":
                        await do_video(update, context, st, u, prompt)
                except Exception as retry_error:
                    log.exception("recovery failed: %s", retry_error)
                    await update.message.reply_text(
                        "⏳ <b>الخدمة تحتاج لحظة لتجهيز طلبك.</b>\n"
                        "أعد المحاولة بعد قليل.",
                        parse_mode="HTML", reply_markup=main_menu(admin))
            else:
                log.warning("generation error: %s", e)
                await update.message.reply_text(
                    f"⚠️ {friendly_error(e)}",
                    parse_mode="HTML", reply_markup=main_menu(admin))
        except Exception as e:
            log.exception("handler error: %s", e)
            await update.message.reply_text(
                f"⚠️ {friendly_error(e)}",
                parse_mode="HTML", reply_markup=main_menu(admin))
        finally:
            if context.user_data.get("state") == state:
                context.user_data.pop("state", None)


def ensure_personas(u: dict) -> None:
    if not cached_personas():
        oc.personas(u["device_uuid"])


def cost_of(u: dict, persona_id: str) -> int:
    ensure_personas(u)
    persona = oc.find_persona(persona_id) or {}
    return _price(persona)


def active_model(typ: str, u: dict, context) -> tuple[str, dict] | None:
    pid = (context.user_data.get(f"preferred_{typ}")
           or (u.get("prefs") or {}).get(typ)
           or DEFAULT_PERSONAS[typ])
    pid = resolve_model_id(typ, pid, u)
    persona = oc.find_persona(pid)
    if not persona:
        return None
    context.user_data[f"preferred_{typ}"] = pid
    return pid, persona


def friendly_error(error: Exception) -> str:
    if isinstance(error, OverchatError):
        if is_quota_error(error):
            return ("<b>نفد رصيد الحساب.</b>\n"
                    "اختر نموذجًا أرخص أو أعد المحاولة لاحقًا.")
        if error.status in (401, 403):
            return ("<b>تعذر الوصول إلى النموذج أو الحساب.</b>\n"
                    "جرّب نموذجًا آخر، أو أعد المحاولة لاحقًا.")
        if error.status == 429:
            return ("<b>الخدمة مزدحمة حاليًا.</b>\n"
                    "انتظر دقيقة ثم أعد المحاولة.")
        if error.status >= 500:
            return ("<b>الخدمة تواجه عطلًا مؤقتًا.</b>\n"
                    "أعد المحاولة بعد قليل.")
        text = str(error).lower()
        if "timeout" in text or "timed out" in text:
            return ("<b>انتهت مهلة الانتظار.</b>\n"
                    "حاول مرة أخرى، أو اختر نموذجًا أسرع.")
        if "no url" in text or "no workflow" in text:
            return ("<b>لم تكتمل عملية التوليد.</b>\n"
                    "أعد المحاولة بعد قليل.")
        if "empty response" in text:
            return ("<b>لم يصل رد من النموذج.</b>\n"
                    "حاول مرة أخرى أو غيّر النموذج.")
        return ("<b>تعذر إكمال الطلب.</b>\n"
                "أعد المحاولة، وإذا استمرت المشكلة جرّب نموذجًا آخر.")
    if isinstance(error, TimeoutError):
        return ("<b>انتهت مهلة الانتظار.</b>\n"
                "أعد المحاولة بعد قليل.")
    if isinstance(error, requests.RequestException):
        return ("<b>تعذر الاتصال بالخدمة.</b>\n"
                "تحقق من اتصالك ثم أعد المحاولة.")
    return ("<b>حدث خطأ غير متوقع.</b>\n"
            "أعد المحاولة، وإذا استمرت المشكلة تواصل مع مالك البوت.")


def _invoke(fn, device_uuid: str, token: str, tries: int = 3):
    """ينفّذ طلب التوليد مع إعادة محاولة عند انقطاع الاتصال."""
    last: Exception | None = None
    for i in range(tries):
        try:
            return fn(device_uuid, token)
        except requests.RequestException as e:
            last = e
            log.warning("تعذّر الاتصال بالخدمة (محاولة %s/%s): %s", i + 1, tries, e)
            time.sleep(2 * (i + 1))
    raise last


async def _run_smart(update, st, u, fn, cost: int) -> Any:
    """يدفع الطلب من حساب رصيده >= التكلفة، وإلا ينشئ حسابًا جديدًا."""
    acc = await asyncio.to_thread(pick_account, u, cost)
    save_state(st)
    try:
        result = await asyncio.to_thread(_invoke, fn, u["device_uuid"], acc["accessToken"])
    except OverchatError as e:
        if is_quota_error(e):
            acc["balance"] = 0
            acc["exhaustedAt"] = time.time()
            save_state(st)
            acc = await asyncio.to_thread(pick_account, u, cost)
            result = await asyncio.to_thread(_invoke, fn, u["device_uuid"], acc["accessToken"])
        elif e.status in (500, 502, 503, 504) or "couldn't complete" in str(e).lower():
            log.warning("خطأ provider مؤقت (%s) — إعادة المحاولة", e)
            await asyncio.sleep(3)
            try:
                result = await asyncio.to_thread(_invoke, fn, u["device_uuid"], acc["accessToken"])
            except OverchatError:
                acc = await asyncio.to_thread(pick_account, u, cost)
                result = await asyncio.to_thread(_invoke, fn, u["device_uuid"], acc["accessToken"])
        else:
            raise
    try:
        with _STATE_LOCK:
            acc["balance"] = max(0, int(acc.get("balance") or cost) - cost)
            acc["balanceAt"] = time.time()
        save_state(st)
    except Exception:
        pass
    return result


async def _charge_gate(update, st, u, cost) -> bool:
    if is_owner(u.get("uid") or update.effective_user.id, st):
        return True
    if user_points(u) < cost:
        await update.message.reply_text(
            "💎 <b>نقاطك لا تكفي</b>\n\n"
            f"سعر الطلب: <b>{fmt_price(cost)}</b>\n"
            f"رصيدك الحالي: <b>{fmt_price(user_points(u))}</b>\n\n"
            "ادعُ صديقًا من 🎁 أو اختر نموذجًا أرخص.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [btn("🎁 دعوة الأصدقاء", "menu:invite")],
                [btn("📚 اختيار نموذج أرخص", "menu:models")],
                [btn("⬅️ القائمة الرئيسية", "menu:main")],
            ]))
        return False
    return True


def _cost_to_charge(u, st, cost) -> float:
    return 0.0 if is_owner(u.get("uid"), st) else float(cost)


def _charged_line(u, st, cost, pending: bool = False) -> str:
    charged = _cost_to_charge(u, st, cost)
    if charged <= 0:
        return "👑 مجانًا (مالك البوت)"
    remaining = user_points(u) - charged if pending else user_points(u)
    return (
        f"💎 {fmt_price(charged)} · "
        f"المتبقي: <b>{fmt_price(max(0.0, remaining))}</b>")


async def do_chat(update, context, st, u, prompt: str) -> None:
    active = active_model("text", u, context)
    if not active:
        await update.message.reply_text(
            "⚠️ <b>النموذج المحدد لم يعد متاحًا.</b>\n"
            "اختر نموذجًا آخر من 📚 النماذج.",
            parse_mode="HTML", reply_markup=main_menu(is_owner(update.effective_user.id, st)))
        return
    pid, persona = active
    cost = _price(persona)
    if not await _charge_gate(update, st, u, cost):
        return
    text = await _run_smart(
        update, st, u, lambda dev, tok: oc.chat(dev, tok, pid, prompt), cost)
    chat_id = update.effective_chat.id
    await send_long(context.bot, chat_id, text)
    charge_points(u, _cost_to_charge(u, st, cost))
    u["gen_count"] = int(u.get("gen_count") or 0) + 1
    save_state(st)
    await context.bot.send_message(
        chat_id,
        f"✅ <b>{esc(model_display_name(persona))}</b>\n{_charged_line(u, st, cost)}",
        parse_mode="HTML", reply_markup=result_kb("text"))


async def do_image(update, context, st, u, prompt: str) -> None:
    active = active_model("image", u, context)
    if not active:
        await update.message.reply_text(
            "⚠️ <b>نموذج الصور المحدد غير متاح.</b>\n"
            "اختر نموذجًا آخر من 📚 النماذج.",
            parse_mode="HTML", reply_markup=main_menu(is_owner(update.effective_user.id, st)))
        return
    pid, persona = active
    cost = _price(persona)
    if not await _charge_gate(update, st, u, cost):
        return
    await update.message.reply_text(
        "🎨 <b>جارٍ توليد الصورة...</b>\n"
        f"النموذج: <b>{esc(model_display_name(persona))}</b> · "
        f"التكلفة: <b>{fmt_price(cost)}</b>",
        parse_mode="HTML")
    url = await _run_smart(
        update, st, u, lambda dev, tok: oc.image(dev, tok, pid, prompt), cost)
    raw = await asyncio.to_thread(download, url)
    data = compress_image(raw)
    caption = (
        f"🎨 <b>{esc(model_display_name(persona))}</b>\n"
        f"{_charged_line(u, st, cost, pending=True)}")
    await _send_with_retry(
        context.bot, update.effective_chat.id, "photo", io.BytesIO(data),
        caption=caption, keyboard=result_kb("image"))
    charge_points(u, _cost_to_charge(u, st, cost))
    u["gen_count"] = int(u.get("gen_count") or 0) + 1
    save_state(st)


async def do_video(update, context, st, u, prompt: str) -> None:
    active = active_model("video", u, context)
    if not active:
        await update.message.reply_text(
            "⚠️ <b>نموذج الفيديو المحدد غير متاح.</b>\n"
            "اختر نموذجًا آخر من 📚 النماذج.",
            parse_mode="HTML", reply_markup=main_menu(is_owner(update.effective_user.id, st)))
        return
    pid, persona = active
    cost = _price(persona)
    if not await _charge_gate(update, st, u, cost):
        return
    await update.message.reply_text(
        "🎬 <b>جارٍ توليد الفيديو...</b>\n"
        f"النموذج: <b>{esc(model_display_name(persona))}</b> · "
        f"التكلفة: <b>{fmt_price(cost)}</b>\n"
        "⏳ قد يستغرق من دقيقة إلى عدة دقائق. سنرسله فور جاهزيته.",
        parse_mode="HTML")
    url = await _run_smart(
        update, st, u, lambda dev, tok: oc.video(dev, tok, pid, prompt), cost)
    data = await asyncio.to_thread(download, url)
    caption = (
        f"🎬 <b>{esc(model_display_name(persona))}</b>\n"
        f"{_charged_line(u, st, cost, pending=True)}")
    await _send_with_retry(
        context.bot, update.effective_chat.id, "video", io.BytesIO(data),
        caption=caption, keyboard=result_kb("video"))
    charge_points(u, _cost_to_charge(u, st, cost))
    u["gen_count"] = int(u.get("gen_count") or 0) + 1
    save_state(st)


async def _send_with_retry(bot, chat_id: int, kind: str, fileobj,
                           caption: str | None = None, keyboard=None,
                           attempts: int = 3) -> None:
    last: Exception | None = None
    for i in range(attempts):
        try:
            fileobj.seek(0)
            if kind == "photo":
                await bot.send_photo(
                    chat_id, photo=fileobj, caption=caption,
                    parse_mode="HTML" if caption else None,
                    reply_markup=keyboard)
            else:
                await bot.send_video(
                    chat_id, video=fileobj, caption=caption,
                    parse_mode="HTML" if caption else None,
                    reply_markup=keyboard)
            return
        except Exception as e:
            last = e
            if i < attempts - 1:
                await asyncio.sleep(2)

    fileobj.seek(0)
    if kind == "photo":
        await bot.send_photo(chat_id, photo=fileobj)
    else:
        await bot.send_video(chat_id, video=fileobj)
    if caption:
        await bot.send_message(
            chat_id, caption, parse_mode="HTML", reply_markup=keyboard)
    elif last:
        log.warning("send retry recovered without caption: %s", last)


def load_token() -> str:
    tok = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if tok:
        return tok
    cfg = load_json(TOKEN_PATH, {})
    if isinstance(cfg, dict) and cfg.get("token"):
        return str(cfg["token"]).strip()
    return DEFAULT_TELEGRAM_TOKEN


async def on_error(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("خطأ في معالجة تحديث: %s", context.error, exc_info=context.error)
    try:
        if update is not None and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ <b>حدث خطأ غير متوقع.</b>\n"
                "أعد المحاولة، وإذا استمرت المشكلة أرسل /cancel ثم ابدأ من جديد.",
                parse_mode="HTML")
    except Exception:
        pass


async def warm_personas() -> None:
    if cached_personas():
        return
    try:
        await asyncio.to_thread(oc.personas, str(uuid.uuid4()))
    except Exception as e:
        log.warning("تعذر تحميل كتالوج النماذج عند البدء: %s", e)


async def post_init(application: Application) -> None:
    """تجهيز أوامر البوت وتحميل كتالوج النماذج قبل استقبال المستخدمين."""
    try:
        await application.bot.set_my_name(BOT_DISPLAY_NAME)
    except Exception as e:
        log.warning("تعذر ضبط اسم البوت: %s", e)
    try:
        await application.bot.set_my_commands([
            BotCommand("start", "بدء البوت والقائمة الرئيسية"),
            BotCommand("help", "دليل الاستخدام"),
            BotCommand("cancel", "إلغاء العملية الحالية"),
        ])
    except Exception as e:
        log.warning("تعذر ضبط أوامر البوت: %s", e)
    if not cached_personas():
        spawn(warm_personas())


def build_app() -> Application:
    req = HTTPXRequest(read_timeout=60, write_timeout=60, connect_timeout=20,
                       media_write_timeout=180)
    application = (
        Application.builder()
        .token(load_token())
        .request(req)
        .get_updates_request(HTTPXRequest(read_timeout=60, write_timeout=60,
                                          connect_timeout=20, media_write_timeout=180))
        .concurrent_updates(True)
        .post_init(post_init)
        .build()
    )
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("cancel", cancel_cmd))
    application.add_handler(CommandHandler("admin", admin_cmd))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_handler(MessageHandler(filters.ATTACHMENT & ~filters.COMMAND,
                                           unsupported_msg))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_cmd))
    application.add_error_handler(on_error)
    return application


def main() -> None:
    global app
    delay = 3
    while True:
        try:
            app = build_app()
            log.info("البوت يعمل... ( polling )")
            app.run_polling(allowed_updates=Update.ALL_TYPES)
            return
        except Exception as e:
            log.warning("انقطع الاتصال (%s) — إعادة المحاولة بعد %s ثانية...", e, delay)
            time.sleep(delay)
            delay = min(delay * 2, 60)


if __name__ == "__main__":
    main()
