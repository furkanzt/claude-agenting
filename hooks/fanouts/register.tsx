// The agenting plugin's fan-out view: shows clean-run fan-outs (cleanrun.py, clean_runtime.mjs) the way Claude Code
// shows a Workflow: a row like the bottom panel's above the prompt, and a /fanouts pane laid out
// like /workflows (phases on the left, the chosen phase's agents on the right; ↑↓ select, esc
// close). The look is copied in look.ts; the data comes from scripts/fanout_scan.py.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, Timer } from 'claude-code'

import type { Fanout, FanoutAgent, Selection } from '../../types'
import { GLYPHS, LOOK_FROM, SEP, WORDS, agentTone, barGlyphs, isGhostty, runTone } from './look'
import type { Phase } from './view'
import {
  BAND_MAX,
  PAGE,
  agentLine,
  announce,
  bandFanouts,
  bandStats,
  barCells,
  carryUnknown,
  description,
  finished,
  fit,
  frameBottom,
  frameTop,
  headerStats,
  isLive,
  labelWidth,
  mergeKnown,
  parseSnapshot,
  phaseCell,
  phaseCol,
  phaseState,
  pageTop,
  pager,
  pick,
  sharedEffort,
} from './view'

const PLUGIN = 'agenting'
const PANE = 'fanouts'
const COMMAND = 'fanouts'
const FAST_MS = 3000
const SLOW_MS = 15000
const SCAN_TIMEOUT_MS = 20000

// Change a tag when that value's fields change: it declines what an earlier version stored.
const snapshot = atom({ plugin: 'agenting', key: 'snapshot' } as const, null, { shape: 'snapshot-3' })
const known = atom({ plugin: 'agenting', key: 'known' } as const, [], { shape: 'known-3' })
const selection = atom({ plugin: 'agenting', key: 'selection' } as const, { dir: null, phase: null, agent: null, top: 0 }, { shape: 'selection-2' })
const scanError = atom({ plugin: 'agenting', key: 'scanError' } as const, null)

type Ui = ReturnType<EngineInterface['ui']['resolve']>

// Module variables start over on a reload; the atoms above stay.
const live: {
  timer: Timer | undefined
  busy: boolean
  cwds: Record<string, string>
  version: string | null
  ghostty: boolean
} = { timer: undefined, busy: false, cwds: {}, version: null, ghostty: false }

// One scanner run: the snapshot into state, a toast for each fan-out that just ended. A snapshot
// that could not read the process table is a failed scan: it would make every run look ended.
async function scan($: EngineInterface): Promise<boolean> {
  const dirs = (await read($, known)).map(k => k.dir)
  const argv = ['python3', '-I', `${$.plugin.root}/scripts/fanout_scan.py`]
  for (const d of dirs) argv.push('--dir', d)
  for (const [pid, cwd] of Object.entries(live.cwds)) argv.push('--cwd', `${pid}=${cwd}`)
  const ran = await $.process.run(argv, { timeoutMs: SCAN_TIMEOUT_MS })
  if (ran.exitCode !== 0) {
    throw new Error(`fanout_scan.py exited ${ran.exitCode}: ${ran.stderr.slice(-300)}`)
  }
  const next = parseSnapshot(ran.stdout)
  if (next.degraded) {
    throw new Error(`fanout_scan.py could not read the process table: ${next.problems.join('; ').slice(0, 200)}`)
  }
  live.cwds = next.cwds
  const prev = await read($, snapshot)
  const shown = { ...carryUnknown(prev, next), cwds: {} }
  for (const f of finished(prev, shown)) $.ui.toast(announce(f))
  await update($, known, list => mergeKnown(list, shown))
  await update($, snapshot, () => shown)
  await update($, scanError, () => null)
  return shown.fanouts.some(isLive)
}

// Scan, then again in FAST_MS while anything runs, else in SLOW_MS. Never rejects: it runs
// from a timer, and after an unload every $ call refuses, which ends the loop quietly.
async function tick($: EngineInterface): Promise<void> {
  if (live.busy) return
  live.busy = true
  let running = false
  try {
    running = await scan($)
  } catch (err) {
    const text = err instanceof Error ? err.message : String(err)
    try {
      await update($, scanError, () => text.slice(0, 300))
      $.ui.log(`${PLUGIN}: ${text}`, { to: 'debug' })
      running = ((await read($, snapshot))?.fanouts ?? []).some(isLive)
    } catch {
      live.busy = false
      return
    }
  } finally {
    live.busy = false
  }
  try {
    live.timer?.cancel()
    live.timer = $.clock.after(running ? FAST_MS : SLOW_MS, () => void tick($))
  } catch {
    // unloaded: no next scan
  }
}

// The pane takes the keyboard (↑↓ move between phases) and Escape closes it.
async function openPane($: EngineInterface) {
  return $.ui.open({ id: PANE, title: WORDS.heading, focus: true, closeOnEscape: true })
}

// A band row pressed (ctrl+x tab, then enter; or a click): the pane, on that fan-out.
async function openOn($: EngineInterface, dir: string) {
  await update($, selection, () => ({ dir, phase: null, agent: null, top: 0 }))
  await openPane($)
}

// A fan-out tab, a phase row or an agent row got the focus ring or a press: show it. On an agent
// row the page scrolls so the row past it stays on screen, as /workflows scrolls.
async function choose($: EngineInterface, key: string) {
  const list = (await read($, snapshot))?.fanouts ?? []
  const sel: Selection = await read($, selection)
  if (key.startsWith('fanout:')) {
    const f = list[Number(key.slice(7))]
    if (f) await update($, selection, () => ({ dir: f.dir, phase: null, agent: null, top: 0 }))
    return
  }
  const { fanout, phase, phases } = pick(list, sel)
  if (!fanout) return
  if (key.startsWith('phase:')) {
    const p = phases[Number(key.slice(6)) - 1]
    if (p) await update($, selection, () => ({ dir: fanout.dir, phase: p.title, agent: null, top: 0 }))
    return
  }
  if (key.startsWith('agent:') && phase) {
    const i = Number(key.slice(6))
    const sameView = sel.dir === fanout.dir && sel.phase === phase.title
    const top = pageTop(i, sameView ? sel.top : 0, phase.agents.length)
    await update($, selection, () => ({ dir: fanout.dir, phase: phase.title, agent: i, top }))
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    // immediate: /fanouts typed while a turn is in flight runs at once, as /rename does; its hook
    // only opens or closes the pane and asks for a scan, so it needs nothing from the turn
    await $.command.register({
      name: COMMAND,
      description: 'Show or hide clean-run fan-outs (cleanrun.py, clean_runtime.mjs) laid out like /workflows',
      immediate: true,
    })
    try {
      live.version = (await $.session.version()).version
      live.ghostty = isGhostty({
        term: (await $.env.get('TERM')) ?? null,
        termProgram: (await $.env.get('TERM_PROGRAM')) ?? null,
      })
    } catch {
      // the version note stays off
    }
    live.timer?.cancel()
    void tick($)
    return started
  })

  // /fanouts opens the pane, or closes it when it is open.
  on('command.run', { command: COMMAND }, async $ => {
    if ((await $.ui.panes()).some(p => p.id === PANE)) {
      await $.ui.close({ id: PANE })
      return { text: `${WORDS.heading} pane closed.` }
    }
    const opened = await openPane($)
    void tick($)
    return { text: opened.isPlaced ? `${WORDS.heading} pane opened (esc closes it).` : `${WORDS.heading} pane: ${opened.reason}` }
  }).catch(() => ({ text: `${WORDS.heading}: the pane could not be opened.` }))

  // ↑↓ move the focus ring between phase rows: the one it lands on is shown. Never blocks a move.
  on('ui.focus', { component: 'Pane', requestId: PANE }, async ($, e, next) => {
    const moved = await next(e)
    if (!moved.deny && e.element) await choose($, e.element)
    return moved
  }).catch(($, e, next) => next(e))

  // The band: one row per running (or just ended) fan-out, as the bottom panel draws a Workflow.
// Each row is a plain Button, so the keyboard reaches the pane without /fanouts: ctrl+x tab, enter.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const snap = await read($, snapshot)
    const shown = bandFanouts(snap, await read($, known))
    if (!snap || shown.length === 0) return next(e)
    const failing = await read($, scanError)
    const ui = $.ui.resolve(e)
    const { Box, Button, Text } = ui
    const fits = shown.length <= Math.min(BAND_MAX, e.props.maxRows)
    const lines = fits ? shown : shown.slice(0, Math.max(0, Math.min(BAND_MAX, e.props.maxRows - 1)))
    const more = shown.length - lines.length
    return (
      <Box flexDirection="column">
        {lines.map((f, i) => (
          // a plain Button draws just the row; ctrl+x tab gives the band the keyboard with the ring
          // on the first row (autoFocus), so enter opens the pane on it
          <Button key={`open:${i}`} plain autoFocus={i === 0 ? true : undefined} onPress={() => openOn($, f.dir)}>
            {panelRow(ui, f, failing !== null && i === lines.length - 1)}
          </Button>
        ))}
        {more > 0 && (
          <Text dimColor wrap="truncate-end">
            {'  '}
            {WORDS.more(more)} {WORDS.kindPlural}
            {SEP}/{COMMAND}
          </Text>
        )}
      </Box>
    )
  })

  // The pane: the /workflows view of one fan-out.
  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const ui = $.ui.resolve(e)
    const { Box, Button, Text } = ui
    const snap = await read($, snapshot)
    const sel = await read($, selection)
    const failure = await read($, scanError)
    const list = snap?.fanouts ?? []
    const platform = snap?.platform ?? ''
    const width = Math.max(40, e.props.bodyColumns - 2)
    const { fanout: f, phase, phases } = pick(list, sel)
    const col = phaseCol(phases)
    const right = width - col - 3
    // for the person, not the maintainer: the layout may differ a little from this version's own
    const versionNote = live.version && live.version !== LOOK_FROM
      ? `layout copied from Claude Code ${LOOK_FROM}; running ${live.version}`
      : null
    return (
      <Box flexDirection="column" paddingLeft={1}>
        {list.length > 1 && (
          <Box gap={2} marginBottom={1}>
            {list.map((x, i) => {
              const tone = runTone(x.state)
              return (
                <Button key={`fanout:${i}`} plain onPress={() => choose($, `fanout:${i}`)}>
                  <Text color={tone.color} dimColor={tone.dim}>{tone.icon}</Text>{' '}
                  <Text color={x === f ? 'permission' : undefined} dimColor={x !== f}>{x.name}</Text>
                </Button>
              )
            })}
          </Box>
        )}
        {f === null ? (
          <Text dimColor>{WORDS.none}</Text>
        ) : (
          <Box flexDirection="column">
            <Text bold color="permission" wrap="truncate-end">{f.name}</Text>
            <Box width={width}>
              <Box flexGrow={1} flexShrink={1}>
                <Text dimColor wrap="truncate-end">{description(f)}</Text>
              </Box>
              <Box flexShrink={0}>
                <Text dimColor> {headerStats(f)}</Text>
              </Box>
            </Box>
            {f.problems[0] && (
              <Text color="warning" wrap="truncate-end">
                {GLYPHS.warning} {f.problems[0]}
              </Text>
            )}
            <Box flexDirection="column" marginTop={1}>
              <Text color="text">{frameTop(right, phase ? columnTitle(phase) : WORDS.phases, col)}</Text>
              {frameRows(ui, $, phases, phase, sel, f, right, col, platform)}
              <Text color="text">{frameBottom(right, col, phase ? pager(viewTop(sel, f, phase), phase.agents.length) : null)}</Text>
            </Box>
          </Box>
        )}
        {failure && (
          <Text color="warning" wrap="truncate-end">
            {GLYPHS.warning} scanner: {failure}
          </Text>
        )}
        <Text dimColor wrap="truncate-end">{WORDS.hint}</Text>
        {versionNote && <Text dimColor wrap="truncate-end">{versionNote}</Text>}
      </Box>
    )
  })
}

// The bottom-panel row: "  ◯ count-long  ████████░░░░░░░░░░░░  2/5 · 23s · ↓ 132.2k tokens · clean fan-out".
function panelRow(ui: Ui, f: Fanout, stale: boolean) {
  const { Text } = ui
  const tone = runTone(f.state)
  const cells = barCells(f)
  const bar = barGlyphs(live.ghostty)
  return (
    <Text wrap="truncate-end">
      {'  '}
      <Text color={tone.color} dimColor={tone.dim}>{tone.icon}</Text>
      <Text dimColor> {f.name}</Text>
      {'  '}
      <Text>{bar.full.repeat(cells.full)}</Text>
      <Text dimColor>{bar.empty.repeat(cells.empty)}</Text>
      {'  '}
      <Text dimColor>{bandStats(f)}</Text>
      {stale && <Text color="warning">{`${SEP}${GLYPHS.warning} scanner failing`}</Text>}
    </Text>
  )
}

// The agent column's title, as /workflows writes it ("Generate · 14 agents"), with the effort the
// phase's agents share when they share one.
function columnTitle(phase: Phase): string {
  const n = phase.agents.length
  const effort = sharedEffort(phase.agents)
  return `${phase.title}${SEP}${n} ${n === 1 ? 'agent' : 'agents'}${effort ? `${SEP}${effort}` : ''}`
}

// The page's first row and the focused agent, for the fan-out and phase on screen only.
function viewTop(sel: Selection, f: Fanout, phase: Phase): number {
  const same = sel.dir === f.dir && sel.phase === phase.title
  return same ? Math.max(0, Math.min(sel.top, Math.max(0, phase.agents.length - PAGE))) : 0
}

function viewAgent(sel: Selection, f: Fanout, phase: Phase): number | null {
  return sel.dir === f.dir && sel.phase === phase.title ? sel.agent : null
}

// The two columns between the frame lines, each its own Box, so the focus ring meets every phase
// row before any agent row: ↑↓ walk the phases, then go on into the agents, as in /workflows.
// "│ ❯ 1 One    1/2 │ ❯⏺ one-a        Opus 5.5 · xhigh · 31.6k tok      12s │"
function frameRows(
  ui: Ui,
  $: EngineInterface,
  phases: Phase[],
  phase: Phase | null,
  sel: Selection,
  f: Fanout,
  right: number,
  col: number,
  platform: string,
) {
  const { Box, Text } = ui
  const v = GLYPHS.frame.v
  const top = phase ? viewTop(sel, f, phase) : 0
  const focused = phase ? viewAgent(sel, f, phase) : null
  const agents = phase ? phase.agents.slice(top, top + PAGE) : []
  const n = Math.max(phases.length, agents.length, 1)
  const lw = labelWidth(phase ? phase.agents : [])
  const withEffort = phase ? sharedEffort(phase.agents) === null : true
  const column = (cell: string) => <Text color="text">{Array.from({ length: n }, () => cell).join('\n')}</Text>
  return (
    <Box>
      {column(`${v} `)}
      <Box flexDirection="column" width={col - 2} flexShrink={0}>
        {Array.from({ length: n }, (_, i) => {
          const p = phases[i]
          return p ? phaseButton(ui, $, p, p === phase, col) : <Text> </Text>
        })}
      </Box>
      {column(` ${v} `)}
      <Box flexDirection="column" width={right - 2} flexShrink={0}>
        {agents.length === 0 ? (
          <Text dimColor>{WORDS.notStarted}</Text>
        ) : (
          agents.map((a, k) => agentButton(ui, $, a, top + k, top + k === focused, lw, right - 2, platform, withEffort))
        )}
        {Array.from({ length: n - Math.max(agents.length, 1) }, () => (
          <Text> </Text>
        ))}
      </Box>
      {column(` ${v}`)}
    </Box>
  )
}

// A phase row, a Button so ↑↓ reach it: the selected one in 'permission', a done one ✔ success,
// one still open its number in 'subtle', one not started dim.
function phaseButton(ui: Ui, $: EngineInterface, p: Phase, selected: boolean, col: number) {
  const { Button, Text } = ui
  const cell = phaseCell(p, selected, col)
  const state = phaseState(p)
  const iconColor = selected ? 'permission' : state === 'done' ? 'success' : state === 'failed' ? 'error' : 'subtle'
  return (
    <Button key={`phase:${p.index}`} plain autoFocus={selected ? true : undefined} onPress={() => choose($, `phase:${p.index}`)}>
      <Text color={iconColor}>{`${cell.pointer} ${cell.icon}`}</Text>{' '}
      <Text color={selected ? 'permission' : undefined} dimColor={!selected && state === 'idle'}>{cell.title}</Text>
      {cell.counts ? ' ' : ''}
      <Text color={selected ? 'permission' : 'subtle'}>{cell.counts}</Text>
    </Button>
  )
}

// An agent row, a plain Button so the focus ring reaches it: "❯✔ label  Opus 5.5 · 31.6k tok  12s",
// laid out to its column's width (a Button holds Text only). A running row is dim; the focused one
// is in 'permission', as /workflows draws its selected row.
function agentButton(
  ui: Ui,
  $: EngineInterface,
  a: FanoutAgent,
  index: number,
  selected: boolean,
  lw: number,
  width: number,
  platform: string,
  withEffort: boolean,
) {
  const { Button, Text } = ui
  const tone = agentTone(a.state, platform)
  const line = agentLine(a, lw, width, selected, withEffort)
  const running = a.state === 'running'
  return (
    <Button key={`agent:${index}`} plain onPress={() => choose($, `agent:${index}`)}>
      <Text color="permission">{line.pointer}</Text>
      <Text color={tone.color} dimColor={tone.dim}>{tone.icon}</Text>{' '}
      <Text color={selected ? 'permission' : undefined} dimColor={!selected && running}>{line.label}</Text>
      <Text color={selected ? 'permission' : undefined} dimColor={!selected}>{line.stats}</Text>
      <Text color="error">{line.error}</Text>
      {line.pad}
      <Text dimColor>{line.time}</Text>
    </Button>
  )
}
