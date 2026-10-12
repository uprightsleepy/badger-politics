# Report to the Wisconsin Elections Commission: 2026 Spring Election ward-by-ward workbook

Draft for the owner to send from their own address to elections@wi.gov.
Internal note, not part of the letter: the site publishes no 2026 spring
results. The pipeline refuses the workbook because the figures below disagree
with each other (`pipeline/scraper/fetch_wec_results.py`), so this is a
defect inside the Commission's file, not a difference between the site and
the file. Re-verified 2026-10-11 by reading the file directly.

---

Subject: Office Totals do not match County Totals in the 2026 Spring Election ward-by-ward report

Hello,

I run Badger Politics (badgerpolitics.org), a free, non-partisan site that
republishes the Commission's certified election results. While loading the
2026 Spring Election ward-by-ward report, I found two contests whose "Office
Totals:" row does not equal the sum of the file's own "County Totals:" rows.
I am writing to ask which figures are the certified ones and whether the file
will be corrected.

File: Ward by Ward Report_Spring Election 2026_All State Contests.xlsx
URL: https://elections.wi.gov/sites/default/files/documents/Ward%20by%20Ward%20Report_Spring%20Election%202026_All%20State%20Contests.xlsx
Downloaded: October 11, 2026

1. Justice of the Supreme Court (sheet "Sheet2", 72 counties)

| Column           | Sum of 72 County Totals rows | Office Totals row | Difference |
|------------------|-----------------------------:|------------------:|-----------:|
| Total Votes Cast | 1,506,862                    | 1,506,842         | 20         |
| Chris Taylor     | 905,510                      | 905,490           | 20         |
| Maria S. Lazar   | 600,256                      | 600,256           | 0          |
| Scattering       | 1,096                        | 1,096             | 0          |

2. Court of Appeals Judge, District 4 (sheet "Sheet5", 24 counties)

| Column           | Sum of 24 County Totals rows | Office Totals row | Difference |
|------------------|-----------------------------:|------------------:|-----------:|
| Total Votes Cast | 347,450                      | 347,431           | 19         |
| Rachel A. Graham | 344,406                      | 344,387           | 19         |
| Scattering       | 3,044                        | 3,044             | 0          |

In both contests every County Totals row equals the sum of its own ward rows,
so the ward and county figures agree with each other; only the Office Totals
row differs. The Court of Appeals District 1 and District 2 contests in the
same file reconcile exactly.

Could you tell me:

- Which figures are the certified statewide totals for these two contests,
  the Office Totals row or the sum of the County Totals?
- Whether a corrected workbook will be posted, and if so where?

I am happy to share the spreadsheet rows behind these sums if that helps.
Thank you for publishing the ward-level files; they are the basis for
everything the site shows about election results.

Regards,

[name]
Badger Politics, badgerpolitics.org
