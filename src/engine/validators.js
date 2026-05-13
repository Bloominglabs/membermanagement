import { ValidationError } from "./errors.js";

// These validators intentionally cover only cross-workflow invariants. More
// specific rules should live beside the use case that needs them.
export function requireNonEmptyString(label, value) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new ValidationError(`${label} is required`);
  }

  return value.trim();
}

export function requirePositiveInteger(label, value) {
  if (!Number.isInteger(value) || value <= 0) {
    throw new ValidationError(`${label} must be a positive integer`);
  }

  return value;
}

export function requireDecision(value) {
  if (value !== "approve" && value !== "reject") {
    throw new ValidationError("decision must be approve or reject");
  }

  return value;
}
