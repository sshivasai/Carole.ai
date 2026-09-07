(args = {}) => {
  const {
    maxNodes = 5000,
    maxItems = 350,
    viewportExpansion = 300,
  } = args;

  const token =
    globalThis.crypto?.randomUUID?.() ||
    `${Date.now()}-${Math.random().toString(36).slice(2)}`;

  const registry = new Map();
  const items = [];
  let visited = 0;
  let refCounter = 0;
  let truncated = false;

  const SKIP = new Set([
    "script", "style", "noscript", "template", "head"
  ]);

  const INTERACTIVE_ROLES = new Set([
    "button", "link", "checkbox", "radio", "switch", "textbox",
    "searchbox", "combobox", "listbox", "option", "tab",
    "menuitem", "menuitemcheckbox", "menuitemradio",
    "slider", "spinbutton", "treeitem"
  ]);

  function compact(value, limit = 180) {
    return String(value ?? "").replace(/\s+/g, " ").trim().slice(0, limit);
  }

  function styleVisible(element) {
    try {
      if (element.closest("[hidden], [inert], [aria-hidden='true']")) {
        return false;
      }

      if (typeof element.checkVisibility === "function") {
        return element.checkVisibility({
          checkOpacity: true,
          checkVisibilityCSS: true,
        });
      }

      const style = getComputedStyle(element);
      return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        style.visibility !== "collapse" &&
        Number(style.opacity) !== 0
      );
    } catch {
      return false;
    }
  }

  function inViewport(rect) {
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      rect.bottom >= -viewportExpansion &&
      rect.right >= -viewportExpansion &&
      rect.top <= innerHeight + viewportExpansion &&
      rect.left <= innerWidth + viewportExpansion
    );
  }

  function hasVisibleRect(element) {
    return Array.from(element.getClientRects()).some(inViewport);
  }

  function isInteractive(element) {
    const tag = element.localName;
    const role = element.getAttribute("role");

    return (
      ["button", "input", "select", "textarea", "summary"].includes(tag) ||
      (tag === "a" && element.hasAttribute("href")) ||
      INTERACTIVE_ROLES.has(role) ||
      element.isContentEditable ||
      element.tabIndex >= 0 ||
      typeof element.onclick === "function" ||
      getComputedStyle(element).cursor === "pointer"
    );
  }

  function nameFor(element) {
    const root = element.getRootNode();
    const labelledBy = element.getAttribute("aria-labelledby");

    if (labelledBy) {
      const value = labelledBy
        .split(/\s+/)
        .map(id => root.getElementById?.(id)?.textContent || "")
        .join(" ");

      if (compact(value)) return compact(value);
    }

    const labels = element.labels
      ? Array.from(element.labels).map(label => label.innerText).join(" ")
      : "";

    return compact(
      element.getAttribute("aria-label") ||
      labels ||
      element.getAttribute("placeholder") ||
      element.innerText ||
      element.getAttribute("alt") ||
      element.getAttribute("title") ||
      element.getAttribute("name") ||
      ""
    );
  }

  function describe(element) {
    const tag = element.localName;
    const type = element.getAttribute("type") || "";
    const attrs = {
      role: element.getAttribute("role") || undefined,
      type: type || undefined,
      name: nameFor(element),
      disabled: Boolean(
        element.matches(":disabled") ||
        element.getAttribute("aria-disabled") === "true"
      ),
      readonly: Boolean(element.readOnly),
    };

    if (
      ["input", "textarea", "select"].includes(tag) &&
      typeof element.value === "string"
    ) {
      const autocomplete = element.getAttribute("autocomplete") || "";
      const sensitive =
        type.toLowerCase() === "password" ||
        /(?:one-time-code|cc-number|cc-csc)/i.test(autocomplete);

      // Include empty current values, not stale HTML value attributes.
      attrs.value = sensitive
        ? (element.value ? "[REDACTED]" : "")
        : compact(element.value, 160);
    }

    if (type === "checkbox" || type === "radio") {
      attrs.checked = Boolean(element.checked);
    } else if (element.hasAttribute("aria-checked")) {
      attrs.checked = element.getAttribute("aria-checked");
    }

    for (const attribute of ["aria-expanded", "aria-selected", "aria-invalid"]) {
      if (element.hasAttribute(attribute)) {
        attrs[attribute] = element.getAttribute(attribute);
      }
    }

    if (tag === "select") {
      attrs.options = Array.from(element.options)
        .slice(0, 40)
        .map(option => ({
          label: compact(option.label, 100),
          value: option.value,
          selected: option.selected,
          disabled: option.disabled,
        }));
      attrs.optionsTruncated = element.options.length > 40;
    }

    return attrs;
  }

  function add(item) {
    if (items.length >= maxItems) {
      truncated = true;
      return false;
    }
    items.push(item);
    return true;
  }

  function walk(node, parentInteractive = false) {
    if (visited >= maxNodes || items.length >= maxItems) {
      truncated = true;
      return;
    }
    visited += 1;

    if (node.nodeType === Node.TEXT_NODE) {
      if (parentInteractive) return;

      const text = compact(node.textContent, 500);
      const parent = node.parentElement;
      if (!text || !parent || !styleVisible(parent)) return;

      const range = document.createRange();
      range.selectNodeContents(node);

      if (Array.from(range.getClientRects()).some(inViewport)) {
        add({ kind: "text", text });
      }
      return;
    }

    if (node.nodeType !== Node.ELEMENT_NODE) return;

    const element = node;
    if (SKIP.has(element.localName)) return;

    // display:contents elements can have visible children without their own box.
    const style = getComputedStyle(element);
    if (
      style.display === "none" ||
      style.visibility === "hidden" ||
      style.visibility === "collapse" ||
      Number(style.opacity) === 0 ||
      element.hidden ||
      element.inert ||
      element.getAttribute("aria-hidden") === "true"
    ) {
      return;
    }

    let interactive = false;

    if (styleVisible(element) && hasVisibleRect(element)) {
      interactive = isInteractive(element);

      if (interactive) {
        const localRef = String(refCounter++);
        registry.set(localRef, element);

        if (!add({
          kind: "element",
          ref: localRef,
          tag: element.localName,
          attrs: describe(element),
        })) {
          return;
        }
      }
    }

    // Frames are traversed separately by Playwright, including cross-origin ones.
    if (element.localName === "iframe") return;

    const root = element.shadowRoot || element;
    for (const child of root.childNodes) {
      walk(child, parentInteractive || interactive);
      if (truncated) break;
    }
  }

  walk(document.body || document.documentElement);

  // Replacing the registry invalidates the previous snapshot.
  window.__caroleSnapshot = { token, nodes: registry };

  return {
    token,
    items,
    truncated,
    scroll: {
      x: scrollX,
      y: scrollY,
      height: document.documentElement.scrollHeight,
      viewportHeight: innerHeight,
    },
  };
}