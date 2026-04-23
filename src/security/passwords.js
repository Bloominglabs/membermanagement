import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";

const HASH_PREFIX = "scrypt";
const SALT_BYTES = 16;
const KEY_BYTES = 64;

export function isPasswordHash(value) {
  return typeof value === "string" && value.startsWith(`${HASH_PREFIX}$`);
}

export function hashPassword(password) {
  const salt = randomBytes(SALT_BYTES).toString("hex");
  const derivedKey = scryptSync(password, salt, KEY_BYTES).toString("hex");

  return `${HASH_PREFIX}$${salt}$${derivedKey}`;
}

export function verifyPassword({ password, passwordHash }) {
  if (!isPasswordHash(passwordHash)) {
    return false;
  }

  const [prefix, salt, expectedKeyHex] = passwordHash.split("$");
  if (prefix !== HASH_PREFIX || !salt || !expectedKeyHex) {
    return false;
  }

  const expectedKey = Buffer.from(expectedKeyHex, "hex");
  const actualKey = scryptSync(password, salt, expectedKey.length);

  return timingSafeEqual(expectedKey, actualKey);
}

