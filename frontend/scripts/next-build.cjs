const { spawnSync } = require("node:child_process");
const path = require("node:path");

process.env.NEXT_FONT_GOOGLE_MOCKED_RESPONSES ??= path.join(
  __dirname,
  "google-font-responses.cjs",
);

const nextBin = require.resolve("next/dist/bin/next");
const result = spawnSync(process.execPath, [nextBin, "build"], {
  env: process.env,
  stdio: "inherit",
});

process.exit(result.status ?? 1);
