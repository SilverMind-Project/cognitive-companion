<template>
  <div ref="editorHost" class="template-input-wrapper">
    <div ref="editorEl" class="template-input-editor" :class="{ 'template-input-focus': focused }" />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, shallowRef } from "vue";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { autocompletion, CompletionContext } from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { syntaxTree } from "@codemirror/language";
import { api } from "../../../../services/api.js";

const props = defineProps({
  modelValue: { type: String, default: "" },
  multiline: { type: Boolean, default: false },
  ruleContext: { type: Object, default: () => ({ labels: [], stepOutputs: {} }) },
  label: { type: String, default: "" },
});

const emit = defineEmits(["update:modelValue"]);

const editorEl = ref(null);
const editorHost = ref(null);
const focused = ref(false);

const view = shallowRef(null);

// Cached data keys for autocomplete
let dataKeysCache = null;
let dataKeysLoading = false;

async function loadDataKeys() {
  if (dataKeysCache) return dataKeysCache;
  if (dataKeysLoading) return [];
  dataKeysLoading = true;
  try {
    const keys = await api.getDataKeys();
    dataKeysCache = keys;
    return keys;
  } catch {
    return { trigger: [], system: [], step_outputs: {} };
  } finally {
    dataKeysLoading = false;
  }
}

function buildCompletions(dataKeys) {
  const result = [];

  // Trigger variables
  for (const v of dataKeys.trigger || []) {
    result.push({ label: v.key, detail: v.description || "Trigger context", type: "variable" });
  }

  // System variables
  for (const v of dataKeys.system || []) {
    result.push({ label: v.key, detail: v.description || "System", type: "variable" });
  }

  // General pattern
  result.push({ label: "steps.<label>.outputs.<key>", detail: "General pattern", type: "text" });

  // Per-step-type output schemas
  const stepOutputs = dataKeys.step_outputs || {};
  for (const [stepType, schema] of Object.entries(stepOutputs)) {
    const props = schema.properties || {};
    for (const [propName, propSchema] of Object.entries(props)) {
      result.push({
        label: `steps.<label>.outputs.${propName}`,
        detail: `${stepType}: ${propSchema.description || propName}`,
        type: "variable",
      });
    }
  }

  // Per-instance entries for current pipeline labels
  for (const label of props.ruleContext.labels || []) {
    const schema = props.ruleContext.stepOutputs?.[label];
    if (!schema?.properties) continue;
    for (const propName of Object.keys(schema.properties)) {
      result.push({
        label: `steps.${label}.outputs.${propName}`,
        detail: `${label} output`,
        type: "variable",
      });
    }
  }

  return result;
}

// Autocomplete source function for CodeMirror
function autocompleteSource(context) {
  const pos = context.pos;
  const text = context.state.doc.toString();

  // Check if we're inside {{ ... }}
  // Find the last {{ before the cursor that hasn't been closed
  let braceStart = -1;
  for (let i = pos - 1; i >= 0; i--) {
    if (text[i] === "{" && i > 0 && text[i - 1] === "{") {
      braceStart = i + 1;
      break;
    }
    if (text[i] === "}" && i > 0 && text[i - 1] === "}") {
      // Found closing braces before opening - not inside {{
      break;
    }
  }

  // If we're not inside {{ }}, only trigger autocomplete if typing {{
  if (braceStart === -1) {
    // Check if we just typed the second {
    if (pos >= 2 && text[pos - 2] === "{" && text[pos - 1] === "{") {
      // User just typed {{ — trigger autocomplete
      return loadDataKeys().then((keys) => {
        const completions = buildCompletions(keys);
        return {
          from: pos,
          options: completions.map((c) => ({
            label: c.label,
            detail: c.detail,
            type: c.type,
          })),
        };
      });
    }
    return null;
  }

  // We are inside {{ ... }} — find the partial word
  const insideText = text.slice(braceStart, pos);
  const lastDot = insideText.lastIndexOf(".");
  const partial = lastDot >= 0 ? insideText.slice(lastDot + 1) : insideText;

  return loadDataKeys().then((keys) => {
    const completions = buildCompletions(keys);
    const filtered = completions.filter((c) =>
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

// CodeMirror extensions
function createExtensions() {
  const updateListener = EditorView.updateListener.of((update) => {
    if (update.docChanged) {
      const val = update.state.doc.toString();
      emit("update:modelValue", val);
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
    EditorView.theme({
      "&": { maxHeight: props.multiline ? "none" : "56px" },
      ".cm-scroller": {
        fontFamily: "var(--cc-font-mono, monospace)",
        fontSize: "14px",
        lineHeight: "1.6",
      },
      ".cm-content": {
        padding: "8px 12px",
      },
      ".cm-gutters": {
        display: "none",
      },
    }),
  ];
}

onMounted(() => {
  const state = EditorState.create({
    doc: props.modelValue || "",
    extensions: createExtensions(),
  });

  view.value = new EditorView({
    state,
    parent: editorEl.value,
  });
});

// Sync external modelValue changes into CodeMirror
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

.template-input-editor {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.22);
  border-radius: var(--cc-radius-sm, 8px);
  background: var(--cc-surface-3);
  transition: border-color 0.2s;
  overflow: hidden;
}

.template-input-focus {
  border-color: rgb(var(--v-theme-primary));
}

.template-input-editor :deep(.cm-editor) {
  background: transparent;
}

.template-input-editor :deep(.cm-editor.cm-focused) {
  outline: none;
}

.template-input-editor :deep(.cm-completionIcon) {
  opacity: 0.6;
}

.template-input-editor :deep(.cm-tooltip-autocomplete) {
  background: var(--cc-bg-elevated);
  border: 1px solid var(--cc-glass-border-strong);
  border-radius: var(--cc-radius-md);
  box-shadow: var(--cc-shadow-lg);
  padding: 4px;
}

.template-input-editor :deep(.cm-tooltip-autocomplete .cm-completionInfo) {
  font-size: 12px;
  color: var(--cc-text-2);
}

.template-input-editor :deep(.cm-tooltip-autocomplete .cm-completionLabel) {
  font-family: var(--cc-font-mono);
  font-size: 13px;
}
</style>
