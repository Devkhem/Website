# TikTok Developer Setup

Developer portal:

- `https://developers.tiktok.com/`
- App URL: `https://developers.tiktok.com/app/7639043122118690837/pending`
- App ID: `7639043122118690837`
- Current app status: pending

Target account:

- `@thatslife6969`

## Fastest Practical Path

Start with manual posting from the Agent-generated queue while preparing the official developer integration. This avoids waiting for app approval before the first revenue test.

## Developer Setup Checklist

1. Create or log in to a TikTok Developer account.
2. Use the existing app: `7639043122118690837`.
3. Add Login Kit if OAuth authorization is needed.
4. Add Content Posting API to the app.
5. Configure redirect URI.
6. Request required scopes:
   - `video.upload` for uploading drafts/inbox items
   - `video.publish` for Direct Post
   - `user.info.basic` for account identification where needed
7. Have `@thatslife6969` authorize the app.
8. Store tokens locally in `.env`, never in source files.
9. First test with draft/private flow.
10. Apply for audit before attempting public Direct Post at scale.

## If The App Page Says Pending

Pending usually means TikTok is still reviewing or waiting for required app details. Check these items on the app page:

- App name and description are filled in
- Website/App URL is filled in if required
- Privacy Policy URL is filled in if required
- Terms of Service URL is filled in if required
- Redirect URI is set to `http://localhost:8080/tiktok/callback` for local testing
- Content Posting API product is added
- Requested scopes include `video.upload` first
- Scope/app review form is submitted

Do not wait for full Direct Post approval before starting content tests. Keep posting manually to `@thatslife6969` while the app is pending.

## Site Verification Token

TikTok verification token:

```text
tiktok-developers-site-verification=NXqfMa78DDVE3kfChv83eL0tFQQ8Y3p6
```

If you selected **Domain** verification, add this as a DNS TXT record on the domain you own:

```text
Type: TXT
Name/Host: @
Value: tiktok-developers-site-verification=NXqfMa78DDVE3kfChv83eL0tFQQ8Y3p6
```

If you selected **URL prefix** verification, upload this file to the verified URL prefix:

```text
public/tiktok-developers-site-verification.txt
```

Current Netlify verification URL:

```text
https://spontaneous-conkies-a04ee3.netlify.app/tiktok-developers-site-verification.txt
```

This project is configured for Netlify static deploy through `netlify.toml`. See:

```text
docs/netlify-verification-deploy.md
```

The public URL should return exactly:

```text
tiktok-developers-site-verification=NXqfMa78DDVE3kfChv83eL0tFQQ8Y3p6
```

## Recommended First Integration

Use `video.upload` first. It uploads the video to the creator's TikTok inbox so the account owner can review and publish inside TikTok. This fits the current workflow because every post still needs human approval.

Use `video.publish` only after the app and account are ready for Direct Post. TikTok requires querying creator info before posting and using the privacy options returned by that endpoint.

## Current Project Files

- `.env.example` lists required local environment variables.
- `data/tiktok_account.json` stores non-secret account settings.
- `scripts/check_tiktok_connection.py` checks whether the local environment is ready.
- `docs/tiktok-account-connection.md` explains the account workflow status.

## Platform Boundaries

- Direct Post requires user consent and a valid access token.
- Unapproved or unaudited clients may be limited to private/self-only posting.
- Draft uploads still require the creator to open TikTok and complete posting.
- The Agent should never claim a video was posted until the API confirms it or the user manually marks it as posted.
