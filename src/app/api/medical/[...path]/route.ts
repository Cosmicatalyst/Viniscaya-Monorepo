import { isSignedIn } from "@/lib/session";

async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  if (!(await isSignedIn())) return Response.json({ error: "Please sign in again." }, { status: 401 });
  const { path } = await context.params;
  const target = path.join("/");
  if (!/^(health|v1\/models|v1\/files|v1\/files\/[a-f0-9]{32}\/preview|v1\/inference|v1\/cases|v1\/samples|v1\/stats|v1\/jobs|v1\/threads|v1\/threads\/[a-f0-9]{32}|v1\/jobs\/[a-f0-9]{32}(\/(result|report|segmentation|chat-context))?)$/.test(target)) return Response.json({ error: "Unknown endpoint." }, { status: 404 });
  if (!["GET", "HEAD"].includes(request.method)) {
    const origin = request.headers.get("origin");
    try {
      if (origin && new URL(origin).host !== request.headers.get("host")) return Response.json({ error: "Invalid request." }, { status: 403 });
    } catch { return Response.json({ error: "Invalid request." }, { status: 403 }); }
  }
  if (!process.env.MEDICAL_API_TOKEN) return Response.json({ error: "Local API is not configured." }, { status: 503 });
  try {
    const contentType = request.headers.get("content-type");
    const response = await fetch(`${process.env.MEDICAL_API_URL || "http://127.0.0.1:8000"}/${target}${new URL(request.url).search}`, {
      method: request.method,
      headers: { Authorization: `Bearer ${process.env.MEDICAL_API_TOKEN}`, ...(contentType ? { "Content-Type": contentType } : {}) },
      body: ["POST", "PUT"].includes(request.method) ? request.body : undefined,
      // Stream uploads rather than loading whole-slide files into memory.
      ...({ duplex: "half" } as Record<string, string>),
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(60000)]),
      cache: "no-store",
    });
    return new Response(response.body, { status: response.status, headers: {
      "Content-Type": response.headers.get("content-type") || "application/json",
      "Cache-Control": "no-store",
      ...(response.headers.get("content-disposition") ? { "Content-Disposition": response.headers.get("content-disposition")! } : {}),
    } });
  } catch { return Response.json({ error: "Local Python server is unavailable. Start the medical API and retry." }, { status: 503 }); }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
