/**
 * Cache Manager
 *
 * Simple client-side cache with TTL (Time To Live) support.
 * Prevents duplicate API calls for identical requests.
 *
 * @module utils/cache-manager
 */

/**
 * Cache Manager with TTL support
 */
export class CacheManager {
  /**
   * Create a cache manager
   *
   * @param {number} ttlMs - Time to live in milliseconds (default: 60000 = 1 minute)
   */
  constructor(ttlMs = 60000) {
    this.cache = new Map();
    this.ttlMs = ttlMs;
  }

  /**
   * Store a value in cache
   *
   * @param {string} key - Cache key
   * @param {*} value - Value to cache
   */
  set(key, value) {
    this.cache.set(key, {
      value,
      timestamp: Date.now()
    });
  }

  /**
   * Retrieve a value from cache
   *
   * @param {string} key - Cache key
   * @returns {*} Cached value or null if expired/missing
   */
  get(key) {
    const cached = this.cache.get(key);

    if (!cached) {
      return null;
    }

    const age = Date.now() - cached.timestamp;

    if (age > this.ttlMs) {
      this.cache.delete(key);
      return null;
    }

    return cached.value;
  }

  /**
   * Check if a key exists in cache and is not expired
   *
   * @param {string} key - Cache key
   * @returns {boolean} True if key exists and is valid
   */
  has(key) {
    return this.get(key) !== null;
  }

  /**
   * Clear all cached items
   */
  clear() {
    this.cache.clear();
  }

  /**
   * Remove expired items from cache
   *
   * @returns {number} Number of items removed
   */
  prune() {
    let removed = 0;
    const now = Date.now();

    for (const [key, entry] of this.cache.entries()) {
      if (now - entry.timestamp > this.ttlMs) {
        this.cache.delete(key);
        removed++;
      }
    }

    return removed;
  }

  /**
   * Get cache statistics
   *
   * @returns {Object} Cache stats {size, oldestAge, newestAge}
   */
  getStats() {
    const now = Date.now();
    let oldestAge = 0;
    let newestAge = Infinity;

    for (const entry of this.cache.values()) {
      const age = now - entry.timestamp;
      oldestAge = Math.max(oldestAge, age);
      newestAge = Math.min(newestAge, age);
    }

    return {
      size: this.cache.size,
      oldestAge: oldestAge || 0,
      newestAge: newestAge === Infinity ? 0 : newestAge
    };
  }
}
