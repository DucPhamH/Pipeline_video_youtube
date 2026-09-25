#!/usr/bin/env node
/**
 * Qidian VIP chapter decrypt helper.
 * Requires Node 18+ and Fock asset `4819793b.qeooxh.js` in this directory
 * (auto-downloaded by Python ensure_fock_asset from Qidian CDN).
 *
 * stdin JSON: [ciphertext, chapterId, fkp, fuid]
 * stdout: decrypted HTML fragment
 *
 * Only works when the account (fuid / cookies) already has chapter access —
 * this does not bypass payment.
 */
"use strict";

const path = require("path");
const fs = require("fs");

const asset = path.join(__dirname, "4819793b.qeooxh.js");
if (!fs.existsSync(asset)) {
  console.error("Missing Fock asset: " + asset);
  process.exit(2);
}

const Fock = require("./4819793b.qeooxh.js");

const shim = {
  outerHeight: 1000,
  innerHeight: 100,
  location: { protocol: "https:", hostname: "vipreader.qidian.com" },
};
global.window = global;
globalThis.window = global;
globalThis.self = global;
for (const [k, v] of Object.entries(shim)) globalThis[k] = v;

async function decrypt(enContent, cuChapterId, fkp, fuid) {
  Fock.initialize();
  Fock.setupUserKey(fuid);
  // fkp is base64 JS that sets unlock keys for this chapter
  eval(Buffer.from(fkp, "base64").toString("utf8"));
  return new Promise((resolve, reject) => {
    Fock.unlock(enContent, cuChapterId, (code, decrypted) => {
      if (code === 0) resolve(decrypted);
      else reject(new Error("Fock.unlock failed, code=" + code));
    });
  });
}

let input = "";
process.stdin.on("data", (c) => (input += c));
process.stdin.on("end", async () => {
  try {
    const [rawEn, rawCid, rawFkp, rawFuid] = JSON.parse(input);
    const result = await decrypt(
      String(rawEn),
      String(rawCid),
      String(rawFkp),
      String(rawFuid)
    );
    process.stdout.write(result);
    process.exit(0);
  } catch (err) {
    console.error(String(err));
    process.exit(1);
  }
});
