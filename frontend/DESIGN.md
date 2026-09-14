---
name: PolicyMate AI
description: A trusted academic policy workspace for cited answers, official documents, and governed administration.
colors:
  primary: "#b5121b"
  primary-hover: "#930f16"
  primary-active: "#760c12"
  primary-soft: "#fff1f2"
  background: "#f5f7fb"
  card: "#ffffff"
  text: "#101828"
  text-secondary: "#344054"
  text-muted: "#667085"
  text-subtle: "#98a2b3"
  border: "#e4e9f2"
  border-strong: "#d0d7e5"
  surface-muted: "#f7f9fc"
  success: "#087443"
  success-soft: "#ecfdf3"
  warning: "#b54708"
  warning-soft: "#fffaeb"
  error: "#b42318"
  error-soft: "#fef3f2"
  info: "#175cd3"
  info-soft: "#eff8ff"
typography:
  display:
    fontFamily: 'Inter, "Be Vietnam Pro", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "clamp(34px, 4vw, 56px)"
    fontWeight: 760
    lineHeight: 1.03
    letterSpacing: "-0.05em"
  headline:
    fontFamily: 'Inter, "Be Vietnam Pro", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "clamp(26px, 3vw, 34px)"
    fontWeight: 700
    lineHeight: 1.22
    letterSpacing: "-0.035em"
  title:
    fontFamily: 'Inter, "Be Vietnam Pro", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "17px"
    fontWeight: 700
    lineHeight: 1.35
    letterSpacing: "-0.02em"
  body:
    fontFamily: 'Inter, "Be Vietnam Pro", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  label:
    fontFamily: 'Inter, "Be Vietnam Pro", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "12px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "normal"
  control:
    fontFamily: 'Inter, "Be Vietnam Pro", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "normal"
rounded:
  small: "9px"
  control: "10px"
  card: "14px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "20px"
  xl: "24px"
  section: "34px"
  page-inline: "clamp(20px, 2.4vw, 36px)"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.card}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "0 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.card}"
  button-secondary:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "0 16px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text-secondary}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "0 16px"
  button-danger:
    backgroundColor: "{colors.error}"
    textColor: "{colors.card}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "0 16px"
  search-field:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 12px"
  status-success:
    backgroundColor: "{colors.success-soft}"
    textColor: "{colors.success}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "3px 9px"
  document-card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text}"
    rounded: "{rounded.card}"
    padding: "20px"
  citation-card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text}"
    rounded: "12px"
    padding: "14px"
  navigation-item:
    backgroundColor: "{colors.primary-soft}"
    textColor: "{colors.primary}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "0 12px"
  data-table:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text-secondary}"
    typography: "{typography.body}"
    rounded: "{rounded.card}"
---

# Design System: PolicyMate AI

## Overview

**Creative North Star: "The Verified Academic Desk"**

The Verified Academic Desk treats PolicyMate AI as an institutional workspace: calm, document-led, and explicit about evidence. Academic red identifies decisive actions, active navigation, and institutional anchors; paper white and slate neutrals carry the reading work.

Density adapts to the job. Student flows keep a spacious task-first foreground, while admin views become compact enough for tables and governance without compressing labels or status context. The product narrative moves from authentication, to cited search and answers, to official PDF inspection, then to version, access, and RBAC administration.

Depth is light and border-led. Motion is brief and functional, Lucide line icons clarify actions, and every important status remains readable without relying on color alone.

**Key Characteristics:**

- Academic red is reserved for identity, primary actions, focus, and active state.
- Paper-white surfaces sit on a cool archive canvas with slate typography.
- Citations, validity, version, and access state stay adjacent to the content they qualify.
- Student surfaces breathe; admin surfaces use compact, scannable rows and tables.
- Lucide line icons reinforce function without becoming decoration.

## Colors

The palette pairs institutional Academic HUST Red with paper-white surfaces, cool slate neutrals, and restrained semantic colors for document and workflow state.

### Primary

- **Academic HUST Red:** Identity marks, primary calls to action, active navigation, selected controls, links that advance a task, and visible focus.
- **Deep Academic Red:** Hover emphasis for red actions and links.
- **Seal Red:** Pressed-state depth where an active state is implemented.
- **Blush Paper:** Selected navigation, quiet branded icon wells, and low-emphasis red hover surfaces.

### Secondary

- **Verified Green:** Current, successful, active, and reviewed states.
- **Review Amber:** Superseded, pending, warning, and needs-review states.
- **Reference Blue:** Informational states and analytical reference data only; it does not replace the academic red brand voice.

### Neutral

- **Archive Canvas:** The cool page background behind work surfaces.
- **Paper White:** Cards, panels, fields, navigation, and document reading surfaces.
- **Institutional Ink:** Primary headings and high-emphasis content.
- **Slate Copy:** Supporting text and dense operational values.
- **Evidence Gray:** Descriptions, metadata labels, helper text, and inactive navigation.
- **Quiet Gray:** Placeholders and the lowest-emphasis labels.
- **Hairline Slate:** Default dividers and card boundaries.
- **Structural Slate:** Stronger control borders and hover boundaries.
- **Cool Desk:** Low-contrast hover, input, and grouped-control backgrounds.

### Named Rules

**The Academic Red Rule.** HUST red marks identity, primary actions, focus, and selected state; status semantics keep their own verified green, review amber, error red, or reference blue.

**The Evidence Color Rule.** Validity and workflow colors always appear with a label or icon; color is never the only carrier of state.

## Typography

**Display Font:** Inter with Be Vietnam Pro and UI sans-serif fallbacks  
**Body Font:** Inter with Be Vietnam Pro and UI sans-serif fallbacks  
**Label Font:** Inter with Be Vietnam Pro and UI sans-serif fallbacks

**Character:** A single contemporary sans-serif voice keeps Vietnamese policy language neutral, readable, and operational. Large headings use tight tracking for authority; body copy and metadata stay plain enough for sustained evidence review.

### Hierarchy

- **Display** (760, fluid 34–56px, 1.03): Home welcome statements and the rare highest-level product message.
- **Headline** (700, fluid 26–34px, 1.22): Page titles, document titles, and admin work-area headings.
- **Title** (700, 17px, 1.35): Panel headers, answer headers, and grouped content titles.
- **Body** (400, 14px, 1.6): Answers, instructions, descriptions, and readable supporting copy; long explanatory lines stay near the observed 68–70ch maximum.
- **Label** (700, 12px, 1.3): Field labels, statuses, table headers, and operational metadata.
- **Control** (600, 14px, 1): Buttons and compact action text.

### Named Rules

**The Document First Rule.** Headlines are compact and decisive; body copy stays readable, while operational metadata uses smaller labels without hiding version, issuer, or effective date.

## Layout

The authenticated shell is desktop-first: admin pages use a fixed 236px navigation rail and a centered workspace up to 1480px, while student pages use a 72px top header and a task-led content column. Core student work areas stay around 1240–1360px. Page gutters use a fluid 20–36px range and commonly tighten to 16px on narrow screens.

Student home and answer views use asymmetric two-column grids: the question or answer owns the wider column while evidence or source context occupies the narrower one. Document detail pairs a 245px metadata rail with the official viewer. Admin dashboards use multi-column metric, chart, and table layouts; these collapse to one or two columns between roughly 1320px and 900px, with most mobile stacking complete by 640–700px. Wide governance tables keep their intrinsic width and scroll horizontally instead of crushing columns.

Spacing is compact but not cramped: 8–16px governs control internals and row gaps, 18–24px governs card interiors, and 32–34px separates major sections. Sticky evidence and metadata panels become static when their companion grid collapses.

**The Task-First Viewport Rule.** Keep the current question, answer, document, or governance task visible before secondary material; collapse columns instead of squeezing them.

## Elevation & Depth

The system is border-led and nearly flat at rest. Hairline slate borders separate most white surfaces from the archive canvas; low ambient shadows are used on reusable cards, a larger shadow lifts menus and dialogs, and stronger red-tinted or dark ambient shadows are reserved for primary call-to-action and showcase moments. Focus depth comes from a red-tinted ring rather than a generic glow.

### Shadow Vocabulary

- **Card Ambient** (`0 1px 2px rgb(16 24 40 / 3%), 0 8px 24px rgb(16 24 40 / 5%)`): Quiet separation for cards, metrics, and answer surfaces.
- **Card Lift** (`0 16px 36px rgb(36 63 108 / 11%)`): Hover or emphasized-card lift; use sparingly.
- **Overlay Lift** (`0 24px 64px rgb(15 23 42 / 18%)`): Menus, drawers, dialogs, and other temporary layers.
- **Focus Ring** (`0 0 0 4px rgb(181 18 27 / 13%)`): Focus-within treatment for fields and grouped controls in authenticated shells.

### Named Rules

**The Border Before Shadow Rule.** Use a 1px border as the default surface boundary; reserve stronger shadows for overlays, hover lift, and signature showcase moments.

## Shapes

Controls use gently rounded 9–10px corners, recurring cards and panels use 12–14px corners, and compact statuses use full pills. Larger 16px corners appear on overlays and feature containers, but they are not the default. Borders remain light and continuous; document and table layouts favor rectangular reading planes over ornamental silhouettes.

**The Soft Utility Rule.** Use 9–10px corners for controls, 12–14px for cards and panels, and full pills only for status or compact tags.

## Components

### Buttons

- **Shape:** Compact rounded controls (10px) with a 40px default minimum height; dense variants use 34px and prominent actions reach 44–46px.
- **Primary:** Academic red, white text, medium-weight control typography, and 16px horizontal padding.
- **Hover / Focus:** Darken to Deep Academic Red; show the global red focus outline or the red-tinted focus ring. Active controls move or scale by about one pixel and reduced-motion mode removes that movement.
- **Secondary:** Paper white with a structural slate border and institutional ink text.
- **Ghost:** Transparent at rest, using a Cool Desk hover surface.
- **Danger:** Error red with white text; destructive outline actions may use a pale error border and error text.

### Chips

- **Style:** Compact 24px-minimum pills with 3px × 9px padding, a small dot when useful, and a soft semantic surface paired with its dark semantic text.
- **State:** Current/success, superseded/review, expired/error, info, and neutral variants must include visible wording.

### Cards / Containers

- **Corner Style:** 12–14px for recurring cards and panels.
- **Background:** Paper White on Archive Canvas; Cool Desk is used inside grouped or lower-emphasis regions.
- **Shadow Strategy:** Flat or Card Ambient at rest, with Card Ambient or Card Lift on interactive hover.
- **Border:** A 1px Hairline Slate border is the default.
- **Internal Padding:** 14–24px according to density; 18–20px is the common dashboard range.

### Inputs / Fields

- **Style:** White or muted-white fields, 9–10px corners, a 1px slate border, and 42–48px control height.
- **Focus:** Academic red border plus the red-tinted Focus Ring; focus remains visible across keyboard and focus-within interactions.
- **Error / Disabled:** Error states pair a pale error surface with dark error text; disabled controls retain their shape and drop to roughly 55–70% opacity.

### Navigation

Desktop administration uses a 236px white rail with 46px rows, Lucide line icons, and a blush-red active item with a 3px inset red marker. Student navigation uses a 72px top header. At 900px and below, the rail becomes an off-canvas panel with a dark overlay; primary top navigation and wide search controls progressively hide by 760px.

### Source Citation

Citation cards are compact evidence objects: document type and validity lead, the official title stays prominent, and reference, version, page, and excerpt metadata remain visible before the source-opening action.

**The Citation Is Navigation Rule.** Citation cards must expose document type, validity, reference, version/page context, and an affordance to open the official source.

### Data Tables

Tables use a bordered white container, muted header band, compact 12–14px rows, tabular numerals, and horizontal overflow for narrow screens. Hover may tint a row, but it must not displace columns or obscure status labels.

## Do's and Don'ts

### Do:

- **Do** use Academic HUST Red for identity, primary actions, focus, and active navigation.
- **Do** keep citations, document version, validity, issuer, and effective date beside the answer or source they qualify.
- **Do** use 1px slate borders and paper-white surfaces as the default hierarchy before adding shadow.
- **Do** collapse multi-column layouts at their observed breakpoints and preserve 44px touch targets where the build already provides them.
- **Do** pair Lucide icons with text or accessible names and honor reduced-motion preferences.

### Don't:

- **Don't** introduce gradients or heavy glass as a recurring identity device; the build's isolated showcase and loading effects are exceptions, not system primitives.
- **Don't** replace Academic HUST Red with the blue literals that remain in the legacy `/student` route or one-off admin accents.
- **Don't** turn compact admin labels into unlabeled icon-only controls or color-only status.
- **Don't** stack cards inside cards when a divider, row, or two-column layout keeps evidence relationships clearer.
- **Don't** use pill radii for general cards, fields, or buttons.
