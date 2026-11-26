"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import { Eye, EyeOff, Loader2, ShieldCheck } from "lucide-react";
import { useAuth, type SignInResult } from "@/lib/auth";
import { AFTER_SIGN_IN } from "@/lib/shell-ui";

type LoginStep =
  | "CREDENTIALS"
  | "NEW_PASSWORD_REQUIRED"
  | "TOTP_REQUIRED"
  | "MFA_SETUP"
  | "FORGOT_REQUEST"
  | "FORGOT_CONFIRM";

type MfaSetupInfo = { secretCode: string; otpauthUri: string };

/** Secret shown in groups of four so it can be typed into an authenticator by hand. */
function groupSecret(secret: string): string {
  return secret.replace(/(.{4})/g, "$1 ").trim();
}

export function LoginView() {
  const router = useRouter();
  const {
    signIn,
    completeNewPassword,
    submitTotpCode,
    verifyTotpSetup,
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
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [infoMsg, setInfoMsg] = useState<string | null>(null);
  const [mfaSetup, setMfaSetup] = useState<MfaSetupInfo | null>(null);
  const [mfaQr, setMfaQr] = useState<string | null>(null);
  const [setupCode, setSetupCode] = useState("");

  // Draw the authenticator QR code in the browser; the secret never leaves this page.
  // enterMfaSetup clears the previous image, so the effect only sets state once the image is ready.
  useEffect(() => {
    if (!mfaSetup) return;
    let cancelled = false;
    QRCode.toDataURL(mfaSetup.otpauthUri, { margin: 1, width: 192 })
      .then((url) => {
        if (!cancelled) setMfaQr(url);
      })
      .catch(() => {
        if (!cancelled) setMfaQr(null);
      });
    return () => {
      cancelled = true;
    };
  }, [mfaSetup]);

  /** Moves to the authenticator setup screen when Cognito asks for MFA_SETUP. */
  const enterMfaSetup = (result: Extract<SignInResult, { status: "MFA_SETUP_REQUIRED" }>) => {
    setMfaQr(null);
    setMfaSetup({ secretCode: result.secretCode, otpauthUri: result.otpauthUri });
    setSetupCode("");
    setStep("MFA_SETUP");
    setInfoMsg(
      "Two-factor authentication is required. Add this account to an authenticator app, then enter the code it shows."
    );
  };

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
        router.push(AFTER_SIGN_IN);
      } else if (result.status === "NEW_PASSWORD_REQUIRED") {
        setStep("NEW_PASSWORD_REQUIRED");
        setInfoMsg(
          "Your account requires setting a permanent password before continuing."
        );
      } else if (result.status === "TOTP_REQUIRED") {
        setStep("TOTP_REQUIRED");
      } else if (result.status === "MFA_SETUP_REQUIRED") {
        enterMfaSetup(result);
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
        router.push(AFTER_SIGN_IN);
      } else if (result.status === "TOTP_REQUIRED") {
        setStep("TOTP_REQUIRED");
      } else if (result.status === "MFA_SETUP_REQUIRED") {
        enterMfaSetup(result);
      }
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Could not update password."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleMfaSetupSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMsg(null);
    if (!/^\d{6}$/.test(setupCode.trim())) {
      setErrorMsg("Enter the 6-digit code shown in your authenticator app.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await verifyTotpSetup(setupCode);
      if (result.status === "SIGNED_IN") {
        setMfaSetup(null);
        router.push(AFTER_SIGN_IN);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Could not verify the code.");
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
        router.push(AFTER_SIGN_IN);
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
          : step === "MFA_SETUP"
            ? "Set up two-factor authentication"
          : step === "NEW_PASSWORD_REQUIRED"
            ? "Set permanent password"
            : step === "FORGOT_REQUEST" || step === "FORGOT_CONFIRM"
              ? "Reset your password"
              : "Log in to Project A"}
      </h1>

      {step === "CREDENTIALS" && (
        <>
          <form onSubmit={handleLoginSubmit} className="mt-6 space-y-4" noValidate>
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

            <div className="flex items-center justify-end pt-0.5 text-[13px]">
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
            <span>Enter the 6-digit code from your authenticator app.</span>
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

      {step === "MFA_SETUP" && mfaSetup && (
        <form onSubmit={handleMfaSetupSubmit} className="mt-5 space-y-4">
          <ol className="list-decimal space-y-1 pl-5 text-[13px] text-[#374151]">
            <li>
              Open an authenticator app (Google Authenticator, Microsoft
              Authenticator or similar) and add an account.
            </li>
            <li>Scan this code, or type the key below by hand.</li>
            <li>Enter the 6-digit code the app shows.</li>
          </ol>
          <div className="flex justify-center">
            {mfaQr ? (
              // eslint-disable-next-line @next/next/no-img-element -- data URL drawn in the browser
              <img
                src={mfaQr}
                alt="QR code for adding Project A to an authenticator app"
                width={192}
                height={192}
                className="rounded-[6px] border border-[#E5E7EB]"
              />
            ) : (
              <div className="flex h-[192px] w-[192px] items-center justify-center rounded-[6px] border border-[#E5E7EB] text-[12px] text-[#6B7280]">
                Preparing QR code…
              </div>
            )}
          </div>
          <div>
            <p className="text-[12px] font-medium text-[#374151]">Key</p>
            <p className="mt-1 select-all break-all rounded-[6px] bg-[#F3F4F6] px-3 py-2 font-mono text-[13px] tracking-[0.08em] text-[#1D1F20]">
              {groupSecret(mfaSetup.secretCode)}
            </p>
          </div>
          <div className="flex items-center gap-2 text-[13px] text-[#374151]">
            <ShieldCheck className="h-4 w-4 text-[#EE730A]" />
            <label htmlFor="mfa-setup-code">Code from the app</label>
          </div>
          <input
            id="mfa-setup-code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={setupCode}
            onChange={(e) => setSetupCode(e.target.value)}
            placeholder="000000"
            className="h-[44px] w-full rounded-[6px] border border-[#B6B6B6] bg-white px-3 text-center font-mono text-[18px] tracking-[0.3em] text-[#1D1F20] outline-none focus:border-[#0051C3]"
          />
          <button
            type="submit"
            disabled={submitting}
            className="flex h-[42px] w-full items-center justify-center gap-2 rounded-[6px] bg-[#EE730A] text-[14px] font-semibold text-white hover:bg-[#D96504] disabled:opacity-60 cursor-pointer"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            <span>Verify &amp; finish</span>
          </button>
        </form>
      )}

      {step === "FORGOT_REQUEST" && (
        <form onSubmit={handleForgotRequest} className="mt-5 space-y-4">
          <p className="text-[13px] text-[#595959]">
            We&rsquo;ll email you a code to reset your password.
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
      </div>
    </div>
  );
}
