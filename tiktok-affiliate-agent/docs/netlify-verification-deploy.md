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
public/tiktok-developers-site-verification.txt
```

After deploy, the URL should be:

```text
https://spontaneous-conkies-a04ee3.netlify.app/tiktok-developers-site-verification.txt
```

It must show exactly:

```text
tiktok-developers-site-verification=NXqfMa78DDVE3kfChv83eL0tFQQ8Y3p6
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
