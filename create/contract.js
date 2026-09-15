// RFC 8785 JSON Canonicalization Scheme with an application safe-integer domain.
// Observation arrays are ordered by key using UTF-16 code units, separately from JCS.
export const CANONICALIZATION = 'RFC8785-JCS; observations sorted by UTF-16 key; safe integers; v2';

function validString(value) {
  if (!value.isWellFormed()) throw new Error('Strings must not contain unpaired surrogates.');
  return JSON.stringify(value);
}

export function canonical(value) {
  if (value === null || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'string') return validString(value);
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('Numbers must be finite.');
    if (Number.isInteger(value) && !Number.isSafeInteger(value)) throw new Error('Integer values must be within the safe integer domain.');
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype) {
    return '{' + Object.keys(value).sort().map(key => validString(key) + ':' + canonical(value[key])).join(',') + '}';
  }
  throw new Error('Only JSON values are supported.');
}

export function observationBytes(observations) {
  const keys = new Set();
  for (const row of observations) {
    if (!row || typeof row.key !== 'string' || !row.key || keys.has(row.key)) throw new Error('Observation keys must be nonempty and unique.');
    if (typeof row.value !== 'number' || !Number.isFinite(row.value)) throw new Error('Observation values must be finite numbers.');
    keys.add(row.key);
  }
  return canonical([...observations].sort((a, b) => a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
}

export async function prepareDefinition(value) {
  if (!Array.isArray(value.sources) || !value.sources.length) throw new Error('Add at least one public source with complete provenance.');
  if (!Array.isArray(value.observations) || !value.observations.length) throw new Error('Add at least one source-linked observation.');
  const bytes = new TextEncoder().encode(observationBytes(value.observations));
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  const seed = Array.from(digest, b => b.toString(16).padStart(2, '0')).join('');
  return {...value, seed: {algorithm:'sha256', canonicalization:CANONICALIZATION,
    inputs:value.observations.map(row => row.key).sort(), url_parameter:'seed', value:seed}};
}
