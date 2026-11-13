import { readdirSync, readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const bytes = readdirSync("dist/assets")
  .filter((file) => file.endsWith(".js"))
  .reduce(
    (sum, file) => sum + gzipSync(readFileSync(`dist/assets/${file}`)).length,
    0,
  );
console.log(
  `JavaScript gzip: ${bytes} bytes (${(bytes / 1024).toFixed(2)} KiB)`,
);
if (bytes >= 200_000) process.exit(1);
