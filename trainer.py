"""
ALBRAZIL WORM - Trainer + Simulation
قراءة البيانات + فهمها + دمجها مع الأسلوب الأساسي + محاكاة قبل/بعد
"""

from pathlib import Path
import json
from datetime import datetime

UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"


def read_uploaded_files() -> str:
    """قراءة كل الملفات المرفوعة ودمج محتواها"""
    contents = []
    for file_path in UPLOAD_DIR.glob("*"):
        if file_path.is_file():
            try:
                # نحاول نقرأ كنص
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                contents.append(f"--- ملف: {file_path.name} ---\n{text[:5000]}")  # نحد عشان الحجم
            except Exception:
                contents.append(f"--- ملف: {file_path.name} --- (مش نصي أو فيه مشكلة)")
    return "\n\n".join(contents) if contents else "مفيش ملفات"


def build_training_style(description: str, files_content: str) -> str:
    """
    بناء الأسلوب الجديد اللي الموديل هيتبعه بعد التدريب
    بيدمج وصف المستخدم + محتوى الملفات مع الأسلوب الأساسي
    """
    style = f"""
الأسلوب المطلوب بعد التدريب:

{description}

محتوى البيانات اللي اترفعت:
{files_content[:8000]}

التعليمات:
- افهم البيانات دي كويس ونفذ بنفس طريقتها وأسلوبها.
- ادمج الطريقة دي مع أسلوبك الأساسي (الحر + الدقيق + الشامل).
- لو البيانات فيها قواعد أو أمثلة، اتبعها.
"""
    return style.strip()


def simulate_before_after(description: str, files_content: str) -> dict:
    """
    محاكاة افتراضية بسيطة (قبل وبعد)
    حالياً مجرد تسجيل، لاحقاً نربطها باختبارات حقيقية
    """
    result = {
        "timestamp": datetime.now().isoformat(),
        "description": description,
        "files_summary": files_content[:500] + "..." if len(files_content) > 500 else files_content,
        "before": "الأداء قبل التدريب (الأسلوب الأساسي فقط)",
        "after": "الأداء بعد دمج البيانات الجديدة",
        "status": "simulation_done"
    }

    # حفظ نتيجة المحاكاة
    sim_path = Path(__file__).resolve().parent / "last_simulation.json"
    sim_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return result