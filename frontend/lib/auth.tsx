"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserAttribute,
  CognitoUserPool,
  CognitoUserSession,
} from "amazon-cognito-identity-js";
import { AWS_CONFIG } from "./config";

export type CognitoGroup = "team_admin" | "field_team" | "datagent";

export interface AuthUser {
  sub: string;
  email: string;
  groups: CognitoGroup[];
  approved: boolean;
}

export type SignInResult =
  | { status: "SIGNED_IN"; user: AuthUser }
  | { status: "NEW_PASSWORD_REQUIRED"; email: string }
  | { status: "TOTP_REQUIRED"; email: string };

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isApproved: boolean;
  hasGroup: (...allowed: CognitoGroup[]) => boolean;
  getIdToken: (forceRefresh?: boolean) => Promise<string | null>;
  signIn: (email: string, password: string) => Promise<SignInResult>;
  completeNewPassword: (newPassword: string) => Promise<SignInResult>;
  submitTotpCode: (code: string) => Promise<SignInResult>;
  signUp: (email: string, password: string) => Promise<{ userConfirmed: boolean }>;
  confirmSignUp: (email: string, code: string) => Promise<void>;
  resendConfirmationCode: (email: string) => Promise<void>;
  forgotPassword: (email: string) => Promise<void>;
  confirmForgotPassword: (
    email: string,
    code: string,
    newPassword: string
  ) => Promise<void>;
  signOut: () => void;
}

const VALID_GROUPS = new Set<CognitoGroup>([
  "team_admin",
  "field_team",
  "datagent",
]);

function getUserPool(): CognitoUserPool {
  return new CognitoUserPool({
    UserPoolId: AWS_CONFIG.cognitoUserPoolId,
    ClientId: AWS_CONFIG.cognitoClientId,
  });
}

function extractUserFromSession(session: CognitoUserSession): AuthUser {
  const payload = session.getIdToken().decodePayload() as Record<string, unknown>;
  const rawGroups = payload["cognito:groups"];
  const list = Array.isArray(rawGroups)
    ? rawGroups.map(String)
    : typeof rawGroups === "string" && rawGroups
      ? rawGroups.split(",").map((g) => g.trim())
      : [];

  const groups = list.filter((g): g is CognitoGroup =>
    VALID_GROUPS.has(g as CognitoGroup)
  );

  return {
    sub: String(payload["sub"] ?? ""),
    email: String(payload["email"] ?? payload["cognito:username"] ?? ""),
    groups,
    approved: groups.length > 0,
  };
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const pendingChallengeUserRef = useRef<CognitoUser | null>(null);
  const pendingChallengeAttrsRef = useRef<Record<string, unknown>>({});

  // Restore existing Cognito session on mount
  useEffect(() => {
    let active = true;
    try {
      const pool = getUserPool();
      const current = pool.getCurrentUser();
      if (!current) {
        setIsLoading(false);
        return;
      }
      current.getSession(
        (err: Error | null, session: CognitoUserSession | null) => {
          if (!active) return;
          if (!err && session && session.isValid()) {
            setUser(extractUserFromSession(session));
          } else {
            setUser(null);
          }
          setIsLoading(false);
        }
      );
    } catch {
      if (active) {
        setUser(null);
        setIsLoading(false);
      }
    }
    return () => {
      active = false;
    };
  }, []);

  const getIdToken = useCallback(
    async (forceRefresh = false): Promise<string | null> => {
      const pool = getUserPool();
      const current = pool.getCurrentUser();
      if (!current) return null;

      return new Promise<string | null>((resolve) => {
        current.getSession(
          (err: Error | null, session: CognitoUserSession | null) => {
            if (err || !session) {
              setUser(null);
              resolve(null);
              return;
            }
            if (!forceRefresh && session.isValid()) {
              resolve(session.getIdToken().getJwtToken());
              return;
            }
            const refreshToken = session.getRefreshToken();
            current.refreshSession(
              refreshToken,
              (rErr: Error | null, refreshed: CognitoUserSession | null) => {
                if (rErr || !refreshed) {
                  setUser(null);
                  resolve(null);
                  return;
                }
                setUser(extractUserFromSession(refreshed));
                resolve(refreshed.getIdToken().getJwtToken());
              }
            );
          }
        );
      });
    },
    []
  );

  const signIn = useCallback(
    async (email: string, password: string): Promise<SignInResult> => {
      const normalized = email.trim().toLowerCase();
      const pool = getUserPool();
      const cognitoUser = new CognitoUser({ Username: normalized, Pool: pool });
      const authDetails = new AuthenticationDetails({
        Username: normalized,
        Password: password,
      });

      return new Promise<SignInResult>((resolve, reject) => {
        cognitoUser.authenticateUser(authDetails, {
          onSuccess: (session) => {
            pendingChallengeUserRef.current = null;
            const authUser = extractUserFromSession(session);
            setUser(authUser);
            resolve({ status: "SIGNED_IN", user: authUser });
          },
          onFailure: (err) => {
            reject(new Error(err?.message || "Invalid email or password."));
          },
          newPasswordRequired: (userAttributes) => {
            pendingChallengeUserRef.current = cognitoUser;
            const cleaned = { ...(userAttributes as Record<string, unknown>) };
            delete cleaned.email_verified;
            delete cleaned.email;
            pendingChallengeAttrsRef.current = cleaned;
            resolve({ status: "NEW_PASSWORD_REQUIRED", email: normalized });
          },
          totpRequired: () => {
            pendingChallengeUserRef.current = cognitoUser;
            resolve({ status: "TOTP_REQUIRED", email: normalized });
          },
        });
      });
    },
    []
  );

  const completeNewPassword = useCallback(
    async (newPassword: string): Promise<SignInResult> => {
      const cognitoUser = pendingChallengeUserRef.current;
      if (!cognitoUser) {
        throw new Error("No pending password challenge. Please log in again.");
      }
      return new Promise<SignInResult>((resolve, reject) => {
        cognitoUser.completeNewPasswordChallenge(
          newPassword,
          pendingChallengeAttrsRef.current,
          {
            onSuccess: (session) => {
              pendingChallengeUserRef.current = null;
              const authUser = extractUserFromSession(session);
              setUser(authUser);
              resolve({ status: "SIGNED_IN", user: authUser });
            },
            onFailure: (err) => {
              reject(
                new Error(err?.message || "Failed to update temporary password.")
              );
            },
            totpRequired: () => {
              resolve({
                status: "TOTP_REQUIRED",
                email: cognitoUser.getUsername(),
              });
            },
          }
        );
      });
    },
    []
  );

  const submitTotpCode = useCallback(async (code: string): Promise<SignInResult> => {
    const cognitoUser = pendingChallengeUserRef.current;
    if (!cognitoUser) {
      throw new Error("No pending MFA challenge. Please log in again.");
    }
    return new Promise<SignInResult>((resolve, reject) => {
      cognitoUser.sendMFACode(
        code.trim(),
        {
          onSuccess: (session) => {
            pendingChallengeUserRef.current = null;
            const authUser = extractUserFromSession(session);
            setUser(authUser);
            resolve({ status: "SIGNED_IN", user: authUser });
          },
          onFailure: (err) => {
            reject(new Error(err?.message || "Invalid MFA verification code."));
          },
        },
        "SOFTWARE_TOKEN_MFA"
      );
    });
  }, []);

  const signUp = useCallback(
    async (
      email: string,
      password: string
    ): Promise<{ userConfirmed: boolean }> => {
      const normalized = email.trim().toLowerCase();
      const pool = getUserPool();
      const attrs = [
        new CognitoUserAttribute({ Name: "email", Value: normalized }),
      ];

      return new Promise((resolve, reject) => {
        pool.signUp(normalized, password, attrs, [], (err, result) => {
          if (err || !result) {
            reject(new Error(err?.message || "Registration failed."));
            return;
          }
          resolve({ userConfirmed: Boolean(result.userConfirmed) });
        });
      });
    },
    []
  );

  const confirmSignUp = useCallback(
    async (email: string, code: string): Promise<void> => {
      const pool = getUserPool();
      const cognitoUser = new CognitoUser({
        Username: email.trim().toLowerCase(),
        Pool: pool,
      });
      return new Promise((resolve, reject) => {
        cognitoUser.confirmRegistration(code.trim(), true, (err) => {
          if (err) {
            reject(new Error(err?.message || "Verification code invalid."));
            return;
          }
          resolve();
        });
      });
    },
    []
  );

  const resendConfirmationCode = useCallback(
    async (email: string): Promise<void> => {
      const pool = getUserPool();
      const cognitoUser = new CognitoUser({
        Username: email.trim().toLowerCase(),
        Pool: pool,
      });
      return new Promise((resolve, reject) => {
        cognitoUser.resendConfirmationCode((err) => {
          if (err) {
            reject(new Error(err?.message || "Could not resend code."));
            return;
          }
          resolve();
        });
      });
    },
    []
  );

  const forgotPassword = useCallback(async (email: string): Promise<void> => {
    const pool = getUserPool();
    const cognitoUser = new CognitoUser({
      Username: email.trim().toLowerCase(),
      Pool: pool,
    });
    return new Promise((resolve, reject) => {
      cognitoUser.forgotPassword({
        onSuccess: () => resolve(),
        onFailure: (err) =>
          reject(new Error(err?.message || "Could not start password reset.")),
      });
    });
  }, []);

  const confirmForgotPassword = useCallback(
    async (email: string, code: string, newPassword: string): Promise<void> => {
      const pool = getUserPool();
      const cognitoUser = new CognitoUser({
        Username: email.trim().toLowerCase(),
        Pool: pool,
      });
      return new Promise((resolve, reject) => {
        cognitoUser.confirmPassword(code.trim(), newPassword, {
          onSuccess: () => resolve(),
          onFailure: (err) =>
            reject(new Error(err?.message || "Password reset failed.")),
        });
      });
    },
    []
  );

  const signOut = useCallback(() => {
    const pool = getUserPool();
    const current = pool.getCurrentUser();
    current?.signOut();
    pendingChallengeUserRef.current = null;
    setUser(null);
  }, []);

  const hasGroup = useCallback(
    (...allowed: CognitoGroup[]) => {
      if (!user) return false;
      return allowed.some((g) => user.groups.includes(g));
    },
    [user]
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      isAuthenticated: Boolean(user),
      isApproved: Boolean(user?.approved),
      hasGroup,
      getIdToken,
      signIn,
      completeNewPassword,
      submitTotpCode,
      signUp,
      confirmSignUp,
      resendConfirmationCode,
      forgotPassword,
      confirmForgotPassword,
      signOut,
    }),
    [
      user,
      isLoading,
      hasGroup,
      getIdToken,
      signIn,
      completeNewPassword,
      submitTotpCode,
      signUp,
      confirmSignUp,
      resendConfirmationCode,
      forgotPassword,
      confirmForgotPassword,
      signOut,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
}
