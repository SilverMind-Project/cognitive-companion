<template>
  <div class="template-input-wrapper mb-1">
    <div v-if="label" class="template-input-label text-caption font-weight-medium mb-1">{{ label }}</div>
    <div
      ref="editorEl"
      class="template-input-editor"
      :class="{
        'template-input-focus': focused,
        'template-input-resizable': multiline,
      }"
      :style="containerStyle"
    />
    <div v-if="hint" class="template-input-hint text-caption text-medium-emphasis mt-1 px-1">{{ hint }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, shallowRef, inject } from "vue";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, tooltips } from "@codemirror/view";
import { autocompletion } from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { api } from "../../../../services/api.js";

// Global base theme for autocomplete tooltips. EditorView.baseTheme() injects
// styles without a scoped class prefix so they reach tooltip elements placed in
// document.body (outside the editor root) by tooltips({ parent: document.body }).
// CM6's StyleModule deduplicates these, so multiple TemplateInput instances
// do not double-inject the CSS.
const tooltipBaseTheme = EditorView.baseTheme({
  ".cm-tooltip-autocomplete": {
    background: "rgb(var(--v-theme-surface-bright)) !important",
    border: "1px solid rgba(var(--v-theme-on-surface), 0.12) !important",
    borderRadius: "var(--cc-radius-md, 10px) !important",
    boxShadow: "0 8px 32px rgba(0,0,0,0.3) !important",
    padding: "4px !important",
    zIndex: "2400 !important",
    color: "rgb(var(--v-theme-on-surface)) !important",
  },
  ".cm-tooltip-autocomplete .cm-completionLabel": {
    fontFamily: "var(--cc-font-mono, monospace)",
    fontSize: "13px",
    color: "rgb(var(--v-theme-on-surface)) !important",
  },
  ".cm-tooltip-autocomplete .cm-completionDetail": {
    fontSize: "12px",
    color: "rgba(var(--v-theme-on-surface), 0.6) !important",
  },
  ".cm-tooltip-autocomplete ul li[aria-selected]": {
    background: "rgba(var(--v-theme-primary, 10 132 255), 0.18) !important",
    color: "rgb(var(--v-theme-on-surface)) !important",
  },
});

const props = defineProps({
  modelValue: { type: String, default: "" },
  multiline: { type: Boolean, default: false },
  label: { type: String, default: "" },
  hint: { type: String, default: "" },
  rows: { type: Number, default: 4 },
});

const emit = defineEmits(["update:modelValue"]);

// Rule context injected by StepConfigDialog. Provides step labels + output schemas
// for per-pipeline autocomplete suggestions. No prop drilling required.
const injectedRuleContext = inject(
  "pipelineRuleContext",
  computed(() => ({ labels: [], stepOutputs: {} }))
);

const editorEl = ref(null);
const focused = ref(false);
const view = shallowRef(null);

// Initial container height is derived from rows. After mount the user can drag
// to resize (multiline only). CM6 fills the container via height: 100%.
const ROW_HEIGHT_PX = 24; // matches lineHeight 1.6 × fontSize 14px ≈ 22.4, rounded up
const PADDING_PX = 16;    // 8px top + 8px bottom from .cm-content

const containerStyle = computed(() => {
  if (!props.multiline) return {};
  return { height: `${props.rows * ROW_HEIGHT_PX + PADDING_PX}px` };
});

// Cached data keys for autocomplete — fetched once, shared across instances
let dataKeysCache = null;
let dataKeysLoading = false;

async function loadDataKeys() {
  if (dataKeysCache) return dataKeysCache;
  if (dataKeysLoading) return { trigger: [], system: [], step_outputs: {} };
  dataKeysLoading = true;
  try {
    dataKeysCache = await api.getDataKeys();
    return dataKeysCache;
  } catch {
    return { trigger: [], system: [], step_outputs: {} };
  } finally {
    dataKeysLoading = false;
  }
}

function buildCompletions(dataKeys) {
  const result = [];
  const ruleCtx = injectedRuleContext.value;

  for (const v of dataKeys.trigger || []) {
    result.push({ label: v.key, detail: v.description || "Trigger context", type: "variable" });
  }
  for (const v of dataKeys.system || []) {
    result.push({ label: v.key, detail: v.description || "System", type: "variable" });
  }

  result.push({ label: "steps.<label>.outputs.<key>", detail: "General pattern", type: "text" });

  // Per-step-type output schemas from backend
  for (const [stepType, schema] of Object.entries(dataKeys.step_outputs || {})) {
    for (const [propName, propSchema] of Object.entries(schema.properties || {})) {
      result.push({
        label: `steps.<label>.outputs.${propName}`,
        detail: `${stepType}: ${propSchema.description || propName}`,
        type: "variable",
      });
    }
  }

  // Per-instance completions for this pipeline's actual step labels
  const labels = ruleCtx?.labels ?? [];
  const stepOutputs = ruleCtx?.stepOutputs ?? {};
  for (const stepLabel of labels) {
    const schema = stepOutputs[stepLabel];
    if (!schema?.properties) continue;
    for (const propName of Object.keys(schema.properties)) {
      result.push({
        label: `steps.${stepLabel}.outputs.${propName}`,
        detail: `${stepLabel} output`,
        type: "variable",
      });
    }
  }

  return result;
}

function autocompleteSource(context) {
  const pos = context.pos;
  const text = context.state.doc.toString();

  // Determine if the cursor is inside an open {{ ... }}
  let braceStart = -1;
  for (let i = pos - 1; i >= 0; i--) {
    if (text[i] === "{" && i > 0 && text[i - 1] === "{") {
      braceStart = i + 1;
      break;
    }
    if (text[i] === "}" && i > 0 && text[i - 1] === "}") {
      break; // closed brace before any open — not inside {{ }}
    }
  }

  if (braceStart === -1) {
    // Only trigger immediately after the user types "{{"
    if (pos >= 2 && text[pos - 2] === "{" && text[pos - 1] === "{") {
      return loadDataKeys().then((keys) => ({
        from: pos,
        options: buildCompletions(keys).map((c) => ({
          label: c.label,
          detail: c.detail,
          type: c.type,
        })),
      }));
    }
    return null;
  }

  // Inside {{ ... }}: offer filtered completions based on what's typed so far
  const insideText = text.slice(braceStart, pos);
  const lastDot = insideText.lastIndexOf(".");
  const partial = lastDot >= 0 ? insideText.slice(lastDot + 1) : insideText;

  return loadDataKeys().then((keys) => {
    const filtered = buildCompletions(keys).filter((c) =>
      c.label.toLowerCase().includes(partial.toLowerCase())
    );
    return {
      from: pos - partial.length,
      options: filtered.map((c) => ({
        label: c.label,
        detail: c.detail,
        type: c.type,
        apply: c.label,
      })),
    };
  });
}

function createExtensions() {
  const updateListener = EditorView.updateListener.of((update) => {
    if (update.docChanged) {
      emit("update:modelValue", update.state.doc.toString());
    }
  });

  const focusListener = EditorView.domEventHandlers({
    focus: () => { focused.value = true; },
    blur: () => { focused.value = false; },
  });

  return [
    updateListener,
    focusListener,
    history(),
    keymap.of([...defaultKeymap, ...historyKeymap]),
    autocompletion({
      activateOnTyping: true,
      override: [autocompleteSource],
      defaultKeymap: true,
    }),
    // Render autocomplete tooltips as direct children of document.body so they
    // escape any overflow:hidden / clip ancestors (e.g. StepConfigDialog's
    // scrollable content pane).
    tooltips({ parent: document.body }),
    tooltipBaseTheme,
    EditorView.theme({
      // Fill the container element so CSS resize: vertical works cleanly.
      "&": {
        height: props.multiline ? "100%" : "56px",
        minHeight: props.multiline ? "56px" : "56px",
      },
      ".cm-scroller": {
        fontFamily: "var(--cc-font-mono, monospace)",
        fontSize: "14px",
        lineHeight: "1.6",
        overflowY: "auto",
      },
      ".cm-content": { padding: "8px 12px" },
      ".cm-gutters": { display: "none" },
    }),
  ];
}

onMounted(() => {
  const state = EditorState.create({
    doc: props.modelValue || "",
    extensions: createExtensions(),
  });
  view.value = new EditorView({ state, parent: editorEl.value });
});

// Sync external modelValue changes into CodeMirror (e.g. when a step is loaded)
watch(
  () => props.modelValue,
  (newVal) => {
    if (!view.value) return;
    const current = view.value.state.doc.toString();
    if (newVal !== current) {
      view.value.dispatch({
        changes: { from: 0, to: current.length, insert: newVal || "" },
      });
    }
  }
);

onBeforeUnmount(() => {
  view.value?.destroy();
  view.value = null;
});
</script>

<style scoped>
.template-input-wrapper {
  position: relative;
}

.template-input-label {
  color: rgba(var(--v-theme-on-surface), 0.7);
  letter-spacing: 0.009em;
}

.template-input-editor {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.22);
  border-radius: var(--cc-radius-sm, 8px);
  background: var(--cc-surface-3);
  transition: border-color 0.2s;
  /* overflow: hidden keeps rounded corners and clips the CM editor to the border.
     It also satisfies the CSS requirement for resize: vertical to activate. */
  overflow: hidden;
}

/* Vertical resize handle — only for multiline inputs */
.template-input-resizable {
  resize: vertical;
  min-height: 56px;
}

.template-input-focus {
  border-color: rgb(var(--v-theme-primary));
  border-width: 2px;
}

.template-input-hint {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 12px;
  line-height: 1.4;
}

.template-input-editor :deep(.cm-editor) {
  background: transparent;
  /* Fill the container so the resize handle controls editor height */
  height: 100%;
}

.template-input-editor :deep(.cm-editor.cm-focused) {
  outline: none;
}

.template-input-editor :deep(.cm-completionIcon) {
  opacity: 0.6;
}
</style>
