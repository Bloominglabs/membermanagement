import test from "node:test";
import assert from "node:assert/strict";

import { hashPassword, isPasswordHash, verifyPassword } from "../../src/security/passwords.js";
import { createDefaultDocument } from "../../src/adapters/store/default-document.js";

test("password hashing produces a verifiable non-plaintext value", () => {
  const hash = hashPassword("change-me");

  assert.equal(isPasswordHash(hash), true);
  assert.equal(hash.includes("change-me"), false);
  assert.equal(verifyPassword({ password: "change-me", passwordHash: hash }), true);
  assert.equal(verifyPassword({ password: "wrong-password", passwordHash: hash }), false);
});

test("default document stores password hashes instead of raw passwords", () => {
  const document = createDefaultDocument();

  assert.equal(document.accounts.length > 0, true);
  assert.equal("password" in document.accounts[0], false);
  assert.equal(isPasswordHash(document.accounts[0].passwordHash), true);
});

