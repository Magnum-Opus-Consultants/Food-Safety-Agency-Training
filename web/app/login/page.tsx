"use client";

// Matches the FSA sign-in used by the APS portal (aps-demo.fsa-pty.co.za/login): photo background
// with a dark overlay, logo and company name above a white card, icon inputs, teal primary button.

import { useQueryClient } from "@tanstack/react-query";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api, ApiError } from "@/lib/api";

export default function Login() {
  const router = useRouter();
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [forgot, setForgot] = useState(false);
  const [refusal, setRefusal] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  async function signIn(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setRefusal(null);
    try {
      await api("/auth/login", { method: "POST", body: { username, password }, screen: "login" });
      qc.clear();
      router.replace("/training-home");
    } catch (err) {
      setRefusal(err as ApiError);
      setPassword("");
      setBusy(false);
    }
  }

  return (
    <div className="fsa-login">
      <div className="fsa-login-inner">
        <div className="fsa-login-brand">
          <Image src="/brand/fsa-logo.png" alt="Food Safety Agency Logo" width={96} height={49} priority />
          <h1>Food Safety Agency (Pty) Ltd</h1>
          <h2>Training Hub · Secure Login Portal</h2>
        </div>
        <div className="fsa-login-card">
          <div className="fsa-login-title"><i className="fas fa-lock" aria-hidden /> Sign In</div>
          {refusal ? (
            <div className="fsa-alert" role="alert">
              <i className="fas fa-circle-exclamation" aria-hidden />
              <span>{refusal.blockedBy[0] ?? refusal.message}</span>
            </div>
          ) : null}
          <form onSubmit={signIn} noValidate>
            <label htmlFor="username">Username</label>
            <div className="fsa-input">
              <i className="fas fa-user" aria-hidden />
              <input id="username" name="username" autoComplete="username" autoFocus value={username}
                     onChange={(e) => setUsername(e.target.value)} placeholder="Enter your username" />
            </div>
            <label htmlFor="password">Password</label>
            <div className="fsa-input">
              <i className="fas fa-lock" aria-hidden />
              <input id="password" name="password" type={show ? "text" : "password"} autoComplete="current-password"
                     value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password" />
              <button type="button" className="fsa-eye" onClick={() => setShow(!show)}
                      aria-label={show ? "Hide password" : "Show password"}>
                <i className={`fas ${show ? "fa-eye-slash" : "fa-eye"}`} aria-hidden />
              </button>
            </div>
            <div className="fsa-forgot">
              <button type="button" onClick={() => setForgot(!forgot)}>Forgot Password?</button>
            </div>
            {forgot ? (
              <p className="fsa-forgot-note">Passwords are reset by HR and Administration. Ask them to issue a new one;
                five failed attempts lock a username for fifteen minutes.</p>
            ) : null}
            <button type="submit" className="fsa-signin" disabled={busy}>
              <i className={`fas ${busy ? "fa-spinner fa-spin" : "fa-sign-in-alt"}`} aria-hidden /> {busy ? "Signing in…" : "Sign In"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
