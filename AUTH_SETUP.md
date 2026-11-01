# VarshaGuard account authentication setup

The account system uses **username + password** for sign-in and **Twilio Verify over WhatsApp** to verify new accounts and authorize password resets. Twilio credentials are used only by the Flask backend.

## 1. Configure Twilio Verify

1. Create a Twilio account and a Verify Service.
2. Configure an approved/eligible WhatsApp sender for the Verify service and follow Twilio's WhatsApp onboarding requirements.
3. Copy the Account SID, Auth Token, and Verify Service SID into the backend deployment's environment variables. Never commit these values or put them in frontend JavaScript.
4. Review Twilio's WhatsApp template, recipient-consent, country availability, and pricing requirements before production use.

Required backend environment variables:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_VERIFY_SERVICE_SID`
- `SECRET_KEY`: long random value used to sign session cookies
- `DATABASE_URL`: persistent PostgreSQL connection string (recommended for deployment)
- `COOKIE_SECURE=true` on HTTPS production. For local HTTP development only, set `COOKIE_SECURE=false`.

The app can fall back to SQLite for local development. Do not use a local SQLite file as the production database on an ephemeral/serverless deployment; data may be lost between instances or redeploys. Provision persistent PostgreSQL and use its connection string as `DATABASE_URL`.

Example local environment (use your own values; do not commit a real .env file):

```env
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_VERIFY_SERVICE_SID=VA...
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URL=postgresql://user:password@host:5432/varshaguard
COOKIE_SECURE=false
```

Install dependencies with `pip install -r requirements.txt`, then start the Flask app using the project's existing run command.

## 2. Account flows

- **Sign up:** choose a unique username (3–24 letters/numbers/underscores), password (10–128 characters), and WhatsApp number in E.164 format (for example, `+919876543210`). Verify the WhatsApp code before the account is created.
- **Log in:** username + password.
- **Forgot password:** enter the WhatsApp number attached to the account, verify a fresh code, and set a new password.
- **Log out:** clears the signed session cookie.

Passwords are stored as Werkzeug password hashes, not plaintext. Account and challenge records are stored in the database. OTP verification is delegated to Twilio Verify; unverified numbers cannot complete sign-up or password reset. Challenge records expire after 10 minutes in this app, while Twilio controls the actual OTP validity.

## 3. Security and production checklist

- Use a persistent PostgreSQL database, a high-entropy `SECRET_KEY`, HTTPS, and `COOKIE_SECURE=true`.
- Keep Twilio secrets exclusively in backend environment settings.
- The Flask API requires a signed-in session for dashboard API routes other than health and auth endpoints.
- Use Twilio Verify's service limits and configure monitoring/alerts for verification spend. Add an edge/WAF rate limit for login and OTP endpoints before public launch; the app applies a 45-second resend cooldown per phone and purpose, but that is not a substitute for distributed IP/account rate limiting.
- Configure backups, database migrations, logging, and an account deletion/support process before production.
- Test signup, duplicate username, wrong/expired OTP, login, logout, password reset, API access while logged out, and persistence across a redeploy.
- The previous Firebase Google/SMS implementation is replaced for this flow; this version does not offer Google sign-in.

## Official documentation

- Twilio Verify WhatsApp: https://www.twilio.com/docs/verify/whatsapp
- Twilio Verify API: https://www.twilio.com/docs/verify/api
- Flask sessions: https://flask.palletsprojects.com/en/stable/quickstart/#sessions
