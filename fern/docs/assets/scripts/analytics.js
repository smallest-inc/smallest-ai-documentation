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

  // PostHog direct-capture config (Fern's React-bundled posthog-js does not
  // reliably expose window.posthog when this script runs, so we POST to the
  // /capture/ endpoint ourselves. Same project key Fern uses, so events land
  // in the existing project alongside Fern's native $pageview/$autocapture.)
  var POSTHOG = {
    key: "phc_sPVVNGLTV6b6CDMbmxkUjwNB6NvmEJKMcgT6EsN8m96j",
    host: "https://us.i.posthog.com",
  };

  function getDistinctId() {
    try {
      if (window.posthog && typeof window.posthog.get_distinct_id === "function") {
        var ferns = window.posthog.get_distinct_id();
        if (ferns) return ferns;
      }
    } catch (e) {}
    var key = "docs_analytics_distinct_id";
    try {
      var stored = localStorage.getItem(key);
      if (stored) return stored;
      var fresh = "dc_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10);
      localStorage.setItem(key, fresh);
      return fresh;
    } catch (e) {
      return "dc_anon_" + Math.random().toString(36).slice(2, 10);
    }
  }

  // Session ID with 30-min idle-timeout sessionization, mirroring how
  // PostHog's posthog-js handles sessions. Without this every event was
  // landing with $session_id = NULL, which broke every session-based
  // metric in PostHog (count(DISTINCT $session_id), helpfulness numerator,
  // funnel session-window joins, etc.). 30 min matches PostHog default.
  function getSessionId() {
    // 1. Reuse Fern's PostHog SDK session id when it's there — keeps our
    // events in the same session as $pageview / $autocapture
    try {
      if (window.posthog && typeof window.posthog.get_session_id === "function") {
        var phSid = window.posthog.get_session_id();
        if (phSid) return phSid;
      }
    } catch (e) {}

    var IDLE_MS = 30 * 60 * 1000; // 30-minute idle = new session
    var KEY = "docs_analytics_session";
    try {
      var raw = localStorage.getItem(KEY);
      if (raw) {
        var s = JSON.parse(raw);
        if (s && s.id && s.lastActive && Date.now() - s.lastActive < IDLE_MS) {
          s.lastActive = Date.now();
          localStorage.setItem(KEY, JSON.stringify(s));
          return s.id;
        }
      }
    } catch (e) {}

    var fresh = "ds_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10);
    try {
      localStorage.setItem(KEY, JSON.stringify({ id: fresh, lastActive: Date.now() }));
    } catch (e) {}
    return fresh;
  }

  function sendPostHogDirect(eventName, properties) {
    var payload = {
      api_key: POSTHOG.key,
      event: eventName,
      distinct_id: getDistinctId(),
      properties: Object.assign(
        {
          $current_url: window.location.href,
          $pathname: window.location.pathname,
          $host: window.location.host,
          $referrer: document.referrer || "$direct",
          $session_id: getSessionId(),
          $lib: "smallest-docs-analytics",
          $insert_id: eventName + "-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10),
        },
        properties
      ),
      timestamp: new Date().toISOString(),
    };
    try {
      fetch(POSTHOG.host + "/capture/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        keepalive: true,
      }).catch(function () {});
    } catch (e) {}
  }

  // Dual-send to both platforms
  function track(eventName, properties) {
    var enriched = Object.assign({}, properties, {
      product: (properties && properties.product) || getProduct(),
      page_path: window.location.pathname,
      page_title: document.title,
      timestamp: new Date().toISOString(),
    });

    // Mixpanel (SDK attaches to window.mixpanel synchronously via loadMixpanel)
    if (window.mixpanel) {
      mixpanel.track(eventName, enriched);
    }

    // PostHog (direct HTTP capture; see POSTHOG block above for why)
    sendPostHogDirect(eventName, enriched);
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
        'button.fern-copy-button, [data-copy], .copy-button, button[aria-label*="copy"], button[aria-label*="Copy"]'
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
        'button.fern-copy-button, [data-copy], .copy-button, button[aria-label*="copy"], button[aria-label*="Copy"]'
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

  // 8. Feedback — covers Fern's "Was this helpful?" Yes/No widget at the
  // bottom of every page (no specific class on the buttons; identified by
  // text + an ancestor whose text mentions "helpful") AND the page-level
  // ".fern-feedback-button" (the "Report incorrect code" pencil icon
  // inside code blocks).
  function setupFeedbackTracking() {
    document.addEventListener("click", function (e) {
      // Pattern A: Fern's "Report incorrect code" button (negative signal
      // about a specific code block, distinct from page-level helpful)
      var reportBtn = e.target.closest("button.fern-feedback-button");
      if (reportBtn) {
        track("docs_feedback_submitted", {
          rating: "negative",
          source: "report_code",
        });
        return;
      }

      // Pattern B: legacy / data-attr-based widgets
      var legacy = e.target.closest(
        '[data-feedback], .feedback-button, .thumbs-up, .thumbs-down, [aria-label*="helpful"]'
      );
      if (legacy) {
        var isPositive =
          legacy.classList.contains("thumbs-up") ||
          legacy.getAttribute("data-feedback") === "positive" ||
          (legacy.getAttribute("aria-label") || "").includes("yes");
        track("docs_feedback_submitted", {
          rating: isPositive ? "positive" : "negative",
          source: "widget",
        });
        return;
      }

      // Pattern C: Fern's page-level Yes/No buttons under "Was this helpful?"
      var btn = e.target.closest("button");
      if (!btn) return;
      var btnText = (btn.textContent || "").trim().toLowerCase();
      if (btnText !== "yes" && btnText !== "no") return;
      // confirm by checking for a "helpful" / "useful" prompt within ~3
      // ancestors (avoids false positives on unrelated Yes/No buttons)
      var node = btn;
      for (var i = 0; i < 4 && node; i++) {
        var around = (node.textContent || "").toLowerCase();
        if (around.includes("helpful") || around.includes("useful") || around.includes("did this")) {
          track("docs_feedback_submitted", {
            rating: btnText === "yes" ? "positive" : "negative",
            source: "yes_no",
          });
          return;
        }
        node = node.parentElement;
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

  // 10. API Playground interaction — Fern's "Try it" button on API ref
  // pages. Enriched with full API context (type / variant / protocol /
  // method) so reports can split TTS Lightning v3.1 (REST) vs Pulse
  // Realtime (WebSocket) vs Atoms Agents Create (REST), etc.
  function setupAPIPlaygroundTracking() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("button");
      if (!btn) return;
      var text = (btn.textContent || "").trim().toLowerCase();
      var legacyMatch = e.target.closest(
        '[data-playground], .api-playground button[type="submit"], .playground-run, button.try-it'
      );
      if (text === "try it" || text === "send" || text === "run" || legacyMatch) {
        var ctx = getApiContext() || {};
        track("docs_api_playground_used", {
          endpoint: window.location.pathname,
          api_type: ctx.api_type || "unknown",
          api_name: ctx.api_name || "",
          api_variant: ctx.api_variant || null,
          api_protocol: ctx.api_protocol || "unknown",
          api_method: ctx.api_method || null,
          button_text: text,
        });
      }
    });
  }

  // 11. API key copy detection — fires when a user copies a snippet that
  // contains an API-key-shaped string. Uses the copy-button click handler
  // rather than the clipboard API so it works even if the clipboard is
  // gated. Captures either a real key pattern or a placeholder the user
  // will replace (both indicate intent to authenticate).
  function setupAPIKeyCopyTracking() {
    var API_KEY_PATTERN = /(sk_[A-Za-z0-9]{16,}|phc_[A-Za-z0-9]{16,}|ak_[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9_-]{16,}|YOUR[_-]?API[_-]?KEY|SMALLEST[_-]?API[_-]?KEY|<YOUR[_-]API[_-]KEY>|your[_-]?api[_-]?key)/;
    document.addEventListener("click", function (e) {
      var copyBtn = e.target.closest(
        'button.fern-copy-button, [data-copy], .copy-button, button[aria-label*="copy"], button[aria-label*="Copy"]'
      );
      if (!copyBtn) return;
      var codeBlock = copyBtn.closest("pre, .code-block, [data-language]");
      if (!codeBlock) return;
      var text = codeBlock.textContent || "";
      if (API_KEY_PATTERN.test(text)) {
        track("docs_api_key_copied", {
          snippet_type: /Bearer|Authorization/i.test(text) ? "auth_header" : "env_var",
        });
      }
    });
  }

  // 12. Quickstart completion — fires once per session per quickstart page
  // when the user both (a) reaches ≥90% scroll and (b) has copied at least
  // one code block on that page. This is the strongest high-intent signal
  // of "user actually followed the quickstart through," short of a signup.
  function setupQuickstartCompletionTracking() {
    var isQuickstart = function () {
      var p = window.location.pathname.toLowerCase();
      return (
        p.indexOf("quickstart") !== -1 ||
        p.indexOf("quick-start") !== -1 ||
        p.indexOf("get-started") !== -1 ||
        p.indexOf("getting-started") !== -1
      );
    };
    var state = { codeCopied: false, scrollHit: false, fired: false, path: "" };
    function reset() {
      state = { codeCopied: false, scrollHit: false, fired: false, path: window.location.pathname };
    }
    reset();
    // Reset state on SPA navigation so each quickstart page is tracked independently
    window.addEventListener("popstate", reset);
    var origPush = history.pushState;
    history.pushState = function () { origPush.apply(this, arguments); reset(); };
    var origReplace = history.replaceState;
    history.replaceState = function () { origReplace.apply(this, arguments); reset(); };

    function maybeFire() {
      if (!isQuickstart()) return;
      if (state.fired) return;
      if (state.codeCopied && state.scrollHit) {
        state.fired = true;
        track("docs_quickstart_completed", {
          page_path: window.location.pathname,
        });
      }
    }

    document.addEventListener("click", function (e) {
      var copyBtn = e.target.closest(
        'button.fern-copy-button, [data-copy], .copy-button, button[aria-label*="copy"], button[aria-label*="Copy"]'
      );
      if (copyBtn) {
        state.codeCopied = true;
        maybeFire();
      }
    });

    window.addEventListener(
      "scroll",
      function () {
        var docHeight = document.documentElement.scrollHeight - window.innerHeight;
        if (docHeight <= 0) return;
        var scrollPct = Math.round((window.scrollY / docHeight) * 100);
        if (scrollPct >= 90) {
          state.scrollHit = true;
          maybeFire();
        }
      },
      { passive: true }
    );
  }

  // 13. Code language switch — clicks on .fern-code-group-tab (Python /
  // JavaScript / cURL / Python SDK). Tells us which language users prefer
  // for each product/section.
  function setupCodeLanguageSwitchTracking() {
    var lastActiveByGroup = new WeakMap();
    document.addEventListener("click", function (e) {
      var tab = e.target.closest(".fern-code-group-tab, [class*='code-group-tab']");
      if (!tab) return;
      var toLanguage = (tab.textContent || "").trim();
      var group = tab.closest("[role='tablist'], .fern-code-block, .fern-code-group") || tab.parentElement;
      var fromLanguage = lastActiveByGroup.get(group) || "";
      if (toLanguage && toLanguage !== fromLanguage) {
        track("docs_code_language_switched", {
          from_language: fromLanguage || "(initial)",
          to_language: toLanguage,
        });
        lastActiveByGroup.set(group, toLanguage);
      }
    });
  }

  // 14. AI search ("Ask AI" button) — Fern's AI chat. High-value adoption
  // signal; users opening this typically have a specific question.
  function setupAISearchTracking() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("button");
      if (!btn) return;
      var label = (btn.getAttribute("aria-label") || "").toLowerCase();
      var text = (btn.textContent || "").trim().toLowerCase();
      if (label === "ask ai" || text === "ask ai" || text.includes("ask ai")) {
        track("docs_ai_search_used", {});
      }
    });
  }

  // 15. Copy page (Fern feature that exports the entire page as Markdown,
  // typically used to paste into ChatGPT/Claude). Strong signal that the
  // user is about to ask an AI for help with our product.
  function setupCopyPageTracking() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("button");
      if (!btn) return;
      var text = (btn.textContent || "").trim().toLowerCase();
      if (text === "copy page" || text.includes("copy page")) {
        track("docs_copy_page_used", {});
      }
    });
  }

  // 16. Version switch — clicks inside .fern-version-selector. Tells us
  // which old Waves versions still get traffic.
  function setupVersionSwitchTracking() {
    document.addEventListener("click", function (e) {
      var versionTrigger = e.target.closest(".fern-version-selector");
      if (versionTrigger) {
        // The dropdown opens; capture the trigger click as opening intent
        track("docs_version_selector_opened", {
          current_version: (versionTrigger.textContent || "").trim().slice(0, 20),
        });
        return;
      }
      // When a user picks a version option (link inside the dropdown)
      var versionLink = e.target.closest("a[href*='/v']");
      if (versionLink) {
        var match = (versionLink.href || "").match(/\/v(\d+\.\d+\.\d+)\//);
        if (match) {
          track("docs_version_switched", {
            to_version: match[1],
            from_path: window.location.pathname,
          });
        }
      }
    });
  }

  // 17. External link clicks — clicks on links going outside docs.smallest.ai
  // (github, discord, app.smallest.ai, blog, twitter). Useful for referral
  // attribution and community-channel signal.
  function setupExternalLinkTracking() {
    document.addEventListener("click", function (e) {
      var link = e.target.closest("a[href]");
      if (!link) return;
      var href = link.href || "";
      if (!/^https?:\/\//.test(href)) return;
      try {
        var u = new URL(href);
        if (
          u.hostname === window.location.hostname ||
          u.hostname.endsWith(".buildwithfern.com") ||
          u.hostname === "buildwithfern.com"
        ) return;
        // Already covered by docs_signup_clicked / docs_console_link_clicked
        if (u.hostname === "console.smallest.ai" || u.hostname === "app.smallest.ai") return;
        track("docs_external_link_clicked", {
          destination_domain: u.hostname,
          destination_url: href.slice(0, 200),
          link_text: (link.textContent || "").trim().slice(0, 60),
        });
      } catch (e) {}
    });
  }

  // Helper: derive rich API context from URL when on an API reference page.
  // Returns null if not on /api-reference/. Output:
  //   api_type:     tts | stt | voice-cloning | pronunciation | atoms | unknown
  //   api_name:     last URL segment (e.g. synthesize-lightning-v-31-speech)
  //   api_variant:  lightning-v3.1 | lightning-v2 | lightning-large | pulse | null
  //   api_protocol: rest | websocket | streaming
  //   api_method:   POST | GET | DELETE | WSS | null (parsed from page H1/title)
  function getApiContext() {
    var path = window.location.pathname.toLowerCase();
    if (path.indexOf("api-reference") === -1) return null;

    var apiType = "unknown";
    if (/text-to-speech|lightning|tts/.test(path)) apiType = "tts";
    else if (/speech-to-text|pulse|stt/.test(path)) apiType = "stt";
    else if (/voice-cloning|voice-clone/.test(path)) apiType = "voice-cloning";
    else if (/pronunciation/.test(path)) apiType = "pronunciation";
    else if (path.indexOf("/atoms/") !== -1) apiType = "atoms";

    var apiVariant = null;
    if (/lightning[-_]?v[-_]?3[-_.]1|lightning-v-?31|lightning-v-3-1/.test(path)) apiVariant = "lightning-v3.1";
    else if (/lightning[-_]?v[-_]?2|lightning-v-?2/.test(path)) apiVariant = "lightning-v2";
    else if (/lightning[-_]?large/.test(path)) apiVariant = "lightning-large";
    else if (/pulse/.test(path)) apiVariant = "pulse";

    var apiProtocol = "rest";
    if (/realtime|websocket|wss|stream(?!ing)/.test(path)) apiProtocol = "websocket";
    else if (/streaming|sse|server-sent/.test(path)) apiProtocol = "streaming";

    var apiMethod = null;
    var titleEl = document.querySelector("h1, [class*='endpoint-title' i], [class*='method' i]");
    var titleText = (titleEl && (titleEl.textContent || "")) || document.title || "";
    var methodMatch = titleText.match(/\b(POST|GET|DELETE|PUT|PATCH|WSS|WS)\b/i);
    if (methodMatch) apiMethod = methodMatch[1].toUpperCase();
    if (apiMethod === "WS") apiMethod = "WSS";
    if (apiMethod === "WSS") apiProtocol = "websocket";

    var lastSeg = path.split("/").filter(Boolean).pop() || "";
    return {
      api_type: apiType,
      api_name: lastSeg,
      api_variant: apiVariant,
      api_protocol: apiProtocol,
      api_method: apiMethod,
    };
  }

  // 18. API endpoint viewed — auto-fires on every pageview of an
  // /api-reference/ page. Tells us which endpoints get eyeballs vs
  // which get tried (compare with docs_api_playground_used to find
  // gap pages where docs are read but not tried).
  function setupAPIEndpointViewTracking() {
    function maybeFire() {
      var ctx = getApiContext();
      if (!ctx) return;
      track("docs_api_endpoint_viewed", {
        endpoint: window.location.pathname,
        api_type: ctx.api_type,
        api_name: ctx.api_name,
        api_variant: ctx.api_variant,
        api_protocol: ctx.api_protocol,
        api_method: ctx.api_method,
      });
    }
    maybeFire();
    window.addEventListener("popstate", maybeFire);
    var origPush = history.pushState;
    history.pushState = function () { origPush.apply(this, arguments); setTimeout(maybeFire, 100); };
    var origReplace = history.replaceState;
    history.replaceState = function () { origReplace.apply(this, arguments); setTimeout(maybeFire, 100); };
  }

  // 19. Search no-results — fires when the user typed ≥3 chars and the
  // dropdown shows zero matches. Critical content-gap signal — every
  // recurring no-result query is a page that should exist.
  function setupSearchNoResultsTracking() {
    var lastQuery = "";
    var lastFireAt = 0;
    var observer = new MutationObserver(function () {
      var input = document.querySelector('input[type="search"], input[placeholder*="Search" i], input[placeholder*="Find" i]');
      if (!input) return;
      var q = (input.value || "").trim();
      if (q.length < 3) return;
      var noResults =
        document.querySelector('[class*="no-result" i], [data-no-results]') ||
        Array.from(document.querySelectorAll('[role="option"], [class*="empty" i]')).some(function (el) {
          return /no results|no matches|nothing found/i.test(el.textContent || "");
        });
      if (noResults && q !== lastQuery && Date.now() - lastFireAt > 2000) {
        lastQuery = q;
        lastFireAt = Date.now();
        track("docs_search_no_results", { query: q });
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  // 20. Page dwell time — fires on page unload AND SPA navigation away.
  // Captures seconds spent on the page. Complements scroll_depth: a user
  // can scroll to 100% in 3s (skim) or 90s (deep read); dwell separates.
  function setupDwellTimeTracking() {
    var startedAt = Date.now();
    var currentPath = window.location.pathname;
    function fire(reason) {
      var seconds = Math.round((Date.now() - startedAt) / 1000);
      if (seconds < 2) return; // skip navigation glitches
      track("docs_page_dwell_time", {
        seconds: seconds,
        page_path: currentPath,
        reason: reason, // 'unload' | 'spa_nav'
      });
    }
    function reset() {
      fire("spa_nav");
      startedAt = Date.now();
      currentPath = window.location.pathname;
    }
    window.addEventListener("popstate", reset);
    var origPush2 = history.pushState;
    history.pushState = function () {
      if (window.location.pathname !== currentPath) { reset(); }
      origPush2.apply(this, arguments);
    };
    window.addEventListener("beforeunload", function () { fire("unload"); });
    window.addEventListener("pagehide", function () { fire("unload"); });
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
      setupAPIKeyCopyTracking();
      setupQuickstartCompletionTracking();
      setupCodeLanguageSwitchTracking();
      setupAISearchTracking();
      setupCopyPageTracking();
      setupVersionSwitchTracking();
      setupExternalLinkTracking();
      setupAPIEndpointViewTracking();
      setupSearchNoResultsTracking();
      setupDwellTimeTracking();
    }, 500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
