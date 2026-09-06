Use $prompt-authoring to draft or repair a prompt for a selected receiver.

Goal: produce a compact, outcome-first prompt. The authoring profile is gpt-6-astra; select the receiver's runtime/profile/kind independently. Keep only task-critical context and reference reusable workflow.

Must not forget: apply the skill's behavior-example gate only when triggered. Follow its native/portable/Goal Mode routing. For a portable result run `orch-prompts prompt-check --runtime <receiver-runtime> --profile <receiver-profile> --kind <kind>` or state `prompt-check not run`. The generated Goal objective needs no prompt-check.

Output: ready-to-use prompt, receiver runtime/profile/kind, char count, and applicable check result or limitation.

Stop: ask only when missing receiver, write zone, or success criteria would misdirect the result.
