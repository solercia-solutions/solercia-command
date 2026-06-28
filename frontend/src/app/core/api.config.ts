/**
 * Base URL of the FastAPI backend (v1).
 *
 * Relative path on purpose: the Angular dev server proxies `/api` to the
 * backend (see proxy.conf.json), so requests are same-origin. This works on
 * localhost and through any HTTPS tunnel (e.g. VS Code dev tunnels) without
 * hardcoding hosts or triggering CORS.
 */
export const apiBase = '/api/v1';
