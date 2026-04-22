/**
 * parseApiError — safely extracts a human-readable message from any API error.
 *
 * FastAPI returns 422 validation errors with `detail` as an ARRAY of
 * { type, loc, msg, ... } objects. Passing that array directly to
 * `toast.error(...)` or any JSX child crashes React ("Objects are not
 * valid as a React child"), taking the whole app down to a blank screen.
 *
 * Call sites must always render the return value of this function, never
 * `err.response.data.detail` directly.
 */
export function parseApiError(err: unknown, fallback: string): string {
    const detail = (err as any)?.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) return detail.trim()
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
    if (err instanceof Error && err.message) return err.message
    return fallback
}

/**
 * Strict email format check. The browser's `type="email"` validator accepts
 * loose values like "a@b" — this guards against that before we call the API.
 */
export function isValidEmail(value: string): boolean {
    const trimmed = value.trim()
    if (!trimmed) return false
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    return re.test(trimmed)
}
