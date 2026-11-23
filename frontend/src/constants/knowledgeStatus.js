// Workflow status of knowledge documents, info cards, and quizzes, shown as a chip. One
// definition: four views each kept their own copy in material palette names.
const KNOWLEDGE_STATUS_COLORS = {
  uploaded: "info",
  chunked: "warning",
  draft: "info",
  approved: "success",
  archived: "secondary",
};

export function knowledgeStatusColor(status) {
  return KNOWLEDGE_STATUS_COLORS[status] ?? "default";
}
