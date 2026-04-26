---
sidebar_position: 1
title: Google OAuth Setup
---

# Google OAuth Setup

Enable "Sign in with Google" by creating your own OAuth client.

## Steps

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a project (or select existing)
3. Click **Create Credentials** → **OAuth Client ID**
4. Application type: **Web application**
5. Authorized redirect URIs: `http://localhost:9002/googleCallback` (and your production URL)
6. Copy the **Client ID**

## Configure

Set the client ID in your Docker Compose or `.env`:

```bash
VITE_GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
```

:::info
Google OAuth Client IDs are public identifiers (not secrets). The Client Secret stays server-side. Security is enforced by redirect URI restrictions.
:::

## Without Google OAuth

Google login is optional. Users can always register and login with email/password. If `VITE_GOOGLE_CLIENT_ID` is empty, the Google login button won't appear.
