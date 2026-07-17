/**
 * API client barrel.
 *
 * @module api
 *
 * Every method here is defined in a typed domain module under `services/modules/`, built on the
 * one request core in {@link http.ts}. This file exists only so the ~180 existing
 * `api.someMethod(...)` call sites keep working; it holds no logic of its own.
 *
 * **New code should import the module directly** rather than reaching through this barrel:
 *
 *     import { getRules } from "@/services/modules/rules";
 *
 * Adding an endpoint means adding it to (or creating) a domain module. Do not add a method
 * here, and do not call `fetch` from a component.
 *
 * Types come from `src/generated/api-types.d.ts`, generated from the backend's OpenAPI schema
 * (`npm run generate:api`). If an endpoint's type is missing or `unknown`, the backend route is
 * missing `response_model` -- fix it there.
 */

import { useAuthStore } from "@/stores/auth";
import * as activitiesModule from "./modules/activities";
import * as adminModule from "./modules/admin";
import * as companionModule from "./modules/companion";
import * as gateGraphsModule from "./modules/gate_graphs";
import * as guidedModule from "./modules/guided";
import * as haModule from "./modules/ha";
import * as healthModule from "./modules/health";
import * as imageModule from "./modules/image";
import * as infoCardsModule from "./modules/info_cards";
import * as interactionsModule from "./modules/interactions";
import * as knowledgeModule from "./modules/knowledge";
import * as layoutsModule from "./modules/layouts";
import * as mediaModule from "./modules/media";
import * as occupancyModule from "./modules/occupancy";
import * as personsModule from "./modules/persons";
import * as pipelineModule from "./modules/pipeline";
import * as quizzesModule from "./modules/quizzes";
import * as roomsModule from "./modules/rooms";
import * as routinesModule from "./modules/routines";
import * as rulesModule from "./modules/rules";
import * as sensorsModule from "./modules/sensors";
import * as signalsModule from "./modules/signals";
import * as webhooksModule from "./modules/webhooks";
import * as workflowsModule from "./modules/workflows";

/**
 * @deprecated The auth store owns the API key: call `useAuthStore().setApiKey(key)`.
 *
 * Kept so the existing `api.setApiKey(...)` call sites keep working. It delegates rather than
 * writing localStorage itself: a direct write would update storage while leaving the store's
 * reactive key stale, so the provider seam would keep sending the old key until a reload.
 */
function setApiKey(key) {
  useAuthStore().setApiKey(key);
}

export const api = {
  setApiKey,

  ...activitiesModule,
  ...adminModule,
  ...companionModule,
  ...gateGraphsModule,
  ...guidedModule,
  ...haModule,
  ...healthModule,
  ...imageModule,
  ...infoCardsModule,
  ...interactionsModule,
  ...knowledgeModule,
  ...layoutsModule,
  ...mediaModule,
  ...occupancyModule,
  ...personsModule,
  ...pipelineModule,
  ...quizzesModule,
  ...roomsModule,
  ...routinesModule,
  ...rulesModule,
  ...sensorsModule,
  ...signalsModule,
  ...webhooksModule,
  ...workflowsModule,
};

export { openPipelineSocket } from "./modules/ws";
