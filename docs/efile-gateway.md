# Authorized e-file gateway integration contract

**This is a DOBHRAP-specific interface, not an IRS API or a promise that a commercial provider exposes these routes.** Select an authorized provider, implement a bridge translating this interface to its approved submission API, and test it before enabling transmission. No gateway server or provider-specific bridge is included in this repository.

Configure a server-owned HTTPS `EFILE_GATEWAY_URL` and a narrowly scoped `EFILE_GATEWAY_TOKEN`. Redirects are not followed. Authentication is `Authorization: Bearer <token>`.

## POST /submissions

Request JSON:

```json
{
  "idempotency_key": "persistent-dobhrap-job-uuid",
  "provider_return_id": "provider_prepared_return_reference",
  "signature_authorization_id": "provider_signature_reference",
  "form": "1040",
  "tax_year": "2026",
  "consent_confirmed": true
}
```

The bridge must validate the return belongs to the correct organization, validate the exact return version and taxpayer signature, validate year/form coverage, deduplicate the idempotency key durably, enforce provider authorization and translate to the chosen provider API. Reusing a key with a different payload must fail. The reference must identify an immutable, validated filing package, not a mutable draft. DOBHRAP does not capture the signature itself.

Return a stable identifier:

```json
{"id":"submission_reference","status":"received"}
```

Returning success means the gateway received the submission. It must not fabricate tax-authority acceptance. Identifiers must match `[A-Za-z0-9_-]{1,160}`.

## GET /submissions/{id}

Return the current provider/authority acknowledgement:

```json
{
  "id": "submission_reference",
  "status": "accepted",
  "authority_submission_id": "actual-authority-reference",
  "acknowledged_at": "2026-10-16T12:00:00Z",
  "rejection_codes": []
}
```

Pending, rejected and processing states must remain distinguishable from accepted. An authenticated gateway status response is displayed to the administrator as provider data; DOBHRAP does not independently verify IRS acknowledgements. Redact sensitive information from errors and logs.

## Acceptance testing

Before live enablement test: invalid/expired authorization, wrong organization, unsigned or changed return, unsupported form/year, duplicate keys, payload conflicts, network timeout after provider acceptance, rejection details and eventual acknowledgement. Run only synthetic taxpayer data in sandbox. For an uncertain DOBHRAP job reconcile the gateway/provider console before creating any replacement workflow.
