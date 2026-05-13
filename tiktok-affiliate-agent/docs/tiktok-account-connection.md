# TikTok Account Connection

Target account:

- Handle: `@thatslife6969`
- URL: `https://www.tiktok.com/@thatslife6969`
- Current status in this project: workflow connected
- Direct posting status: not connected

## What Is Connected Now

The account is now part of the local Agent workflow. The system can:

- Generate content plans for this page
- Create captions and hashtags for this page
- Build a posting queue for this page
- Track metrics by this page
- Prepare TikTok-ready posting data

## What Is Not Connected Yet

The system cannot publish directly to TikTok yet. Direct posting requires an official TikTok developer integration and authorization from the TikTok account owner.

## Direct Posting Requirements

To post from the Agent to `@thatslife6969`, we need:

1. A TikTok Developer app
2. Content Posting API enabled
3. Direct Post configuration enabled
4. Approved `video.publish` scope
5. OAuth authorization from `@thatslife6969`
6. A valid user access token
7. A video file or a verified public URL for the video
8. Human approval before publishing

Important platform boundary: TikTok states that unaudited clients are restricted to private posting mode until the API client passes audit. So the first implementation should support draft/private testing first, then public posting after approval.

## Recommended Connection Path

### Phase 1: Manual Posting, Agent Prepared

Use the generated posting queue, captions, and checklist. Manually upload to `@thatslife6969`.

This is the fastest way to start earning because it avoids waiting for API approval.

### Phase 2: Semi-Automated Draft Pipeline

Generate video and caption automatically, then send to an approval folder. After approval, upload manually or through a supported scheduler.

### Phase 3: Official Direct Post API

Build OAuth and Content Posting API integration:

- Query creator info before posting
- Initialize video post
- Upload video to TikTok
- Poll publish status
- Store publish ID and metrics

## Approval Checklist Before Any Post

- Correct account: `@thatslife6969`
- Correct affiliate product in basket
- Correct caption and hashtags
- Price and promotion checked
- No overclaiming
- AI-generated content label applied if needed
- Video reviewed by human

