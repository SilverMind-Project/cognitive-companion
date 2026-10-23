# Common mistakes

Read when reviewing frontend changes. Part of the `front-end` skill; the rules summary is in `../SKILL.md`.

## Common mistakes to avoid

1. **Hardcoded hex colors or `rgba()` values in scoped styles**: always use `--cc-*` tokens. Hardcoded colors ignore the ccMarauders theme override and will look wrong in Marauders mode.
2. **Blue/purple colors that aren't in the DS**: no `#007aff`, no `#5e5ce6`, no purple. If you need a status color, use the DS semantic tokens (`--cc-success`, `--cc-warning`, `--cc-error`, `--cc-info`).
2a. **Vuetify material color names on `color=`**: never `color="green|orange|purple|deep-purple|blue|red"` on `v-icon`/`v-chip`/`v-btn` -- those are Vuetify's material palette, not the DS. Map to DS semantic theme colors: `green`->`success`, `orange`/`amber`->`warning`, `red`->`error`, `blue`/`deep-purple`->`info` (or `secondary` for a warm accent like a capability badge). For a neutral/muted chip, **remove** the `color` attr so `variant="tonal"` falls back to the warm `--cc-surface-2`; do not invent a `--cc-grey` token. For a muted icon use `color="var(--cc-text-3)"`.
2b. **Undefined `--cc-*` token names** silently fall back (to the fallback arg, or to an invalid value -> default). The real tokens: brand is `--cc-brand` (not `--cc-primary`); secondary/tertiary text is `--cc-text-2` / `--cc-text-3` (not `--cc-text-secondary`/`--cc-text-primary`). When in doubt, grep the name against `theme.css`. A quick audit: collect `var(--cc-*)` names used vs. the names defined in `theme.css`/`marauders.css` and diff -- any "used but not defined" is a bug (component-local CSS vars defined in the same scoped block are the only legitimate exception).
3. **Scoped `<style>` blocks with surface/text colors**: use global utility classes and Vuetify variants instead.
3a. **Static `:items-per-page`** on data tables: use server-side pagination with `:items-length`.
4. **Not resetting `page = 1` on filter changes**: causes empty pages when filters narrow results.
5. **`item-title="title"` on layout selects**: layout objects use `display_name`, not `title`.
6. **Sending fields not in the backend schema**: check the Pydantic model for allowed fields (many schemas use `extra="forbid"`).
7. **`toLocaleString()` for dates**: use `formatDateTime` from `@/services/timezone.js`.
8. **`alert()` / `confirm()` in Vue**: use `useNotify()` / `useConfirm()`.
9. **Extra fields in PATCH requests**: PATCH schemas have `extra="forbid"`. Only send fields defined in the Update schema.
10. **Incomplete test harnesses**: unresolved Vuetify components, missing router injections, and Vue Router config warnings are defects. Mount with the right plugin or explicit stubs; never suppress the warning.
10a. **Data consts in a plain `<script>` block referenced from the template**: in an SFC that has *both* `<script>` and `<script setup>` (e.g. the pipeline step configs, which export `stepDefaults`/`stepTabs` from `<script>`), the template can resolve **component imports** from the plain `<script>` (shared module scope) but **not** plain data consts -- those resolve only from `<script setup>` bindings. A `const FOO = [...]` in `<script>` is `undefined` in the template (silent: it falls back to a prop default, no build error). Declare template-referenced data in `<script setup>` (it may still read an import from the plain `<script>`, since they share module scope). The build won't catch this; a mounted runtime check will.
11. **Margin classes on Vuetify wrapper components inside slot templates**: `v-chip`, `v-btn`, and `v-avatar` render internal DOM wrappers that can absorb `mr-2`/`ml-2` classes, making the margin invisible. Always wrap these components in a `<div>` with the margin class when they appear in `#prepend` or `#append` slots:

    ```html
    <!-- WRONG: margin may land on an internal wrapper -->
    <template #prepend>
      <v-chip class="mr-2">Label</v-chip>
    </template>

    <!-- RIGHT: margin on a plain div is always visible -->
    <template #prepend>
      <div class="mr-2">
        <v-chip>Label</v-chip>
      </div>
    </template>
    ```

    Simple elements (`v-icon`, `<span>`) do not have this issue and can take margin classes directly. In `#prepend` slots, use `mr-2` (push content right); in `#append` slots, use `ml-2` (push content left).
12. **Cross-contract fallback fetch**: a `catch` that recovers the same value from a *different* endpoint's envelope (e.g. falling back to `getMediaBuffer()` when `getSampleImage()` fails). Couples you to a contract you don't own and swallows the error; call the dedicated endpoint alone and `notify.error` on failure. See "One endpoint owns each fact; no cross-contract fallbacks".
