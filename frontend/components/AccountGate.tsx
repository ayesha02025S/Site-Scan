"use client";

import { ClerkProvider, SignIn, SignUp, useAuth } from "@clerk/nextjs";
import { useState, type ReactNode } from "react";

const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

export default function AccountGate({ children }: { children: ReactNode }) {
  if (!publishableKey) {
    return (
      <main className="account-page">
        <section className="account-intro">
          <p className="eyebrow">SITE SCAN</p>
          <h1>Account setup in progress</h1>
          <p>Sign-in is being configured. Please try again shortly.</p>
        </section>
      </main>
    );
  }
  return (
    <ClerkProvider
      publishableKey={publishableKey}
      signInFallbackRedirectUrl="/"
      signUpFallbackRedirectUrl="/"
      appearance={{
        variables: {
          colorPrimary: "#d8ae68",
          colorBackground: "#131619",
          colorForeground: "#e4e7e9",
          colorMutedForeground: "#aeb6bf",
          colorInput: "#0d0f11",
          colorInputForeground: "#e4e7e9",
          borderRadius: "4px",
        },
      }}
    >
      <SessionGate>{children}</SessionGate>
    </ClerkProvider>
  );
}

function SessionGate({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, userId, sessionId } = useAuth();
  const [register, setRegister] = useState(false);
  if (!isLoaded)
    return (
      <main className="account-page" aria-live="polite">
        Loading your account…
      </main>
    );
  if (isSignedIn) return <div key={`${userId}:${sessionId}`}>{children}</div>;
  return (
    <main className="account-page">
      <section className="account-intro">
        <p className="eyebrow">SITE SCAN / YOUR WORKSPACE</p>
        <h1>
          A clearer view.
          <br />
          Your own workspace.
        </h1>
        <p>
          Sign in to run assessments, revisit your reports, and follow your
          website’s health over time.
        </p>
        <p className="account-detail">
          Your scans belong to your account and stay available across sessions
          and devices.
        </p>
      </section>
      <section
        className="account-form"
        aria-label={register ? "Create an account" : "Sign in"}
      >
        {register ? <SignUp routing="hash" /> : <SignIn routing="hash" />}
        <button
          className="account-switch"
          onClick={() => setRegister(!register)}
        >
          {register
            ? "Already have an account? Sign in"
            : "New to Site Scan? Create an account"}
        </button>
      </section>
    </main>
  );
}
