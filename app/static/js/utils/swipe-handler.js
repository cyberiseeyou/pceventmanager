/**
 * Swipe Gesture Handler
 * Lightweight touch swipe detection for mobile navigation.
 *
 * Usage:
 *   initSwipe(element, {
 *     onSwipeLeft: () => navigateNext(),
 *     onSwipeRight: () => navigatePrev()
 *   });
 */

function initSwipe(element, callbacks = {}) {
    if (!element) return;

    const THRESHOLD = 50;     // Minimum px distance to trigger swipe
    const RESTRAINT = 100;    // Max perpendicular px (prevent diagonal triggers)
    const MAX_TIME = 300;     // Max ms for swipe gesture

    let startX, startY, startTime;

    element.addEventListener('touchstart', (e) => {
        const touch = e.changedTouches[0];
        startX = touch.pageX;
        startY = touch.pageY;
        startTime = Date.now();
    }, { passive: true });

    element.addEventListener('touchend', (e) => {
        const touch = e.changedTouches[0];
        const dx = touch.pageX - startX;
        const dy = touch.pageY - startY;
        const elapsed = Date.now() - startTime;

        if (elapsed > MAX_TIME) return;
        if (Math.abs(dy) > RESTRAINT) return;
        if (Math.abs(dx) < THRESHOLD) return;

        if (dx < 0 && callbacks.onSwipeLeft) {
            callbacks.onSwipeLeft();
        } else if (dx > 0 && callbacks.onSwipeRight) {
            callbacks.onSwipeRight();
        }
    }, { passive: true });
}
