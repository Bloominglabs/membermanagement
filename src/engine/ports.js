import { ConfigurationError } from "./errors.js";

// Ports are the engine's adapter contract. Failing early on missing methods
// keeps runtime wiring mistakes from surfacing as partial workflow failures.
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
