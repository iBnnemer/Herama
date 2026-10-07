export type IconName =
  | "sidebar" | "tasks" | "plan" | "browser" | "terminal" | "files"
  | "gear" | "send" | "chevron" | "close"
  | "search" | "pin" | "plus" | "trash" | "bolt" | "message" | "box" | "clock" | "clip" | "stop" | "bulb" | "shield" | "gauge" | "sun" | "moon" | "back" | "forward" | "reload" | "home" | "copy" | "reply" | "edit" | "smile" | "check";

const PATHS: Record<IconName, JSX.Element> = {
  sidebar: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></>,
  tasks: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  plan: <><path d="M9 6h11M9 12h11M9 18h11" /><path d="M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2" /></>,
  browser: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18" /></>,
  terminal: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 10l3 2-3 2M12 15h5" /></>,
  files: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
  gear: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></>,
  send: <path d="M12 19V5M5 12l7-7 7 7" />,
  chevron: <path d="M6 9l6 6 6-6" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></>,
  pin: <><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3z" /><path d="M12 14v7" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  trash: <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />,
  bolt: <path d="M13 3L5 14h6l-1 7 8-11h-6z" />,
  message: <path d="M4 5h16v11H9l-5 4z" />,
  box: <><path d="M3 8l9-5 9 5v8l-9 5-9-5z" /><path d="M3 8l9 5 9-5M12 13v8" /></>,
  clip: <path d="M21 11l-9 9a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8" />,
  stop: <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  bulb: <><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z" /></>,
  gauge: <><path d="M4 17a8 8 0 1 1 16 0" /><path d="M12 17l4-5" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5" /></>,
  moon: <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" />,
  back: <path d="M19 12H5M11 6l-6 6 6 6" />,
  forward: <path d="M5 12h14M13 6l6 6-6 6" />,
  reload: <path d="M20 12a8 8 0 1 1-2.5-5.800M20 4v5h-5" />,
  home: <path d="M4 11l8-7 8 7M6 10v10h4v-6h4v6h4V10" />,
  copy: <><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h8" /></>,
  reply: <path d="M10 8L4 13l6 5v-3.5c5 0 8 1.5 10 5-.5-5.500-4-9-10-9.500z" />,
  edit: <path d="M4 20h4L19 9l-4-4L4 16zM13.500 6.500l4 4" />,
  smile: <><circle cx="12" cy="12" r="9" /><path d="M8.500 14.500a4.500 4.500 0 0 0 7 0M9 9.500h.01M15 9.500h.01" /></>,
  check: <path d="M5 12.500l4.500 4.500L19 7.500" />,
  shield: <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />,
};

export default function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" style={{ display: "block" }}>
      {PATHS[name]}
    </svg>
  );
}
