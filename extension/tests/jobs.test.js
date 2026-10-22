import { test } from "node:test";
import assert from "node:assert/strict";
import { latestByKey, unmatchedJobs } from "../lib/jobs.js";

const job = (id, key, status = "done") => ({ id, key, status, label: key });

test("latestByKey keeps the newest job per key, in first-seen order", () => {
  const jobs = [job("1", "a"), job("2", "b"), job("3", "a", "running")];
  const latest = latestByKey(jobs);
  assert.deepEqual([...latest.keys()], ["a", "b"]);
  assert.equal(latest.get("a").id, "3");
  assert.equal(latest.get("b").id, "2");
  assert.equal(latestByKey([]).size, 0);
});

test("unmatchedJobs lists the jobs no option row shows", () => {
  const jobs = [job("1", "page|video", "running"), job("2", "other|audio"), job("3", "other|audio", "running")];
  assert.deepEqual(unmatchedJobs(jobs, []).map((j) => j.id), ["1", "3"]);
  assert.deepEqual(unmatchedJobs(jobs, ["page|video", "page|audio"]).map((j) => j.id), ["3"]);
  assert.deepEqual(unmatchedJobs(jobs, new Set(["page|video", "other|audio"])), []);
});
