/**
 * lockSuppress — single-use flag to skip the session lock for one
 * background/foreground cycle.
 *
 * Use this before any action that intentionally backgrounds the app
 * but should NOT trigger the session lock:
 *   - Image / camera picker
 *   - Share sheet
 *   - File picker
 *   - Biometric prompt (handled separately by the lock screen itself)
 *
 * Usage:
 *   suppressNextLock();
 *   const result = await ImagePicker.launchImageLibraryAsync(...);
 *   // lock was automatically skipped for this background trip
 */

let _suppressed = false;

/** Call immediately before any action that will background the app. */
export function suppressNextLock(): void {
  _suppressed = true;
}

/**
 * Called by the AppState handler — returns true if the lock should be
 * skipped for this foreground event, and resets the flag automatically.
 */
export function consumeLockSuppression(): boolean {
  if (_suppressed) {
    _suppressed = false;
    return true;
  }
  return false;
}
