import "server-only";
import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

export const sessionCookie = "viniscaya-session";
export function createSession() {
  const expires = String(Date.now() + 1000 * 60 * 60 * 24);
  const signature = createHmac("sha256", process.env.SESSION_SECRET!).update(expires).digest("hex");
  return `${expires}.${signature}`;
}
export async function isSignedIn() {
  const value = (await cookies()).get(sessionCookie)?.value;
  if (!value || !process.env.SESSION_SECRET) return false;
  const [expires, signature] = value.split(".");
  if (!signature || Number(expires) <= Date.now() || !Number.isFinite(Number(expires))) return false;
  const expected = createHmac("sha256", process.env.SESSION_SECRET).update(expires).digest("hex");
  return signature.length === expected.length && timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
}
