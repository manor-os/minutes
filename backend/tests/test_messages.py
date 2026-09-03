from api.services import messages as m


def test_selected_language_wins_over_browser_language():
    assert m.pick_language("ja", "zh-CN,zh;q=0.9,en;q=0.8") == "ja"


def test_browser_accept_language_used_when_nothing_selected():
    assert m.pick_language(None, "zh-CN,zh;q=0.9,en;q=0.8") == "zh"
    assert m.pick_language("", "fr-FR,fr;q=0.9") == "fr"


def test_unknown_languages_fall_back_to_english():
    assert m.pick_language("xx", "yy-ZZ;q=0.9") == "en"
    assert m.pick_language(None, None) == "en"


def test_accept_language_skips_unsupported_entries():
    assert m.pick_language(None, "tlh, ko;q=0.8") == "ko"


def test_region_and_underscore_variants_normalize():
    assert m.normalize_language("zh_TW") == "zh"
    assert m.normalize_language("pt-BR") == "pt"


def test_credit_message_is_localized():
    assert m.message("credit_exhausted", "zh") == "额度不足,请充值后再试。"
    assert m.message("credit_exhausted", "en").startswith("Your AI credits are used up")
    assert m.message("credit_exhausted", "ja") != m.message("credit_exhausted", "en")
    assert m.message("credit_exhausted", None) == m.message("credit_exhausted", "en")


def test_every_settings_language_has_every_message():
    settings_languages = {
        "en", "zh", "ja", "ko", "es", "fr", "de", "pt", "ar", "ru",
        "it", "nl", "hi", "th", "vi", "id", "tr", "pl", "uk", "sv",
    }
    for key, table in m.MESSAGES.items():
        missing = settings_languages - set(table)
        assert not missing, f"{key} lacks {sorted(missing)}"
        assert all(table[lang].strip() for lang in settings_languages)
