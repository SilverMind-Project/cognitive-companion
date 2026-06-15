/**
 * API response shape contracts.
 *
 * Every endpoint that returns structured data declares its shape here.
 * In dev mode, responses are validated against these contracts and mismatches
 * are logged as console warnings so wiring bugs are caught immediately.
 *
 * ## How to use
 *
 * 1. Define a shape below with `def(path, shape)`.
 * 2. Pass the contract name to `request()`: `request("/quizzes", { contract: "quizzes.list" })`.
 * 3. The shape is only validated in dev mode (`import.meta.env.DEV`).
 *
 * ## Shape DSL
 *
 * - `"array"` — any array
 * - `"object"` — any non-null, non-array object
 * - `{ key: spec, ... }` — object with expected keys + type specs
 * - `{ key: "?" }` — optional key (present or absent)
 */

const contracts = new Map();

function def(path, shape) {
  contracts.set(path, shape);
}

// ---------------------------------------------------------------------------
// Knowledge
// ---------------------------------------------------------------------------
def("quizzes.list", { items: "array", total: "number" });
def("quizzes.single", "object");

def("info-cards.list", { items: "array", total: "number" });
def("info-cards.single", "object");

def("knowledge.documents.list", { items: "array" });
def("knowledge.documents.single", "object");

def("knowledge.layouts.list", { layouts: "array" });
def("knowledge.layouts.single", "object");

def("knowledge.interactions.queries", "array");
def("knowledge.interactions.sessions", "array");
def("knowledge.interactions.session", "object");
def("knowledge.interactions.deliveries", "array");

// ---------------------------------------------------------------------------
// Rules
// ---------------------------------------------------------------------------
def("rules.list", "array");
def("rules.single", "object");
def("rules.export", "object");
def("rules.import", "object");
def("rule.edges.list", [{ id: "number", rule_id: "number", source_step_id: "number", source_port: "string", target_step_id: "number", target_port: "string" }]);
def("rule.edges.replace", [{ id: "number", rule_id: "number", source_step_id: "number", source_port: "string", target_step_id: "number", target_port: "string" }]);
def("rule.steps.positions.update", { updated: "number" });

// ---------------------------------------------------------------------------
// Workflows
// ---------------------------------------------------------------------------
def("workflows.list", "array");
def("workflows.single", "object");
def("workflows.detail", {
  id: "number",
  rule_id: "number",
  status: "string",
  graph: "?",
  timeline: "array",
  can_cancel: "boolean",
  can_rerun: "boolean",
});

// ---------------------------------------------------------------------------
// Rooms, Sensors, Persons
// ---------------------------------------------------------------------------
def("rooms.list", "array");
def("rooms.single", "object");

def("sensors.list", "array");
def("sensors.single", "object");

def("persons.list", "array");
def("persons.single", "object");
def("persons.enrolled", "array");
def("persons.locations", "array");
def("persons.location", "object");
def("persons.history", "array");
def("persons.sightings", "array");

// ---------------------------------------------------------------------------
// Alerts, Events, Activities
// ---------------------------------------------------------------------------
def("signals.feed", "array");
def("events.list", "array");
def("activities.list", "array");

// ---------------------------------------------------------------------------
// Dashboard / occupancy
// ---------------------------------------------------------------------------
def("occupancy", { occupancy: "object" });

// ---------------------------------------------------------------------------
// Image / E-Ink
// ---------------------------------------------------------------------------
def("image.templates.list", "array");
def("image.templates.single", "object");
def("image.fonts", { fonts: "array" });
def("image.states", "array");

// ---------------------------------------------------------------------------
// Media
// ---------------------------------------------------------------------------
def("media.buffer", { items: "array", total: "number" });
def("media.aggregators", { items: "array", total: "number" });

// ---------------------------------------------------------------------------
// Interactive responses
// ---------------------------------------------------------------------------
def("interactive.responses.list", "array");

// ---------------------------------------------------------------------------
// CTS Analytics
// ---------------------------------------------------------------------------
def("cts.heatmap", { person_id: "string", bins: "array" });
def("cts.transitZones", "array");
def("cts.gait.trend", { person_id: "string", days: "array", trend: "string" });

// ---------------------------------------------------------------------------
// Pipeline runs
// ---------------------------------------------------------------------------
def("pipeline.runs.list", "array");
def("pipeline.runs.single", { execution_id: "number", rule_id: "number", status: "string", nodes: "array", edges: "array" });
def("pipeline.ingest.activity", "array");

// ---------------------------------------------------------------------------
// Validation (dev-only)
// ---------------------------------------------------------------------------

function _checkType(value, spec, path) {
  if (typeof spec === "string") {
    switch (spec) {
      case "array":
        return Array.isArray(value);
      case "object":
        return value !== null && typeof value === "object" && !Array.isArray(value);
      case "number":
        return typeof value === "number";
      case "string":
        return typeof value === "string";
      case "boolean":
        return typeof value === "boolean";
      case "?":
        return true; // optional — always ok
      default:
        console.warn(`[contracts] Unknown type specifier "${spec}" at ${path}`);
        return true;
    }
  }

  if (typeof spec === "object" && spec !== null && !Array.isArray(spec)) {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      console.warn(`[contracts] Expected object at ${path}, got ${value === null ? "null" : typeof value}`);
      return false;
    }
    for (const [key, valSpec] of Object.entries(spec)) {
      if (valSpec === "?") continue;
      if (!(key in value)) {
        console.warn(`[contracts] Missing key "${key}" at ${path}`);
        return false;
      }
      _checkType(value[key], valSpec, `${path}.${key}`);
    }
    return true;
  }

  return true;
}

/**
 * Validate a response against a named contract.  No-op in production.
 *
 * @param {string} contract  Contract name registered with `def()`.
 * @param {*}      data      Parsed JSON response body.
 */
export function validateContract(contract, data) {
  if (!import.meta.env.DEV) return;

  const spec = contracts.get(contract);
  if (!spec) {
    console.warn(`[contracts] Unknown contract "${contract}"`);
    return;
  }

  _checkType(data, spec, contract);
}
