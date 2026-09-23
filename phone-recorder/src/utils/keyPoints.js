// Clean key points for display: older meetings may have raw LLM output stored
// (```json fences, brackets, quoted strings with trailing commas)
export const cleanKeyPoints = (points) => {
  if (!Array.isArray(points)) return [];
  return points
    .map(p => typeof p === 'string' ? p : (p?.text || p?.description || p?.point || JSON.stringify(p)))
    .map(s => String(s).trim())
    .filter(s => s && !/^(```\w*|```|\[|\]|\{|\})\s*,?\s*$/.test(s))
    .map(s => s.replace(/,\s*$/, '').trim())
    .map(s => (s.startsWith('"') && s.endsWith('"') && s.length > 1) ? s.slice(1, -1) : s)
    .filter(Boolean);
};

// The Summary tab already names the content. Generated notes sometimes repeat
// that label as the first Markdown heading, so omit only that exact heading in
// the reading view while preserving the stored text for editing and export.
export const cleanSummaryForDisplay = (summary) => {
  const value = String(summary || '');
  const heading = value.match(/^\s{0,3}#{1,6}[ \t]+(?:meeting[ \t]+summary|summary)[ \t]*:?[ \t]*(?:\r?\n)+/i);
  return heading ? value.slice(heading[0].length) : value;
};
