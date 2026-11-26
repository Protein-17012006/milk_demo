"use client";

import React, { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, Circle, Eye, EyeOff, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth";

export function RegisterView() {
  const router = useRouter();
  const { signUp, confirmSignUp, resendConfirmationCode } = useAuth();

  const [step, setStep] = useState<"FORM" | "CONFIRM" | "DONE">("FORM");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [infoMsg, setInfoMsg] = useState<string | null>(null);

  const passwordChecks = useMemo(
    () => [
      { label: "At least 8 characters", met: password.length >= 8 },
      { label: "Contains 1 number", met: /\d/.test(password) },
      {
        label: "Contains uppercase & lowercase letters",
        met: /[a-z]/.test(password) && /[A-Z]/.test(password),
      },
      {
        label: "Contains 1 special character",
        met: /[^A-Za-z0-9]/.test(password),
      },
    ],
    [password]
  );

  const allRulesMet = passwordChecks.every((r) => r.met);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMsg(null);
    setInfoMsg(null);

    if (!email.trim()) {
      setErrorMsg("Please enter a valid email address.");
      return;
    }
    if (!allRulesMet) {
      setErrorMsg("Password must satisfy all security criteria above.");
      return;
    }
    if (password !== confirmPassword) {
      setErrorMsg("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    try {
      const { userConfirmed } = await signUp(email, password);
      if (userConfirmed) {
        setStep("DONE");
      } else {
        setStep("CONFIRM");
        setInfoMsg(
          `A 6-digit verification code has been sent to ${email.trim().toLowerCase()}.`
        );
      }
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Could not create account."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleConfirmCode = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMsg(null);
    if (!verificationCode.trim()) {
      setErrorMsg("Please enter the verification code from your email.");
      return;
    }
    setSubmitting(true);
    try {
      await confirmSignUp(email, verificationCode);
      setStep("DONE");
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Verification code is invalid."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleResend = async () => {
    setErrorMsg(null);
    try {
      await resendConfirmationCode(email);
      setInfoMsg("A fresh verification code was sent to your email.");
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Could not resend code."
      );
    }
  };

  return (
    <div className="w-full">
      <h1 className="text-[26px] font-semibold leading-tight tracking-[-0.02em] text-[#1D1F20]">
        {step === "CONFIRM"
          ? "Verify your email"
          : step === "DONE"
            ? "Account created"
            : "Create your Project A account"}
      </h1>
      <p className="mt-1.5 text-[13.5px] font-normal text-[#595959]">
        {step === "DONE"
          ? "Your email is verified. An administrator has to approve the account before it can see shelf data."
          : "Get started with shelf monitoring and store analytics in minutes."}
      </p>

      {step === "FORM" && (
        <>
          <form onSubmit={handleSubmit} className="mt-6 space-y-4" noValidate>
            <div>
              <label
                htmlFor="register-email"
                className="block text-[13px] font-medium text-[#1D1F20]"
              >
                Email
              </label>
              <input
                id="register-email"
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
                htmlFor="register-password"
                className="block text-[13px] font-medium text-[#1D1F20]"
              >
                Password
              </label>
              <div className="relative mt-1.5">
                <input
                  id="register-password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Create a strong password"
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

              <ul className="mt-2.5 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                {passwordChecks.map((rule) => (
                  <li
                    key={rule.label}
                    className={`flex items-center gap-1.5 text-[12px] transition-colors ${
                      rule.met ? "text-[#16A34A]" : "text-[#6B7280]"
                    }`}
                  >
                    {rule.met ? (
                      <Check className="h-3.5 w-3.5 shrink-0" strokeWidth={2.4} />
                    ) : (
                      <Circle
                        className="h-3 w-3 shrink-0 text-[#9CA3AF]"
                        strokeWidth={2}
                      />
                    )}
                    <span>{rule.label}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <label
                htmlFor="register-confirm"
                className="block text-[13px] font-medium text-[#1D1F20]"
              >
                Confirm Password
              </label>
              <div className="relative mt-1.5">
                <input
                  id="register-confirm"
                  name="confirmPassword"
                  type={showConfirm ? "text" : "password"}
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Re-enter your password"
                  className="h-[42px] w-full rounded-[6px] border border-[#B6B6B6] bg-white pl-3 pr-10 text-[14px] text-[#1D1F20] placeholder:text-[#9CA3AF] outline-none transition-colors focus:border-[#0051C3] focus:ring-2 focus:ring-[#0051C3]/15"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirm((prev) => !prev)}
                  aria-label={
                    showConfirm
                      ? "Hide confirm password"
                      : "Show confirm password"
                  }
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 flex h-7 w-7 items-center justify-center rounded text-[#6B7280] hover:bg-[#F3F4F6] hover:text-[#1D1F20] cursor-pointer"
                >
                  {showConfirm ? (
                    <EyeOff className="h-[17px] w-[17px]" strokeWidth={1.8} />
                  ) : (
                    <Eye className="h-[17px] w-[17px]" strokeWidth={1.8} />
                  )}
                </button>
              </div>
            </div>

            <p className="pt-0.5 text-[12px] leading-relaxed text-[#595959]">
              A new account needs an administrator&apos;s approval before it can see shelf data.
            </p>

            <button
              type="submit"
              disabled={submitting}
              className="flex h-[42px] w-full items-center justify-center gap-2 rounded-[6px] bg-[#EE730A] text-[14px] font-semibold text-white hover:bg-[#D96504] active:bg-[#C2560A] disabled:opacity-60 transition-colors cursor-pointer"
            >
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
              <span>{submitting ? "Creating account..." : "Sign up"}</span>
            </button>
          </form>
        </>
      )}

      {step === "CONFIRM" && (
        <form onSubmit={handleConfirmCode} className="mt-5 space-y-4">
          <input
            type="text"
            inputMode="numeric"
            value={verificationCode}
            onChange={(e) => setVerificationCode(e.target.value)}
            placeholder="Enter 6-digit verification code"
            className="h-[44px] w-full rounded-[6px] border border-[#B6B6B6] bg-white px-3 text-center font-mono text-[16px] tracking-[0.25em] text-[#1D1F20] outline-none focus:border-[#0051C3]"
          />
          <button
            type="submit"
            disabled={submitting}
            className="flex h-[42px] w-full items-center justify-center gap-2 rounded-[6px] bg-[#EE730A] text-[14px] font-semibold text-white hover:bg-[#D96504] disabled:opacity-60 cursor-pointer"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            <span>Verify email</span>
          </button>
          <button
            type="button"
            onClick={handleResend}
            className="w-full text-center text-[13px] font-medium text-[#0051C3] hover:underline cursor-pointer"
          >
            Resend verification code
          </button>
        </form>
      )}

      {step === "DONE" && (
        <div className="mt-5 space-y-4">
          <div className="rounded-[8px] border border-[#BBF7D0] bg-[#F0FDF4] p-4 text-[13px] text-[#166534]">
            Email verified for <strong>{email}</strong>. You can sign in now; shelf data appears once an
            administrator approves the account.
          </div>
          <button
            type="button"
            onClick={() => router.push("/login")}
            className="flex h-[42px] w-full items-center justify-center rounded-[6px] bg-[#EE730A] text-[14px] font-semibold text-white hover:bg-[#D96504] cursor-pointer"
          >
            Continue to Log in
          </button>
        </div>
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

      <div className="mt-6 flex flex-wrap items-center justify-between gap-2 text-[13px] text-[#595959]">
        <p>
          Already have an account?{" "}
          <Link
            href="/login"
            className="font-medium text-[#0051C3] hover:underline"
          >
            Log in
          </Link>
        </p>
        <Link href="/" className="text-[12.5px] text-[#0051C3] hover:underline">
          Back to Workspace
        </Link>
      </div>
    </div>
  );
}
