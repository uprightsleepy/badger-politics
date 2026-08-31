/** Paging for the long lists. getStaticPaths runs outside a page's own
 * frontmatter scope and cannot see a constant declared there, which is
 * why every paged route used to repeat the literal; an import reaches
 * both scopes. */
export const PER_PAGE = 200;
/** The federal roll-call pages were published at 250 a page; changing
 * the size would move every vote onto a different URL. */
export const FEDERAL_VOTES_PER_PAGE = 250;

export const pageCount = (total: number, perPage = PER_PAGE): number =>
  Math.max(1, Math.ceil(total / perPage));

/** 1-based bounds of the rows a page shows: "Showing 201-400 of 1,234". */
export const pageBounds = (page: number, total: number, perPage = PER_PAGE) => ({
  first: (page - 1) * perPage + 1,
  last: Math.min(page * perPage, total),
});
