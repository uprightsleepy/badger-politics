/** Display and URL forms of the Legislature's subject index headings. */
// index headings print a subheading after an em dash ("Motor vehicle — Accident"),
// "--" before 2015; older archives spelled it " _ " in lowercase keys
export const subjectDisplay = (subject: string): string =>
  subject
    .split(/ (?:_|—|--) /)
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(": ");

export const subjectSlug = (subject: string): string =>
  subject.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
