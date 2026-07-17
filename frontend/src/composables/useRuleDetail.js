import { ref, computed, watch } from "vue";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";
import { getAppTimezone } from "@/services/timezone.js";

export const TRIGGER_TYPES = [
  { title: "Sensor Event", value: "sensor_event" },
  { title: "Cron Schedule", value: "cron" },
  { title: "Manual", value: "manual" },
  { title: "Webhook", value: "webhook" },
  { title: "Occupancy Duration", value: "occupancy_duration" },
  { title: "Telegram Command", value: "telegram" },
  { title: "Dementia Signal", value: "dementia_signal" },
];

export function sensorIcon(type) {
  const map = {
    camera: "mdi-cctv",
    presence: "mdi-motion-sensor",
    button: "mdi-gesture-tap-button",
    light: "mdi-lightbulb",
    eink: "mdi-image-edit",
  };
  return map[type] || "mdi-access-point";
}

/** Rule settings, reference data (sensors/rooms/rules/persons), and the settings-tab actions. */
export function useRuleDetail(ruleId, router) {
  const { notify } = useNotify();

  const rule = ref(null);
  const form = ref({});
  const executing = ref(false);
  const exporting = ref(false);

  const allSensors = ref([]);
  const allRooms = ref([]);
  const allRules = ref([]);
  const allPersons = ref([]);
  const telegramDefaultChatIds = ref([]);

  const sensorItems = computed(() =>
    allSensors.value.map((s) => ({
      ...s,
      _label: `${s.name || s.id} (${s.sensor_type}${s.room_name ? ", " + s.room_name : ""})`,
    })),
  );

  const roomNames = computed(() => allRooms.value.map((r) => r.name));
  const personIds = computed(() => allPersons.value.map((p) => p.id));

  const otherRuleItems = computed(() =>
    allRules.value
      .filter((r) => r.id !== ruleId.value)
      .map((r) => ({ ...r, _label: `${r.name} (#${r.id})` })),
  );

  function ruleNameById(id) {
    const r = allRules.value.find((r) => r.id === id);
    return r ? r.name : "";
  }

  async function loadRule() {
    try {
      rule.value = await api.getRule(ruleId.value);
      form.value = {
        name: rule.value.name,
        description: rule.value.description || "",
        enabled: rule.value.enabled,
        trigger_type: rule.value.trigger_types?.[0] || "sensor_event",
        schedule_cron: rule.value.cron_triggers?.[0]?.expression || "",
        primary_sensor_id: rule.value.primary_sensor_id || "",
        cool_off_minutes: rule.value.cool_off_minutes,
        max_daily_triggers: rule.value.max_daily_triggers,
        max_concurrent_executions: rule.value.max_concurrent_executions ?? 1,
        execution_timeout_minutes: rule.value.execution_timeout_minutes ?? 5,
        occupancy_config: rule.value.occupancy_config || { min_minutes: 40 },
        telegram_trigger_config: (() => {
          const cfg = rule.value.telegram_trigger_config || {};
          const ids = cfg.allowed_chat_ids?.length
            ? cfg.allowed_chat_ids
            : telegramDefaultChatIds.value;
          return {
            command: cfg.command ?? "",
            allowed_chat_ids: [...ids],
            respond_with_ack: cfg.respond_with_ack ?? true,
          };
        })(),
      };
    } catch (e) {
      notify(e.message, "error");
    }
  }

  async function loadTelegramDefaults() {
    try {
      const data = await api.getTelegramTriggerDefaults();
      telegramDefaultChatIds.value = data?.allowed_chat_ids ?? [];
    } catch {
      telegramDefaultChatIds.value = [];
    }
  }

  async function loadReferenceData() {
    const [sensors, rooms, rules, persons] = await Promise.all([
      api.getSensors().catch(() => []),
      api.getRooms().catch(() => []),
      api.getRules().catch(() => []),
      api.getPersons().catch(() => []),
    ]);
    allSensors.value = Array.isArray(sensors) ? sensors : [];
    allRooms.value = Array.isArray(rooms) ? rooms : [];
    allRules.value = Array.isArray(rules) ? rules : [];
    allPersons.value = Array.isArray(persons) ? persons : [];
  }

  async function saveSettings() {
    if (form.value.trigger_type === "telegram") {
      const ids = form.value.telegram_trigger_config?.allowed_chat_ids ?? [];
      if (!ids.length) {
        notify("Allowed Chat IDs are required for Telegram trigger rules.", "error");
        return;
      }
    }
    try {
      const triggerType = form.value.trigger_type || "sensor_event";

      // Build the payload for RuleUpdate (backend uses trigger_types list + cron_trigger_ids)
      const { schedule_cron, trigger_type: _unused, ...rest } = form.value;
      const payload = {
        ...rest,
        trigger_types: [triggerType],
      };

      // Manage cron trigger lifecycle: cron expressions are now separate CronTrigger
      // rows linked via rule_cron_triggers join table.
      if (triggerType === "cron" && schedule_cron) {
        const existingCronId = rule.value.cron_triggers?.[0]?.id;
        if (existingCronId) {
          await api.updateCronTrigger(existingCronId, {
            expression: schedule_cron,
            timezone: getAppTimezone(),
          });
          payload.cron_trigger_ids = [existingCronId];
        } else {
          const ct = await api.createCronTrigger({
            name: `${rule.value.name} cron`,
            expression: schedule_cron,
            timezone: getAppTimezone(),
          });
          payload.cron_trigger_ids = [ct.id];
        }
      } else if (triggerType !== "cron" && rule.value.cron_triggers?.length) {
        // Rule no longer uses cron — unlink existing cron triggers
        payload.cron_trigger_ids = [];
      }

      await api.updateRule(ruleId.value, payload);
      await loadRule();
      notify("Settings saved");
    } catch (e) {
      notify(e.message, "error");
    }
  }

  async function executeRule() {
    executing.value = true;
    try {
      const result = await api.executeRule(ruleId.value);
      notify(`Execution started (#${result.execution_id})`);
      if (result.execution_id) {
        await router.push({
          name: "admin-executions",
          query: {
            tab: "live",
            rule_id: ruleId.value,
            execution: result.execution_id,
          },
        });
      }
    } catch (e) {
      notify(e.message, "error");
    } finally {
      executing.value = false;
    }
  }

  async function exportRule() {
    exporting.value = true;
    try {
      const bundle = await api.exportRule(ruleId.value);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const name = (bundle.rule?.name || "rule").replace(/\s+/g, "_").toLowerCase();
      a.download = `${name}.cc-rule.json`;
      a.click();
      URL.revokeObjectURL(url);
      notify.success("Rule exported.");
    } catch (e) {
      notify.error("Export failed: " + (e.message || "Unknown error"));
    } finally {
      exporting.value = false;
    }
  }

  // Back-fill system defaults into the form as soon as they arrive from the API.
  // Runs whether the defaults load before or after the rule data.
  watch(telegramDefaultChatIds, (defaults) => {
    if (
      form.value.trigger_type === "telegram" &&
      !form.value.telegram_trigger_config?.allowed_chat_ids?.length &&
      defaults.length
    ) {
      form.value.telegram_trigger_config = {
        ...form.value.telegram_trigger_config,
        allowed_chat_ids: [...defaults],
      };
    }
  });

  return {
    rule,
    form,
    executing,
    exporting,
    sensorItems,
    roomNames,
    personIds,
    otherRuleItems,
    ruleNameById,
    loadRule,
    loadTelegramDefaults,
    loadReferenceData,
    saveSettings,
    executeRule,
    exportRule,
  };
}
