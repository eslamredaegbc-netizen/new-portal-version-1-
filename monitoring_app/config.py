from pathlib import Path

APP_NAME = "منصة الرصد الإعلامي لقطاع الإعلام"
OWNER_NAME = "قطاع التطوير التقني"
COPYRIGHT_NOTICE = "جميع الحقوق محفوظة لقطاع التطوير التقني"

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = BASE_DIR / "exports"
STATIC_DIR = BASE_DIR / "static"
DB_PATH = DATA_DIR / "monitoring.db"

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "Admin@123"
DEFAULT_FULL_NAME = "مدير النظام"

SOURCE_LABELS = {
    "web": "ويب عام",
    "news": "أخبار",
    "official": "مواقع رسمية",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "youtube": "YouTube",
    "forums": "منتديات ومجتمعات",
    "images": "صور",
    "direct": "روابط مباشرة",
}

DEFAULT_SOURCE_SELECTION = [
    "news",
    "official",
    "facebook",
    "instagram",
    "youtube",
    "forums",
    "web",
    "images",
]

NEGATIVE_RED_CATEGORIES = {"شكوى", "استغاثة", "طلب مساعدة", "انتقاد", "تشهير"}
NEUTRAL_YELLOW_CATEGORIES = {"خبر محايد", "غير ذي صلة", "مكرر"}
POSITIVE_GREEN_CATEGORIES = {"إشادة"}

CATEGORY_LABELS = [
    "شكوى",
    "استغاثة",
    "طلب مساعدة",
    "انتقاد",
    "تشهير",
    "إشادة",
    "خبر محايد",
    "غير ذي صلة",
    "مكرر",
]

FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/tahoma.ttf"),
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

OPEN_SOURCE_MODEL_RECOMMENDATION = {
    "recommended_as_of": "2026-04-21",
    "text_model": "Qwen3.6-35B-A3B",
    "multimodal_model": "Qwen3-VL",
    "reason": (
        "ملائم للتطبيقات الإنتاجية متعددة اللغات مع دعم قوي للعربية وإتاحة تشغيله عبر "
        "خوادم OpenAI-compatible مثل SGLang أو vLLM."
    ),
}
