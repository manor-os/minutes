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
