const path = require("path");
const fs = require("fs");

const candidates = [
  path.join("D:\\NovelApp", "projects"),
  path.join("%USERPROFILE%\\AppData\\Roaming\\novelapp-desktop\\data", "projects"),
];

for (const c of candidates) {
  console.log("候选:", c, "存在:", fs.existsSync(c));
  if (!fs.existsSync(c)) continue;
  const book = "<书名>";
  const base = path.join(c, book, "设定库");
  console.log("  设定库:", base, "存在:", fs.existsSync(base));
  const pd = path.join(base, "承诺");
  console.log("  承诺:", pd, "存在:", fs.existsSync(pd));
  if (fs.existsSync(pd)) console.log("    文件数:", fs.readdirSync(pd).length);
  const id = path.join(base, "信息差");
  console.log("  信息差:", id, "存在:", fs.existsSync(id));
  if (fs.existsSync(id)) console.log("    文件数:", fs.readdirSync(id).length);
  console.log();
}