# Workspace Rule: Active Usage of Installed Skills (.agents/skills)

All AI agents working on this codebase **MUST** actively utilize and adhere to the skills installed in `.agents/skills/` before and during implementation.

## Mandatory Directives

### 1. Impeccable Design Quality & Craft Floor (`impeccable`)
- **Mandatory Quality Standard**: Consult and execute with `impeccable` for all frontend development.
- **Craft Floor Enforcement**:
  - Apply `Operate` mode to all POS, cashier, billing, and backoffice screens (scanability, contrast, keyboard shortcuts, and zero latency outrank decorative fluff).
  - Perform `polish`, `typeset`, and `harden` passes on all components prior to delivering tasks.
  - Test UI on retail display resolutions: 1366×768 (standard POS) and 1600×900.

### 2. UI, Art Direction & Layout Aesthetics
- **`design-taste-frontend`**: Anti-slop frontend art direction, curated layouts, rich color palettes, typography, and avoiding generic/templated UI.
- **`ui-ux-pro-max`**: Comprehensive UI/UX intelligence, accessibility, spacing tokens, tables/grids, and stack-specific best practices.
- **`ui-styling`**: Component styling patterns, Tailwind CSS architecture, and consistent design tokens.
- **`design-system`**: Three-layer design tokens (primitive → semantic → component).
- **`pick-ui-library`**: Evaluating and integrating accessible UI component primitives.
- **`brand` & `design`**: Brand voice, visual assets, and style guide consistency.

### 3. Motion, Animation & Interaction Craft (Emil Kowalski Philosophy)
- **`emil-design-eng`**: Emil Kowalski's guidelines on tactile feedback, component craft, and subtle interaction details.
- **`animate`**: Building animations from scratch (purpose, timing, curve, interrupts, exits).
- **`animation-performance`**: Keeping animations inside the 60fps frame budget (composite-only properties: `transform`, `opacity`).
- **`animation-vocabulary`**: Reverse-lookup nomenclature for motion effects.
- **`apple-design`**: Fluid physical springs, spatial consistency, depth, and tactile responsiveness.
- **`find-animation-opportunities`**: Locating high-value micro-interaction moments for cashier workflows.
- **`review-animations` & `improve-animations`**: Auditing, refining, and polishing animation transitions.
- **`remove-animations`**: Removing animations that impede speed on high-frequency POS/cashier keyboard workflows.
- **`ask-sonner`**: Standardizing all application toast notifications with Sonner.

### 4. Prototyping, Stress-Testing & Hardening
- **`prototype`**: Rapid prototyping and validating UX flows before committing to full data layers.
- **`break-ui`**: Stress-testing components with worst-case data (overflows, long Sinhala/Tamil/English strings, extreme currency figures, zero/huge stock counts).
- **`impeccable`**: Continuously polish typography, contrast, hierarchy, and responsive behavior (1366×768 / 1600×900).

### 5. Backend Architecture & Secure API Design (`secure-api-builder`)
- **Mandatory API Security Standard**: Consult and execute with `secure-api-builder` for all backend routes, database queries, and network communication:
  - **Input Validation**: Strict Zod schema validation for all query params, path parameters, and request payloads. Reject unknown fields.
  - **SQL Injection Prevention**: 100% parameterized queries via PostgreSQL `pg` driver; zero query string concatenation.
  - **Output DTOs**: Never leak raw database objects, stack traces, internal paths, or credentials.
  - **Defense in Depth**: Server-side role and terminal permission verification on every request.
  - **Rate Limiting & Timeouts**: Enforce timeouts on DB queries, throttles on sensitive endpoints, and idempotency keys on payment operations.

---

## Execution Rule
- When any frontend, UI, animation, or backend API task is initiated, inspect the relevant `SKILL.md` file located at `.agents/skills/<skill_name>/SKILL.md`.
- Never generate generic, low-effort, or MVP-slop interfaces or insecure API endpoints when these specialized guidelines are present.
