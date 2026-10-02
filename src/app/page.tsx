"use client";

import Image from "next/image";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { login } from "@/app/actions";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setPending(true);
    setMessage("");
    try {
      const result = await login(formData);
      if (result.success) router.push("/dashboard");
      else setMessage(result.message);
    } catch {
      setMessage("Unable to sign in. Please try again.");
    } finally {
      setPending(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <form className="login-form" onSubmit={handleSubmit}>
          <h1 id="login-title">viniścaya</h1>
          <div className="login-fields">
            <label className="sr-only" htmlFor="user-id">ID</label>
            <Input id="user-id" name="userId" placeholder="ID" autoComplete="username" required className="login-input" />
            <label className="sr-only" htmlFor="password">Password</label>
            <Input id="password" name="password" type="password" placeholder="Pass" autoComplete="current-password" required className="login-input" />
          </div>
          <Button type="submit" disabled={pending} className="login-submit">{pending ? "Signing in…" : "Continue"}</Button>
          <p className="login-message" role="status">{message}</p>
        </form>
      </section>
      <section className="photo-panel" aria-label="A peaceful mountain landscape">
        <Image src="/login-landscape.jpg" alt="Sunlit mountains and a green valley framed by flowers" fill priority sizes="(max-width: 767px) 100vw, 50vw" className="landscape-photo" />
        <h2 className="photo-caption">Helping those who<br />save lives, save more.</h2>
      </section>
    </main>
  );
}
