/**
 * E-ink image templates, rendered display state, and previews.
 *
 * The preview helpers return object URLs: the caller owns them and must `URL.revokeObjectURL`
 * when the component unmounts.
 */

import {
  client,
  postFormForBlobUrl,
  postJsonForBlobUrl,
  requestBlobUrl,
  requestForm,
  unwrap,
} from "@/services/http";
import type { components } from "@/generated/api-types";

type Schemas = components["schemas"];

export type ImageTemplateOut = Schemas["ImageTemplateOut"];
export type ActiveImageStateOut = Schemas["ActiveImageStateOut"];

// ─── Templates ─────────────────────────────────────────────────────────────

export const getImageTemplates = () => unwrap(client.GET("/api/v1/image/templates", {}));

export const createImageTemplate = (formData: FormData) =>
  requestForm("/api/v1/image/templates", "POST", formData);

export const updateImageTemplate = (id: number, data: Schemas["ImageTemplateUpdate"]) =>
  unwrap(
    client.PUT("/api/v1/image/templates/{template_id}", {
      params: { path: { template_id: id } },
      body: data,
    }),
  );

export const updateImageTemplateImage = (id: number, formData: FormData) =>
  requestForm(`/api/v1/image/templates/${id}/image`, "PUT", formData);

export const deleteImageTemplate = (id: number) =>
  unwrap(
    client.DELETE("/api/v1/image/templates/{template_id}", {
      params: { path: { template_id: id } },
    }),
  );

export const getImageFonts = () => unwrap(client.GET("/api/v1/image/fonts", {}));

/** Background image of a saved template, as an authenticated object URL. Caller revokes. */
export const getImageTemplatePreview = (id: number) =>
  requestBlobUrl(`/api/v1/image/templates/${id}/preview`);

// ─── Display state ─────────────────────────────────────────────────────────

export const getImageStates = () => unwrap(client.GET("/api/v1/image/states", {}));

export const renderImage = (data: Schemas["RenderPayload"]) =>
  unwrap(client.POST("/api/v1/image/render", { body: data }));

/**
 * Reset the given sensors (or all when omitted) to their default template.
 *
 * The body is the bare id array: the endpoint's `sensor_ids: list[str] | None` parameter *is*
 * the body. The old client wrapped it as `{sensor_ids: [...]}`, which could only 422; nothing
 * calls it today, so the break was invisible.
 */
export const resetImage = (sensorIds?: string[]) =>
  unwrap(client.POST("/api/v1/image/reset", { body: sensorIds ?? null }));

// ─── Previews (binary) ─────────────────────────────────────────────────────

/**
 * Preview a render. Returns an object URL of the PNG; the caller revokes it.
 *
 * Not on the typed client: the response is image bytes, not JSON.
 */
export const previewImage = (data: Schemas["RenderPreviewPayload"]): Promise<string> =>
  postJsonForBlobUrl("/api/v1/image/preview", data);

/**
 * Preview using FormData (new-template upload, or live region/font overrides).
 *
 * Fields: text, regions_json, font_filename, template_id? (int), image? (File).
 * Returns an object URL of the preview PNG; the caller revokes it.
 */
export const previewImageForm = (formData: FormData): Promise<string> =>
  postFormForBlobUrl("/api/v1/image/preview-form", formData);
