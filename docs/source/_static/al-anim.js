// Active-learning animation on the landing page.
//
// 1. Hide it until the page is parsed. The SVG is large and is painted while it streams in:
//    before the SMIL timeline takes over, every moving group shows up at its static position
//    and full opacity, a jumble of tokens for a moment. This script is loaded in <head>, so it
//    marks <html> before the SVG is painted; the CSS keeps the animation invisible (its space
//    stays reserved, so nothing jumps) and fades it in once the class is removed. Without
//    JavaScript the class is never set and the animation shows as usual.
// 2. Pause it when it is not being shown: either the reader asked for reduced motion, or it is
//    the layout that is currently hidden.
(function () {
    var root = document.documentElement;
    root.classList.add("al-loading");

    function apply() {
        var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        var svgs = document.querySelectorAll(".al-anim svg");
        Array.prototype.forEach.call(svgs, function (svg) {
            var hidden = !svg.getClientRects().length;
            if (reduce || hidden) {
                if (svg.pauseAnimations) svg.pauseAnimations();
            } else if (svg.unpauseAnimations) {
                svg.unpauseAnimations();
            }
        });
    }

    var revealed = false;
    function reveal() {
        if (revealed) return;
        revealed = true;
        // Start from the beginning of the cycle, then show it after the first animated frame
        // has been computed.
        Array.prototype.forEach.call(document.querySelectorAll(".al-anim svg"), function (svg) {
            if (svg.setCurrentTime) svg.setCurrentTime(0);
        });
        apply();
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                root.classList.remove("al-loading");
            });
        });
    }

    // Chrome starts the SMIL timeline of inline SVG only at the window `load` event, not at
    // DOMContentLoaded: revealing earlier shows the static positions. The timeout is a safety
    // net for a page whose `load` is held back by a slow image.
    if (document.readyState === "complete") reveal();
    else window.addEventListener("load", reveal);
    setTimeout(reveal, 4000);
    window.addEventListener("resize", apply);
})();
