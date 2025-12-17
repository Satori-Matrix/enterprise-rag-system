# Google OAuth Setup Guide for Chainlit
**Date**: December 12, 2025  
**System**: Your Company RAG Chat Interface  
**URL**: https://chat.your-domain.com

---

## ✅ STEP 1: Create Google Cloud Project

1. Go to: https://console.cloud.google.com/
2. Click "Select a project" → "NEW PROJECT"
3. Name: `Your Company Chainlit`
4. Click "CREATE"

---

## ✅ STEP 2: Configure OAuth Consent Screen

1. In Google Cloud Console, go to: **APIs & Services** → **OAuth consent screen**
   - Direct link: https://console.cloud.google.com/apis/credentials/consent
2. Choose: **External** (allows any Gmail user you whitelist)
3. Click **"CREATE"**

**Fill in the form:**
- **App name**: `Your Company Knowledge Assistant`
- **User support email**: `asimt7382@gmail.com` (your email)
- **App logo**: (optional - skip for now)
- **Application home page**: `https://chat.your-domain.com`
- **Authorized domains**: Click "ADD DOMAIN" → enter `hstgr.cloud`
- **Developer contact email**: `asimt7382@gmail.com`

4. Click **"SAVE AND CONTINUE"**

**Scopes page:**
- Click **"ADD OR REMOVE SCOPES"**
- Find and select:
  - ✅ `userinfo.email`
  - ✅ `userinfo.profile`
  - ✅ `openid`
- Click **"UPDATE"**
- Click **"SAVE AND CONTINUE"**

**Test users page:**
- Click **"ADD USERS"**
- Add these emails (one per line):
  ```
  asimt7382@gmail.com
  info@revivebattery.eu
  tsim-2000@hotmail.com
  ananta.revive@gmail.com
  chepkemoi.projectmanager@gmail.com
  sharan.lb08@gmail.com
  ```
- Click **"ADD"**
- Click **"SAVE AND CONTINUE"**

**Summary page:**
- Review and click **"BACK TO DASHBOARD"**

---

## ✅ STEP 3: Create OAuth 2.0 Credentials

1. Go to: **APIs & Services** → **Credentials**
   - Direct link: https://console.cloud.google.com/apis/credentials
2. Click **"CREATE CREDENTIALS"** → **"OAuth client ID"**
3. Application type: **"Web application"**
4. Name: `Chainlit Web App`

**Authorized JavaScript origins:**
- Click **"ADD URI"**
- Add: `https://chat.your-domain.com`

**Authorized redirect URIs:**
- Click **"ADD URI"**
- Add: `https://chat.your-domain.com/auth/oauth/google/callback`

5. Click **"CREATE"**

**IMPORTANT - COPY THESE VALUES:**
```
Client ID: [Copy this - looks like: 123456789-abc.apps.googleusercontent.com]
Client Secret: [Copy this - looks like: GOCSPX-abc123def456]
```

⚠️ **Keep these safe! You'll need them in the next step.**

---

## ✅ STEP 4: Update Chainlit Configuration

**Update `/root/chainlit-revive/.env`:**

Replace these lines:
```
OAUTH_GOOGLE_CLIENT_ID=placeholder
OAUTH_GOOGLE_CLIENT_SECRET=placeholder
```

With your actual values:
```
OAUTH_GOOGLE_CLIENT_ID=<your-client-id>
OAUTH_GOOGLE_CLIENT_SECRET=<your-client-secret>
```

**Remove Microsoft OAuth (not needed):**
```
OAUTH_AZURE_AD_CLIENT_ID=placeholder
OAUTH_AZURE_AD_CLIENT_SECRET=placeholder
OAUTH_AZURE_AD_TENANT_ID=common
```

---

## ✅ STEP 5: Update Chainlit app.py

Modify the authentication to use OAuth with email whitelist.

---

## ✅ STEP 6: Rebuild and Test

```bash
cd /root/chainlit-revive
docker compose down
docker compose up -d --build
```

**Test:**
1. Go to: https://chat.your-domain.com
2. Click "Sign in with Google"
3. Choose your Google account
4. Authorize the app
5. You should be logged in!

---

## 🔒 Security Notes

- Only whitelisted emails can access
- OAuth tokens expire automatically
- No passwords to manage
- Google handles authentication security

---

## ⚠️ Troubleshooting

**Error: "redirect_uri_mismatch"**
- Check redirect URI exactly matches: `https://chat.your-domain.com/auth/oauth/google/callback`
- No trailing slash!

**Error: "Access blocked"**
- Make sure user email is in the Test Users list
- App must be in "Testing" mode (not Published)

**"Sign in with Google" button not showing**
- Check .env has correct Client ID
- Rebuild container: `docker compose up -d --build`

---

**Status**: Ready for configuration
**Next**: Waiting for Google Cloud credentials from user

