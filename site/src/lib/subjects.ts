/** Display and URL forms of the Legislature's subject index headings. */
// headings print a subheading after an em dash ("Motor vehicle — Accident"), "--"
// before 2015; " _ " is the old key spelling a deploy may hold until the next nightly
export const subjectDisplay = (subject: string): string =>
  subject.replace(/ (?:_|—|--) /g, ": ");

export const subjectSlug = (subject: string): string =>
  subject.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
