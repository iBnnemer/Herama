import type { Conversation, Project } from "../../types";
import PageShell, { card, ghostBtn, primaryBtn, Empty } from "./PageShell";

interface Props {
  projects: Project[];
  conversations: Conversation[];
  activeProjectId: string;
  onAdd: () => void;
  onOpen: (p: Project) => void;
  onNewSession: (projectId: string) => void;
  onRemove: (id: string) => void;
}

export default function ProjectsPage(p: Props) {
  return (
    <PageShell title="Projects" hint="A project is a folder. Opening one points the file browser and terminal at it and groups its sessions."
      action={<button style={primaryBtn} onClick={p.onAdd}>Add project folder</button>}>
      {p.projects.length === 0 && <Empty text="No projects yet. Add a folder to get started." />}
      {p.projects.map(pr => {
        const n = p.conversations.filter(c => c.projectId === pr.id).length;
        return (
          <div key={pr.id} style={{ ...card, display: "flex", alignItems: "center", gap: 12, borderColor: pr.id === p.activeProjectId ? "var(--accent)" : "var(--border)" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{pr.name}</div>
              <div style={{ fontSize: 11, color: "var(--text-dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{pr.dir}</div>
              <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>{n} session{n === 1 ? "" : "s"}</div>
            </div>
            <button style={ghostBtn} onClick={() => p.onOpen(pr)}>Open</button>
            <button style={ghostBtn} onClick={() => p.onNewSession(pr.id)}>New session</button>
            <button style={{ ...ghostBtn, color: "var(--red)" }} onClick={() => p.onRemove(pr.id)}>Remove</button>
          </div>
        );
      })}
    </PageShell>
  );
}
