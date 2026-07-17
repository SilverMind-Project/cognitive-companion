import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const mocks = vi.hoisted(() => ({
  getRule: vi.fn(),
  updateRule: vi.fn(),
  getSensors: vi.fn(),
  getRooms: vi.fn(),
  getRules: vi.fn(),
  getPersons: vi.fn(),
  getTelegramTriggerDefaults: vi.fn(),
  executeRule: vi.fn(),
  exportRule: vi.fn(),
  addRuleContext: vi.fn(),
  deleteRuleContext: vi.fn(),
  addRuleDep: vi.fn(),
  deleteRuleDep: vi.fn(),
  getWorkflows: vi.fn(),
  createCronTrigger: vi.fn(),
  updateCronTrigger: vi.fn(),
  notify: vi.fn(),
  push: vi.fn(),
  replace: vi.fn(),
  route: { params: { id: "7" }, query: {} },
}));
mocks.notify.success = vi.fn();
mocks.notify.error = vi.fn();

vi.mock("@/services/api.js", () => ({
  api: {
    getRule: (...a) => mocks.getRule(...a),
    updateRule: (...a) => mocks.updateRule(...a),
    getSensors: (...a) => mocks.getSensors(...a),
    getRooms: (...a) => mocks.getRooms(...a),
    getRules: (...a) => mocks.getRules(...a),
    getPersons: (...a) => mocks.getPersons(...a),
    getTelegramTriggerDefaults: (...a) => mocks.getTelegramTriggerDefaults(...a),
    executeRule: (...a) => mocks.executeRule(...a),
    exportRule: (...a) => mocks.exportRule(...a),
    addRuleContext: (...a) => mocks.addRuleContext(...a),
    deleteRuleContext: (...a) => mocks.deleteRuleContext(...a),
    addRuleDep: (...a) => mocks.addRuleDep(...a),
    deleteRuleDep: (...a) => mocks.deleteRuleDep(...a),
    getWorkflows: (...a) => mocks.getWorkflows(...a),
    createCronTrigger: (...a) => mocks.createCronTrigger(...a),
    updateCronTrigger: (...a) => mocks.updateCronTrigger(...a),
  },
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: mocks.notify }),
}));

vi.mock("@/services/timezone.js", () => ({
  formatDateTime: (iso) => iso || "",
  getAppTimezone: () => "America/Los_Angeles",
  DATETIME_COLUMN_WIDTH: 180,
}));

vi.mock("vue-router", () => ({
  useRoute: () => mocks.route,
  useRouter: () => ({ push: mocks.push, replace: mocks.replace }),
}));

vi.mock("@/components/pipeline/CronBuilder.vue", () => ({
  default: {
    name: "CronBuilder",
    props: ["modelValue", "timezone"],
    template: '<div data-testid="cron-builder">{{ modelValue }}</div>',
  },
}));

vi.mock("@/components/pipeline/PipelineCanvas.vue", () => ({
  default: {
    name: "PipelineCanvas",
    props: ["ruleId"],
    template: '<div data-testid="pipeline-canvas">{{ ruleId }}</div>',
  },
}));

import RuleDetailView from "../../src/views/admin/RuleDetailView.vue";

const RULE = {
  id: 7,
  name: "Pacing alert",
  description: "desc",
  enabled: true,
  trigger_types: ["sensor_event"],
  primary_sensor_id: "sensor-1",
  cool_off_minutes: 5,
  max_daily_triggers: 10,
  max_concurrent_executions: 1,
  execution_timeout_minutes: 5,
  occupancy_config: { min_minutes: 40 },
  cron_triggers: [],
  telegram_trigger_config: {},
  contexts: [
    { id: 1, context_type: "room", negate: false, config_json: { room_name: "Kitchen" } },
    { id: 2, context_type: "room_transition", negate: false, config_json: { foo: "bar" } },
  ],
  dependencies: [
    { id: 5, parent_rule_id: 3, lookback_minutes: 20, require_success: true },
  ],
};

const stubs = {
  "v-btn": {
    template: '<button @click="$emit(\'click\')"><slot /></button>',
    props: ["icon", "variant", "color", "prependIcon", "loading", "to", "size"],
  },
  "v-chip": { template: "<span><slot /></span>", props: ["color", "size", "variant"] },
  "v-tabs": {
    template:
      '<div><button v-for="t in [\'settings\',\'pipeline\',\'contexts\',\'dependencies\',\'executions\']" :key="t" :data-testid="\'tab-\'+t" @click="$emit(\'update:modelValue\', t)">{{t}}</button></div>',
    props: ["modelValue", "color"],
  },
  "v-tab": { template: "<span />" },
  "v-window": { template: "<div><slot /></div>", props: ["modelValue"] },
  "v-window-item": { template: "<div><slot /></div>", props: ["value"] },
  "v-card": { template: "<section><slot /></section>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>", props: ["cols", "md"] },
  "v-spacer": { template: "<div />" },
  "v-progress-circular": { template: "<div />" },
  "v-text-field": {
    template:
      '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ["modelValue", "label", "type"],
  },
  "v-textarea": {
    template:
      '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ["modelValue", "label", "rows"],
  },
  "v-select": {
    template:
      '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><option v-for="it in normalizedItems" :key="it.value" :value="it.value">{{ it.title }}</option></select>',
    props: ["modelValue", "items", "label", "itemTitle", "itemValue"],
    computed: {
      normalizedItems() {
        return (this.items || []).map((it) =>
          typeof it === "string" ? { title: it, value: it } : it,
        );
      },
    },
  },
  "v-autocomplete": {
    template:
      '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><option v-for="it in items" :key="it">{{ it }}</option></select>',
    props: ["modelValue", "items", "label", "itemTitle", "itemValue", "clearable"],
  },
  "v-combobox": {
    template: '<input @input="$emit(\'update:modelValue\', [$event.target.value])" />',
    props: ["modelValue", "items", "label", "multiple", "chips"],
  },
  "v-switch": {
    template:
      '<input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
    props: ["modelValue", "label", "color"],
  },
  "v-checkbox": {
    template:
      '<input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
    props: ["modelValue", "label"],
  },
  "v-alert": { template: "<div><slot /></div>", props: ["type", "variant", "density"] },
  "v-dialog": {
    template: '<div v-if="modelValue"><slot /></div>',
    props: ["modelValue", "maxWidth"],
  },
  "v-list": { template: "<ul><slot /></ul>" },
  "v-list-item": {
    template: '<li><slot name="prepend" /><slot /><slot name="append" /></li>',
  },
  "v-list-item-title": { template: "<div><slot /></div>" },
  "v-icon": { template: "<i><slot /></i>", props: ["size", "color"] },
  "v-data-table": {
    template:
      '<div data-testid="exec-table"><div v-for="item in items" :key="item.id" class="exec-row" @click="$emit(\'click:row\', $event, { item })"><slot name="item.status" :item="item" /><slot name="item.started_at" :item="item" /><slot name="item.completed_at" :item="item" /><slot name="item._duration" :item="item" /></div><slot name="no-data" /></div>',
    props: ["headers", "items", "loading", "itemValue", "hover"],
  },
};

function mountView() {
  return mount(RuleDetailView, { global: { stubs } });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.route.query = {};
  mocks.getRule.mockResolvedValue(structuredClone(RULE));
  mocks.getSensors.mockResolvedValue([
    { id: "sensor-1", name: "Front door", sensor_type: "presence", room_name: "Hallway" },
  ]);
  mocks.getRooms.mockResolvedValue([{ id: 1, name: "Kitchen" }, { id: 2, name: "Bedroom" }]);
  mocks.getRules.mockResolvedValue([
    { id: 7, name: "Pacing alert" },
    { id: 3, name: "Night watch" },
  ]);
  mocks.getPersons.mockResolvedValue([{ id: "p1" }]);
  mocks.getTelegramTriggerDefaults.mockResolvedValue({ allowed_chat_ids: [] });
  mocks.getWorkflows.mockResolvedValue([
    { id: 20, status: "completed", started_at: "2026-07-01T10:00:00Z", completed_at: "2026-07-01T10:00:05Z" },
  ]);
  mocks.updateRule.mockResolvedValue({});
  mocks.executeRule.mockResolvedValue({ execution_id: 99 });
  mocks.exportRule.mockResolvedValue({ rule: { name: "Pacing alert" } });
  mocks.addRuleContext.mockResolvedValue({});
  mocks.deleteRuleContext.mockResolvedValue({});
  mocks.addRuleDep.mockResolvedValue({});
  mocks.deleteRuleDep.mockResolvedValue({});
});

describe("RuleDetailView", () => {
  it("renders the rule header once loaded", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.text()).toContain("Pacing alert");
    expect(wrapper.text()).toContain("Active");
    expect(mocks.getRule).toHaveBeenCalledWith(7);
  });

  it("clicking Test Run starts an execution and routes to it", async () => {
    const wrapper = mountView();
    await flushPromises();
    const testRunBtn = wrapper.findAll("button").find((b) => b.text().includes("Test Run"));
    await testRunBtn.trigger("click");
    await flushPromises();
    expect(mocks.executeRule).toHaveBeenCalledWith(7);
    expect(mocks.push).toHaveBeenCalledWith({
      name: "admin-executions",
      query: { tab: "live", rule_id: 7, execution: 99 },
    });
  });

  it("Export builds a download from the exported bundle", async () => {
    const createObjectURL = vi.fn().mockReturnValue("blob:x");
    const revokeObjectURL = vi.fn();
    global.URL.createObjectURL = createObjectURL;
    global.URL.revokeObjectURL = revokeObjectURL;
    const wrapper = mountView();
    await flushPromises();
    const exportBtn = wrapper.findAll("button").find((b) => b.text().includes("Export"));
    await exportBtn.trigger("click");
    await flushPromises();
    expect(mocks.exportRule).toHaveBeenCalledWith(7);
    expect(createObjectURL).toHaveBeenCalled();
    expect(mocks.notify.success).toHaveBeenCalledWith("Rule exported.");
  });

  it("saves settings with the trigger_types payload shape", async () => {
    const wrapper = mountView();
    await flushPromises();
    await wrapper.find('[data-testid="tab-settings"]').trigger("click");
    await flushPromises();
    const nameInput = wrapper.find("input");
    await nameInput.setValue("Pacing alert v2");
    const saveBtn = wrapper.findAll("button").find((b) => b.text().includes("Save Settings"));
    await saveBtn.trigger("click");
    await flushPromises();
    expect(mocks.updateRule).toHaveBeenCalledWith(
      7,
      expect.objectContaining({
        name: "Pacing alert v2",
        trigger_types: ["sensor_event"],
      }),
    );
    const [, payload] = mocks.updateRule.mock.calls[0];
    expect(payload).not.toHaveProperty("trigger_type");
    expect(payload).not.toHaveProperty("schedule_cron");
  });

  it("embeds the pipeline canvas with the rule id", async () => {
    const wrapper = mountView();
    await flushPromises();
    const canvas = wrapper.find('[data-testid="pipeline-canvas"]');
    expect(canvas.exists()).toBe(true);
    expect(canvas.text()).toBe("7");
  });

  it("renders context filters and summaries, including the raw-JSON fallback type", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.text()).toContain("Kitchen");
    expect(wrapper.text()).toContain("room_transition");
  });

  it("deletes a context via the delete button", async () => {
    const wrapper = mountView();
    await flushPromises();
    await wrapper.find('[data-testid="tab-contexts"]').trigger("click");
    await flushPromises();
    const deleteBtn = wrapper.findAll("li button").find((b) => b.exists());
    await deleteBtn.trigger("click");
    await flushPromises();
    expect(mocks.deleteRuleContext).toHaveBeenCalledWith(7, 1);
  });

  it("renders dependencies and adds a new one", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.text()).toContain("Night watch");
    await wrapper.find('[data-testid="tab-dependencies"]').trigger("click");
    await flushPromises();
    const addDepBtn = wrapper.findAll("button").find((b) => b.text().includes("Add Dependency"));
    await addDepBtn.trigger("click");
    await flushPromises();
    const confirmAdd = wrapper.findAll("button").find((b) => b.text() === "Add");
    await confirmAdd.trigger("click");
    await flushPromises();
    expect(mocks.addRuleDep).toHaveBeenCalled();
  });

  it("loads executions when the executions tab is selected and rows navigate", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(mocks.getWorkflows).not.toHaveBeenCalled();
    await wrapper.find('[data-testid="tab-executions"]').trigger("click");
    await flushPromises();
    expect(mocks.getWorkflows).toHaveBeenCalledWith({ rule_id: 7, limit: 50 });
    const row = wrapper.find(".exec-row");
    expect(row.text()).toContain("completed");
    await row.trigger("click");
    expect(mocks.push).toHaveBeenCalledWith({
      name: "admin-executions",
      query: { tab: "history", rule_id: 7, execution: 20 },
    });
  });
});
