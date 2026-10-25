# ALBRAZIL WORM

نظام ذكاء اصطناعي ذكي + نظام تدريب مربوطين ببعض.

## المميزات
- فاحص طلب ذكي
- اختيار ودمج موديلات من OpenRouter
- واجهة تدريب (رفع ملفات + وصف + قفل مؤقت)
- محاكاة قبل/بعد التدريب

## التشغيل المحلي
```bash
pip install -r requirements.txt
export OPENROUTER_API_KEY="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"
uvicorn main:app --host 0.0.0.0 --port 8000