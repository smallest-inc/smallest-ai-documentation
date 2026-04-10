/**
 * docs.smallest.ai — Unified Analytics Script
 * Sends events to both Mixpanel and PostHog
 *
 * PostHog SDK is loaded natively by Fern via docs.yml analytics config.
 * This script loads Mixpanel and sets up custom event tracking for both.
 */

(function () {
  "use strict";

  // ============================================================
  // CONFIG
  // ============================================================
  const CONFIG = {
    MIXPANEL_TOKEN: "005a880f58fbad433a357b2bfc7f4d54",
  };

  // ============================================================
  // MIXPANEL SDK LOADER (PostHog is loaded by Fern natively)
  // ============================================================

  function loadMixpanel() {
    (function (f, b) {
      if (!b.__SV) {
        var e, g, i, h;
        window.mixpanel = b;
        b._i = [];
        b.init = function (e, f, c) {
          function g(a, d) {
            var b = d.split(".");
            2 == b.length && ((a = a[b[0]]), (d = b[1]));
            a[d] = function () {
              a.push([d].concat(Array.prototype.slice.call(arguments, 0)));
            };
          }
          var a = b;
          "undefined" !== typeof c ? (a = b[c] = []) : (c = "mixpanel");
          a.people = a.people || [];
          a.toString = function (a) {
            var d = "mixpanel";
            "mixpanel" !== c && (d += "." + c);
            a || (d += " (stub)");
            return d;
          };
          a.people.toString = function () {
            return a.toString(1) + ".people (stub)";
          };
          i = "disable time_event track track_pageview track_links track_forms track_with_groups add_group set_group remove_group register register_once alias unregister identify name_tag set_config reset opt_in_tracking opt_out_tracking has_opted_in_tracking has_opted_out_tracking clear_opt_in_out_tracking start_batch_senders people.set people.set_once people.unset people.increment people.append people.union people.track_charge people.clear_charges people.delete_user people.remove".split(
            " "
          );
          for (h = 0; h < i.length; h++) g(a, i[h]);
          var j = "set set_once union unset remove delete".split(" ");
          a.get_group = function () {
            function b(c) {
              d[c] = function () {
                call2_args = arguments;
                call2 = [c].concat(Array.prototype.slice.call(call2_args, 0));
                a.push([e, call2]);
              };
            }
            for (
              var d = {},
                e = ["get_group"].concat(
                  Array.prototype.slice.call(arguments, 0)
                ),
                c = 0;
              c < j.length;
              c++
            )
              b(j[c]);
            return d;
          };
          b._i.push([e, f, c]);
        };
        b.__SV = 1.2;
        e = f.createElement("script");
        e.type = "text/javascript";
        e.async = !0;
        e.src =
          "undefined" !== typeof MIXPANEL_CUSTOM_LIB_URL
            ? MIXPANEL_CUSTOM_LIB_URL
            : "file:" === f.location.protocol &&
              "//cdn.mxpnl.com/libs/mixpanel-2-latest.min.js".match(/^\/\//)
            ? "https://cdn.mxpnl.com/libs/mixpanel-2-latest.min.js"
            : "//cdn.mxpnl.com/libs/mixpanel-2-latest.min.js";
        g = f.getElementsByTagName("script")[0];
        g.parentNode.insertBefore(e, g);
      }
    })(document, window.mixpanel || []);

    mixpanel.init(CONFIG.MIXPANEL_TOKEN, {
      track_pageview: false,
      persistence: "localStorage",
    });
  }

  // ============================================================
  // HELPERS
  // ============================================================

  function getProduct() {
    var path = window.location.pathname;
    if (path.startsWith("/waves")) return "waves";
    if (path.startsWith("/atoms")) return "atoms";
    return "unknown";
  }

  function getSection() {
    var path = window.location.pathname;
    if (path.includes("/api-reference")) return "api-reference";
    if (path.includes("/quickstart") || path.includes("/quick-start"))
      return "quickstart";
    if (path.includes("/getting-started") || path.includes("/get-started"))
      return "getting-started";
    if (path.includes("/cookbook") || path.includes("/examples"))
      return "cookbooks";
    if (path.includes("/self-host") || path.includes("/on-prem"))
      return "self-host";
    if (path.includes("/integrations")) return "integrations";
    if (path.includes("/developer-guide") || path.includes("/documentation"))
      return "guides";
    if (path.includes("/mcp")) return "mcp";
    if (path.includes("/model-cards") || path.includes("/benchmarks"))
      return "benchmarks";
    return "other";
  }

  function getUTMParams() {
    var params = new URLSearchParams(window.location.search);
    return {
      utm_source: params.get("utm_source") || "",
      utm_medium: params.get("utm_medium") || "",
      utm_campaign: params.get("utm_campaign") || "",
    };
  }

  // Dual-send to both platforms
  function track(eventName, properties) {
    var enriched = Object.assign({}, properties, {
      product: (properties && properties.product) || getProduct(),
      page_path: window.location.pathname,
      page_title: document.title,
      timestamp: new Date().toISOString(),
    });

    // Mixpanel
    if (window.mixpanel) {
      mixpanel.track(eventName, enriched);
    }

    // PostHog (loaded by Fern)
    if (window.posthog) {
      posthog.capture(eventName, enriched);
    }
  }

  // ============================================================
  // EVENT TRACKERS
  // ============================================================

  // 1. Page View
  function trackPageView() {
    var utm = getUTMParams();
    track("docs_page_viewed", Object.assign({
      page_path: window.location.pathname,
      page_title: document.title,
      product: getProduct(),
      section: getSection(),
      referrer: document.referrer,
    }, utm));
  }

  // 2. Code Copy
  function setupCodeCopyTracking() {
    document.addEventListener("click", function (e) {
      var copyBtn = e.target.closest(
        '[data-copy], .copy-button, button[aria-label*="copy"], button[aria-label*="Copy"]'
      );
      if (copyBtn) {
        var codeBlock = copyBtn.closest("pre, .code-block, [data-language]");
        var language = codeBlock
          ? codeBlock.getAttribute("data-language") ||
            (codeBlock.className.match(/language-(\w+)/) || [])[1] ||
            "unknown"
          : "unknown";

        track("docs_code_copied", {
          language: language,
          snippet_id:
            (codeBlock && codeBlock.id) || (codeBlock && codeBlock.getAttribute("data-snippet")) || "",
        });
      }
    });
  }

  // 3. Search tracking
  function setupSearchTracking() {
    var observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          if (node.nodeType === 1) {
            var searchInput = node.querySelector(
              'input[type="search"], input[placeholder*="Search"], input[placeholder*="search"]'
            );
            if (searchInput) {
              var debounceTimer;
              searchInput.addEventListener("input", function (e) {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(function () {
                  if (e.target.value.length >= 3) {
                    track("docs_search_performed", {
                      query: e.target.value,
                    });
                  }
                }, 1000);
              });
            }
          }
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });

    // Also track search result clicks
    document.addEventListener("click", function (e) {
      var resultLink = e.target.closest('[data-search-result], .search-result a, [role="option"] a');
      if (resultLink) {
        track("docs_search_result_clicked", {
          result_title: resultLink.textContent.trim(),
          result_url: resultLink.href || "",
        });
      }
    });
  }

  // 4. Navigation clicks
  function setupNavTracking() {
    document.addEventListener("click", function (e) {
      var navLink = e.target.closest("nav a, aside a, .sidebar a");
      if (navLink) {
        track("docs_nav_clicked", {
          nav_item: navLink.textContent.trim(),
          from_page: window.location.pathname,
        });
      }
    });
  }

  // 5. Product toggle (Waves <-> Atoms)
  function setupProductToggleTracking() {
    document.addEventListener("click", function (e) {
      var toggle = e.target.closest(
        '[data-product-toggle], .product-toggle, .version-switcher a, .product-switcher a'
      );
      if (toggle) {
        var currentProduct = getProduct();
        var targetText = toggle.textContent.trim().toLowerCase();
        var toProduct = targetText.includes("waves")
          ? "waves"
          : targetText.includes("atoms")
          ? "atoms"
          : "unknown";

        if (toProduct !== currentProduct) {
          track("docs_product_toggled", {
            from_product: currentProduct,
            to_product: toProduct,
          });
        }
      }
    });
  }

  // 6. CTA / Signup / Console clicks
  function setupCTATracking() {
    document.addEventListener("click", function (e) {
      var link = e.target.closest("a");
      if (!link) return;

      var href = link.href || "";
      var text = link.textContent.trim().toLowerCase();

      // Signup / Console links
      if (
        href.includes("console.smallest.ai") ||
        href.includes("app.smallest.ai") ||
        text.includes("sign up") ||
        text.includes("get started") ||
        text.includes("create account")
      ) {
        track("docs_signup_clicked", {
          cta_location: (e.target.closest("header, nav, main, footer") || {}).tagName || "unknown",
          cta_text: link.textContent.trim(),
        });
      }

      // Pricing links
      if (href.includes("pricing") || text.includes("pricing")) {
        track("docs_pricing_clicked", {});
      }

      // Console links (general)
      if (
        href.includes("console.smallest.ai") ||
        href.includes("app.smallest.ai")
      ) {
        track("docs_console_link_clicked", {
          destination: href,
        });
      }
    });
  }

  // 7. SDK install copy detection
  function setupSDKInstallTracking() {
    document.addEventListener("click", function (e) {
      var copyBtn = e.target.closest(
        '[data-copy], .copy-button, button[aria-label*="copy"], button[aria-label*="Copy"]'
      );
      if (!copyBtn) return;

      var codeBlock = copyBtn.closest("pre, .code-block");
      if (!codeBlock) return;

      var text = codeBlock.textContent || "";
      if (
        text.includes("pip install") ||
        text.includes("npm install") ||
        text.includes("yarn add") ||
        text.includes("pnpm add") ||
        text.includes("bun add")
      ) {
        var language = "unknown";
        if (text.includes("pip install")) language = "python";
        else if (text.includes("npm install") || text.includes("yarn add") || text.includes("pnpm add") || text.includes("bun add"))
          language = "javascript";

        track("docs_sdk_install_copied", {
          language: language,
        });
      }
    });
  }

  // 8. Feedback
  function setupFeedbackTracking() {
    document.addEventListener("click", function (e) {
      var feedbackBtn = e.target.closest(
        '[data-feedback], .feedback-button, .thumbs-up, .thumbs-down, [aria-label*="helpful"]'
      );
      if (feedbackBtn) {
        var isPositive =
          feedbackBtn.classList.contains("thumbs-up") ||
          feedbackBtn.getAttribute("data-feedback") === "positive" ||
          (feedbackBtn.getAttribute("aria-label") || "").includes("yes");

        track("docs_feedback_submitted", {
          rating: isPositive ? "positive" : "negative",
        });
      }
    });
  }

  // 9. Scroll depth
  function setupScrollTracking() {
    var maxScroll = 0;
    var tracked25 = false, tracked50 = false, tracked75 = false, tracked100 = false;

    window.addEventListener(
      "scroll",
      function () {
        var scrollTop = window.scrollY;
        var docHeight = document.documentElement.scrollHeight - window.innerHeight;
        if (docHeight <= 0) return;

        var scrollPct = Math.round((scrollTop / docHeight) * 100);
        maxScroll = Math.max(maxScroll, scrollPct);

        if (maxScroll >= 25 && !tracked25) { tracked25 = true; track("docs_scroll_depth", { depth: 25 }); }
        if (maxScroll >= 50 && !tracked50) { tracked50 = true; track("docs_scroll_depth", { depth: 50 }); }
        if (maxScroll >= 75 && !tracked75) { tracked75 = true; track("docs_scroll_depth", { depth: 75 }); }
        if (maxScroll >= 100 && !tracked100) { tracked100 = true; track("docs_scroll_depth", { depth: 100 }); }
      },
      { passive: true }
    );
  }

  // 10. API Playground interaction
  function setupAPIPlaygroundTracking() {
    document.addEventListener("click", function (e) {
      var playgroundBtn = e.target.closest(
        '[data-playground], .api-playground button[type="submit"], .playground-run, button.try-it'
      );
      if (playgroundBtn) {
        track("docs_api_playground_used", {
          endpoint: window.location.pathname,
        });
      }
    });
  }

  // ============================================================
  // SPA NAVIGATION HANDLER
  // ============================================================

  function setupSPATracking() {
    var lastPath = window.location.pathname;

    window.addEventListener("popstate", function () {
      if (window.location.pathname !== lastPath) {
        lastPath = window.location.pathname;
        trackPageView();
      }
    });

    var originalPushState = history.pushState;
    var originalReplaceState = history.replaceState;

    history.pushState = function () {
      originalPushState.apply(this, arguments);
      if (window.location.pathname !== lastPath) {
        lastPath = window.location.pathname;
        trackPageView();
      }
    };

    history.replaceState = function () {
      originalReplaceState.apply(this, arguments);
      if (window.location.pathname !== lastPath) {
        lastPath = window.location.pathname;
        trackPageView();
      }
    };
  }

  // ============================================================
  // INIT
  // ============================================================

  function init() {
    loadMixpanel();
    // PostHog is loaded by Fern natively via docs.yml analytics config

    setTimeout(function () {
      trackPageView();
      setupSPATracking();
      setupCodeCopyTracking();
      setupSearchTracking();
      setupNavTracking();
      setupProductToggleTracking();
      setupCTATracking();
      setupSDKInstallTracking();
      setupFeedbackTracking();
      setupScrollTracking();
      setupAPIPlaygroundTracking();
    }, 500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
