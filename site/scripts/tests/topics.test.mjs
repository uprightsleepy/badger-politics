import assert from "node:assert/strict";
import { test } from "node:test";
import { TOPICS, inTopic } from "../../src/lib/topics.ts";

const topic = (slug) => TOPICS.find((t) => t.slug === slug);

test("every topic has its own unique page slug", () => {
  assert.equal(TOPICS.length, 8);
  assert.equal(new Set(TOPICS.map((t) => t.slug)).size, 8);
});

test("a heading family takes its subheadings in every separator spelling; a regex takes only what it matches", () => {
  assert.ok(inTopic(topic("schools"), "School"));
  assert.ok(inTopic(topic("schools"), "School — Charter school"));
  assert.ok(inTopic(topic("schools"), "School -- Board"));
  assert.ok(inTopic(topic("schools"), "Milwaukee — School"));
  assert.ok(!inTopic(topic("schools"), "Milwaukee"));
  assert.ok(!inTopic(topic("schools"), "Schoolcraft, John"));
  assert.ok(inTopic(topic("data-centers"), "Data processing"));
  assert.ok(!inTopic(topic("data-centers"), "Data processing — Privacy issues"));
  assert.ok(inTopic(topic("taxes"), "Forestry — Taxation"));
  assert.ok(inTopic(topic("health-care"), "Drugs"));
  assert.ok(!inTopic(topic("health-care"), "Drugs — Criminal acts and law enforcement"));
  assert.ok(!inTopic(topic("taxes"), "Taxidermy"));
});
