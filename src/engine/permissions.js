import { AuthorizationError } from "./errors.js";

// The first rewrite slice keeps policy small on purpose. More granular staff
// roles and member self-service permissions will follow in later ADRs.
export const ROLE_PERMISSIONS = Object.freeze({
  "staff-admin": ["*"],
  "member-self": [
    "self:prepay",
    "self:donate",
    "self:cancel",
    "self:application:create"
  ]
});

export function hasPermission(roles, permission) {
  return roles.some((role) => {
    const grants = ROLE_PERMISSIONS[role] ?? [];
    return grants.includes("*") || grants.includes(permission);
  });
}

export function requirePermission({ roles, permission }) {
  if (!hasPermission(roles, permission)) {
    throw new AuthorizationError("forbidden");
  }
}
