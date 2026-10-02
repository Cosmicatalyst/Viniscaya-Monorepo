"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { createSession, sessionCookie } from "@/lib/session";

export async function login(formData: FormData) {
  if (formData.get("userId") !== process.env.LOGIN_ID || formData.get("password") !== process.env.LOGIN_PASSWORD) {
    return { success: false, message: "Incorrect ID or password." };
  }
  (await cookies()).set(sessionCookie, createSession(), {
    httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 86400,
  });
  return { success: true, message: "" };
}

export async function logout() {
  (await cookies()).delete(sessionCookie);
  redirect("/");
}
