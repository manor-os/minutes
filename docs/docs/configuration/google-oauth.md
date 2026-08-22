---
sidebar_position: 1
title: Google OAuth Setup
---

# Google OAuth Setup

Cloud edition supports Google sign-in alongside Manor OAuth.

## Steps

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a project (or select existing)
3. Click **Create Credentials** -> **OAuth Client ID**
4. Application type: **Web application**
5. Authorized redirect URIs: `https://minutes.manorai.xyz/googleCallback` (and your local callback if needed)
6. Copy the **Client ID**

## Configure

Set the client ID and callback URL:

```bash
VITE_GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
VITE_GOOGLE_REDIRECT_URI=https://minutes.manorai.xyz/googleCallback
MANOR_GOOGLE_OAUTH_URL=https://app.manorai.xyz/api/v1/auth/oauth/google
MANOR_GOOGLE_PROFILE_URL=https://app.manorai.xyz/api/v1/auth/me
```

The frontend receives a Google authorization code, then the cloud backend exchanges it through Manor's Google OAuth API and returns a Minutes JWT. Do not configure a `VITE_GOOGLE_CLIENT_SECRET`; frontend `VITE_*` variables are public.

Community edition still uses local email/password accounts and does not enable cloud OAuth routes.
