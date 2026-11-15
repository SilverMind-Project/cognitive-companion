/**
 * Visitor cluster admin surface.
 *
 * Proxies person-identification-service's visitor clustering API through the CC BFF.
 * Naming a cluster is a two-system transaction (face-service member + CC household member);
 * review (attribute to an existing member, or dismiss) and merge only affect the review queue.
 */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

type Schemas = components["schemas"];

export const listVisitorClusters = (status?: string) =>
  unwrap(
    client.GET("/api/v1/visitors/clusters", {
      params: { query: status ? { status } : {} },
    }),
  );

export const getVisitorCluster = (clusterId: string) =>
  unwrap(
    client.GET("/api/v1/visitors/clusters/{cluster_id}", {
      params: { path: { cluster_id: clusterId } },
    }),
  );

export const nameVisitorCluster = (clusterId: string, body: Schemas["NameVisitorRequest"]) =>
  unwrap(
    client.POST("/api/v1/visitors/clusters/{cluster_id}/name", {
      params: { path: { cluster_id: clusterId } },
      body,
    }),
  );

export type VisitorReviewRequest = Schemas["VisitorReviewRequest"];

/** Attribute clusters to an enrolled member, or dismiss them. Never enrolls anything. */
export const reviewVisitorClusters = (body: VisitorReviewRequest) =>
  unwrap(client.POST("/api/v1/visitors/clusters/review", { body }));

export const mergeVisitorClusters = (clusterA: string, clusterB: string) =>
  unwrap(
    client.POST("/api/v1/visitors/clusters/{cluster_a}/merge/{cluster_b}", {
      params: { path: { cluster_a: clusterA, cluster_b: clusterB } },
    }),
  );
