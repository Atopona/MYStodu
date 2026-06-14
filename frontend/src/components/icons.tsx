import React from "react";

const I = ({ d, size = 12, vb = 24 }: { d: string; size?: number; vb?: number }) => (
  <svg
    width={size}
    height={size}
    viewBox={`0 0 ${vb} ${vb}`}
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    className="inline-block shrink-0"
  >
    <path d={d} />
  </svg>
);

export const IconBolt = ({ size = 12 }: { size?: number }) => (
  <I size={size} d="M13 2 L5 13 H11 L9 22 L19 9 H12 Z" />
);
export const IconPlay = ({ size = 12 }: { size?: number }) => (
  <I size={size} d="M6 4 L20 12 L6 20 Z" />
);
export const IconLock = ({ size = 12 }: { size?: number }) => (
  <I size={size} d="M7 11 V8 a5 5 0 0 1 10 0 v3 M5 11 h14 v10 H5 Z" />
);
export const IconUnlock = ({ size = 12 }: { size?: number }) => (
  <I size={size} d="M7 11 V8 a5 5 0 0 1 9.6 -1.6 M5 11 h14 v10 H5 Z" />
);
export const IconDice = ({ size = 12 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="inline-block shrink-0">
    <rect x="3" y="3" width="18" height="18" rx="3" />
    <circle cx="8.5" cy="8.5" r="1.4" fill="currentColor" stroke="none" />
    <circle cx="15.5" cy="15.5" r="1.4" fill="currentColor" stroke="none" />
    <circle cx="15.5" cy="8.5" r="1.4" fill="currentColor" stroke="none" />
    <circle cx="8.5" cy="15.5" r="1.4" fill="currentColor" stroke="none" />
  </svg>
);
export const IconCamera = ({ size = 22 }: { size?: number }) => (
  <I size={size} d="M4 7 h3 l2 -2 h6 l2 2 h3 v12 H4 Z M12 16 a3.5 3.5 0 1 0 0 -7 a3.5 3.5 0 0 0 0 7 Z" />
);
export const IconFilm = ({ size = 22 }: { size?: number }) => (
  <I size={size} d="M4 4 h16 v16 H4 Z M4 9 h16 M4 15 h16 M9 4 v16 M15 4 v16" />
);
export const IconSpark = ({ size = 22 }: { size?: number }) => (
  <I size={size} d="M12 2 L13.8 9 L21 12 L13.8 15 L12 22 L10.2 15 L3 12 L10.2 9 Z" />
);
export const IconX = ({ size = 12 }: { size?: number }) => (
  <I size={size} d="M5 5 L19 19 M19 5 L5 19" />
);
export const IconGear = ({ size = 13 }: { size?: number }) => (
  <I
    size={size}
    d="M12 15.5 a3.5 3.5 0 1 0 0-7 a3.5 3.5 0 0 0 0 7 Z M19.4 13.5 l1.8 1 -1.8 3.2 -2 -.6 a7 7 0 0 1 -1.7 1 l-.4 2.1 h-3.6 l-.4 -2.1 a7 7 0 0 1 -1.7 -1 l-2 .6 -1.8 -3.2 1.8 -1 a7 7 0 0 1 0 -2 l-1.8 -1 1.8 -3.2 2 .6 a7 7 0 0 1 1.7 -1 l.4 -2.1 h3.6 l.4 2.1 a7 7 0 0 1 1.7 1 l2 -.6 1.8 3.2 -1.8 1 a7 7 0 0 1 0 2 Z"
  />
);
export const IconHistory = ({ size = 12 }: { size?: number }) => (
  <I size={size} d="M3 12 a9 9 0 1 0 3-6.7 M3 4 v5 h5 M12 7 v5 l4 2" />
);
export const IconExternal = ({ size = 11 }: { size?: number }) => (
  <I size={size} d="M14 4 h6 v6 M20 4 L11 13 M9 6 H5 v13 h13 v-4" />
);
export const IconUpload = ({ size = 18 }: { size?: number }) => (
  <I size={size} d="M12 16 V4 M7 9 l5 -5 5 5 M4 20 h16" />
);
export const IconDownload = ({ size = 12 }: { size?: number }) => (
  <I size={size} d="M12 4 v12 M7 11 l5 5 5 -5 M4 20 h16" />
);
export const IconTrash = ({ size = 12 }: { size?: number }) => (
  <I size={size} d="M4 7 h16 M9 7 V4 h6 v3 M6 7 l1 13 h10 l1 -13 M10 11 v6 M14 11 v6" />
);
export const IconReuse = ({ size = 12 }: { size?: number }) => (
  <I size={size} d="M4 12 a8 8 0 0 1 14 -5 M18 3 v4 h-4 M20 12 a8 8 0 0 1 -14 5 M6 21 v-4 h4" />
);
export const IconStop = ({ size = 12 }: { size?: number }) => (
  <I size={size} d="M6 6 h12 v12 H6 Z" />
);
export const IconChat = ({ size = 11 }: { size?: number }) => (
  <I size={size} d="M4 5 h16 v11 H9 l-5 4 Z" />
);
export const IconEye = ({ size = 11 }: { size?: number }) => (
  <I size={size} d="M2 12 C5 6 9 4 12 4 s7 2 10 8 c-3 6 -7 8 -10 8 s-7 -2 -10 -8 Z M12 15 a3 3 0 1 0 0 -6 a3 3 0 0 0 0 6 Z" />
);
export const IconWalk = ({ size = 11 }: { size?: number }) => (
  <I size={size} d="M13 5 a1.5 1.5 0 1 0 0 -3 a1.5 1.5 0 0 0 0 3 Z M9 22 l2.5 -6 L9 13 l1 -5 4 -1 3 3 3 1 M11 8 l-3 2 -1 4 M14 16 l3 6" />
);

export function Logo() {
  return (
    <span className="inline-flex items-center justify-center w-6 h-6 rounded-sm bg-gradient-to-br from-acid to-neon">
      <svg width="14" height="14" viewBox="0 0 24 24" stroke="#0a0f0a" strokeWidth="3.4" strokeLinecap="round">
        <path d="M7 19 L12 5 M13 19 L18 5" fill="none" />
      </svg>
    </span>
  );
}
