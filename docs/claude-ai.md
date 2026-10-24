# Claude AI assistant

Claude is available as an administrator-selected provider for the prepaid text AI assistant. It uses Anthropic's Messages API with an independent encrypted API key. Existing OpenAI policies and request histories remain compatible. This change does not switch the separate tax-document extraction or support-ticket AI pipelines to Claude.

After deploying with `ansible/pull-and-deploy.yml`:

1. Open **Super admin → Provider provisioning & keys → Claude AI**. Save `ANTHROPIC_API_KEY` and the exact `CLAUDE_MODEL` available to your Anthropic project. Confirm your administrator password. Blank key fields preserve the saved key. Never paste API keys into chat.
2. Use **Test claude** to check the selected model via the read-only Models API. This does not purchase a generated response or verify every generation capability.
3. Open **AI assistant → Manage AI service pricing**, select **Anthropic Claude**, enter the exact model ID and current input, cached-read and output USD prices per million tokens. Verify the rates against your provider project before enabling requests. Rates are per provider/model; do not reuse OpenAI prices for Claude.
4. Users see the selected provider in the consent and maximum-charge confirmation. Their USD balance reserves a maximum charge, settles verified actual token usage at provider cost × 1.30 rounded up once to cents, and releases the unused reservation.

Requests are independent plain text messages. Documents, prior conversations and account records are not automatically shared. There is no automatic provider fallback or paid retry. Errors and unsupported usage retain a reconciliation hold for administrator review. Cache writes, tools, images, nonstandard service tiers and externally negotiated discounts are unsupported; unexpected usage must be reconciled rather than silently priced. Responses ending at the output-token limit are still billed for returned usage.

References: https://platform.claude.com/docs/en/api/messages/create ; https://platform.claude.com/docs/en/api/versioning ; https://platform.claude.com/docs/en/about-claude/pricing . API version is pinned to `2026-10-21`; update only after compatibility review. No live API calls or credentials are required for the automated mocked tests.
