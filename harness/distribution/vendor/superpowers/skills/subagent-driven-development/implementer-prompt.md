# Implementer prompt

Use this compact native same-session contract; fill only task-specific facts.

```text
Goal: <one finished outcome and the relevant task/source reference>
Write zone: <owned files or module; preserve other owners' changes>
Verification: <none during work; root final acceptance, or the explicitly assigned target>
Stop: <unresolved ownership or a real scope/authority boundary>
```

Final acceptance is root-owned unless this task is the assigned final verification stream.
A focused diagnostic may unblock an edit. Worker completion does not itself
schedule another test run or reviewer. Inspect your own diff as useful and
return the changed files, result, evidence actually obtained, and material gaps.
Do not fabricate proof to fill a report field.

Include enough requirements and source pointers to implement the outcome.
Keep routine reversible decisions local; ask the parent when missing intent
or ownership would change the result. Do not copy the transcript or shared
policy. Native prompts do not require prompt-authoring or prompt-check.
