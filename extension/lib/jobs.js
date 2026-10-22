// Grouping a tab's download jobs for the popup.

// The newest job for each key, in the order the keys first appear.
export function latestByKey(jobs) {
  const latest = new Map();
  for (const job of jobs) latest.set(job.key, job);
  return latest;
}

// The newest job for each key that no option row shows, such as a job for
// another URL on this tab, or any job while the page is still being probed.
export function unmatchedJobs(jobs, rowKeys) {
  const shown = new Set(rowKeys);
  return [...latestByKey(jobs).values()].filter((job) => !shown.has(job.key));
}
