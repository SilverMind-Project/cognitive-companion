/**
 * App-info lifecycle.
 *
 * Owns the *fetch* of the operator-configured app info at startup; `services/timezone.js` stays
 * the formatting engine. That split is deliberate: timezone.js reads localStorage on every
 * formatter call specifically so Vite HMR cannot reset it to "UTC" mid-session (see its module
 * docstring), and its formatters are pure functions called from non-component code. Routing them
 * through a store would reintroduce the bug that design fixed. The store is the lifecycle owner,
 * not the source of truth for formatting.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { getAppInfo } from "@/services/modules/admin";
import { getAppTimezone, initTimezone } from "@/services/timezone.js";
import { useNotify } from "@/composables/useNotify";

export const useAppConfigStore = defineStore("appConfig", () => {
  const timezone = ref<string>(getAppTimezone());
  const appName = ref<string>("");
  const appVersion = ref<string>("");
  const loaded = ref(false);

  /**
   * Fetch app info and hand the timezone to timezone.js.
   *
   * Never throws: a backend that is down at page load must not block the mount. The formatters
   * then fall back to the last cached value (or UTC), which is the pre-refactor behavior.
   */
  async function bootstrap(): Promise<void> {
    try {
      const info = await getAppInfo();
      initTimezone(info.timezone);
      timezone.value = getAppTimezone();
      appName.value = info.name;
      appVersion.value = info.version;
      loaded.value = true;
    } catch {
      const { notify } = useNotify();
      notify.warning(`Failed to fetch app-info; timezone defaults to ${getAppTimezone()}`);
    }
  }

  return { timezone, appName, appVersion, loaded, bootstrap };
});
