import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const distAssets = join(process.cwd(), "dist", "assets");
const budgets = { ".js": 450 * 1024, ".css": 64 * 1024 };

if (!statSync(distAssets, { throwIfNoEntry: false })) {
  console.error("dist/assets is missing; run npm run build first.");
  process.exit(1);
}

let failed = false;
for (const file of readdirSync(distAssets)) {
  const extension = file.slice(file.lastIndexOf("."));
  const budget = budgets[extension];
  if (!budget) continue;
  const size = statSync(join(distAssets, file)).size;
  const result = size <= budget ? "ok" : "over budget";
  console.log(`${result}: ${file} ${(size / 1024).toFixed(1)} KiB / ${(budget / 1024).toFixed(0)} KiB`);
  if (size > budget) failed = true;
}

if (failed) process.exit(1);
