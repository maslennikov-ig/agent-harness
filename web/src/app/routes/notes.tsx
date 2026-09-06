import { createFileRoute } from "@tanstack/react-router";
import { NotesScreen } from "@/features/notes/notes-screen";

export const Route = createFileRoute("/notes")({ component: NotesScreen });
