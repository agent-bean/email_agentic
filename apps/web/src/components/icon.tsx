const paths = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  research: "M12 5v14 M5 12h14",
  inbox: "M3 5h18v14H3z M3 6l9 7 9-7",
  sent: "M4 12a8 8 0 1 1 2 5 M4 17v-5h5 M9 11l3 3 5-5",
  company:
    "M5 21V3h14v18 M2 21h20 M9 7h1 M14 7h1 M9 11h1 M14 11h1 M10 21v-5h4v5",
  knowledge:
    "M12 5c-3-2-6-2-10-1v15c4-1 7-1 10 1 3-2 6-2 10-1V4c-4-1-7-1-10 1z M12 5v15",
  system:
    "M5 3v7 M5 14v7 M12 3v11 M12 18v3 M19 3v3 M19 10v11 M2 10h6 M9 14h6 M16 6h6",
  arrow: "M4 12h16 M14 6l6 6-6 6",
  shield: "M12 2l8 4v6c0 5-8 10-8 10S4 17 4 12V6z M8 12l3 3 5-6",
} as const;

export function Icon({ name }: { name: keyof typeof paths }) {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
