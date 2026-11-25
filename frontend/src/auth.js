import { UserManager, WebStorageStateStore } from "oidc-client-ts";

const authority = import.meta.env.VITE_OIDC_AUTHORITY || "";
const clientId = import.meta.env.VITE_OIDC_CLIENT_ID || "";
const audience = import.meta.env.VITE_OIDC_AUDIENCE || "";
const redirectUri = import.meta.env.VITE_OIDC_REDIRECT_URI || `${window.location.origin}/`;

export const authConfigured = Boolean(authority && clientId && audience);

const volatileValues = new Map();
const volatileStorage = {
  get length() { return volatileValues.size; },
  clear: () => volatileValues.clear(),
  getItem: (key) => volatileValues.get(String(key)) ?? null,
  key: (index) => Array.from(volatileValues.keys())[index] ?? null,
  removeItem: (key) => volatileValues.delete(String(key)),
  setItem: (key, value) => volatileValues.set(String(key), String(value)),
};

const userManager = authConfigured
  ? new UserManager({
      authority,
      client_id: clientId,
      redirect_uri: redirectUri,
      post_logout_redirect_uri: redirectUri,
      response_type: "code",
      scope: "openid profile email",
      extraQueryParams: { audience },
      userStore: new WebStorageStateStore({ store: volatileStorage }),
      stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
      automaticSilentRenew: false,
    })
  : null;

let initialization;

export function initializeAuth() {
  if (!authConfigured) return Promise.resolve(null);
  if (!initialization) {
    initialization = (async () => {
      const callbackUrl = new URL(window.location.href);
      if (callbackUrl.searchParams.has("code") && callbackUrl.searchParams.has("state")) {
        await userManager.signinRedirectCallback();
        window.history.replaceState(
          {},
          document.title,
          `${callbackUrl.pathname}${callbackUrl.hash}`,
        );
      } else if (callbackUrl.searchParams.has("error")) {
        throw new Error("Identity provider rejected the sign-in request.");
      }
      const user = await userManager.getUser();
      return user && !user.expired ? user : null;
    })();
  }
  return initialization;
}

export function signIn() {
  if (!userManager) throw new Error("OIDC authentication is not configured.");
  return userManager.signinRedirect();
}

export function signOut() {
  return userManager ? userManager.removeUser() : Promise.resolve();
}

export async function getAccessToken() {
  if (!userManager) return null;
  const user = await userManager.getUser();
  return user && !user.expired ? user.access_token : null;
}
