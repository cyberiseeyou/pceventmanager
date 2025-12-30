/**
 * Debounce Utility
 *
 * Delays function execution until after a specified delay has elapsed
 * since the last time the function was invoked.
 *
 * @module utils/debounce
 */

/**
 * Creates a debounced function that delays invoking func until after delayMs
 * milliseconds have elapsed since the last time the debounced function was invoked.
 *
 * @param {Function} func - The function to debounce
 * @param {number} delayMs - The number of milliseconds to delay
 * @returns {Function} The debounced function
 *
 * @example
 * const debouncedSave = debounce(saveData, 300);
 * input.addEventListener('input', () => debouncedSave(input.value));
 */
export function debounce(func, delayMs) {
  let timeoutId;

  return function debounced(...args) {
    const context = this;

    clearTimeout(timeoutId);

    timeoutId = setTimeout(() => {
      func.apply(context, args);
    }, delayMs);
  };
}

/**
 * Creates a debounced function that returns a Promise.
 * Useful for async operations.
 *
 * @param {Function} func - The async function to debounce
 * @param {number} delayMs - The number of milliseconds to delay
 * @returns {Function} The debounced function that returns a Promise
 */
export function debounceAsync(func, delayMs) {
  let timeoutId;
  let pendingResolve;
  let pendingReject;

  return function debouncedAsync(...args) {
    const context = this;

    // Reject previous pending promise
    if (pendingReject) {
      pendingReject(new Error('Debounced call superseded'));
    }

    clearTimeout(timeoutId);

    return new Promise((resolve, reject) => {
      pendingResolve = resolve;
      pendingReject = reject;

      timeoutId = setTimeout(async () => {
        try {
          const result = await func.apply(context, args);
          pendingResolve(result);
          pendingResolve = null;
          pendingReject = null;
        } catch (error) {
          pendingReject(error);
          pendingResolve = null;
          pendingReject = null;
        }
      }, delayMs);
    });
  };
}
