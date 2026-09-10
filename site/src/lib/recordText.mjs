import { parseFragment } from "parse5";

const BLOCKS = new Set(["address", "blockquote", "br", "div", "dl", "dt", "dd", "h1", "h2", "h3",
  "h4", "h5", "h6", "hr", "li", "ol", "p", "pre", "table", "tr", "ul"]);
const HIDDEN = new Set(["script", "style", "template"]);

/** Read source HTML as text at build time; the archived record stays verbatim. */
export const recordText = (value) => {
  if (!value) return "";
  const text = (node) => {
    if (node.nodeName === "#text") return node.value;
    if (HIDDEN.has(node.tagName)) return "";
    const content = (node.childNodes ?? []).map(text).join("");
    if (BLOCKS.has(node.tagName)) return `\n${content}\n`;
    return node.tagName === "td" || node.tagName === "th" ? `${content} ` : content;
  };
  return text(parseFragment(value)).replace(/[^\S\n]+/g, " ")
    .replace(/ *\n */g, "\n").replace(/\n+/g, "\n").trim();
};
