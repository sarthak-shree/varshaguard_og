# Authentication setup

VarshaGuard uses Firebase Authentication for passwordless Google sign-in and phone-number OTP delivered by **SMS**. The UI does not implement a custom password store.

## One-time setup

1. Create/open a project at https://console.firebase.google.com/.
2. In **Authentication → Sign-in method**, enable **Google** and **Phone**.
3. In **Authentication → Settings → Authorized domains**, add the production domain and any local development host.
4. Register a Web app in Project settings and copy its web configuration into `frontend/firebase-config.js`. This browser config is public by design; protect your project with authorized domains, security rules, quotas, and App Check where appropriate. Never place service-account credentials in frontend files.
5. Test phone sign-in using Firebase's test phone numbers first. Production SMS delivery may incur charges and is subject to Firebase quotas and regional availability.
6. Deploy and test Google login, OTP send/verify, direct access to protected dashboard pages, and logout.

## What is protected

The client-side auth guard redirects unauthenticated visitors from the main dashboard and Bihar Live page to `/login.html`. Firebase persists the signed-in browser session; logout calls Firebase `signOut`. This is a frontend access gate, not backend authorization. Before protecting private data or privileged API operations, verify Firebase ID tokens on the Flask backend and enforce authorization server-side.

## If you specifically want WhatsApp OTP

Firebase Phone Authentication sends OTP by SMS; it does not deliver its built-in phone OTP through WhatsApp. For WhatsApp OTP, use **Twilio Verify with the WhatsApp channel** (or Meta WhatsApp Business Platform Cloud API with an approved authentication template and your own OTP verification/session backend). Twilio Verify is the simpler managed verification option; it requires a Twilio account, a WhatsApp-enabled sender, and server-side credentials stored as environment variables. Do not put Twilio auth tokens in browser JavaScript. WhatsApp OTP is not wired into this Firebase-only implementation.

Official docs:
- Firebase Google sign-in: https://firebase.google.com/docs/auth/web/google-signin
- Firebase phone auth: https://firebase.google.com/docs/auth/web/phone-auth
- Twilio Verify WhatsApp: https://www.twilio.com/docs/verify/whatsapp
