// What the frame around every signed-in page shows, and where sign-in leads.

/** Every account lands on the Dashboard: it answers "what is on the shelf now", the first thing a viewer asks. */
export const AFTER_SIGN_IN = "/dashboard";

export type ShellState = "loading" | "to-login" | "waiting" | "ready";

/**
 * loading: the saved session is still being read, so nobody is sent anywhere yet.
 * to-login: nobody is signed in; the pages have nothing to show.
 * waiting: signed in, but no administrator has approved the account yet.
 */
export function shellState(a: { isLoading: boolean; isAuthenticated: boolean; isApproved: boolean }): ShellState {
  if (a.isLoading) return "loading";
  if (!a.isAuthenticated) return "to-login";
  return a.isApproved ? "ready" : "waiting";
}

export const WAITING_TEXT =
  "Your account is waiting for approval. An administrator has to approve it before shelf data appears.";
