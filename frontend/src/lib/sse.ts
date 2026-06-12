import { getToken } from '../api'

export type SseHandler = (event: MessageEvent) => void

/**
 * Open an SSE stream to /api/events.
 * Returns a cleanup function to close the stream.
 */
export function openSse(
  path: string,
  onMessage: SseHandler,
  onError?: (e: Event) => void,
): () => void {
  // Append token as query param since EventSource doesn't support custom headers.
  const url = `${path}?token=${encodeURIComponent(getToken())}`
  const es = new EventSource(url)

  es.onmessage = onMessage
  es.onerror = onError ?? null

  return () => es.close()
}
