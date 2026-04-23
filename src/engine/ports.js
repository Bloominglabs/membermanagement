import { ConfigurationError } from "./errors.js";

export function assertPort(label, port, methods) {
  if (!port) {
    throw new ConfigurationError(`${label} is required`);
  }

  const missingMethods = methods.filter((method) => typeof port[method] !== "function");

  if (missingMethods.length > 0) {
    throw new ConfigurationError(
      `${label} must implement ${missingMethods.join(", ")}`
    );
  }
}

