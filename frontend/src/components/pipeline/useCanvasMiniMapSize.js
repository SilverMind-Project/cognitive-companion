import { nextTick, onBeforeUnmount, onMounted, reactive } from "vue";

const DEFAULT_WIDTH = 220;
const DEFAULT_HEIGHT = 124;

function resolveElement(targetRef) {
  const target = targetRef.value;
  if (!target) return null;
  if (typeof Element !== "undefined" && target instanceof Element) return target;
  if (typeof Element !== "undefined" && target.$el instanceof Element) return target.$el;
  return null;
}

export function useCanvasMiniMapSize(targetRef, width = DEFAULT_WIDTH) {
  const size = reactive({
    width,
    height: DEFAULT_HEIGHT,
  });

  let resizeObserver = null;

  function update() {
    const element = resolveElement(targetRef);
    if (!element) return;

    const { width: canvasWidth, height: canvasHeight } = element.getBoundingClientRect();
    if (canvasWidth <= 0 || canvasHeight <= 0) return;

    size.width = width;
    size.height = Math.round((width * canvasHeight) / canvasWidth);
  }

  onMounted(async () => {
    await nextTick();
    update();

    const element = resolveElement(targetRef);
    if (!element || typeof ResizeObserver === "undefined") return;

    resizeObserver = new ResizeObserver(update);
    resizeObserver.observe(element);
  });

  onBeforeUnmount(() => {
    resizeObserver?.disconnect();
  });

  return size;
}
