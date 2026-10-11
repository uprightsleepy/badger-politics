/** Hand-inked spot illustrations for the home page topic cards. Each is the inside of a
 * 160x100 SVG: `p` fills are paper, `a` fills take the card's accent, and every stroke is ink.
 * The wobble and the paper grain come from the shared filters in TopicArtDefs. */
export const TOPIC_ART: Record<string, string> = {
  schools: `
    <path class="p" d="M44 74h70v12H44z"/><path d="M51 74v12M107 77v6"/>
    <path class="a" d="M50 62h60v12H50z"/><path d="M56 62v12M104 65v6"/>
    <path class="p" d="M42 50h64v12H42z"/><path d="M48 50v12M100 53v6"/>
    <path class="a" d="M78 49c-11 1-16-7-14-14 2-6 9-8 14-4 5-4 12-2 14 4 2 7-3 15-14 14z"/>
    <path d="M78 32c0-5 2-8 5-10"/><path class="p" d="M81 27c5-6 11-6 14-3-4 5-10 6-14 3z"/>
    <path d="M118 40l16-16 5 5-16 16-7 2z" class="p"/><path d="M131 27l5 5"/>
    <path d="M30 88h100"/>`,
  taxes: `
    <path class="p" d="M50 46h40v6c7 4 9 10 9 17v13c0 4-3 6-6 6H47c-3 0-6-2-6-6V69c0-7 2-13 9-17z"/>
    <path d="M47 46h46"/><path d="M50 52h40"/>
    <ellipse class="a" cx="58" cy="82" rx="8" ry="3"/><ellipse class="a" cx="78" cy="82" rx="8" ry="3"/>
    <ellipse class="a" cx="68" cy="77" rx="8" ry="3"/><ellipse class="a" cx="82" cy="72" rx="8" ry="3"/>
    <circle class="a" cx="72" cy="30" r="8"/><path d="M72 26v8"/>
    <path d="M60 22l-4-4M84 22l4-4M72 14v-5"/>
    <path class="p" d="M160 14h-26c-8 0-12 3-14 7H96c-5 0-5 7 0 7h20c1 4 6 8 14 8h30z"/>
    <path class="p" d="M128 14c-2-5-8-8-13-5-2 2 0 5 5 6z"/><path d="M122 31h10M124 35h8M150 12v26"/>`,
  roads: `
    <circle class="p" cx="132" cy="22" r="9"/><path d="M132 7V3M145 14l3-3M147 24h4"/>
    <rect class="a" x="30" y="38" width="94" height="38" rx="9"/>
    <rect class="p" x="38" y="45" width="15" height="14" rx="2"/><rect class="p" x="57" y="45" width="15" height="14" rx="2"/>
    <rect class="p" x="76" y="45" width="15" height="14" rx="2"/><rect class="p" x="98" y="45" width="18" height="22" rx="2"/>
    <path d="M30 66h64"/><circle class="p" cx="120" cy="69" r="2"/>
    <circle class="p" cx="52" cy="77" r="8"/><circle cx="52" cy="77" r="2"/>
    <circle class="p" cx="104" cy="77" r="8"/><circle cx="104" cy="77" r="2"/>
    <path d="M10 86h140"/><path d="M18 94h12M44 94h12M70 94h12M96 94h12M122 94h12"/>
    <path d="M14 52h10M8 60h12"/>`,
  health: `
    <path d="M52 26l-5-5M80 20v-7M108 26l5-5"/>
    <path class="a" d="M80 76C62 64 50 54 53 42c3-11 18-14 27-3 9-11 24-8 27 3 3 12-9 22-27 34z"/>
    <path class="ps" d="M80 45v16M72 53h16"/>
    <g id="hand-l"><path class="p" d="M10 92V76c12-2 26-7 42-7 11 0 19 4 19 9 0 4-6 5-13 3l-7-1c-5 6-12 10-20 12z"/>
      <path d="M48 75h13M24 74v18"/></g>
    <use href="#hand-l" transform="matrix(-1 0 0 1 160 0)"/>`,
  datacenters: `
    <rect class="p" x="58" y="16" width="50" height="70" rx="4"/>
    <rect class="a" x="64" y="23" width="38" height="13" rx="2"/><rect class="a" x="64" y="41" width="38" height="13" rx="2"/>
    <rect class="a" x="64" y="59" width="38" height="13" rx="2"/>
    <circle class="p" cx="70" cy="29.5" r="2"/><circle class="p" cx="70" cy="47.5" r="2"/><circle class="p" cx="70" cy="65.5" r="2"/>
    <path class="ps" d="M78 29.5h18M78 47.5h18M78 65.5h18"/>
    <path d="M58 90h50M108 80c16 0 16 12 30 10 8-1 10-6 10-12"/>
    <rect class="p" x="142" y="66" width="12" height="11" rx="2"/><path d="M145 66v-6M151 66v-6"/>
    <path class="p" d="M38 22l-12 22h10l-6 20 18-26H38l6-16z"/>
    <path class="a" d="M24 78c0-6 6-12 6-12s6 6 6 12c0 4-3 6-6 6s-6-2-6-6z"/>`,
  housing: `
    <path class="p" d="M36 52l34-26 34 26v36H36z"/><path d="M30 56l40-32 40 32"/>
    <path class="p" d="M86 38V26h9v19"/>
    <path class="a" d="M60 66h18v22H60z"/><circle cx="73" cy="78" r="1.5"/>
    <rect class="p" x="84" y="58" width="13" height="13"/><path d="M90.5 58v13M84 64.5h13"/>
    <rect class="p" x="44" y="58" width="11" height="11"/><path d="M49.5 58v11M44 63.5h11"/>
    <path d="M24 88h96"/>
    <path d="M136 14v12"/><circle class="a" cx="136" cy="36" r="10"/><circle class="p" cx="136" cy="36" r="3"/>
    <path d="M136 46v34M136 66h7M136 73h9"/>`,
  water: `
    <circle class="p" cx="124" cy="24" r="10"/><path d="M124 8V4M138 12l3-3M140 24h5M110 12l-3-3"/>
    <path class="a" d="M0 66c16-20 38-22 58-6 16-16 40-20 60-6 14-8 30-6 42 2v14H0z"/>
    <path d="M30 52V40"/><circle class="p" cx="30" cy="36" r="7"/>
    <path d="M44 48v-8"/><circle class="p" cx="44" cy="36" r="5"/>
    <path class="p" d="M0 70h160v30H0z"/>
    <path d="M12 82q6-4 12 0t12 0M104 88q6-4 12 0t12 0M120 78q6-4 12 0t12 0"/>
    <path class="a" d="M66 72c6-12 20-14 28-6-6 8-18 11-28 6z"/><path class="a" d="M66 72l-9-6 2 12z"/>
    <circle cx="86" cy="67" r="1.4"/><path d="M60 84l-4 4M98 82l4 4M80 86v5"/>`,
  jobs: `
    <circle class="a" cx="30" cy="40" r="10"/><path d="M30 35v10"/>
    <path class="p" d="M14 62l26-6 4 18-26 6z"/><path d="M22 66l12-3M24 72l12-3"/>
    <path class="a" d="M52 72c0-20 12-32 28-32s28 12 28 32z"/>
    <path class="p" d="M44 72h72c3 0 3 7 0 7H44c-3 0-3-7 0-7z"/>
    <path d="M80 40v18M70 43c-3 6-4 14-4 26M90 43c3 6 4 14 4 26"/>
    <g transform="translate(-8 4) rotate(35 134 60)">
      <rect class="p" x="129" y="44" width="10" height="42" rx="5"/>
      <path class="p" d="M127.4 26A12 12 0 1 0 140.6 26L137 33h-6z"/>
    </g>
    <path d="M30 88h110"/>`,
};

/** Rendered once per page: the ink wobble and the paper grain the illustrations share. */
export const TOPIC_ART_DEFS = `
  <filter id="ink-wobble"><feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="3"/>
    <feDisplacementMap in="SourceGraphic" scale="2.2"/></filter>
  <filter id="paper-grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/>
    <feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.09 0"/></filter>`;
