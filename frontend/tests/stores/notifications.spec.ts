import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";

import CcSnackbarHost from "@/components/CcSnackbarHost.vue";
import { useNotify } from "@/composables/useNotify.js";
import { DEFAULT_TIMEOUT, useNotificationsStore } from "@/stores/notifications";

// Vuetify is stubbed rather than installed, per the convention in tests/views. The stub renders
// its slot and re-emits the dismiss event, which is all the host's contract depends on.
const stubs = {
  "v-snackbar": {
    template: `<div class="snackbar" :data-color="color" :data-timeout="timeout">
      <slot />
      <button class="close" @click="$emit('update:model-value', false)">x</button>
    </div>`,
    props: ["modelValue", "color", "timeout", "location"],
  },
};

function mountHost() {
  return mount(CcSnackbarHost, { global: { stubs } });
}

describe("notifications store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("collects messages from independent modules into one queue", () => {
    // Two unrelated modules each reach for the notifier, as a view and a shared composable do.
    const moduleA = useNotify();
    const moduleB = useNotify();

    moduleA.notify.error("disk on fire");
    moduleB.notify.success("saved");

    const store = useNotificationsStore();
    expect(store.queue.map((n) => [n.text, n.color])).toEqual([
      ["disk on fire", "error"],
      ["saved", "success"],
    ]);
  });

  it("keeps the notify.<level> call signature and the 3000ms timeout", () => {
    const { notify } = useNotify();
    notify("plain");
    notify.warning("careful");
    notify.info("fyi");

    const store = useNotificationsStore();
    expect(store.queue.map((n) => n.color)).toEqual(["success", "warning", "info"]);
    expect(store.queue.every((n) => n.timeout === DEFAULT_TIMEOUT)).toBe(true);
  });

  it("renders a message raised by a non-component module (C14 regression)", async () => {
    // The defect: useNotify used to mint fresh refs per call, so a message raised here -- in a
    // plain module, not the component owning the snackbar -- was written to refs no template
    // rendered and the user never saw it. This fails against the old implementation.
    const host = mountHost();

    useNotify().notify.error("raised from a non-component module");
    await host.vm.$nextTick();

    expect(host.text()).toContain("raised from a non-component module");
    expect(host.find(".snackbar").attributes("data-color")).toBe("error");
  });

  it("renders concurrent messages simultaneously", async () => {
    const host = mountHost();
    const store = useNotificationsStore();

    store.error("first");
    store.success("second");
    await host.vm.$nextTick();

    expect(host.findAll(".snackbar")).toHaveLength(2);
    expect(host.text()).toContain("first");
    expect(host.text()).toContain("second");
  });

  it("a snackbar timing out dismisses only its own message", async () => {
    const host = mountHost();
    const store = useNotificationsStore();
    store.notify("one");
    store.notify("two");
    await host.vm.$nextTick();

    await host.findAll(".close")[0].trigger("click");

    expect(store.queue.map((n) => n.text)).toEqual(["two"]);
    expect(host.findAll(".snackbar")).toHaveLength(1);
  });

  it("dismiss is a no-op for an id already gone", () => {
    const store = useNotificationsStore();
    const id = store.notify("one");
    store.dismiss(id);
    store.dismiss(id);

    expect(store.queue).toEqual([]);
  });
});
