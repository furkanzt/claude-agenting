// Tests for the fan-out view (hooks/fanouts/): run with `python3 scripts/quality/run_plugin_tests.py`, which
// copies the plugin's own files to a temp folder first (plain `claude plugin test .` would also run evals/private/).
import { expect, mock, test } from 'claude-code/testing'
import type { Mounted, TestBody } from 'claude-code/testing'
import type { On } from 'claude-code'

import type { Fanout, FanoutAgent, Snapshot } from '../types'
import { agentStats, bandFanouts, finished, headerStats, phaseCell, phaseCol, phases } from '../hooks/fanouts/view'
import { count, duration, modelName } from '../hooks/fanouts/look'

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

// The engine around the plugin, answering each scan with the next snapshot (the last repeats).
function engine(on: On, answers: Array<Snapshot | 'fail'>, version = '2.1.317', during?: (scan: number) => Promise<void>, env: Record<string, string> = {}) {
  const scans: string[][] = []
  const toasts: string[] = []
  const opened: Array<Record<string, unknown>> = []
  const registered: Array<Record<string, unknown>> = []
  const closed: string[] = []
  let panes: Array<{ id: string; title: string; isShown: boolean; isFocused: boolean; isPlaced: boolean }> = []
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('command.register', (_, e) => {
    registered.push({ ...e })
    return { value: { command: 'fanouts' } }
  })
  on('session.version', () => ({ value: { version } }))
  on('env.get', (_, e) => ({ value: env[e.name] }))
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.log', () => ({ value: undefined }))
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
  return { scans, toasts, opened, closed, registered }
}

async function started($: Engine, on: On, answers: Array<Snapshot | 'fail'>, version?: string, env?: Record<string, string>) {
  const clock = mock.clock(on, { now: NOW * 1000 })
  const eng = engine(on, answers, version, undefined, env)
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
  const other = fanout({ id: '/w/b', dir: '/w/b', name: 'other', state: 'done', alive: false, pid: null, ended_at: NOW - 5 })
  await started($, on, [snap([fanout(), other])])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.findAll({ type: 'Button', text: /merge5|other/ })).map(b => b.text)).toEqual(['◯ merge5', '◯ other'])
  await ui.press({ key: 'fanout:1' })
  expect((await ui.find({ type: 'Text', text: /^other$/ }))?.props.color).toBe('permission')
  expect((await ui.find({ type: 'Text', text: /agents · / }))?.text).toContain('· done')
  await ui.unmount()
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
  const f = fanout({ state: 'died', alive: false, problems: ['no process, and the last run never finished', 'a second problem'] })
  await started($, on, [snap([f])])
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
  expect((await ui.find({ type: 'Text', text: /No clean fan-outs/ }))?.text).toMatch(/^No clean fan-outs yet\./)
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

// keep a typed reference to the mount type the kit hands back
export type PaneMount = Mounted<'terminal', 'Pane'>
