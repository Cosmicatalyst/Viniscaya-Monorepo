"use client";

import { useState } from "react";
import { LogOut, Menu, X, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { ReportChatContext } from "@/components/report-chat-context";
import { logout } from "@/app/actions";
import { CoDoc } from "@/components/co-doc";
import { Home } from "@/components/home";
import { SpecialtyWorkspace } from "@/components/specialty-workspace";
import { SavedWorkspace } from "@/components/saved-workspace";
import type { ChatMessage } from "@/lib/medical-api";

const specialties = ["Cancer", "Proteins", "Radiology", "Neurology", "Cardiac", "General"];
const groups = [["Home"], specialties, ["Threads", "Library"], ["Co-Doc"]];

export function Dashboard() {
  const [active, setActive] = useState("Home");
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [thread, setThread] = useState<{id: string; messages: ChatMessage[]; report_ids?: string[]}>();
  return (
    <ReportChatContext.Provider value={(jobId,seed) => {setThread({id: crypto.randomUUID().replaceAll("-", ""), messages: seed ? [{role:"user",content:`Brain-response research report for discussion (predictions, not patient measurements):\n${seed}`}]:[], report_ids: seed ? [] : [jobId]});setActive("Co-Doc");}}><main className={`dashboard-shell ${collapsed ? "sidebar-collapsed" : ""} ${active === "Co-Doc" ? "chat-active" : ""}`}>
      <button className="mobile-menu" onClick={() => setMenuOpen(!menuOpen)} aria-label={menuOpen ? "Close navigation" : "Open navigation"} aria-expanded={menuOpen}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
      <aside id="main-sidebar" className={`app-sidebar ${menuOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-top"><a href="/dashboard" className="sidebar-brand">viniścaya</a><button className="sidebar-toggle" onClick={() => setCollapsed(true)} aria-label="Collapse sidebar" aria-expanded={!collapsed} aria-controls="main-sidebar"><PanelLeftClose size={18}/></button></div>
        <nav aria-label="Main navigation">
          {groups.map((group, index) => <div className="sidebar-group" key={index}>
            {group.map(item => <button key={item} className={`sidebar-link ${active === item ? "is-active" : ""}`} aria-current={active === item ? "page" : undefined} onClick={() => { setActive(item); setMenuOpen(false); }}>{item}<span className="active-dot" /></button>)}
          </div>)}
        </nav>
        <form action={logout} className="sidebar-logout"><button type="submit"><LogOut size={16} />Sign out</button></form>
      </aside>
      <section className="dashboard-content">
        <header className="dashboard-header"><div className="dashboard-heading">{collapsed && <button className="sidebar-toggle sidebar-expand" onClick={() => setCollapsed(false)} aria-label="Expand sidebar" aria-expanded={false} aria-controls="main-sidebar"><PanelLeftOpen size={18}/></button>}<span>{active}</span></div><div className="profile-avatar" aria-label="Thishya Abhay">TA</div></header>
        <div className="co-doc-host" hidden={active !== "Co-Doc"}><CoDoc key={thread?.id || "new"} initialThread={thread} /></div>
        {active === "Co-Doc" ? null : active === "Home" ? <Home navigate={setActive} /> : specialties.includes(active) ? <SpecialtyWorkspace key={active} category={active} /> : <SavedWorkspace key={active} kind={active as "Threads" | "Library"} openThread={(id, messages, report_ids) => {setThread({id,messages,report_ids});setActive("Co-Doc");}} />}
      </section>
    </main></ReportChatContext.Provider>
  );
}
