export type Connection = { url: string; token: string };
export type Experiment = {
  id: string;
  name: string;
  command: string;
  shell: string;
  cwd: string;
  status: string;
  queue_position: number;
  pid: number | null;
  exit_code: number | null;
  created_by: string;
  tags: string;
  notes: string;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  stdout_path: string;
  stderr_path: string;
};
export type Summary = Record<string, number | boolean> & { paused: boolean };
export type Snapshot = {
  experiments: Experiment[];
  summary: Summary;
  total: number;
};
export type Info = {
  version: string;
  root: string;
  platform: string;
  default_shell: string;
  shells: string[];
};
export async function request<T>(
  c: Connection,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(c.url + path, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      Authorization: `Bearer ${c.token}`,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  const text = await response.text();
  let result;
  try {
    result = JSON.parse(text);
  } catch {
    throw new Error(text || `HTTP ${response.status}`);
  }
  if (!response.ok) throw new Error(result.error || text);
  return result;
}
export async function subscribe(
  c: Connection,
  signal: AbortSignal,
  onChange: () => void,
  onState: (connected: boolean) => void,
) {
  while (!signal.aborted) {
    try {
      const r = await fetch(c.url + "/events", {
        headers: { Authorization: `Bearer ${c.token}` },
        signal,
      });
      if (!r.ok || !r.body) throw new Error("Events unavailable");
      onState(true);
      onChange();
      const reader = r.body.getReader(),
        decoder = new TextDecoder();
      let buffer = "";
      try {
        while (!signal.aborted) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true }).replace(/\r/g, "");
          let boundary;
          while ((boundary = buffer.indexOf("\n\n")) >= 0) {
            const message = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            if (message.includes("event: change")) onChange();
          }
        }
      } finally {
        await reader.cancel().catch(() => {});
        reader.releaseLock();
      }
    } catch (e) {
      if (signal.aborted) return;
    }
    onState(false);
    await new Promise<void>((resolve) => {
      const done = () => {
        clearTimeout(timer);
        signal.removeEventListener("abort", done);
        resolve();
      };
      const timer = setTimeout(done, 1500);
      signal.addEventListener("abort", done, { once: true });
    });
  }
}
