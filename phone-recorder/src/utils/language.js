// The language the user picked in Settings ("Transcript Language", stored as
// transcript_language). The backend phrases user-facing errors — out of
// credit, missing API key — in this language when we send it as X-Language;
// with no explicit choice it falls back to the browser's Accept-Language.

export function getSelectedLanguage() {
  try {
    return (localStorage.getItem("transcript_language") || "").trim();
  } catch {
    return "";
  }
}

export function languageHeaders() {
  const lang = getSelectedLanguage();
  return lang ? { "X-Language": lang } : {};
}
