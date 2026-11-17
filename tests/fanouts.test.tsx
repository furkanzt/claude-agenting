// Tests for the fan-out view (hooks/fanouts/): run with `python3 scripts/quality/run_plugin_tests.py`, which
// copies the plugin's own files to a temp folder first (plain `claude plugin test .` would also run evals/private/).
import { expect, mock, test } from 'claude-code/testing'
import type { Mounted, TestBody } from 'claude-code/testing'
import type { On } from 'claude-code'

import type { Fanout, FanoutAgent, Selection, Snapshot, SpendRun } from '../types'
import { agentStats, bandFanouts, finished, headerStats, phaseCell, phaseCol, phases } from '../hooks/fanouts/view'
import * as view from '../hooks/fanouts/view'
import { count, duration, modelName } from '../hooks/fanouts/look'

// The pane's list and the spend record, as view.ts exports them; read through the module so each
// test that needs one names it.
const V = view as unknown as {
  paneFanouts(snap: Snapshot | null, sel: Selection): Fanout[]
  heldPin(pinned: string | null, snap: Snapshot): string | null
  mergeSpend(runs: SpendRun[], snap: Snapshot): SpendRun[]
  spendTotal(runs: SpendRun[]): { usd: number; runs: number }
  spendPath(base: { stateDir?: string | null; home?: string | null }, sessionId: string): string | null
}

// Nothing sits beneath the plugin: each hook here stands for the engine. A call on `$` is
// answered `{ value }`; an event by its own result.

const NOW = 1_800_000_000

function agent(over: Partial<FanoutAgent>): FanoutAgent {
  return {
    id: 'x', label: 'x', phase: null, state: 'done', model: 'claude-opus-5-5', effort: 'xhigh',
    elapsed_s: 30, out_tokens: 2000, tokens: 31600, cost_usd: 0.1, attempts: 1, error: null, ...over,
  }
}

function many(n: number, state: FanoutAgent['state'], phase: string | null = 'P'): FanoutAgent[] {
  return Array.from({ length: n }, (_, i) => agent({ id: `a${i}`, label: `task:${i}`, phase, state }))
}

function fanout(over: Partial<Fanout> = {}): Fanout {
  const agents = over.agents ?? [
    agent({ id: 'gkc_A', label: 'gkc:A', phase: 'GKC', state: 'done', elapsed_s: 277, tokens: 35900, cost_usd: 1.26 }),
    agent({ id: 'den_E', label: 'denetle:E', phase: 'Denetle', state: 'running', model: 'claude-sonnet-5-5', effort: 'high', elapsed_s: 28, tokens: null, cost_usd: null, attempts: 0 }),
    agent({ id: 'den_F', label: 'denetle:F', phase: 'Denetle', state: 'queued', elapsed_s: null, tokens: null, cost_usd: null, attempts: 0 }),
  ]
  return {
    id: '/w/clean/merge5', kind: 'runtime', name: 'merge5', dir: '/w/clean/merge5',
    script: 'merge_phases.js', pid: 27785, alive: true, state: 'running',
    started_at: NOW - 429, ended_at: null, elapsed_s: 429, jobs: 6,
    phases: ['GKC', 'Denetle'], agents,
    counts: { total: 3, done: 1, running: 1, queued: 1, failed: 0, skipped: 0 },
    cost_usd: 6.36, tokens: 132200, last_log: 'done gkc:A (277 s)', warnings: [], problems: [], ...over,
  }
}

function snap(fanouts: Fanout[], now = NOW): Snapshot {
  return { v: 1, now, platform: 'darwin', fanouts, cwds: { '27785': '/w' }, problems: [] }
}

const BAND = {
  plugin: 'agenting',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 160,
    scroll: { offset: 0, bodyRows: 9 }, view: {},
  },
} as const

const PANE = {
  plugin: 'agenting',
  component: 'Pane',
  requestId: 'fanouts',
  props: {
    title: 'Clean fan-outs', isFocused: true, bodyColumns: 100, placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 }, view: {},
  },
} as const

type Engine = Parameters<TestBody>[0]

// What else the engine answers: the chat's session id, and how many file writes, session id reads and
// reads of the spend file's folder variables (AGENTING_STATE_DIR, HOME) it refuses first. spend is the
// record a reload would find already stored: the engine hands it out until the plugin writes its own.
type Extra = { sessionId?: string; failWrites?: number; failIds?: number; failEnv?: number; spend?: { runs: SpendRun[]; written: number | null } }

// The engine around the plugin, answering each scan with the next snapshot (the last repeats).
// HOME is /home/me unless the test's env says otherwise; files written are recorded, not written.
function engine(on: On, answers: Array<Snapshot | 'fail'>, version = '2.1.317', during?: (scan: number) => Promise<void>, env: Record<string, string> = {}, extra: Extra = {}) {
  const scans: string[][] = []
  const toasts: string[] = []
  const opened: Array<Record<string, unknown>> = []
  const registered: Array<Record<string, unknown>> = []
  const closed: string[] = []
  const writes: Array<{ path: string; text: string }> = []
  const logs: Array<{ text: string; to: string }> = []
  const vars: Record<string, string> = { HOME: '/home/me', ...env }
  let refuse = extra.failWrites ?? 0
  let refuseIds = extra.failIds ?? 0
  let refuseEnv = extra.failEnv ?? 0
  let panes: Array<{ id: string; title: string; isShown: boolean; isFocused: boolean; isPlaced: boolean }> = []
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  // the stored record: read as it stands until the plugin has written its own
  if (extra.spend) {
    const stored = { shape: 'spend-1', value: extra.spend }
    on('state.get', { plugin: 'agenting', key: 'spend' }, async (_, e, next) => {
      const answer = await next(e)
      const held = answer.value as { value?: unknown; version: number } | undefined
      return held && held.value === undefined ? { value: { ...held, value: stored } } as never : answer
    })
  }
  on('command.register', (_, e) => {
    registered.push({ ...e })
    return { value: { command: 'fanouts' } }
  })
  on('session.version', () => ({ value: { version } }))
  on('session.id', () => {
    if (refuseIds > 0) {
      refuseIds--
      return { deny: 'no session yet' }
    }
    return { value: extra.sessionId ?? 'sess-1' }
  })
  on('env.get', (_, e) => {
    if (refuseEnv > 0 && (e.name === 'AGENTING_STATE_DIR' || e.name === 'HOME')) {
      refuseEnv--
      return { deny: 'env unreadable' }
    }
    return { value: vars[e.name] }
  })
  on('fs.write', (_, e) => {
    if (refuse > 0) {
      refuse--
      return { deny: 'disk full' }
    }
    writes.push({ path: e.path, text: e.text })
    return { value: undefined }
  })
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.log', (_, e) => {
    logs.push({ text: e.text, to: e.to })
    return { value: undefined }
  })
  on('ui.open', (_, e) => {
    opened.push({ ...e })
    panes = [{ id: e.id, title: e.title ?? e.id, isShown: true, isFocused: true, isPlaced: true }]
    return { value: { isPlaced: true } }
  })
  on('ui.panes', () => ({ value: panes }))
  on('ui.focus', () => ({}))
  on('ui.close', (_, e) => {
    closed.push(e.id)
    panes = panes.filter(p => p.id !== e.id)
    return { value: undefined }
  })
  on('process.run', async (_, e) => {
    scans.push([...e.argv])
    if (during) await during(scans.length)
    const a = answers[Math.min(scans.length - 1, answers.length - 1)]
    if (a === 'fail' || a === undefined) {
      return { value: { exitCode: 1, stdout: '', stderr: 'Traceback: boom', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    return { value: { exitCode: 0, stdout: JSON.stringify(a), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  return { scans, toasts, opened, closed, registered, writes, logs }
}

async function started($: Engine, on: On, answers: Array<Snapshot | 'fail'>, version?: string, env?: Record<string, string>, extra?: Extra) {
  const clock = mock.clock(on, { now: NOW * 1000 })
  const eng = engine(on, answers, version, undefined, env, extra)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await clock.settle()
  return { clock, ...eng }
}

function engineDraws(on: On) {
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine</Text>
  })
}

const run = (command: string) => ({
  command, args: '', origin: { kind: 'composer' as const }, presentation: { isFullscreen: false, columns: 160 },
})

const NONE = 'No clean fan-outs running. One shows here while cleanrun.py runs (or an external clean_runtime.mjs).'

// A plugin loaded beside agenting that reads what agenting stored, as any plugin may read it:
// /peek-selection and /peek-spend answer the stored value, its shape tag included.
const peek = {
  name: 'peek',
  register(on: On) {
    on('command.run', { command: 'peek-selection' }, async $ => ({
      text: JSON.stringify((await $.state.get({ plugin: 'agenting', key: 'selection' })).value ?? null),
    }))
    on('command.run', { command: 'peek-spend' }, async $ => ({
      text: JSON.stringify((await $.state.get({ plugin: 'agenting', key: 'spend' } as never)).value ?? null),
    }))
  },
}

async function stored($: Engine, key: 'selection' | 'spend') {
  const answer = (await $.command.run(run(`peek-${key}`))) as { text: string }
  return JSON.parse(answer.text)
}

// The fan-out the pane shows (its bold name) and its tab row.
async function shownName(ui: PaneMount) {
  return (await ui.findAll({ type: 'Text' })).find(t => t.props.bold)?.text ?? null
}

async function tabs(ui: PaneMount) {
  return (await ui.findAll({ type: 'Button' })).filter(b => b.key?.startsWith('fanout:')).map(b => b.text)
}

// The spend file's contents, one per write.
function spent(writes: Array<{ path: string; text: string }>) {
  return writes.map(w => JSON.parse(w.text) as { v: number; session_id: string; usd: number; runs: number; updated_at: number })
}

// ---------------- the band: the bottom panel's Workflow row ----------------

test('the band draws the bottom-panel Workflow row, and says it is a clean fan-out', async ($, on) => {
  await started($, on, [snap([fanout()])])
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    const row = await ui.find({ type: 'Text', text: /merge5/ })
    expect(row?.text).toBe('◯ merge5  ▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱▱▱▱  1/3 · 7m09s · ↓ 132.2k tokens · clean fan-out')
    const texts = await ui.findAll({ type: 'Text' })
    expect(texts.find(t => t.text === '◯')?.props).toMatchObject({ dimColor: true })
    expect(texts.find(t => t.text === ' merge5')?.props).toMatchObject({ dimColor: true })
    expect(texts.find(t => t.text === '▰▰▰▰▰▰')?.props.color).toBeUndefined()
    expect(texts.find(t => t.text === '▱▱▱▱▱▱▱▱▱▱▱▱▱▱')?.props).toMatchObject({ dimColor: true })
    // the row is a plain Button with its digit: the engine draws "1: " and then the row
    const buttons = await ui.findAll({ type: 'Button' })
    expect(buttons.map(b => [b.key, b.props.plain, b.props.hotkey, b.text])).toEqual([['open:0', true, '1', row?.text]])
    await ui.unmount()
  }
})

test('pressing a band row (ctrl+x tab, enter) opens the pane on that fan-out, with the keyboard', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other' })
  const { opened } = await started($, on, [snap([fanout(), other])])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  // ctrl+x tab gives the band the keyboard with the ring on the first row, so enter presses it
  expect((await band.findAll({ type: 'Button' })).map(b => [b.key, b.props.autoFocus ?? null])).toEqual([['open:0', true], ['open:1', null]])
  await band.press({ key: 'open:1' })
  await band.unmount()
  expect(opened).toEqual([{ id: 'fanouts', title: 'Clean fan-outs', focus: true, closeOnEscape: true }])
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const names = await pane.findAll({ type: 'Text', text: /^other$/ })
  expect(names.find(t => t.props.bold)?.props).toMatchObject({ bold: true, color: 'permission' })
  await pane.unmount()
})

test('each band row carries its digit, so typing 2 into an empty prompt opens the pane on the second, mid-turn too', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other' })
  const { opened } = await started($, on, [snap([fanout(), other])])
  // isWorking: Claude is mid-turn; the band and its digits stay
  const band = await $.ui.mount({ ...BAND, surface: 'terminal', props: { ...BAND.props, isWorking: true } })
  const buttons = await band.findAll({ type: 'Button' })
  expect(buttons.map(b => [b.key, b.props.hotkey])).toEqual([['open:0', '1'], ['open:1', '2']])
  // the engine presses the Button whose hotkey is the digit typed
  await band.press({ key: buttons.find(b => b.props.hotkey === '2')!.key })
  await band.unmount()
  expect(opened).toEqual([{ id: 'fanouts', title: 'Clean fan-outs', focus: true, closeOnEscape: true }])
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await pane.findAll({ type: 'Text', text: /^other$/ })).find(t => t.props.bold)).toBeDefined()
  await pane.unmount()
})

test('beside a docked pane the band row is clipped to the band\'s width after its digit, never wrapped', async ($, on) => {
  await started($, on, [snap([fanout()])])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal', props: { ...BAND.props, bodyColumns: 70 } })
  const row = (await band.find({ type: 'Text', text: /merge5/ }))?.text ?? ''
  // 70 cells less the engine's "1: ": the stats give way, the name and the bar stay whole
  expect(row).toBe('◯ merge5  ▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱▱▱▱  1/3 · 7m09s · ↓ 132.2k tokens · cl…')
  expect([...row].length).toBe(67)
  await band.unmount()
})

async function bandBar($: Engine, on: On, env: Record<string, string>) {
  await started($, on, [snap([fanout()])], '2.1.317', env)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const text = (await ui.find({ type: 'Text', text: /merge5/ }))?.text ?? ''
  await ui.unmount()
  return text
}

test('in Ghostty (TERM_PROGRAM ghostty) the bar is █░, as the engine draws it there', async ($, on) => {
  expect(await bandBar($, on, { TERM_PROGRAM: 'ghostty' })).toContain('  ██████░░░░░░░░░░░░░░  1/3')
})

test('in Ghostty (TERM xterm-ghostty) the bar is █░, as the engine draws it there', async ($, on) => {
  expect(await bandBar($, on, { TERM: 'xterm-ghostty' })).toContain('  ██████░░░░░░░░░░░░░░  1/3')
})

test('with only GHOSTTY_RESOURCES_DIR set the bar stays ▰▱, as the engine draws it then', async ($, on) => {
  expect(await bandBar($, on, { TERM: 'xterm-256color', GHOSTTY_RESOURCES_DIR: '/g' })).toContain('  ▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱▱▱▱  1/3')
})

test('a finished run is ◯ in success, a failed one ✘, a stopped one ⚠', async ($, on) => {
  const done = fanout({ id: '/w/a', dir: '/w/a', name: 'a', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  const failed = fanout({ id: '/w/b', dir: '/w/b', name: 'b', state: 'failed', alive: false, pid: null, ended_at: NOW - 5 })
  const died = fanout({ id: '/w/c', dir: '/w/c', name: 'c', state: 'died', alive: false, pid: null, ended_at: NOW - 5 })
  await started($, on, [snap([done, failed, died])])
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const texts = await ui.findAll({ type: 'Text' })
  expect(texts.filter(t => ['◯', '✘', '⚠'].includes(t.text)).map(t => [t.text, t.props.color])).toEqual([
    ['◯', 'success'], ['✘', 'error'], ['⚠', 'warning'],
  ])
  await ui.unmount()
})

test('the band leaves the drawing to the engine when no fan-out runs', async ($, on) => {
  engineDraws(on)
  await started($, on, [snap([])])
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text' }))?.text).toBe('engine')
  await ui.unmount()
})

test('with a survey up the band is the engine\'s, even while a fan-out runs', async ($, on) => {
  engineDraws(on)
  await started($, on, [snap([fanout()])])
  let ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /merge5/ }))?.text).toMatch(/^◯ merge5 /)
  await ui.unmount()
  ui = await $.ui.mount({ ...BAND, surface: 'terminal', props: { ...BAND.props, hasSurvey: true } })
  expect((await ui.find({ type: 'Text' }))?.text).toBe('engine')
  await ui.unmount()
})

test('the band shows three rows at most, and fits maxRows', async ($, on) => {
  const four = ['a', 'b', 'c', 'd'].map(n => fanout({ id: `/w/${n}`, dir: `/w/${n}`, name: n }))
  await started($, on, [snap(four)])
  let ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.findAll({ type: 'Text', text: /^◯ [abcd] / })).toHaveLength(3)
  expect((await ui.find({ type: 'Text', text: /more/ }))?.text).toBe('  +1 more clean fan-outs · /fanouts')
  await ui.unmount()
  ui = await $.ui.mount({ ...BAND, surface: 'terminal', props: { ...BAND.props, maxRows: 2 } })
  expect(await ui.findAll({ type: 'Text', text: /^◯ [abcd] / })).toHaveLength(1)
  expect((await ui.find({ type: 'Text', text: /more/ }))?.text).toBe('  +3 more clean fan-outs · /fanouts')
  await ui.unmount()
})

test('an ended run keeps its band row five minutes from when it was seen ending', async ($, on) => {
  engineDraws(on)
  const ended = fanout({ state: 'died', alive: false, pid: null, ended_at: NOW - 10000, problems: ['no process'] })
  const { clock } = await started($, on, [snap([fanout()]), snap([ended], NOW + 3), snap([ended], NOW + 3 + 290), snap([ended], NOW + 3 + 310)])
  await clock.advance(3000)    // seen ending at NOW + 3
  let ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /merge5/ }))?.text).toMatch(/^⚠ merge5 /)
  await ui.unmount()
  await clock.advance(15000)   // 290 s after: still there
  ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /merge5/ }))?.text).toMatch(/^⚠ merge5 /)
  await ui.unmount()
  await clock.advance(15000)   // 310 s after: gone
  ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text' }))?.text).toBe('engine')
  await ui.unmount()
})

test('a run first seen long after it ended does not get band time', async ($, on) => {
  engineDraws(on)
  await started($, on, [snap([fanout({ state: 'done', alive: false, pid: null, ended_at: NOW - 3600 })])])
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text' }))?.text).toBe('engine')
  await ui.unmount()
})

test('the stale marker shows only while the scanner fails, and clears on the next good scan', async ($, on) => {
  const { clock } = await started($, on, [snap([fanout()]), 'fail', snap([fanout()], NOW + 6)])
  let ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /scanner failing/ })).toBeUndefined()
  await ui.unmount()
  await clock.advance(3000)
  ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.findAll({ type: 'Text' })).find(t => t.text === ' · ⚠ scanner failing')?.props.color).toBe('warning')
  await ui.unmount()
  await clock.advance(3000)
  ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /scanner failing/ })).toBeUndefined()
  await ui.unmount()
})

// ---------------- the pane: the /workflows view ----------------

test('the pane is the /workflows view: header, Phases column, the open phase\'s agents, on every surface', async ($, on) => {
  await started($, on, [snap([fanout()])])
  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    const name = await ui.find({ type: 'Text', text: /^merge5$/ })
    expect(name?.props).toMatchObject({ bold: true, color: 'permission' })
    expect((await ui.find({ type: 'Text', text: /^clean fan-out/ }))?.text).toBe('clean fan-out · merge_phases.js')
    expect((await ui.find({ type: 'Text', text: /agents · / }))?.text).toBe(' 1/3 agents · 7m09s · $6.36')
    expect((await ui.find({ type: 'Text', text: /^╭/ }))?.text).toMatch(/^╭ Phases ─+┬ Denetle · 2 agents ─+╮$/)
    expect((await ui.find({ type: 'Button', text: /GKC/ }))?.text).toBe('  ✔ GKC      1/1')
    expect((await ui.find({ type: 'Button', text: /Denetle/ }))?.text).toBe('❯ 2 Denetle  0/2')
    // agent rows: plain Buttons laid out to the column (75 cells here), the time at its right edge
    const rowE = await ui.find({ type: 'Button', text: /denetle:E/ })
    expect(rowE?.text).toMatch(/^ ⏺ denetle:E {4}Sonnet 5\.5 · high +28s$/)
    expect([...(rowE?.text ?? '')].length).toBe(75)
    expect((await ui.find({ type: 'Button', text: /denetle:F/ }))?.text).toMatch(/^ ◌ denetle:F {4}Opus 5\.5 · xhigh · queued *$/)
    expect((await ui.find({ type: 'Text', text: /^╰/ }))?.text).toMatch(/^╰─+┴─+╯$/)
    expect((await ui.find({ type: 'Text', text: /select/ }))?.text).toBe('↑↓ select · esc close')
    await ui.unmount()
  }
})

test('picking a phase, by press or by moving the focus ring, shows its agents', async ($, on) => {
  await started($, on, [snap([fanout()])])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'phase:1' })
  // one shared effort: once in the column title, not in the row, which reads as a Workflow row does
  expect((await ui.find({ type: 'Text', text: /^╭/ }))?.text).toMatch(/┬ GKC · 1 agent · xhigh ─/)
  expect((await ui.find({ type: 'Button', text: /gkc:A/ }))?.text).toMatch(/^ ✔ gkc:A {8}Opus 5\.5 · 35\.9k tok +4m37s$/)
  expect((await ui.find({ type: 'Button', text: /GKC/ }))?.text).toBe('❯ ✔ GKC      1/1')
  // what ↓ does: the person moves the focus ring onto the next phase
  await $.ui.focus({ component: 'Pane', requestId: 'fanouts', element: 'phase:2', origin: { kind: 'person' } })
  expect((await ui.find({ type: 'Text', text: /^╭/ }))?.text).toMatch(/┬ Denetle · 2 agents ─/)
  await ui.unmount()
})

test('the selected phase is in permission, a done one ✔ success, an open one\'s number subtle', async ($, on) => {
  await started($, on, [snap([fanout()])])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const texts = await ui.findAll({ type: 'Text' })
  expect(texts.find(t => t.text === '  ✔')?.props.color).toBe('success')
  expect(texts.find(t => t.text === '❯ 2')?.props.color).toBe('permission')
  expect(texts.find(t => t.text === '0/2')?.props.color).toBe('permission')
  expect(texts.find(t => t.text === '1/1')?.props.color).toBe('subtle')
  expect(texts.find(t => t.text === '⏺')?.props.color).toBe('subtle')
  expect(texts.filter(t => /^[╭╰]/.test(t.text)).map(t => t.props.color)).toEqual(['text', 'text'])
  await ui.unmount()
})

test('a phase not started yet says so', async ($, on) => {
  await started($, on, [snap([fanout({ phases: ['GKC', 'Denetle', 'Düzelt'] })])])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Button', text: /Düzelt/ }))?.text).toBe('  3 Düzelt')
  await ui.press({ key: 'phase:3' })
  expect((await ui.find({ type: 'Text', text: /Not started/ }))?.text).toBe('Not started yet')
  await ui.unmount()
})

test('several fan-outs get a row of tabs; picking one shows it', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other', cost_usd: 1.5 })
  await started($, on, [snap([fanout(), other])])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.findAll({ type: 'Button', text: /merge5|other/ })).map(b => b.text)).toEqual(['◯ merge5', '◯ other'])
  await ui.press({ key: 'fanout:1' })
  expect((await ui.find({ type: 'Text', text: /^other$/ }))?.props.color).toBe('permission')
  expect((await ui.find({ type: 'Text', text: /agents · / }))?.text).toBe(' 1/3 agents · 7m09s · $1.50')
  await ui.unmount()
})

test('a finished run leaves the pane\'s tabs on the first scan that reports it ended, and keeps its band row', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other' })
  const ended = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW + 3 })
  const { clock } = await started($, on, [snap([fanout(), other]), snap([fanout(), ended], NOW + 3)])
  let pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await tabs(pane)).toEqual(['◯ merge5', '◯ other'])
  await pane.unmount()
  await clock.advance(3000)
  pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await tabs(pane)).toEqual([])
  expect(await pane.find({ type: 'Text', text: /^other$/ })).toBeUndefined()
  expect(await shownName(pane)).toBe('merge5')
  await pane.unmount()
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await band.findAll({ type: 'Text', text: /^◯ (merge5|other) / })).map(t => t.text.split(' ')[1])).toEqual(['merge5', 'other'])
  await band.unmount()
})

test('when the run on screen ends, the pane falls back to the first running one', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other' })
  const ended = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'failed', alive: false, pid: null, ended_at: NOW + 3 })
  const { clock } = await started($, on, [snap([fanout(), other]), snap([fanout(), ended], NOW + 3)])
  let pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await pane.press({ key: 'fanout:1' })
  expect(await shownName(pane)).toBe('other')
  await pane.unmount()
  await clock.advance(3000)
  pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await shownName(pane)).toBe('merge5')
  expect(await pane.find({ type: 'Text', text: /^other$/ })).toBeUndefined()
  await pane.unmount()
})

test('with no fan-out running the pane says none runs, even with finished runs in the snapshot', async ($, on) => {
  const done = fanout({ id: '/w/a', dir: '/w/a', name: 'a', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  const failed = fanout({ id: '/w/b', dir: '/w/b', name: 'b', state: 'failed', alive: false, pid: null, ended_at: NOW - 5 })
  await started($, on, [snap([done, failed])])
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await pane.find({ type: 'Text', text: /No clean fan-outs/ }))?.text).toBe(NONE)
  expect(await shownName(pane)).toBeNull()
  expect(await pane.findAll({ type: 'Button' })).toEqual([])
  await pane.unmount()
})

test('pressing the band row of a finished run shows it in the pane, selected, beside the running tabs', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW - 5, cost_usd: 1.5 })
  // another finished run in the band, not pressed: it gets no tab
  const older = fanout({ id: '/w/c', dir: '/w/c', name: 'older', state: 'failed', alive: false, pid: null, ended_at: NOW - 5 })
  await started($, on, [snap([fanout(), other, older])])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'open:1' })
  await band.unmount()
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await tabs(pane)).toEqual(['◯ merge5', '◯ other'])
  // its tab and its header are both in permission: it is the one on screen
  expect((await pane.findAll({ type: 'Text', text: /^other$/ })).map(t => t.props.color)).toEqual(['permission', 'permission'])
  expect(await shownName(pane)).toBe('other')
  expect((await pane.find({ type: 'Text', text: /agents · / }))?.text).toBe(' 1/3 agents · 7m09s · $1.50 · done')
  await pane.unmount()
})

test('a phase press keeps the band\'s finished run in the pane; picking another tab drops it', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  await started($, on, [snap([fanout(), other])])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'open:1' })
  await band.unmount()
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  // a phase of it, by press and by the focus ring: it stays
  await pane.press({ key: 'phase:1' })
  expect(await shownName(pane)).toBe('other')
  expect((await pane.find({ type: 'Text', text: /^╭/ }))?.text).toMatch(/┬ GKC · 1 agent · xhigh ─/)
  await $.ui.focus({ component: 'Pane', requestId: 'fanouts', element: 'phase:2', origin: { kind: 'person' } })
  expect(await shownName(pane)).toBe('other')
  // an agent row of it, by press: it stays
  await pane.press({ key: 'phase:1' })
  await pane.press({ key: 'agent:0' })
  expect(await shownName(pane)).toBe('other')
  // its own tab: it stays
  await pane.press({ key: 'fanout:1' })
  expect(await shownName(pane)).toBe('other')
  expect(await tabs(pane)).toEqual(['◯ merge5', '◯ other'])
  // another tab: it leaves the pane
  await pane.press({ key: 'fanout:0' })
  expect(await shownName(pane)).toBe('merge5')
  expect(await tabs(pane)).toEqual([])
  expect(await pane.find({ type: 'Text', text: /^other$/ })).toBeUndefined()
  await pane.unmount()
})

test('/fanouts drops the band\'s finished run from the pane', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  await started($, on, [snap([fanout(), other])])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'open:1' })
  await band.unmount()
  // the band opened the pane: /fanouts closes it, /fanouts again opens it
  expect(await $.command.run(run('fanouts'))).toMatchObject({ text: 'Clean fan-outs pane closed.' })
  expect(await $.command.run(run('fanouts'))).toMatchObject({ text: 'Clean fan-outs pane opened (esc closes it).' })
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await shownName(pane)).toBe('merge5')
  expect(await tabs(pane)).toEqual([])
  expect(await pane.find({ type: 'Text', text: /^other$/ })).toBeUndefined()
  await pane.unmount()
})

test('a phase press acts on the run the pane shows, not on a finished run still selected', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  await started($, on, [snap([fanout(), other])])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'open:1' })
  await band.unmount()
  await $.command.run(run('fanouts'))
  await $.command.run(run('fanouts'))
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await shownName(pane)).toBe('merge5')
  expect((await pane.find({ type: 'Text', text: /^╭/ }))?.text).toMatch(/┬ Denetle · 2 agents ─/)
  await pane.press({ key: 'phase:1' })
  expect(await shownName(pane)).toBe('merge5')
  expect((await pane.find({ type: 'Text', text: /^╭/ }))?.text).toMatch(/┬ GKC · 1 agent · xhigh ─/)
  await pane.unmount()
})

test('a run opened from the band while it runs leaves the pane when it ends', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other' })
  const ended = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW + 3 })
  const { clock } = await started($, on, [snap([fanout(), other]), snap([fanout(), ended], NOW + 3)])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'open:1' })
  await band.unmount()
  let pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await shownName(pane)).toBe('other')
  await pane.unmount()
  await clock.advance(3000)
  pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await shownName(pane)).toBe('merge5')
  expect(await pane.find({ type: 'Text', text: /^other$/ })).toBeUndefined()
  await pane.unmount()
})

test('a tab press selects the run drawn at that index, whatever the snapshot order', async ($, on) => {
  // a finished run ahead of the running ones in the snapshot, though the scanner puts running first
  const old = fanout({ id: '/w/old', dir: '/w/old', name: 'old', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  const a = fanout({ id: '/w/a', dir: '/w/a', name: 'a' })
  const b = fanout({ id: '/w/b', dir: '/w/b', name: 'b' })
  await started($, on, [snap([old, a, b])])
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await tabs(pane)).toEqual(['◯ a', '◯ b'])
  await pane.press({ key: 'fanout:1' })
  expect(await shownName(pane)).toBe('b')
  await pane.press({ key: 'fanout:0' })
  expect(await shownName(pane)).toBe('a')
  await pane.unmount()
})

test('a band-opened finished run does not come back to the pane when a later run in its folder ends', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  const again = fanout({ id: '/w/b', dir: '/w/b', name: 'other' })
  const ended = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW + 6 })
  const { clock } = await started($, on, [snap([fanout(), other]), snap([fanout(), again], NOW + 3), snap([fanout(), ended], NOW + 6)])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'open:1' })
  await band.unmount()
  await clock.advance(3000)
  // a new run in the folder shows because it runs
  let pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await tabs(pane)).toEqual(['◯ merge5', '◯ other'])
  await pane.unmount()
  await clock.advance(3000)
  // its end was reported by a scan: it leaves, though the person never pressed the band row again
  pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await tabs(pane)).toEqual([])
  expect(await shownName(pane)).toBe('merge5')
  expect(await pane.find({ type: 'Text', text: /^other$/ })).toBeUndefined()
  await pane.unmount()
})

test('a band-opened finished run does not come back to the pane when its folder left the snapshot and a later run there ended', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  const later = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'failed', alive: false, pid: null, ended_at: NOW + 6 })
  const { clock } = await started($, on, [snap([fanout(), other]), snap([fanout()], NOW + 3), snap([fanout(), later], NOW + 6)])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'open:1' })
  await band.unmount()
  await clock.advance(3000)
  await clock.advance(3000)
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await tabs(pane)).toEqual([])
  expect(await shownName(pane)).toBe('merge5')
  expect(await pane.find({ type: 'Text', text: /^other$/ })).toBeUndefined()
  await pane.unmount()
})

test('a band row pressed while a scan is letting go of the held run is not undone by that scan', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  const again = fanout({ id: '/w/b', dir: '/w/b', name: 'other' })
  const third = fanout({ id: '/w/c', dir: '/w/c', name: 'third', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  let armed = false
  let band: Awaited<ReturnType<Engine['ui']['mount']>> | null = null
  // the first read of the selection after the clock moves is the scan's own: the person presses the
  // third run's band row right after it, before the scan lets go of the run it read as held
  on('state.get', { plugin: 'agenting', key: 'selection' }, async (_, e, next) => {
    const answer = await next(e)
    if (armed) {
      armed = false
      await (band as { press(a: { key: string }): Promise<unknown> }).press({ key: 'open:2' })
    }
    return answer
  })
  const { clock } = await started($, on, [snap([fanout(), other]), snap([fanout(), again, third], NOW + 3)])
  band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'open:1' })
  armed = true
  await clock.advance(3000)
  await band.unmount()
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await tabs(pane)).toEqual(['◯ merge5', '◯ other', '◯ third'])
  expect(await shownName(pane)).toBe('third')
  await pane.unmount()
})

test('a band-opened finished run stays in the pane over scans that still report it ended', async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  const { clock } = await started($, on, [snap([fanout(), other]), snap([fanout(), other], NOW + 3)])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'open:1' })
  await band.unmount()
  await clock.advance(3000)
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await tabs(pane)).toEqual(['◯ merge5', '◯ other'])
  expect(await shownName(pane)).toBe('other')
  await pane.unmount()
})

test('moving the focus ring onto a fan-out tab shows the run drawn at that index, whatever the snapshot order', async ($, on) => {
  const old = fanout({ id: '/w/old', dir: '/w/old', name: 'old', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  const a = fanout({ id: '/w/a', dir: '/w/a', name: 'a' })
  const b = fanout({ id: '/w/b', dir: '/w/b', name: 'b' })
  await started($, on, [snap([old, a, b])])
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await tabs(pane)).toEqual(['◯ a', '◯ b'])
  await $.ui.focus({ component: 'Pane', requestId: 'fanouts', element: 'fanout:1', origin: { kind: 'person' } })
  expect(await shownName(pane)).toBe('b')
  await $.ui.focus({ component: 'Pane', requestId: 'fanouts', element: 'fanout:0', origin: { kind: 'person' } })
  expect(await shownName(pane)).toBe('a')
  await pane.unmount()
})

test('the focus ring on the band-opened run\'s own tab keeps it in the pane; on another tab it lets it go', async ($, on) => {
  const old = fanout({ id: '/w/old', dir: '/w/old', name: 'old', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  const a = fanout({ id: '/w/a', dir: '/w/a', name: 'a' })
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  await started($, on, [snap([old, a, other])])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'open:2' })
  await band.unmount()
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await tabs(pane)).toEqual(['◯ a', '◯ other'])
  expect(await shownName(pane)).toBe('other')
  await $.ui.focus({ component: 'Pane', requestId: 'fanouts', element: 'fanout:1', origin: { kind: 'person' } })
  expect(await shownName(pane)).toBe('other')
  expect(await tabs(pane)).toEqual(['◯ a', '◯ other'])
  await $.ui.focus({ component: 'Pane', requestId: 'fanouts', element: 'fanout:0', origin: { kind: 'person' } })
  expect(await shownName(pane)).toBe('a')
  expect(await tabs(pane)).toEqual([])
  await pane.unmount()
})

test('the selection is stored under the shape tag selection-3, holding the finished run the band opened', { plugins: [peek] }, async ($, on) => {
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  await started($, on, [snap([fanout(), other])])
  let band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  // a running row: nothing to hold
  await band.press({ key: 'open:0' })
  expect(await stored($, 'selection')).toEqual({ shape: 'selection-3', value: { dir: '/w/clean/merge5', phase: null, agent: null, top: 0, pinned: null } })
  // a finished row: held
  await band.press({ key: 'open:1' })
  await band.unmount()
  expect(await stored($, 'selection')).toEqual({ shape: 'selection-3', value: { dir: '/w/b', phase: null, agent: null, top: 0, pinned: '/w/b' } })
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await pane.press({ key: 'fanout:0' })
  await pane.unmount()
  expect(await stored($, 'selection')).toEqual({ shape: 'selection-3', value: { dir: '/w/clean/merge5', phase: null, agent: null, top: 0, pinned: null } })
})

test('one fan-out has no tabs', async ($, on) => {
  await started($, on, [snap([fanout()])])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Button', text: /merge5/ })).toBeUndefined()
  await ui.unmount()
})

test('the agent column shows ten rows at a time, with the pager in the bottom border', async ($, on) => {
  const big = fanout({ agents: many(450, 'done'), phases: ['P'], counts: { total: 450, done: 450, running: 0, queued: 0, failed: 0, skipped: 0 } })
  await started($, on, [snap([big])])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.findAll({ type: 'Button' })).filter(b => b.key?.startsWith('agent:')).map(b => b.key)).toEqual(
    Array.from({ length: 10 }, (_, i) => `agent:${i}`))
  expect((await ui.find({ type: 'Text', text: /^╰/ }))?.text).toMatch(/^╰─+┴─+ 1-10 of 450 ↓ ╯$/)
  await ui.unmount()
})

test('↓ past the phases moves ❯ onto the agents, and the page scrolls to keep the next row in view', async ($, on) => {
  const f = fanout({ agents: many(14, 'done'), phases: ['P'], counts: { total: 14, done: 14, running: 0, queued: 0, failed: 0, skipped: 0 } })
  await started($, on, [snap([f])])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const focus = (element: string) => $.ui.focus({ component: 'Pane', requestId: 'fanouts', element, origin: { kind: 'person' } })
  const bottom = async () => (await ui.find({ type: 'Text', text: /^╰/ }))?.text ?? ''
  const pointed = async () => (await ui.findAll({ type: 'Button' })).filter(b => b.text.startsWith('❯✔')).map(b => b.key)
  await focus('agent:3')
  expect(await pointed()).toEqual(['agent:3'])
  expect(await bottom()).toMatch(/ 1-10 of 14 ↓ ╯$/)
  await focus('agent:9')
  expect(await pointed()).toEqual(['agent:9'])
  expect(await bottom()).toMatch(/ 2-11 of 14 ↑↓ ╯$/)
  await focus('agent:13')
  expect(await bottom()).toMatch(/ 5-14 of 14 ↑ ╯$/)
  await focus('phase:1')
  expect(await pointed()).toEqual([])
  expect(await bottom()).toMatch(/ 1-10 of 14 ↓ ╯$/)
  await ui.unmount()
})

test('a phase whose agents share one effort names it once, in the column title', async ($, on) => {
  await started($, on, [snap([fanout()])])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  // Denetle mixes high and xhigh: each row names its effort, the title none
  expect((await ui.find({ type: 'Text', text: /^╭/ }))?.text).toMatch(/┬ Denetle · 2 agents ─/)
  expect((await ui.find({ type: 'Button', text: /denetle:E/ }))?.text).toMatch(/Sonnet 5\.5 · high +28s$/)
  // GKC's one agent is xhigh: the title says it, the row reads as a Workflow row
  await ui.press({ key: 'phase:1' })
  expect((await ui.find({ type: 'Text', text: /^╭/ }))?.text).toMatch(/┬ GKC · 1 agent · xhigh ─/)
  expect((await ui.find({ type: 'Button', text: /gkc:A/ }))?.text).toMatch(/^ ✔ gkc:A {8}Opus 5\.5 · 35\.9k tok +4m37s$/)
  await ui.unmount()
})

test('a call still queued, its effort unknown, does not hide the effort the others share', async ($, on) => {
  const f = fanout({
    agents: [
      agent({ id: 'a', label: 'gen:1', phase: 'G', state: 'running', effort: 'xhigh', tokens: null, elapsed_s: 9 }),
      agent({ id: 'b', label: 'gen:2', phase: 'G', state: 'queued', effort: null, model: null, tokens: null, elapsed_s: null }),
    ],
    phases: ['G'],
  })
  await started($, on, [snap([f])])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /^╭/ }))?.text).toMatch(/┬ G · 2 agents · xhigh ─/)
  expect((await ui.find({ type: 'Button', text: /gen:1/ }))?.text).toMatch(/^ ⏺ gen:1 {8}Opus 5\.5 +9s$/)
  expect((await ui.find({ type: 'Button', text: /gen:2/ }))?.text).toMatch(/^ ◌ gen:2 {8}queued *$/)
  await ui.unmount()
})

test('the focus ring meets every phase row before any agent row', async ($, on) => {
  await started($, on, [snap([fanout()])])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.findAll({ type: 'Button' })).map(b => b.key)).toEqual(['phase:1', 'phase:2', 'agent:0', 'agent:1'])
  await ui.unmount()
})

test('a failed agent\'s row ends with its error', async ($, on) => {
  const f = fanout({
    agents: [agent({ id: 'a', label: 'denetle:T1', phase: 'Denetle', state: 'failed', error: 'output did not validate' })],
    phases: ['Denetle'], counts: { total: 1, done: 0, running: 0, queued: 0, failed: 1, skipped: 0 },
  })
  await started($, on, [snap([f])])
  // wide enough for the whole reason
  let ui = await $.ui.mount({ ...PANE, surface: 'terminal', props: { ...PANE.props, bodyColumns: 130 } })
  const row = await ui.find({ type: 'Button', text: /denetle:T1/ })
  expect(row?.text).toMatch(/^ ✘ denetle:T1 {3}Opus 5\.5 · 31\.6k tok · failed — output did not validate +30s$/)
  expect((await ui.findAll({ type: 'Text' })).find(t => t.text === ' — output did not validate')?.props.color).toBe('error')
  await ui.unmount()
  // narrower: the reason is cut, never the frame (the row keeps its column's 55 cells)
  ui = await $.ui.mount({ ...PANE, surface: 'terminal', props: { ...PANE.props, bodyColumns: 80 } })
  const cut = (await ui.find({ type: 'Button', text: /denetle:T1/ }))?.text ?? ''
  expect(cut).toMatch(/· failed — [^…]*… +30s$/)
  expect([...cut].length).toBe(55)
  await ui.unmount()
})

test('a run\'s first problem shows under the header, the others do not', async ($, on) => {
  const f = fanout({ state: 'died', alive: false, pid: null, ended_at: NOW - 5, problems: ['no process, and the last run never finished', 'a second problem'] })
  await started($, on, [snap([f])])
  // a stopped run reaches the pane through its band row
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'open:0' })
  await band.unmount()
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const texts = (await ui.findAll({ type: 'Text' })).map(t => t.text)
  const header = texts.findIndex(t => t.startsWith('clean fan-out'))
  expect(texts.slice(header, header + 3)).toEqual(['clean fan-out · merge_phases.js', ' 1/3 agents · 7m09s · $6.36 · stopped', '⚠ no process, and the last run never finished'])
  expect(texts.some(t => t.includes('a second problem'))).toBe(false)
  await ui.unmount()
})

test('a scanner that fails is reported in the pane, not thrown', async ($, on) => {
  await started($, on, ['fail'])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /No clean fan-outs/ }))?.text).toBe(NONE)
  expect((await ui.find({ type: 'Text', text: /scanner:/ }))?.text).toBe('⚠ scanner: fanout_scan.py exited 1: Traceback: boom')
  await ui.unmount()
})

test('the pane notes when Claude Code is another version than the look was copied from', async ($, on) => {
  await started($, on, [snap([])], '2.1.400')
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const note = await ui.find({ type: 'Text', text: /layout copied/ })
  expect(note?.text).toBe('layout copied from Claude Code 2.1.317; running 2.1.400')
  expect(note?.props).toMatchObject({ dimColor: true })
  await ui.unmount()
})

test('no version note under the version the look was copied from', async ($, on) => {
  await started($, on, [snap([])], '2.1.317')
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /layout copied/ })).toBeUndefined()
  await ui.unmount()
})

test('no version note when the engine gives no version', async ($, on) => {
  await started($, on, [snap([])], '')
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /layout copied/ })).toBeUndefined()
  await ui.unmount()
})

// ---------------- opening and closing ----------------

test('/fanouts opens the pane with the keyboard, Escape closing it; /fanouts again closes it', async ($, on) => {
  const { opened, closed } = await started($, on, [snap([])])
  const first = await $.command.run(run('fanouts'))
  expect(first).toMatchObject({ text: 'Clean fan-outs pane opened (esc closes it).' })
  expect(opened).toEqual([{ id: 'fanouts', title: 'Clean fan-outs', focus: true, closeOnEscape: true }])
  const second = await $.command.run(run('fanouts'))
  expect(second).toMatchObject({ text: 'Clean fan-outs pane closed.' })
  expect(closed).toEqual(['fanouts'])
})

test('/fanouts runs at once while a turn is in flight, as /rename does', async ($, on) => {
  const { registered } = await started($, on, [snap([])])
  expect(registered).toEqual([{
    name: 'fanouts',
    description: 'Show or hide clean-run fan-outs (cleanrun.py, clean_runtime.mjs) laid out like /workflows',
    immediate: true,
  }])
})

test('the selected phase takes the focus ring when the pane takes the keyboard', async ($, on) => {
  await started($, on, [snap([fanout()])])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const buttons = await ui.findAll({ type: 'Button' })
  expect(buttons.filter(b => b.props.autoFocus).map(b => b.text)).toEqual(['❯ 2 Denetle  0/2'])
  await ui.unmount()
})

// ---------------- the poll loop, toasts and what is passed back ----------------

test('a toast says when a running fan-out finishes; a stopped one says stopped', async ($, on) => {
  const done = fanout({ state: 'done', alive: false, pid: null, ended_at: NOW + 3, elapsed_s: 432, counts: { total: 3, done: 3, running: 0, queued: 0, failed: 0, skipped: 0 } })
  const { clock, toasts } = await started($, on, [snap([fanout()]), snap([done], NOW + 3)])
  expect(toasts).toHaveLength(0)
  await clock.advance(3000)
  expect(toasts).toEqual(['clean fan-out merge5 finished: 3/3 agents · 7m12s · $6.36'])
})

test('a stopped run is announced as stopped', async ($, on) => {
  const stopped = fanout({ state: 'died', alive: false, pid: null, ended_at: NOW + 2 })
  const { clock, toasts } = await started($, on, [snap([fanout()]), snap([stopped], NOW + 3)])
  await clock.advance(3000)
  expect(toasts).toEqual(['clean fan-out merge5 stopped: 1/3 agents · 7m09s · $6.36'])
})

test('a scan that cannot read the process table keeps the last snapshot: no false end toast', async ($, on) => {
  const degraded = { ...snap([], NOW + 3), degraded: true, problems: ['ps failed: OSError()'] }
  const { clock, toasts } = await started($, on, [snap([fanout()]), degraded])
  await clock.advance(3000)
  expect(toasts).toEqual([])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await band.find({ type: 'Text', text: /merge5/ }))?.text).toMatch(/^◯ merge5 /)
  await band.unmount()
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await pane.find({ type: 'Text', text: /scanner:/ }))?.text).toContain('could not read the process table')
  await pane.unmount()
})

test('a run unreadable for one scan keeps its row and its end is still announced', async ($, on) => {
  const unknown = { ...fanout(), kind: 'unknown' as const, state: 'unknown' as const, agents: [], problems: ['cwd unreadable'] }
  const done = fanout({ state: 'done', alive: false, pid: null, ended_at: NOW + 6 })
  const { clock, toasts } = await started($, on, [snap([fanout()]), snap([unknown], NOW + 3), snap([done], NOW + 6)])
  await clock.advance(3000)
  expect(toasts).toEqual([])
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /merge5/ }))?.text).toMatch(/^◯ merge5 /)
  await ui.unmount()
  await clock.advance(3000)
  expect(toasts).toHaveLength(1)
  expect(toasts[0]).toMatch(/^clean fan-out merge5 finished: /)
})

test('it scans every 3 s while a fan-out runs and every 15 s while none does', async ($, on) => {
  const { clock, scans } = await started($, on, [snap([fanout()]), snap([]), snap([])])
  expect(scans).toHaveLength(1)
  await clock.advance(3000)
  expect(scans).toHaveLength(2)
  await clock.advance(14000)
  expect(scans).toHaveLength(2)
  await clock.advance(1000)
  expect(scans).toHaveLength(3)
})

test('/fanouts while a scan is scheduled does not start a second loop', async ($, on) => {
  const { clock, scans } = await started($, on, [snap([fanout()])])
  await $.command.run(run('fanouts'))
  await clock.settle()
  const before = scans.length
  await clock.advance(30000)
  expect(scans.length - before).toBe(10)
})

test('the scanner is given back the folders it reported and the cwds it resolved', async ($, on) => {
  const { clock, scans } = await started($, on, [snap([fanout()])])
  await clock.advance(3000)
  const second = scans[1] ?? []
  expect(second.slice(0, 2)).toEqual(['python3', '-I'])
  expect(second[2]).toMatch(/\/scripts\/fanout_scan\.py$/)
  expect(second.slice(3)).toEqual(['--dir', '/w/clean/merge5', '--cwd', '27785=/w'])
})

test('an ended folder is passed back for two hours, then dropped', async ($, on) => {
  const ended = fanout({ state: 'done', alive: false, pid: null, ended_at: NOW + 2 })
  const { clock, scans } = await started($, on, [
    snap([fanout()]), snap([ended], NOW + 3), snap([ended], NOW + 3 + 7100), snap([ended], NOW + 3 + 7300), snap([], NOW + 7400),
  ])
  await clock.advance(3000)    // scan 2: seen ending at NOW + 3
  await clock.advance(15000)   // scan 3: 7100 s later
  await clock.advance(15000)   // scan 4: 7300 s later
  await clock.advance(15000)   // scan 5
  expect(scans[3]).toContain('/w/clean/merge5')
  expect(scans[4]).not.toContain('--dir')
})

test('at most twenty folders are passed back, newest first', async ($, on) => {
  const runs = Array.from({ length: 25 }, (_, r) => fanout({
    id: `/w/r${r}`, dir: `/w/r${r}`, name: `r${r}`, state: 'done', alive: false, pid: null, ended_at: NOW - 100 + r,
  }))
  const { clock, scans } = await started($, on, [snap(runs)])
  await clock.advance(15000)
  const dirs = (scans[1] ?? []).filter((_, i, a) => a[i - 1] === '--dir')
  expect(dirs).toHaveLength(20)
  expect(dirs[0]).toBe('/w/r24')
})

// ---------------- this chat's clean fan-out spend, for the status line ----------------

test('this chat\'s clean fan-out spend is written for the status line under HOME/.claude', { plugins: [peek] }, async ($, on) => {
  const { writes } = await started($, on, [snap([fanout()])])
  expect(writes.map(w => w.path)).toEqual(['/home/me/.claude/.agenting-fanout-cost/sess-1.json'])
  expect(spent(writes)).toEqual([{ v: 1, session_id: 'sess-1', usd: 6.36, runs: 1, updated_at: NOW }])
  // kept in the session's state, under its own shape tag
  expect((await stored($, 'spend'))?.shape).toBe('spend-1')
})

test('the spend file goes under AGENTING_STATE_DIR when it is set', async ($, on) => {
  const { writes } = await started($, on, [snap([fanout()])], undefined, { AGENTING_STATE_DIR: '/state' })
  expect(writes.map(w => w.path)).toEqual(['/state/.agenting-fanout-cost/sess-1.json'])
})

test('the spend adds up every run folder of the chat, and counts the folders that cost something', async ($, on) => {
  const a = fanout({ id: '/w/a', dir: '/w/a', name: 'a', cost_usd: 1.25 })
  const b = fanout({ id: '/w/b', dir: '/w/b', name: 'b', state: 'done', alive: false, pid: null, ended_at: NOW - 5, cost_usd: 2.5 })
  const c = fanout({ id: '/w/c', dir: '/w/c', name: 'c', cost_usd: null })
  const { clock, writes } = await started($, on, [snap([a, b, c]), snap([{ ...a, cost_usd: 1.5 }, b, c], NOW + 3)])
  expect(spent(writes).map(w => [w.usd, w.runs])).toEqual([[3.75, 2]])
  await clock.advance(3000)
  expect(spent(writes).map(w => [w.usd, w.runs, w.updated_at])).toEqual([[3.75, 2, NOW], [4, 2, NOW + 3]])
})

test('the spend file is written only when the total, to four decimals, changes', async ($, on) => {
  const { clock, writes } = await started($, on, [
    snap([fanout({ cost_usd: 1 })]),
    snap([fanout({ cost_usd: 1 })], NOW + 3),
    snap([fanout({ cost_usd: 1.00004 })], NOW + 6),
    snap([fanout({ cost_usd: 1.2 })], NOW + 9),
  ])
  expect(writes).toHaveLength(1)
  await clock.advance(3000)
  await clock.advance(3000)
  expect(writes).toHaveLength(1)
  await clock.advance(3000)
  expect(spent(writes).map(w => [w.usd, w.updated_at])).toEqual([[1, NOW], [1.2, NOW + 9]])
})

test('nothing is written while the spend is 0', async ($, on) => {
  const { clock, writes } = await started($, on, [
    snap([fanout({ cost_usd: null })]),
    snap([fanout({ cost_usd: 0 })], NOW + 3),
    snap([fanout({ cost_usd: 0.5 })], NOW + 6),
  ])
  await clock.advance(3000)
  expect(writes).toEqual([])
  await clock.advance(3000)
  expect(spent(writes).map(w => [w.usd, w.runs])).toEqual([[0.5, 1]])
})

test('the spend never goes down: not when a run leaves the snapshot, reports no cost, or a scan fails', async ($, on) => {
  const a = fanout({ id: '/w/a', dir: '/w/a', name: 'a', cost_usd: 2 })
  const b = fanout({ id: '/w/b', dir: '/w/b', name: 'b', cost_usd: 1 })
  const bDone = { ...b, state: 'done' as const, alive: false, pid: null, ended_at: NOW + 6, cost_usd: null }
  const { clock, writes, scans } = await started($, on, [
    snap([a, b]),
    snap([a], NOW + 3),                                  // b is gone from the snapshot
    snap([{ ...a, cost_usd: null }, bDone], NOW + 6),   // no cost reported for either
    'fail',
    snap([{ ...a, cost_usd: 2.5 }], NOW + 12),
  ])
  for (let i = 0; i < 4; i++) await clock.advance(3000)
  expect(scans).toHaveLength(5)
  expect(spent(writes).map(w => [w.usd, w.runs])).toEqual([[3, 2], [3.5, 2]])
})

test('a re-run in the same folder adds to the run before it when it starts running again', async ($, on) => {
  const done = fanout({ state: 'done', alive: false, pid: null, ended_at: NOW - 5, cost_usd: 1 })
  // the scanner reports only the new run's cost, here already above the old one's
  const { clock, writes } = await started($, on, [snap([done]), snap([fanout({ cost_usd: 1.5 })], NOW + 15)])
  await clock.advance(15000)
  expect(spent(writes).map(w => [w.usd, w.runs])).toEqual([[1, 1], [2.5, 1]])
})

test('a re-run in the same folder adds to the run before it when the reported cost drops', async ($, on) => {
  // seen running both times: the first run ended and the next began between two scans
  const { clock, writes } = await started($, on, [
    snap([fanout({ cost_usd: 2 })]),
    snap([fanout({ cost_usd: 0.5 })], NOW + 3),
    snap([fanout({ cost_usd: 0.8 })], NOW + 6),
  ])
  await clock.advance(3000)
  await clock.advance(3000)
  expect(spent(writes).map(w => w.usd)).toEqual([2, 2.5, 2.8])
})

test('a session id that is not a plain file name writes nothing, and the band still draws', async ($, on) => {
  const { writes } = await started($, on, [snap([fanout()])], undefined, undefined, { sessionId: '../other' })
  expect(writes).toEqual([])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await band.find({ type: 'Text', text: /merge5/ }))?.text).toMatch(/^◯ merge5 /)
  await band.unmount()
})

test('a spend write that fails breaks neither the scan, the band nor the pane, and the next scan writes it', async ($, on) => {
  const { clock, writes, logs, scans } = await started($, on, [snap([fanout()]), snap([fanout()], NOW + 3)], undefined, undefined, { failWrites: 1 })
  expect(writes).toEqual([])
  expect(logs.filter(l => l.text.includes('disk full')).map(l => l.to)).toEqual(['debug'])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await band.find({ type: 'Text', text: /merge5/ }))?.text).toMatch(/^◯ merge5 /)
  expect(await band.find({ type: 'Text', text: /scanner failing/ })).toBeUndefined()
  await band.unmount()
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await shownName(pane)).toBe('merge5')
  expect(await pane.find({ type: 'Text', text: /scanner:/ })).toBeUndefined()
  await pane.unmount()
  await clock.advance(3000)
  expect(scans).toHaveLength(2)
  expect(spent(writes).map(w => [w.usd, w.updated_at])).toEqual([[6.36, NOW + 3]])
})

test('a session id that cannot be read breaks neither the scan, the band nor the pane, and the next scan writes the file', async ($, on) => {
  const { clock, writes, logs, scans } = await started($, on, [snap([fanout()]), snap([fanout()], NOW + 3)], undefined, undefined, { failIds: 1 })
  expect(writes).toEqual([])
  expect(logs.filter(l => l.text.includes('no session yet')).map(l => l.to)).toEqual(['debug'])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await band.find({ type: 'Text', text: /merge5/ }))?.text).toMatch(/^◯ merge5 /)
  expect(await band.find({ type: 'Text', text: /scanner failing/ })).toBeUndefined()
  await band.unmount()
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await shownName(pane)).toBe('merge5')
  expect(await pane.find({ type: 'Text', text: /scanner:/ })).toBeUndefined()
  await pane.unmount()
  await clock.advance(3000)
  expect(scans).toHaveLength(2)
  expect(spent(writes).map(w => [w.usd, w.updated_at])).toEqual([[6.36, NOW + 3]])
})

test('an environment variable that cannot be read breaks neither the scan, the band nor the pane, and the next scan writes the file', async ($, on) => {
  const { clock, writes, logs, scans } = await started($, on, [snap([fanout()]), snap([fanout()], NOW + 3)], undefined, undefined, { failEnv: 1 })
  expect(writes).toEqual([])
  expect(logs.filter(l => l.text.includes('env unreadable')).map(l => l.to)).toEqual(['debug'])
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await band.find({ type: 'Text', text: /merge5/ }))?.text).toMatch(/^◯ merge5 /)
  expect(await band.find({ type: 'Text', text: /scanner failing/ })).toBeUndefined()
  await band.unmount()
  const pane = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await shownName(pane)).toBe('merge5')
  expect(await pane.find({ type: 'Text', text: /scanner:/ })).toBeUndefined()
  await pane.unmount()
  await clock.advance(3000)
  expect(scans).toHaveLength(2)
  expect(spent(writes).map(w => [w.usd, w.updated_at])).toEqual([[6.36, NOW + 3]])
})

// A reload starts the module's variables over and keeps what $.state holds: the test has the spend
// record stored as the session starts, with fresh module variables.
test('after a reload the spend carries on from what was stored: the total does not drop, and a total already written is not written again', async ($, on) => {
  const stored: SpendRun[] = [
    { dir: '/w/clean/merge5', settled: 1, current: 2, running: true },
    { dir: '/w/gone', settled: 0, current: 0.5, running: false },
  ]
  const { clock, writes } = await started($, on, [snap([fanout({ cost_usd: 2 })]), snap([fanout({ cost_usd: 2.25 })], NOW + 3)], undefined, undefined, { spend: { runs: stored, written: 3.5 } })
  // the folder's earlier runs and the folder gone from the snapshot still count; 3.5 was written before the reload
  expect(writes).toEqual([])
  await clock.advance(3000)
  expect(spent(writes).map(w => [w.usd, w.runs, w.updated_at])).toEqual([[3.75, 2, NOW + 3]])
})

test('after a reload a run seen running before it is not taken for a new one', async ($, on) => {
  const stored: SpendRun[] = [{ dir: '/w/clean/merge5', settled: 0, current: 2, running: true }]
  const { writes } = await started($, on, [snap([fanout({ cost_usd: 2.5 })])], undefined, undefined, { spend: { runs: stored, written: 2 } })
  expect(spent(writes).map(w => w.usd)).toEqual([2.5])
})

test('a run unreadable in one scan does not count as a new run when it reads again', async ($, on) => {
  const unknown = { ...fanout({ cost_usd: 0 }), kind: 'unknown' as const, state: 'unknown' as const, agents: [], problems: ['cwd unreadable'] }
  const { clock, writes } = await started($, on, [snap([fanout({ cost_usd: 1 })]), snap([unknown], NOW + 3), snap([fanout({ cost_usd: 1.5 })], NOW + 6)])
  await clock.advance(3000)
  expect(spent(writes).map(w => w.usd)).toEqual([1])
  await clock.advance(3000)
  expect(spent(writes).map(w => w.usd)).toEqual([1, 1.5])
})

test('a run first seen unreadable adds nothing, and the cost it reads at later is not added to it', async ($, on) => {
  const unknown = { ...fanout({ cost_usd: 0.7 }), kind: 'unknown' as const, state: 'unknown' as const, agents: [], problems: ['cwd unreadable'] }
  const { clock, writes } = await started($, on, [snap([unknown]), snap([fanout({ cost_usd: 0.9 })], NOW + 15)])
  expect(writes).toEqual([])
  // nothing runs as far as the scan loop knows, so the next scan is 15 s on
  await clock.advance(15000)
  expect(spent(writes).map(w => [w.usd, w.runs])).toEqual([[0.9, 1]])
})

// ---------------- the view's words, unit by unit ----------------

test('model names, counts and durations read as the Workflow view writes them', async () => {
  expect([modelName('claude-opus-5-5'), modelName('claude-sonnet-5-5'), modelName('claude-haiku-5-5'), modelName('gpt-x')])
    .toEqual(['Opus 5.5', 'Sonnet 5.5', 'Haiku 5.5', 'gpt-x'])
  expect([count(812), count(1000), count(31600), count(1_234_567), count(2_500_000), count(null)]).toEqual(['812', '1.0k', '31.6k', '1.2m', '2.5m', null])
  expect([duration(6), duration(72), duration(1725), duration(3720), duration(183600), duration(null)]).toEqual(['6s', '1m12s', '28m45s', '1h02m', '2d03h', null])
})

test('agent stats carry the state where an agent did not simply run', async () => {
  expect(agentStats(agent({ state: 'died' }))).toBe('Opus 5.5 · xhigh · 31.6k tok · stopped')
  expect(agentStats(agent({ state: 'skipped', tokens: null }))).toBe('Opus 5.5 · xhigh · skipped')
  expect(agentStats(agent({ state: 'pending', tokens: null }))).toBe('Opus 5.5 · xhigh · queued')
  expect(agentStats(agent({ state: 'done', resumed: true, tokens: null }))).toBe('Opus 5.5 · xhigh · resumed')
  expect(agentStats(agent({ attempts: 2 }))).toBe('Opus 5.5 · xhigh · 31.6k tok · 2 attempts')
})

test('the header ends with the state of a run that is over', async () => {
  expect(headerStats(fanout())).toBe('1/3 agents · 7m09s · $6.36')
  expect(headerStats(fanout({ state: 'done' }))).toBe('1/3 agents · 7m09s · $6.36 · done')
  expect(headerStats(fanout({ state: 'failed', cost_usd: null }))).toBe('1/3 agents · 7m09s · failed')
  expect(headerStats(fanout({ state: 'died' }))).toBe('1/3 agents · 7m09s · $6.36 · stopped')
})

test('the phase column widens for a long title instead of cutting a short word', async () => {
  const ps = phases(fanout())
  expect(phaseCol(ps)).toBe(18)
  expect(phaseCell(ps[1]!, true, phaseCol(ps))).toEqual({ pointer: '❯', icon: '2', title: 'Denetle ', counts: '0/2' })
  expect(phaseCol(phases(fanout({ phases: ['A very long phase title indeed'], agents: [] })))).toBe(28)
})

test('the view never puts an unreadable fan-out in the band, nor announces one', async () => {
  const unknown = { ...fanout(), state: 'unknown' as const, ended_at: NOW - 5 }
  expect(bandFanouts(snap([unknown]), [{ dir: unknown.dir, endedAt: NOW - 5 }])).toEqual([])
  expect(finished(snap([fanout()]), snap([unknown]))).toEqual([])
})

test('the pane lists the running fan-outs in snapshot order, and the band\'s finished run where the snapshot has it', async () => {
  const old = fanout({ id: '/w/old', dir: '/w/old', name: 'old', state: 'done' })
  const a = fanout({ id: '/w/a', dir: '/w/a', name: 'a' })
  const b = fanout({ id: '/w/b', dir: '/w/b', name: 'b', state: 'failed' })
  const c = fanout({ id: '/w/c', dir: '/w/c', name: 'c' })
  const s = snap([old, a, b, c])
  const sel = (pinned: string | null): Selection => ({ dir: pinned, phase: null, agent: null, top: 0, pinned }) as Selection
  expect(V.paneFanouts(s, sel(null)).map(f => f.name)).toEqual(['a', 'c'])
  expect(V.paneFanouts(s, sel('/w/old')).map(f => f.name)).toEqual(['old', 'a', 'c'])
  expect(V.paneFanouts(s, sel('/w/b')).map(f => f.name)).toEqual(['a', 'b', 'c'])
  // a held folder no longer in the snapshot adds nothing
  expect(V.paneFanouts(s, sel('/w/gone')).map(f => f.name)).toEqual(['a', 'c'])
  expect(V.paneFanouts(null, sel(null))).toEqual([])
})

test('the pane holds the band\'s finished run only while the snapshot still shows its folder ended', async () => {
  const done = fanout({ id: '/w/b', dir: '/w/b', name: 'b', state: 'done' })
  const running = fanout({ id: '/w/b', dir: '/w/b', name: 'b' })
  const unknown = { ...fanout({ id: '/w/b', dir: '/w/b', name: 'b' }), state: 'unknown' as const }
  expect(V.heldPin('/w/b', snap([done]))).toBe('/w/b')
  expect(V.heldPin('/w/b', snap([unknown]))).toBe('/w/b')
  expect(V.heldPin('/w/b', snap([running]))).toBeNull()
  expect(V.heldPin('/w/b', snap([fanout()]))).toBeNull()
  expect(V.heldPin(null, snap([done]))).toBeNull()
})

test('the spend record keeps each folder\'s cost and adds a re-run to the run before it', async () => {
  const a = (over: Partial<Fanout>) => fanout({ id: '/w/a', dir: '/w/a', name: 'a', ...over })
  let runs = V.mergeSpend([], snap([a({ cost_usd: 2 })]))
  expect(runs).toEqual([{ dir: '/w/a', settled: 0, current: 2, running: true }])
  runs = V.mergeSpend(runs, snap([a({ cost_usd: 3, state: 'done' })]))
  expect(runs).toEqual([{ dir: '/w/a', settled: 0, current: 3, running: false }])
  // no cost reported, an unreadable entry, or the folder gone: the last cost stays
  runs = V.mergeSpend(runs, snap([a({ cost_usd: null, state: 'done' })]))
  runs = V.mergeSpend(runs, snap([a({ cost_usd: 0, state: 'unknown' })]))
  runs = V.mergeSpend(runs, snap([]))
  expect(runs).toEqual([{ dir: '/w/a', settled: 0, current: 3, running: false }])
  // running again: a new run, the old cost settled
  runs = V.mergeSpend(runs, snap([a({ cost_usd: 3.5 })]))
  expect(runs).toEqual([{ dir: '/w/a', settled: 3, current: 3.5, running: true }])
  // a lower cost while running: yet another run
  runs = V.mergeSpend(runs, snap([a({ cost_usd: 0.25 })]))
  expect(runs).toEqual([{ dir: '/w/a', settled: 6.5, current: 0.25, running: true }])
  // a new folder joins after the ones already kept
  runs = V.mergeSpend(runs, snap([fanout({ id: '/w/b', dir: '/w/b', name: 'b', cost_usd: null })]))
  expect(runs.map(r => r.dir)).toEqual(['/w/a', '/w/b'])
  expect(V.spendTotal(runs)).toEqual({ usd: 6.75, runs: 1 })
  // a folder whose latest run has no cost yet still counts, for the runs before it
  expect(V.spendTotal([{ dir: '/w/a', settled: 1, current: 0, running: true }])).toEqual({ usd: 1, runs: 1 })
})

test('the spend total is rounded to four decimals', async () => {
  const runs: SpendRun[] = [
    { dir: '/w/a', settled: 0.1, current: 0.2, running: false },
    { dir: '/w/b', settled: 0, current: 0.123456, running: true },
  ]
  expect(V.spendTotal(runs)).toEqual({ usd: 0.4235, runs: 2 })
  expect(V.spendTotal([])).toEqual({ usd: 0, runs: 0 })
})

test('the spend file\'s path: AGENTING_STATE_DIR, else HOME/.claude, named by a plain session id', async () => {
  expect(V.spendPath({ stateDir: '/state', home: '/home/me' }, 'sess-1')).toBe('/state/.agenting-fanout-cost/sess-1.json')
  expect(V.spendPath({ stateDir: null, home: '/home/me' }, 'a_B-9')).toBe('/home/me/.claude/.agenting-fanout-cost/a_B-9.json')
  expect(V.spendPath({ stateDir: '', home: '/home/me' }, 'x')).toBe('/home/me/.claude/.agenting-fanout-cost/x.json')
  for (const bad of ['', '../x', 'a/b', 'a b', 'a.b', 'ş']) {
    expect(V.spendPath({ stateDir: '/state', home: '/home/me' }, bad)).toBeNull()
  }
  expect(V.spendPath({ stateDir: null, home: null }, 'x')).toBeNull()
})

// keep a typed reference to the mount type the kit hands back
export type PaneMount = Mounted<'terminal', 'Pane'>
