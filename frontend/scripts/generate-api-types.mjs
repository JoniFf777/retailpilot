import { access, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import openapiTS, { astToString } from "openapi-typescript";

const input = resolve("openapi.json");
const output = resolve("src/api/openapi.generated.ts");

try {
  await access(input);
} catch {
  throw new Error(`OpenAPI input missing: ${input}. Run scripts/export_openapi.py first.`);
}

const schema = JSON.parse(await readFile(input, "utf8"));
const ast = await openapiTS(schema, { alphabetize: true });
await writeFile(output, astToString(ast), "utf8");
console.log(`OpenAPI TypeScript generated: ${output}`);
