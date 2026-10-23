---
paths: ["**/backend/**/*.py", "**/frontend/src/**"]
---

# Code comments

- A comment explains intent and rationale (why this approach, which trade-off), never what
  standard code plainly does. Prefer a clear name over an explanatory comment.
- No milestone numbers (`M05`), decision-log or ticket ids (`D6`, `#1234`), deadlines, or
  status in comments: code outlives them. A link to a permanent design document is fine.
- When the code changes, change its comment. Public APIs, classes, and complex functions carry
  a docstring that states the contract.
