"use client";

import { ClerkProvider, SignIn, SignUp, useAuth } from "@clerk/nextjs";
import { useEffect, useState, type ReactNode } from "react";
import { Sun, Moon } from "lucide-react";

const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

export default function AccountGate({ children }: { children: ReactNode }) {
  const [loginTheme, setLoginTheme] = useState<"light" | "dark">("dark");

  // User can change the login screen from dark to light
  useEffect(() => {
    const saved = localStorage.getItem("login-theme");

    if (saved === "light" || saved === "dark") {
      setLoginTheme(saved);
    }
  }, []);

  function changeLoginTheme() {
    const next = loginTheme === "dark" ? "light" : "dark";

    setLoginTheme(next);
    localStorage.setItem("login-theme", next);
  }

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
      <SessionGate
        loginTheme={loginTheme}
        onLoginThemeChange={changeLoginTheme}
      >
        {children}
      </SessionGate>
    </ClerkProvider>
  );
}

function SessionGate({
  children,
  loginTheme,
  onLoginThemeChange,
}: {
  children: ReactNode;
  loginTheme: "light" | "dark";
  onLoginThemeChange: () => void;
}) {
  const { isLoaded, isSignedIn, userId, sessionId } = useAuth();
  const [register, setRegister] = useState(false);

  useEffect(() => {
    if (isSignedIn) {
      // Immediately switch the authenticated website to Dark Mode
      delete document.documentElement.dataset.authTheme;
      document.documentElement.dataset.theme = "dark";
    } else {
      // Restore the user's independent login-screen preference
      delete document.documentElement.dataset.theme;
      document.documentElement.dataset.authTheme = loginTheme;
    }
  }, [isSignedIn, loginTheme]);

  if (!isLoaded)
    return (
      <main className="account-page" aria-live="polite">
        Loading your account…
      </main>
    );
  if (isSignedIn) return <div key={`${userId}:${sessionId}`}>{children}</div>;
  return (
    <main className="account-page">
      <button
        type="button"
        className="account-theme-toggle"
        onClick={onLoginThemeChange}
      >
        {loginTheme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
        {loginTheme === "dark" ? "Light mode" : "Dark mode"}
      </button>

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
        {register ? ( // Manages Light Mode 
          <SignUp
            routing="hash"
            appearance={{
              variables:
                loginTheme === "light"
                  ? {
                    colorPrimary: "#d8ae68",
                    colorBackground: "#ffffff",
                    colorForeground: "#000000",
                    colorMutedForeground: "#77766f",
                    colorInput: "#e6e6e6",
                    colorInputForeground: "#000000",
                    colorNeutral: "#000000",
                    borderRadius: "4px",
                  }
                : {
                    colorPrimary: "#d8ae68",
                    colorBackground: "#131619",
                    colorForeground: "#e4e7e9",
                    colorMutedForeground: "#aeb6bf",
                    colorInput: "#0d0f11",
                    colorInputForeground: "#e4e7e9",
                    borderRadius: "4px",
                  },
            }}
          />
        ) : (
          <SignIn
            routing="hash"
            appearance={{
              variables:
                loginTheme === "light"
                  ? {
                    colorPrimary: "#d8ae68",
                    colorBackground: "#ffffff",
                    colorForeground: "#000000",
                    colorMutedForeground: "#77766f",
                    colorInput: "#e6e6e6",
                    colorInputForeground: "#000000",
                    colorNeutral: "#000000",
                    borderRadius: "4px",
                  }
                : {
                    colorPrimary: "#d8ae68",
                    colorBackground: "#131619",
                    colorForeground: "#e4e7e9",
                    colorMutedForeground: "#aeb6bf",
                    colorInput: "#0d0f11",
                    colorInputForeground: "#e4e7e9",
                    borderRadius: "4px",
                }
            }}
          />
        )}
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
