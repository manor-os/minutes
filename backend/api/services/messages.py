"""
User-facing error messages in the language the user chose.

The frontend sends the language picked in Settings as ``X-Language`` (the same
value it stores as ``transcript_language``). When that header is absent the
browser's ``Accept-Language`` decides, and English is the last resort.

Only messages that end users read verbatim live here; log lines and developer
errors stay English.
"""
from typing import Optional

from fastapi import Header

DEFAULT_LANGUAGE = "en"

# The credit message is what a Manor user sees when the entity's AI credits
# are used up (HTTP 402 from the Manor LLM gateway).
MESSAGES: dict = {
    "credit_exhausted": {
        "en": "Your AI credits are used up. Please top up and try again.",
        "zh": "额度不足,请充值后再试。",
        "ja": "AIクレジットが不足しています。チャージしてから再度お試しください。",
        "ko": "AI 크레딧이 부족합니다. 충전 후 다시 시도해 주세요.",
        "es": "Se han agotado tus créditos de IA. Recarga e inténtalo de nuevo.",
        "fr": "Vos crédits IA sont épuisés. Rechargez puis réessayez.",
        "de": "Ihre KI-Credits sind aufgebraucht. Bitte aufladen und erneut versuchen.",
        "pt": "Os seus créditos de IA acabaram. Recarregue e tente novamente.",
        "ar": "نفد رصيد الذكاء الاصطناعي لديك. يرجى إعادة الشحن والمحاولة مرة أخرى.",
        "ru": "Кредиты ИИ закончились. Пополните баланс и попробуйте снова.",
        "it": "I tuoi crediti IA sono esauriti. Ricarica e riprova.",
        "nl": "Je AI-credits zijn op. Waardeer op en probeer het opnieuw.",
        "hi": "आपके AI क्रेडिट समाप्त हो गए हैं। कृपया रिचार्ज करके फिर से प्रयास करें।",
        "th": "เครดิต AI ของคุณหมดแล้ว กรุณาเติมเครดิตแล้วลองอีกครั้ง",
        "vi": "Bạn đã hết tín dụng AI. Vui lòng nạp thêm và thử lại.",
        "id": "Kredit AI Anda sudah habis. Silakan isi ulang lalu coba lagi.",
        "tr": "AI kredileriniz tükendi. Lütfen yükleme yapıp tekrar deneyin.",
        "pl": "Twoje kredyty AI się wyczerpały. Doładuj konto i spróbuj ponownie.",
        "uk": "Кредити ШІ вичерпано. Поповніть баланс і спробуйте ще раз.",
        "sv": "Dina AI-krediter är slut. Fyll på och försök igen.",
    },
    "llm_key_missing": {
        "en": "Add an API key in Settings first.",
        "zh": "请先在「设置」中添加 API key。",
        "ja": "先に「設定」で API キーを追加してください。",
        "ko": "먼저 설정에서 API 키를 추가해 주세요.",
        "es": "Primero añade una clave de API en Ajustes.",
        "fr": "Ajoutez d'abord une clé API dans les Paramètres.",
        "de": "Bitte zuerst in den Einstellungen einen API-Schlüssel hinzufügen.",
        "pt": "Adicione primeiro uma chave de API nas Definições.",
        "ar": "يرجى إضافة مفتاح API في الإعدادات أولاً.",
        "ru": "Сначала добавьте API-ключ в настройках.",
        "it": "Aggiungi prima una chiave API nelle Impostazioni.",
        "nl": "Voeg eerst een API-sleutel toe in Instellingen.",
        "hi": "पहले सेटिंग्स में API कुंजी जोड़ें।",
        "th": "กรุณาเพิ่ม API key ในการตั้งค่าก่อน",
        "vi": "Vui lòng thêm API key trong Cài đặt trước.",
        "id": "Tambahkan API key di Pengaturan terlebih dahulu.",
        "tr": "Önce Ayarlar'da bir API anahtarı ekleyin.",
        "pl": "Najpierw dodaj klucz API w Ustawieniach.",
        "uk": "Спочатку додайте API-ключ у Налаштуваннях.",
        "sv": "Lägg först till en API-nyckel under Inställningar.",
    },
}

SUPPORTED_LANGUAGES = frozenset(MESSAGES["credit_exhausted"].keys())


def normalize_language(value: Optional[str]) -> Optional[str]:
    """``zh-CN`` -> ``zh``; anything we have no translation for -> None."""
    if not value:
        return None
    primary = value.strip().split(";")[0].strip().replace("_", "-").split("-")[0].lower()
    return primary if primary in SUPPORTED_LANGUAGES else None


def pick_language(x_language: Optional[str], accept_language: Optional[str]) -> str:
    """The user's Settings choice wins, then the browser's preference order."""
    chosen = normalize_language(x_language)
    if chosen:
        return chosen
    for part in (accept_language or "").split(","):
        chosen = normalize_language(part)
        if chosen:
            return chosen
    return DEFAULT_LANGUAGE


def resolve_language(
    x_language: Optional[str] = Header(None, alias="X-Language"),
    accept_language: Optional[str] = Header(None, alias="Accept-Language"),
) -> str:
    """FastAPI dependency: language code for messages on this request."""
    return pick_language(x_language, accept_language)


def message(key: str, lang: Optional[str]) -> str:
    table = MESSAGES[key]
    return table.get(normalize_language(lang) or DEFAULT_LANGUAGE) or table[DEFAULT_LANGUAGE]
