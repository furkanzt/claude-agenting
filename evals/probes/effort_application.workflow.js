export const meta = {
  name: 'effort-application-test',
  description: 'Does a Workflow agent() apply its effort option? Haiku 5.5 pinned at low/medium/high/xhigh (3 each) plus 3 unpinned, on one reasoning problem; effort and tokens are read from the transcripts afterwards',
  phases: [{ title: 'Probe', detail: '15 haiku agents, identical prompt' }],
}

const PROMPT = 'A bag holds 9 red, 7 blue, 5 green and 4 yellow marbles. You draw 5 marbles without replacement. What is the exact probability that all four colours appear at least once? Work it out carefully. Give the answer as a fraction in lowest terms, and put only that fraction on the last line of your reply.'

const thunks = [
  ...[1, 2, 3].map((i) => () => agent(PROMPT, { label: `low-${i}`, phase: 'Probe', model: 'haiku', effort: 'low' })),
  ...[1, 2, 3].map((i) => () => agent(PROMPT, { label: `medium-${i}`, phase: 'Probe', model: 'haiku', effort: 'medium' })),
  ...[1, 2, 3].map((i) => () => agent(PROMPT, { label: `high-${i}`, phase: 'Probe', model: 'haiku', effort: 'high' })),
  ...[1, 2, 3].map((i) => () => agent(PROMPT, { label: `xhigh-${i}`, phase: 'Probe', model: 'haiku', effort: 'xhigh' })),
  // routing: inherit
  ...[1, 2, 3].map((i) => () => agent(PROMPT, { label: `unpinned-${i}`, phase: 'Probe', model: 'haiku' })),
]

const out = await parallel(thunks)
return out.map((t, i) => (t == null ? null : String(t).split('\n').filter(Boolean).slice(-1)[0]))
