// Error-reporting seam (client side).
//
// Mirror of the backend's app/observability.py. The base ships with no
// monitoring dependency — reportError just logs to the console. To wire a
// real reporter (Sentry, etc.), install its SDK and call it from inside
// reportError, e.g.:
//
//   import * as Sentry from "@sentry/nextjs";
//   export function reportError(error: unknown, context?: ErrorContext) {
//     Sentry.captureException(error, { extra: context });
//     console.error(error, context);
//   }
//
// Keeping every reporting call behind this one function means components and
// error boundaries never import a vendor SDK directly.

export type ErrorContext = Record<string, unknown>;

export function reportError(error: unknown, context?: ErrorContext): void {
  if (context) {
    console.error(error, context);
  } else {
    console.error(error);
  }
}
