# Qidian VIP decrypt (Node 18+)

Uses your **logged-in account cookies** (`ywguid` / session) — does **not**
bypass payment. Free chapters do not need this tool.

Setup:

1. `node` on PATH (18+)
2. First VIP decrypt call downloads `4819793b.qeooxh.js` from Qidian CDN into
   this folder (or place it here manually)

stdin JSON: `[ciphertext, chapterId, fkp, fuid]` → stdout decrypted HTML.
