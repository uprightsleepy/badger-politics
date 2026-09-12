import assert from "node:assert/strict";
import { test } from "node:test";
import { recordText } from "../../src/lib/recordText.mjs";

test("source HTML becomes readable text without losing words, amounts or comparisons", () => {
  assert.equal(recordText('<div>Approve <b>revised</b> terms &amp; costs.</div><p>$2,612,000;&nbsp;3 &lt; 5.</p>'),
    'Approve revised terms & costs.\n$2,612,000; 3 < 5.');
  assert.equal(recordText('Ordinance 12-26&nbsp;<br>Raise $25,000 to $50,000.'),
    'Ordinance 12-26\nRaise $25,000 to $50,000.');
  assert.equal(recordText('A re<strong>zone</strong> request'), 'A rezone request');
  assert.equal(recordText('Amount < $50,000 and > $25,000'), 'Amount < $50,000 and > $25,000');
  assert.equal(recordText('<div>First item</div><div>Second item'), 'First item\nSecond item');
  assert.equal(recordText(''), '');
  assert.equal(recordText(null), '');
});

test("source markup is never emitted as executable HTML", () => {
  assert.equal(recordText('<script>alert(1)</script><style>body{display:none}</style>' +
    '<template>hidden</template><img src=x onerror=alert(1)>Visible<!-- comment -->'), 'Visible');
  assert.equal(recordText('&lt;script&gt;literal text&lt;/script&gt;'), '<script>literal text</script>');
});

test("glossaries omit self-evident Yes/No entries but retain useful explanations", async () => {
  const { glossaryFor } = await import('../../src/lib/localGloss.ts');
  assert.deepEqual(glossaryFor([], ['Yes', 'No']), []);
  assert.deepEqual(glossaryFor(['REFERRED', 'referred', 'unreviewed action'], ['Aye', 'Nay', 'Abstain']), [
    { term: 'Referred', meaning: 'sent to a committee for review before the council decides' },
    { term: 'Aye', meaning: 'voted yes' },
    { term: 'Nay', meaning: 'voted no' },
    { term: 'Abstain', meaning: 'chose not to vote' },
  ]);
});
