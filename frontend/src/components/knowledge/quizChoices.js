// Multiple-choice answers are referred to by choice id (the tablet sends it, the voice
// agent passes it to submit_quiz_answer), so every choice needs a non-empty id that is
// unique within its question. The editor used to add choices with id null, which the
// server rejected (422) and no answer could ever refer to.

const LETTERS = "abcdefghijklmnopqrstuvwxyz";

function usedIds(choices) {
  return new Set(
    (choices || [])
      .map((c) => (typeof c?.id === "string" ? c.id.trim().toLowerCase() : ""))
      .filter(Boolean),
  );
}

/** The first free id: "a".."z", then "c27", "c28", ... */
export function nextChoiceId(choices = []) {
  const used = usedIds(choices);
  for (const letter of LETTERS) if (!used.has(letter)) return letter;
  let n = LETTERS.length + 1;
  while (used.has(`c${n}`)) n += 1;
  return `c${n}`;
}

/** Choices ready to save: trimmed, each with a unique non-empty id. */
export function normalizeChoices(choices = []) {
  const out = [];
  for (const c of choices || []) {
    const raw = typeof c?.id === "string" ? c.id.trim() : "";
    const id = raw && !usedIds(out).has(raw.toLowerCase()) ? raw : nextChoiceId(out);
    out.push({ id, text: String(c?.text ?? "").trim(), is_correct: Boolean(c?.is_correct) });
  }
  return out;
}

/** The fields the API accepts for a question, with choices normalized. */
export function questionPayload(question) {
  const isChoice = question.question_type === "multiple_choice";
  return {
    question_type: question.question_type || "multiple_choice",
    question_text: question.question_text || "",
    choices: isChoice ? normalizeChoices(question.choices) : [],
    expected_answer: isChoice ? "" : question.expected_answer || "",
    explanation: question.explanation || "",
  };
}
