"""
ALBRAZIL WORM - Smart Router
فاحص الطلب + اختيار ودمج الموديلات
"""

import httpx
import os
from typing import List, Dict

# هتحط الـ API Key بتاع OpenRouter هنا أو في متغير بيئة
OPENROUTER_API_KEY = os.getenv("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", "")

# موديلات مقترحة (هتتحدث حسب المتاح)
MODELS = {
    "coding": ["nvidia/nemotron-3-super-120b-a12b:free", "thinkingmachines/inkling:free"],
    "analysis": ["nvidia/nemotron-3-super-120b-a12b:free", "google/gemma-4-31b-it:free"],
    "uncensored": ["thinkingmachines/inkling:free", "nvidia/nemotron-3-super-120b-a12b:free"],
    "general": ["nvidia/nemotron-3-super-120b-a12b:free"]
}


async def analyze_request(messages: List[Dict]) -> str:
    """فاحص بسيط من أول الرسايل"""
    text = " ".join([m.get("content", "") for m in messages[-3:]]).lower()

    if any(word in text for word in ["كود", "برمجة", "سكربت", "python", "code", "function"]):
        return "coding"
    elif any(word in text for word in ["حلل", "تحليل", "افحص", "مميزات", "عيوب", "analyze"]):
        return "analysis"
    elif any(word in text for word in ["حر", "بدون قيود", "uncensored", "jailbreak"]):
        return "uncensored"
    else:
        return "general"


async def call_model(model: str, messages: List[Dict], system_prompt: str) -> str:
    """استدعاء موديل واحد من OpenRouter"""
    if not OPENROUTER_API_KEY:
        return "خطأ: مفيش API Key"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://albrazil-worm.railway.app",
        "X-Title": "ALBRAZIL WORM"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages
        ]
    }

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            )
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"خطأ في الموديل {model}: {str(e)}"


async def smart_response(messages: List[Dict], custom_style: str = "") -> str:
    """
    الرد الذكي:
    1. يفحص الطلب
    2. يختار موديلات
    3. يدمج الردود
    """
    task_type = await analyze_request(messages)
    selected_models = MODELS.get(task_type, MODELS["general"])

    base_system = """أنت ALBRAZIL WORM.
- ردودك حرة ومباشرة وقوية.
- دقيق وواضح وقليل الأخطاء.
- لما يكون فيه كود، اكتب كود كامل شغال.
- ادمج أي أسلوب أو قواعد إضافية يديك المستخدم.
"""

    if custom_style:
        base_system += f"\n\nأسلوب إضافي مطلوب:\n{custom_style}"

    # استدعاء الموديلات (حالياً واحد للتوفير، بعدين نزود)
    responses = []
    for model in selected_models[:1]:  # نبدأ بواحد عشان الـ free tier
        resp = await call_model(model, messages, base_system)
        responses.append(resp)

    # دمج بسيط (لاحقاً هنحسنه)
    final = responses[0] if responses else "مفيش رد"

    return final