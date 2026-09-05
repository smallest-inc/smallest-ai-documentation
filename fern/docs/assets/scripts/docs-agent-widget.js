/**
 * docs.smallest.ai: in-docs support agent (the Smallest web widget).
 *
 * Renders the Atoms widget bottom-right on every docs page, the same way
 * ElevenLabs runs their own agent on their docs. Dogfoods the product and
 * gives readers a live "ask the docs" path.
 *
 * Setup (one time, in the dashboard):
 *   1. Create a single-prompt agent for docs support. Point its knowledge
 *      base at https://docs.smallest.ai/llms.txt (or the llms-full.txt) and
 *      write a prompt that answers from the docs and links to pages.
 *   2. Open the agent's Widget tab, pick a mode (voice or chat), set the
 *      allowlist to docs.smallest.ai and *.docs.buildwithfern.com so the
 *      preview builds work too.
 *   3. Paste the agent id below. Leave it empty and this script does
 *      nothing (the docs ship with it empty).
 *
 * Reference: /voice-agents/build/widget
 */
(function () {
  if (typeof window === "undefined" || typeof document === "undefined") return;

  var DOCS_AGENT_ID = "";
  if (!DOCS_AGENT_ID) return;
  if (document.querySelector("atoms-widget")) return;

  var el = document.createElement("atoms-widget");
  el.setAttribute("assistant-id", DOCS_AGENT_ID);
  document.body.appendChild(el);

  var script = document.createElement("script");
  script.src = "https://unpkg.com/atoms-widget-core@latest/dist/embed/widget.umd.js";
  script.async = true;
  document.body.appendChild(script);
})();
