export class ApiError extends Error { constructor(public status: number, message: string) { super(message) } }
export async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...options?.headers } })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const message = typeof body.detail === 'string' ? body.detail : body.detail?.message || `请求失败 (${response.status})`
    throw new ApiError(response.status, message)
  }
  return response.json()
}
