const path = require("path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const html = "file://" + path.join(root, "outputs/videos/clip01_html/scene.html");
const outDir = path.join(root, "outputs/videos/clip01_browser_frames");

const fs = require("fs");
fs.mkdirSync(outDir, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  let frame = 0;
  const repeats = [120, 120, 144, 120, 120];
  for (let scene = 0; scene < repeats.length; scene++) {
    await page.goto(`${html}?scene=${scene}`);
    await page.waitForLoadState("networkidle");
    const tmp = path.join(outDir, `scene_${scene}.png`);
    await page.screenshot({ path: tmp, fullPage: false });
    for (let i = 0; i < repeats[scene]; i++) {
      fs.copyFileSync(tmp, path.join(outDir, `frame_${String(frame).padStart(4, "0")}.png`));
      frame++;
    }
  }
  await browser.close();
  console.log(outDir);
  console.log(frame);
})();
