// Web transport only. Queue ordering, validation, deduplication and statistics stay in the API.
export const scopePrefix = location.pathname.match(/^\/jobs\/[a-f0-9]{32}(?=\/)/)?.[0] || '';
export function apiPath(path) {
  return scopePrefix && !/^\/(auth|intake)(\/|\?|$)/.test(path) && !path.startsWith(scopePrefix+'/')
    ? scopePrefix + path : path;
}
export async function request(path, options = {}) {
  const {timeoutMs = 15000, responseType = 'json', ...fetchOptions} = options;
  const abort = new AbortController();
  const timeout = setTimeout(() => abort.abort(), timeoutMs);
  try {
    let token = null;
    try { token = localStorage.getItem('m13.pilot.access.v1'); } catch { /* storage disabled */ }
    const headers = {...(fetchOptions.headers || {})};
    if (token) headers['X-M13-Pilot-Session'] = token;
    const response = await fetch(apiPath(path), {cache: 'no-store', signal: abort.signal, ...fetchOptions, headers});
    if (response.ok && responseType === 'blob') return await response.blob();
    let body;
    try { body = await response.json(); } catch { body = {}; }
    if (!response.ok) {
      if (response.status === 401 && location.pathname !== '/login') location.assign('/login');
      const detail = typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`;
      const error = new Error(detail); error.status = response.status; throw error;
    }
    return body;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('API phản hồi quá lâu; bạn có thể thử lại.');
    throw error;
  } finally { clearTimeout(timeout); }
}
export const submit = payload => request('/verdict', {
  method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
});
