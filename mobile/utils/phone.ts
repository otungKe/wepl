/**
 * Kenyan phone number utilities.
 * Accepted inputs: 07XXXXXXXX · 7XXXXXXXX · +2547XXXXXXXX · 2547XXXXXXXX
 * All normalise to E.164 format: +254XXXXXXXXX
 */

export function normalizeKenyanPhone(raw: string): string | null {
  const digits = raw.replace(/\D/g, "");
  if (digits.startsWith("254") && digits.length === 12) return `+${digits}`;
  if (digits.startsWith("07")  && digits.length === 10) return `+254${digits.slice(1)}`;
  if (digits.startsWith("7")   && digits.length === 9)  return `+254${digits}`;
  return null;
}

export function isValidKenyanPhone(raw: string): boolean {
  return normalizeKenyanPhone(raw) !== null;
}

/** Format E.164 for display: +254 712 345 678 */
export function formatPhoneDisplay(e164: string): string {
  if (e164.startsWith("+254") && e164.length === 13) {
    return `+254 ${e164.slice(4, 7)} ${e164.slice(7, 10)} ${e164.slice(10)}`;
  }
  return e164;
}
