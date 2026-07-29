# UI Redesign Specification & Design System

## 1. Design Philosophy
The goal is to transition Carole.ai to a polished, modern, and sleek aesthetic with a clean, minimalist layout. We are moving away from heavily bordered, "glassmorphism"-heavy styles with excessive box-shadows, toward a flatter, cleaner UI with refined contrasts, subtle hardware-accelerated animations, and robust accessibility.

## 2. Modern Design System Variables

### Color Palette
Eliminate visual clutter by reducing reliance on heavy borders and loud neon accents. We will use a highly refined dark mode base.

```css
:root {
  /* Minimalist Base Colors */
  --bg-app: #0A0A0A;
  --bg-surface: #121212;
  --bg-surface-hover: #1A1A1A;
  --bg-surface-raised: #1C1C1C;
  --border-subtle: #242424;
  --border-focus: #404040;
  
  /* Refined Text */
  --text-primary: #EDEDED;
  --text-secondary: #A1A1AA;
  --text-muted: #71717A;
  
  /* Primary Accents (Sleek, desaturated primary) */
  --accent-primary: #10B981; /* Keep the green, but use it sparingly */
  --accent-primary-hover: #059669;
  --accent-primary-alpha: rgba(16, 185, 129, 0.1);

  /* Semantic Feedback */
  --status-error: #EF4444;
  --status-warning: #F59E0B;
  --status-info: #3B82F6;
  --status-success: #10B981;
}
```

### Typography
We will adopt a highly legible, geometric sans-serif (e.g., Geist, Inter, or system fonts) with tight tracking and clear hierarchy.

```css
:root {
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
  
  --text-xs: 0.75rem; /* 12px */
  --text-sm: 0.875rem; /* 14px */
  --text-base: 1rem; /* 16px */
  --text-lg: 1.125rem; /* 18px */
  --text-xl: 1.25rem; /* 20px */
  
  --tracking-tight: -0.015em;
  --line-height-relaxed: 1.6;
}
```

### Spacing & Layout
A strictly defined 4pt/8pt grid system.

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;

  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-full: 9999px;
}
```

### Hardware-Accelerated Animations
Avoid animating layout properties (`width`, `height`, `margin`, `padding`). Rely purely on `transform` and `opacity` for micro-interactions to ensure 60fps rendering.

```css
:root {
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);
  --duration-fast: 150ms;
  --duration-base: 250ms;
}

/* Micro-interaction for buttons and cards */
.interactive-element {
  transition: transform var(--duration-fast) var(--ease-out),
              background-color var(--duration-fast) var(--ease-out),
              opacity var(--duration-fast) var(--ease-out);
  will-change: transform, opacity;
}

.interactive-element:active {
  transform: scale(0.97); /* Subtle press effect */
}

/* Page/Component Entrance */
@keyframes fadeSlideUp {
  0% {
    opacity: 0;
    transform: translateY(8px);
  }
  100% {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-entrance {
  animation: fadeSlideUp var(--duration-base) var(--ease-out) forwards;
  will-change: transform, opacity;
}
```

## 3. Accessibility (WCAG Guidelines)
- **Contrast**: Ensure all text elements meet the WCAG AA minimum contrast ratio of 4.5:1 against their backgrounds. Our `#A1A1AA` on `#0A0A0A` exceeds this.
- **Focus Rings**: Remove default outlines but *always* provide a custom, highly visible focus ring using `:focus-visible`.
  ```css
  *:focus-visible {
    outline: 2px solid var(--accent-primary);
    outline-offset: 2px;
  }
  ```
- **Interactive Targets**: All clickable items (buttons, links) must have a minimum hit area of 44x44px.

---

## 4. Implementation Plan (Step-by-Step for Coders)

### Step 1: Update Global Styles (`frontend/src/app/globals.css`)
- Replace the existing `:root` variables with the new Design System Variables outlined above.
- Remove all `rgba` glassmorphism and claymorphism effects (e.g., `--bg-glass-panel`, `--shadow-clay`).
- Replace `.card`, `.btn`, and `.input` classes with flattened styles. Remove excessive box-shadows and thick borders.
- Apply the `transform` scale effects to `.btn:active`.
- Add the new hardware-accelerated keyframes (`fadeSlideUp`).

### Step 2: Refactor Layout & App Shell (`frontend/src/app/page.tsx`)
- Update the main layout wrapper to use the new `--bg-app` variable.
- Remove inline styles that set background colors to old `var(--color-canvas)`.
- Ensure components mounted conditionally use the `.animate-entrance` class for smooth transitions.

### Step 3: Minimalist Sidebar (`frontend/src/components/Sidebar.tsx`)
- Remove the logo text sub-branding to reduce visual clutter.
- Switch sidebar active states from heavy backgrounds to a subtle `--border-subtle` highlight or text color change to `--text-primary`.
- Remove drop shadows from hover states.
- Adjust padding to use the new `--space-*` variables.

### Step 4: Streamlined Chat Interface (`frontend/src/components/ChatInterface.tsx`)
- Flatten message bubbles: Remove `box-shadow` and `backdrop-filter`. Use `--bg-surface` for AI messages and a very subtle `--bg-surface-raised` for Human messages.
- Input Area: Make the input field borderless or use a single subtle bottom border. Remove the heavy `border-top` from the input container.
- Update agent avatars to be minimalist icons or initials with flat background colors (no borders or drop shadows).
- Remove the heavy borders on tool outputs and intermediate traces.

### Step 5: Update Other Components
- Iterate through `KanbanBoard.tsx`, `AgentPanel.tsx`, and `SettingsPanel.tsx`.
- Replace instances of `box-shadow` cards with simple `border: 1px solid var(--border-subtle)` panels.
- Standardize all typography classes (e.g., `display-sm`, `body-sm`) in the CSS and ensure components reference them properly without overriding font sizes inline.
