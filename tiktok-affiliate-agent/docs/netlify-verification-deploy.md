# Netlify Verification Deploy

This project is ready to deploy a tiny static verification site to Netlify.

## Netlify Config

`netlify.toml` publishes the `public` directory:

```toml
[build]
  publish = "public"
```

The TikTok verification file is:

```text
public/tiktokvHxgWObij8HtLXiJy2QdUY5BVI4bWcMn.txt
```

Compatibility copies are also published at:

```text
public/tiktok-developers-site-verification
public/.well-known/tiktok-developers-site-verification.txt
public/.well-known/tiktok-developers-site-verification
```

After deploy, the URL should be:

```text
https://spontaneous-conkies-a04ee3.netlify.app/tiktokvHxgWObij8HtLXiJy2QdUY5BVI4bWcMn.txt
```

It must show exactly:

```text
tiktok-developers-site-verification=vHxgWObij8HtLXiJy2QdUY5BVI4bWcMn
```

## Deploy Steps

From this project directory:

```bash
npx netlify status
npx netlify deploy --prod --dir=public
```

If Netlify asks for build settings:

```text
Build command: leave empty
Publish directory: public
```

## TikTok Developer Setting

In TikTok Developer, choose `URL prefix` if you use the Netlify URL. Enter:

```text
https://spontaneous-conkies-a04ee3.netlify.app/
```

Then verify after the text file is live.
