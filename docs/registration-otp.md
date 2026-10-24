# Twilio Verify registration OTP

**Super admin → Registration OTP & Twilio** controls SMS verification for new public registrations. It starts disabled. Save Twilio credentials through **Provider provisioning & keys → Twilio registration OTP**, confirming your administrator password:

- `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`: an existing Twilio account, needed to create a new API key.
- `TWILIO_API_KEY_SID` and `TWILIO_API_KEY_SECRET`: reusable API credentials with Verify permissions; preferred by the adapter when present.
- `TWILIO_VERIFY_SERVICE_SID`: an existing Verify service, if already provisioned.

Keys, secrets and Auth Tokens remain encrypted in server settings and are not sent to the registration page. Twilio must supply the upstream account credentials; this platform does not create a Twilio account or mint its account Auth Token.

**Provision API key & Verify service** reuses saved resources or creates missing ones using Twilio's authenticated REST APIs. It stores returned secrets directly into encrypted provider settings. A durable creation marker prevents an uncertain network outcome from silently creating duplicate keys/services. Inspect Twilio, save any existing resources, then explicitly confirm reconciliation before clearing an uncertain marker. **Test service without sending SMS** uses a read-only service fetch. No live provider calls are made by the automated tests.

Set the daily SMS-request cap (1–1000, default 50), check the enable switch and save with your current administrator password. Enabling authorizes provider SMS/verification charges within that request cap; the cap is not a monetary spending limit. Twilio balance, trial restrictions, permissions, geo restrictions and delivery remain provider controlled. Requests are limited to 10 per source IP per throttle window, three per phone per hour and at least 60 seconds between sends. A trusted loopback proxy's last forwarded address is used for the IP throttle; application requests must not be routed through an untrusted proxy.

The registration form adds an international-format phone field, **Send SMS verification code** and **Verify phone**. The server accepts a code only through Twilio VerificationCheck and issues a random one-use ticket bound to that phone, valid until ten minutes after the SMS request. Tickets are hashed; phone numbers are encrypted; verification codes are not stored. The ticket is consumed in the same transaction as signup. A changed phone, replayed ticket, wrong code, expiry or attempt limit cannot bypass the gate. Five check attempts are allowed per challenge. Unknown provider outcomes are not automatically retried.

Successful signup stores the verified phone on the user profile. Changing that phone through admin profile editing removes its verified flag. This is phone possession verification, not email ownership verification, identity proofing, MFA for existing logins or a forced migration of existing users. Manual super admin account creation and first-run platform setup are exempt; an administrator creating accounts is already authenticated and rechecked.

Resources: `registration_otp.py`, `registration-otp.js`, and database tables `registration_otp_policy`, `registration_otp_challenges`, `registration_otp_usage`. Existing deployment archives include all resources and startup creates the tables. Public routes: `/api/registration/otp/status`, `start`, `check`; root console: `/api/platform/registration-otp`. No extra Python SDK is required.

Official API references: https://www.twilio.com/docs/verify/api/service ; https://www.twilio.com/docs/verify/api/verification ; https://www.twilio.com/docs/verify/api/verification-check .
