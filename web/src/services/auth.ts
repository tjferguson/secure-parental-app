import { Amplify } from 'aws-amplify';
import {
  signIn as amplifySignIn,
  signUp as amplifySignUp,
  signOut as amplifySignOut,
  getCurrentUser as amplifyGetCurrentUser,
  fetchAuthSession,
} from 'aws-amplify/auth';
import { config } from '../config';

export interface AuthUser {
  userId: string;
  email: string;
}

export function configureAuth(): void {
  if (config.localDev) {
    console.log('[Auth] Local dev mode — skipping Amplify configuration');
    return;
  }

  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: config.cognitoUserPoolId,
        userPoolClientId: config.cognitoClientId,
      },
    },
  });
}

export async function signIn(
  email: string,
  password: string
): Promise<AuthUser> {
  if (config.localDev) {
    console.log('[Auth] Local dev sign-in for', email);
    return { userId: 'dev-parent-001', email };
  }

  const result = await amplifySignIn({ username: email, password });
  if (result.isSignedIn) {
    return getCurrentUser();
  }
  throw new Error('Sign-in was not completed. Additional steps may be required.');
}

export async function signUp(
  email: string,
  password: string
): Promise<void> {
  if (config.localDev) {
    console.log('[Auth] Local dev sign-up for', email);
    return;
  }

  await amplifySignUp({
    username: email,
    password,
    options: {
      userAttributes: { email },
    },
  });
}

export async function signOut(): Promise<void> {
  if (config.localDev) {
    console.log('[Auth] Local dev sign-out');
    return;
  }

  await amplifySignOut();
}

export async function getCurrentUser(): Promise<AuthUser> {
  if (config.localDev) {
    return { userId: 'dev-parent-001', email: 'dev@local.test' };
  }

  const user = await amplifyGetCurrentUser();
  return {
    userId: user.userId,
    email: user.signInDetails?.loginId ?? '',
  };
}

export async function getAuthToken(): Promise<string> {
  if (config.localDev) {
    return 'dev-mock-jwt-token';
  }

  const session = await fetchAuthSession();
  const token = session.tokens?.idToken?.toString();
  if (!token) {
    throw new Error('No auth token available — user may not be signed in.');
  }
  return token;
}
