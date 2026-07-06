const nicknameMap = {
  'will': 'william',
  'mike': 'michael',
  'matt': 'matthew',
  'chris': 'christopher',
  'nick': 'nicholas',
  'dan': 'daniel',
  'steve': 'stephen',
  'joe': 'joseph',
  'tom': 'thomas',
  'jim': 'james',
  'bob': 'robert',
  'bill': 'william',
  'dave': 'david',
  'andy': 'andrew',
  'drew': 'andrew',
  'ben': 'benjamin',
  'sam': 'samuel',
  'alex': 'alexander',
  'zach': 'zachary',
  'josh': 'joshua',
  'jon': 'jonathan',
  'nate': 'nathan',
  'jeff': 'jeffrey',
  'greg': 'gregory',
  'doug': 'douglas',
  'ted': 'theodore',
  'tim': 'timothy',
  'tony': 'anthony',
  'jake': 'jacob',
  'luke': 'lucas',
  'eli': 'elijah'
};

/**
 * Strip class-year designations in parentheses from player names.
 * Handles formats like "(Fr)", "(So)", "(Jr)", "(Sr)", "(Gr)",
 * redshirt variants "(RS Fr)", "(R-Fr)", "(RS-Fr)", etc.
 * Does NOT strip non-parenthesized suffixes like "Jr" or "Sr"
 * which are legitimate name suffixes (father/son).
 */
const YEAR_SUFFIX_RE = /\s*\((?:RS[\s-]*|R-)?(?:Fr|So|Jr|Sr|Gr|5th)\)\s*$/i;

function stripYearSuffix(name) {
  if (!name || typeof name !== 'string') return name || '';
  return name.replace(YEAR_SUFFIX_RE, '').trim();
}

function normalizePlayerName(name) {
  const cleaned = String(name || '').toLowerCase().trim();
  if (!cleaned) return '';
  const parts = cleaned.split(/\s+/);
  if (parts.length >= 1 && nicknameMap[parts[0]]) {
    parts[0] = nicknameMap[parts[0]];
  }
  return parts.join(' ');
}

// Extract a jersey number from a GameChanger box score "Info" field.
// Accepts shapes like "#12 (SS)", "#7", "7 (P)", "", etc.
// Returns the number as a string (preserves leading zeros) or null.
function parseJerseyNumber(info) {
  if (info === null || info === undefined) return null;
  const match = String(info).match(/#?\s*(\d{1,3})\b/);
  return match ? match[1] : null;
}

function extractLastName(playerName) {
  if (!playerName || typeof playerName !== 'string') return '';
  const parts = playerName.trim().split(' ');
  return parts.length > 1 ? parts[parts.length - 1] : playerName.trim();
}

function buildInitialLastNameKey(playerName) {
  const normalized = normalizePlayerName(playerName);
  if (!normalized) return null;
  const parts = normalized.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return null;
  const firstInitial = parts[0].charAt(0);
  if (!firstInitial) return null;
  const lastNameNormalized = parts.length > 1 ? parts[parts.length - 1] : parts[0];
  if (!lastNameNormalized) return null;
  return {
    key: `${firstInitial}${lastNameNormalized}`,
    normalizedLastName: lastNameNormalized,
    displayLastName: extractLastName(playerName) || lastNameNormalized,
    firstInitial
  };
}

module.exports = {
  normalizePlayerName,
  extractLastName,
  buildInitialLastNameKey,
  stripYearSuffix,
  parseJerseyNumber
};
