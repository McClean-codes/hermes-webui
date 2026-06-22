"""Behavioural test for the #4650 reasoning-chip request-storm fix.

`syncTopbar()` calls `syncReasoningChip()` on every routine UI refresh, and
during streaming those fire at high frequency. Commit a9ce2889 made
`syncReasoningChip()` refetch `GET /api/reasoning` unconditionally, so ordinary
syncs became a network storm (one request per token -> ~2 tok/s).

The fix restores the pre-a9ce2889 cache short-circuit while keeping that
commit's intent (refresh supported-efforts after a model switch): fetch only
when nothing is cached yet OR the model/provider identity changed since the
last fetch. This test drives the ACTUAL functions from static/ui.js via node
and counts network calls, so the storm cannot silently come back.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.resolve()
UI_JS_PATH = REPO_ROOT / "static" / "ui.js"

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not on PATH")


_DRIVER_SRC = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');

function makeEl() {
  return {
    style: {}, dataset: {}, title: '', textContent: '', value: '',
    classList: { add(){}, remove(){}, toggle(){}, contains(){return false} },
    querySelectorAll(){return []}, querySelector(){return null},
    getBoundingClientRect(){return {left:0,top:0,width:0,height:0}},
  };
}

const els = {
  composerReasoningWrap: makeEl(),
  composerReasoningLabel: makeEl(),
  composerReasoningChip: makeEl(),
  composerReasoningDropdown: makeEl(),
  modelSelect: makeEl(),
};

// Mutable app state the reasoning helpers read from.
global.S = { session: { model: 'gpt-5', model_provider: 'openai' } };
global.window = {};
global.document = { createElement: makeEl, addEventListener(){}, querySelectorAll(){return []}, querySelector(){return null} };
global.$ = id => els[id] || null;

// Count every network call and remember the URL it hit.
let CALLS = [];
global.api = (url) => { CALLS.push(url); return { then: () => ({ catch: () => {} }), catch: () => {} }; };

// Helpers the reasoning code calls.
global._modelStateForSelect = () => ({ model: '', model_provider: null });
global._highlightReasoningOption = () => {};
global._applyReasoningOptions = () => {};

function extractFunc(name) {
  const re = new RegExp('function\\s+' + name + '\\s*\\(');
  const start = src.search(re);
  if (start < 0) throw new Error(name + ' not found');
  let i = src.indexOf('{', start); let depth = 1; i++;
  while (depth > 0 && i < src.length) {
    if (src[i] === '{') depth++; else if (src[i] === '}') depth--; i++;
  }
  return src.slice(start, i);
}

// `let _currentReasoningEffort` / `_currentReasoningEffortsSupported` /
// `_lastReasoningFetchKey` are module-scope state the functions close over;
// declare them in this eval scope so the extracted functions can see them.
var _currentReasoningEffort = null;
var _currentReasoningEffortsSupported = null;
var _lastReasoningFetchKey = null;

eval(extractFunc('_normalizeReasoningEffort'));
eval(extractFunc('_formatReasoningEffortLabel'));
eval(extractFunc('_reasoningEffortContext'));
eval(extractFunc('_reasoningEffortQuery'));
eval(extractFunc('_applyReasoningChip'));
eval(extractFunc('fetchReasoningChip'));
eval(extractFunc('syncReasoningChip'));

// ── Scenario ───────────────────────────────────────────────────────────────
const result = {};

// 1. First sync with nothing cached -> must fetch.
syncReasoningChip();
result.after_first_sync = CALLS.length;

// Simulate the fetch resolving (what _applyReasoningChip does on response).
_applyReasoningChip('high', { supported_efforts: ['low','high'] });

// 2. Ten routine syncs with the SAME model (the streaming storm) -> no new fetch.
for (let i = 0; i < 10; i++) syncReasoningChip();
result.after_ten_same_model_syncs = CALLS.length;

// 3. Model switch -> exactly one more fetch.
global.S.session.model = 'claude-opus-4';
global.S.session.model_provider = 'anthropic';
syncReasoningChip();
result.after_model_switch = CALLS.length;

// 4. More routine syncs on the new model -> still no new fetch.
_applyReasoningChip('low', { supported_efforts: ['low','high'] });
for (let i = 0; i < 5; i++) syncReasoningChip();
result.after_new_model_syncs = CALLS.length;

result.calls = CALLS;
process.stdout.write(JSON.stringify(result));
"""


@pytest.fixture(scope="module")
def driver_path(tmp_path_factory):
    p = tmp_path_factory.mktemp("reasoning_storm_driver") / "driver.js"
    p.write_text(_DRIVER_SRC, encoding="utf-8")
    return str(p)


@pytest.fixture(scope="module")
def outcome(driver_path):
    result = subprocess.run(
        [NODE, driver_path, str(UI_JS_PATH)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"node driver failed: {result.stderr}")
    return json.loads(result.stdout)


def test_first_sync_fetches_once(outcome):
    assert outcome["after_first_sync"] == 1, (
        f"first sync (cold cache) must fetch exactly once: {outcome['calls']}"
    )


def test_repeated_syncs_same_model_do_not_refetch(outcome):
    """The core #4650 regression: 10 routine syncs on the same model must NOT
    issue 10 network calls — that was the per-token request storm."""
    assert outcome["after_ten_same_model_syncs"] == 1, (
        "routine topbar syncs on an unchanged model must serve the cache, not "
        f"refetch — request storm regression: {outcome['calls']}"
    )


def test_model_switch_triggers_one_refetch(outcome):
    """a9ce2889's intent must survive: switching models refreshes the chip's
    supported-efforts, so exactly one fetch fires on the switch."""
    assert outcome["after_model_switch"] == 2, (
        f"a model switch must trigger exactly one refetch: {outcome['calls']}"
    )


def test_syncs_after_switch_do_not_refetch(outcome):
    assert outcome["after_new_model_syncs"] == 2, (
        "routine syncs after a model switch must serve the cache again: "
        f"{outcome['calls']}"
    )
