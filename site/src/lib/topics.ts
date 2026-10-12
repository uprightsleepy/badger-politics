/** The homepage's topic doors. Each gathers a family of the Legislature's own
 * subject headings (display form, "School: Charter school"), so a topic page
 * is our grouping of their index, never a category of our own. A string
 * takes that heading and its subheadings; a RegExp takes exactly what it
 * matches. */
import { subjectDisplay } from "./subjects.ts";

export type Topic = {
  slug: string;
  label: string;
  examples: string;
  headings: (string | RegExp)[];
  // icon color, pale card wash of the same hue, and the gradient behind the icon
  ink: string;
  tint: string;
  panel: [string, string];
};

export const TOPICS: Topic[] = [
  { slug: "schools", label: "Schools", examples: "School funding, vouchers, testing, teachers",
    headings: ["School", "Milwaukee: School", "Teacher", "Public Instruction, Department of",
      "State Superintendent of Public Instruction", "Parochial and private schools",
      "Parochial and private educational institutions", "Technical college", "Technical College System Board",
      "University of Wisconsin", "Higher Educational Aids Board", "Educational Approval Board",
      "Educational Service Agency, Cooperative", "Children: Special education", "Children: Special educational needs"],
    ink: "#0d5c63", tint: "#e6efef", panel: ["#a3d3cf", "#6cafab"] },
  { slug: "taxes", label: "Taxes", examples: "Property, income and sales taxes",
    headings: [/\btax(?:ation|es)?\b/i],
    ink: "#8a6410", tint: "#f9f1df", panel: ["#f3d98f", "#d6b14f"] },
  { slug: "roads-transit", label: "Roads & Transit", examples: "Highways, road repair, buses, the gas tax",
    headings: ["Transportation, Department of", "Transportation Projects Commission", "Transportation and delivery networks",
      "Road", "County: Highway department", "Bridge", "Motor vehicle", "Bus and truck", "Metropolitan transportation",
      "Railroad", "Gasoline"],
    ink: "#3d5a35", tint: "#ecefe5", panel: ["#c3d4a4", "#90ab70"] },
  { slug: "health-care", label: "Health Care", examples: "Medicaid, prescriptions, hospitals, insurance",
    headings: ["Insurance: Health", "Health Insurance Risk-Sharing Plan", "Health Services, Department of",
      "Medical assistance", "Medical service", "Medical practice, Group", "Medical malpractice", "Medical Examining Board",
      /^Drugs$/, "Pharmacy", "Mental health", "Public health", "Hospitals", "Hospitals and health care facilities",
      "Nursing homes and adult care", "Nurses", "Alcohol and other drug abuse"],
    ink: "#4b3f72", tint: "#f3eff9", panel: ["#dccdf0", "#b39cd6"] },
  { slug: "data-centers", label: "Tech & Data Centers", examples: "Big tech campuses, their power and water use, tax breaks",
    headings: [/^Data processing$/, "Electric utility", "Electricity", "Public utility", "Energy conservation"],
    ink: "#2c4a68", tint: "#eceff4", panel: ["#c4d1e4", "#92a6c5"] },
  { slug: "housing", label: "Housing", examples: "Rent, home building, zoning, landlords and tenants",
    headings: ["Housing", "Housing and Economic Development Authority, Wisconsin", "Landlord and tenant",
      "Discrimination in housing", "Mortgage", "Mobile home", "Homestead credit", "Homestead: Exemption",
      "Veteran: Housing", "Building"],
    ink: "#7a4a26", tint: "#f6eae2", panel: ["#ebbd9f", "#cf946f"] },
  { slug: "water-land", label: "Water and Land", examples: "PFAS, lakes, farms, state parks",
    headings: ["Natural Resources, Department of", "Natural Resources Board", "Natural resource", "Environmental protection",
      "Water supply", "Water: Pollution", "Waterways and water power", "Waterworks", "Wells", "Lakes", "Wetland",
      "Shoreland zoning", "Flood plain zoning", "Land", "Land use planning and control", "Land and Water Conservation Board",
      "Forestry", "State park", "Park", "Agriculture", "Agriculture, Trade and Consumer Protection, Department of",
      "Farm and farming", "Farmer", "Farm produce", "Farmland preservation"],
    ink: "#245b46", tint: "#ebf5f3", panel: ["#c4e6dc", "#8bc8b7"] },
  { slug: "jobs-wages", label: "Jobs and Wages", examples: "Minimum wage, unemployment, workers' rights",
    headings: ["Employment", "Employment bureau", "Employment Relations Commission", "Discrimination in employment",
      "Unemployment", "Unemployment insurance", "Worker's compensation", "Wage", "Hours of labor", "Labor", "Labor union",
      "Child labor", "Agricultural labor", "Labor and Industry Review Commission", "Workforce Development, Department of",
      "Apprenticeship"],
    ink: "#5a5136", tint: "#f3ede3", panel: ["#dcc7a3", "#b89e70"] },
];

/** Whether a heading, as the index prints it, belongs to the topic. */
export const inTopic = (topic: Topic, heading: string): boolean => {
  const shown = subjectDisplay(heading);
  return topic.headings.some((h) =>
    h instanceof RegExp ? h.test(shown) : shown === h || shown.startsWith(`${h}: `));
};
