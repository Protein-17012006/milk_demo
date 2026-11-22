"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth";

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"
      />
    </svg>
  );
}

type LoginStep =
  | "CREDENTIALS"
  | "NEW_PASSWORD_REQUIRED"
  | "TOTP_REQUIRED"
  | "FORGOT_REQUEST"
  | "FORGOT_CONFIRM";

export function LoginView() {
  const router = useRouter();
  const {
    signIn,
    completeNewPassword,
    submitTotpCode,
    forgotPassword,
    confirmForgotPassword,
  } = useAuth();

  const [step, setStep] = useState<LoginStep>("CREDENTIALS");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [resetCode, setResetCode] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberDevice, setRememberDevice] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [infoMsg, setInfoMsg] = useState<string | null>(null);

  const handleLoginSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMsg(null);
    setInfoMsg(null);

    if (!email.trim() || !password) {
      setErrorMsg("Please enter both your email and password.");
      return;
    }

    setSubmitting(true);
    try {
      const result = await signIn(email, password);
      if (result.status === "SIGNED_IN") {
        router.push("/category");
      } else if (result.status === "NEW_PASSWORD_REQUIRED") {
        setStep("NEW_PASSWORD_REQUIRED");
        setInfoMsg(
          "Your account requires setting a permanent password before continuing."
        );
      } else if (result.status === "TOTP_REQUIRED") {
        setStep("TOTP_REQUIRED");
        setInfoMsg("Enter the 6-digit code from your Authenticator app.");
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleNewPasswordSubmit = async (
    e: React.FormEvent<HTMLFormElement>
  ) => {
    e.preventDefault();
    setErrorMsg(null);
    if (newPassword.length < 8) {
      setErrorMsg("New password must be at least 8 characters.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await completeNewPassword(newPassword);
      if (result.status === "SIGNED_IN") {
        router.push("/category");
      } else if (result.status === "TOTP_REQUIRED") {
        setStep("TOTP_REQUIRED");
        setInfoMsg("Enter the 6-digit code from your Authenticator app.");
      }
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Could not update password."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleTotpSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMsg(null);
    if (!totpCode.trim()) {
      setErrorMsg("Please enter your 6-digit authenticator code.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await submitTotpCode(totpCode);
      if (result.status === "SIGNED_IN") {
        router.push("/category");
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Invalid MFA code.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleForgotRequest = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMsg(null);
    if (!email.trim()) {
      setErrorMsg("Enter your registered email address first.");
      return;
    }
    setSubmitting(true);
    try {
      await forgotPassword(email);
      setStep("FORGOT_CONFIRM");
      setInfoMsg("Verification code sent to your email.");
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Could not send reset code."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleForgotConfirm = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMsg(null);
    if (!resetCode.trim() || newPassword.length < 8) {
      setErrorMsg("Enter the email code and a new password (min 8 chars).");
      return;
    }
    setSubmitting(true);
    try {
      await confirmForgotPassword(email, resetCode, newPassword);
      setStep("CREDENTIALS");
      setPassword("");
      setNewPassword("");
      setResetCode("");
      setInfoMsg("Password updated. You can now log in with your new password.");
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Could not reset password."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full">
      <h1 className="text-[26px] font-semibold leading-tight tracking-[-0.02em] text-[#1D1F20]">
        {step === "TOTP_REQUIRED"
          ? "Two-factor verification"
          : step === "NEW_PASSWORD_REQUIRED"
            ? "Set permanent password"
            : step === "FORGOT_REQUEST" || step === "FORGOT_CONFIRM"
              ? "Reset your password"
              : "Log in to Project A"}
      </h1>

      {step === "CREDENTIALS" && (
        <>
          <div className="mt-6 flex flex-col gap-2.5">
            <button
              type="button"
              onClick={() =>
                setInfoMsg(
                  "Google federated login is not enabled in Phase 1 — sign in with your Cognito email & password below."
                )
              }
              className="flex h-[42px] w-full items-center justify-center gap-2.5 rounded-[6px] border border-[#D1D5DB] bg-white px-4 text-[14px] font-medium text-[#1D1F20] hover:bg-[#F9FAFB] hover:border-[#9CA3AF] transition-colors cursor-pointer"
            >
              <GoogleIcon />
              <span>Continue with Google</span>
            </button>

            <button
              type="button"
              onClick={() =>
                setInfoMsg(
                  "Enterprise SSO (IAM Identity Center) is for AWS operators. Website users sign in with Cognito + MFA below."
                )
              }
              className="flex h-[42px] w-full items-center justify-center gap-2.5 rounded-[6px] border border-[#D1D5DB] bg-white px-4 text-[14px] font-medium text-[#1D1F20] hover:bg-[#F9FAFB] hover:border-[#9CA3AF] transition-colors cursor-pointer"
            >
              <KeyRound
                className="h-[16px] w-[16px] text-[#4B5563]"
                strokeWidth={1.9}
              />
              <span>Continue with SSO</span>
            </button>
          </div>

          <div className="my-6 flex items-center gap-3">
            <div className="h-px flex-1 bg-[#E5E7EB]" />
            <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-[#6B7280]">
              or
            </span>
            <div className="h-px flex-1 bg-[#E5E7EB]" />
          </div>

          <form onSubmit={handleLoginSubmit} className="space-y-4" noValidate>
            <div>
              <label
                htmlFor="login-email"
                className="block text-[13px] font-medium text-[#1D1F20]"
              >
                Email
              </label>
              <input
                id="login-email"
                name="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                className="mt-1.5 h-[42px] w-full rounded-[6px] border border-[#B6B6B6] bg-white px-3 text-[14px] text-[#1D1F20] placeholder:text-[#9CA3AF] outline-none transition-colors focus:border-[#0051C3] focus:ring-2 focus:ring-[#0051C3]/15"
              />
            </div>

            <div>
              <label
                htmlFor="login-password"
                className="block text-[13px] font-medium text-[#1D1F20]"
              >
                Password
              </label>
              <div className="relative mt-1.5">
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  className="h-[42px] w-full rounded-[6px] border border-[#B6B6B6] bg-white pl-3 pr-10 text-[14px] text-[#1D1F20] placeholder:text-[#9CA3AF] outline-none transition-colors focus:border-[#0051C3] focus:ring-2 focus:ring-[#0051C3]/15"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 flex h-7 w-7 items-center justify-center rounded text-[#6B7280] hover:bg-[#F3F4F6] hover:text-[#1D1F20] cursor-pointer"
                >
                  {showPassword ? (
                    <EyeOff className="h-[17px] w-[17px]" strokeWidth={1.8} />
                  ) : (
                    <Eye className="h-[17px] w-[17px]" strokeWidth={1.8} />
                  )}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between pt-0.5 text-[13px]">
              <label className="inline-flex items-center gap-2 text-[#374151] cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={rememberDevice}
                  onChange={(e) => setRememberDevice(e.target.checked)}
                  className="h-[15px] w-[15px] rounded border-[#B6B6B6] accent-[#EE730A] cursor-pointer"
                />
                <span>Remember this device</span>
              </label>

              <button
                type="button"
                onClick={() => {
                  setErrorMsg(null);
                  setInfoMsg(null);
                  setStep("FORGOT_REQUEST");
                }}
                className="font-medium text-[#0051C3] hover:underline cursor-pointer"
              >
                Forgot your password?
              </button>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="mt-2 flex h-[42px] w-full items-center justify-center gap-2 rounded-[6px] bg-[#EE730A] text-[14px] font-semibold text-white hover:bg-[#D96504] active:bg-[#C2560A] disabled:opacity-60 transition-colors cursor-pointer"
            >
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
              <span>{submitting ? "Signing in..." : "Log in"}</span>
            </button>
          </form>
        </>
      )}

      {step === "NEW_PASSWORD_REQUIRED" && (
        <form onSubmit={handleNewPasswordSubmit} className="mt-5 space-y-4">
          <p className="text-[13px] text-[#595959]">
            Signed in as <strong>{email}</strong>. Create your new password
            (at least 8 characters with uppercase, lowercase, number, and symbol).
          </p>
          <div>
            <label
              htmlFor="new-password"
              className="block text-[13px] font-medium text-[#1D1F20]"
            >
              New Password
            </label>
            <input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Enter permanent password"
              className="mt-1.5 h-[42px] w-full rounded-[6px] border border-[#B6B6B6] bg-white px-3 text-[14px] text-[#1D1F20] outline-none focus:border-[#0051C3] focus:ring-2 focus:ring-[#0051C3]/15"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="flex h-[42px] w-full items-center justify-center gap-2 rounded-[6px] bg-[#EE730A] text-[14px] font-semibold text-white hover:bg-[#D96504] disabled:opacity-60 cursor-pointer"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            <span>Update password &amp; continue</span>
          </button>
        </form>
      )}

      {step === "TOTP_REQUIRED" && (
        <form onSubmit={handleTotpSubmit} className="mt-5 space-y-4">
          <div className="flex items-center gap-2 text-[13px] text-[#374151]">
            <ShieldCheck className="h-4 w-4 text-[#EE730A]" />
            <span>Enter your 6-digit TOTP authenticator code.</span>
          </div>
          <input
            type="text"
            inputMode="numeric"
            maxLength={6}
            value={totpCode}
            onChange={(e) => setTotpCode(e.target.value)}
            placeholder="000000"
            className="h-[44px] w-full rounded-[6px] border border-[#B6B6B6] bg-white px-3 text-center font-mono text-[18px] tracking-[0.3em] text-[#1D1F20] outline-none focus:border-[#0051C3]"
          />
          <button
            type="submit"
            disabled={submitting}
            className="flex h-[42px] w-full items-center justify-center gap-2 rounded-[6px] bg-[#EE730A] text-[14px] font-semibold text-white hover:bg-[#D96504] disabled:opacity-60 cursor-pointer"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            <span>Verify &amp; Log in</span>
          </button>
        </form>
      )}

      {step === "FORGOT_REQUEST" && (
        <form onSubmit={handleForgotRequest} className="mt-5 space-y-4">
          <p className="text-[13px] text-[#595959]">
            We&rsquo;ll send a verification code via AWS Cognito to reset your
            password.
          </p>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@company.com"
            className="h-[42px] w-full rounded-[6px] border border-[#B6B6B6] bg-white px-3 text-[14px] text-[#1D1F20] outline-none focus:border-[#0051C3]"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setStep("CREDENTIALS")}
              className="h-[42px] flex-1 rounded-[6px] border border-[#D1D5DB] text-[13px] font-medium text-[#374151] hover:bg-[#F9FAFB] cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex h-[42px] flex-1 items-center justify-center gap-2 rounded-[6px] bg-[#EE730A] text-[13px] font-semibold text-white hover:bg-[#D96504] disabled:opacity-60 cursor-pointer"
            >
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
              <span>Send code</span>
            </button>
          </div>
        </form>
      )}

      {step === "FORGOT_CONFIRM" && (
        <form onSubmit={handleForgotConfirm} className="mt-5 space-y-4">
          <input
            type="text"
            value={resetCode}
            onChange={(e) => setResetCode(e.target.value)}
            placeholder="Verification code from email"
            className="h-[42px] w-full rounded-[6px] border border-[#B6B6B6] bg-white px-3 text-[14px] text-[#1D1F20] outline-none focus:border-[#0051C3]"
          />
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="New strong password"
            className="h-[42px] w-full rounded-[6px] border border-[#B6B6B6] bg-white px-3 text-[14px] text-[#1D1F20] outline-none focus:border-[#0051C3]"
          />
          <button
            type="submit"
            disabled={submitting}
            className="flex h-[42px] w-full items-center justify-center gap-2 rounded-[6px] bg-[#EE730A] text-[14px] font-semibold text-white hover:bg-[#D96504] disabled:opacity-60 cursor-pointer"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            <span>Confirm new password</span>
          </button>
        </form>
      )}

      {errorMsg && (
        <div
          role="alert"
          className="mt-4 rounded-[6px] border border-[#FECACA] bg-[#FEF2F2] px-3.5 py-2.5 text-[12.5px] text-[#991B1B]"
        >
          {errorMsg}
        </div>
      )}

      {infoMsg && (
        <div
          role="status"
          className="mt-4 rounded-[6px] border border-[#FED7AA] bg-[#FFF7ED] px-3.5 py-2.5 text-[12.5px] text-[#7C2D12]"
        >
          {infoMsg}
        </div>
      )}

      <div className="mt-6 space-y-2.5 text-[13px] text-[#595959]">
        <p>
          Don&rsquo;t have an account?{" "}
          <Link
            href="/register"
            className="font-medium text-[#0051C3] hover:underline"
          >
            Sign up
          </Link>
        </p>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px]">
          <Link href="/" className="text-[#0051C3] hover:underline">
            Back to Workspace
          </Link>
        </div>
      </div>
    </div>
  );
}
