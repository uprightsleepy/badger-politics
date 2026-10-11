/** localStorage that never throws. Blocked storage (privacy settings,
 * some embedded views) throws SecurityError on any access, even reading
 * the property; then nothing is remembered and every page still works. */
export const store = {
  get(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key: string, value: string): void {
    try {
      localStorage.setItem(key, value);
    } catch {}
  },
  remove(key: string): void {
    try {
      localStorage.removeItem(key);
    } catch {}
  },
};
