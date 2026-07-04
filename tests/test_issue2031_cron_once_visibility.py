"""Regression coverage for #2031 one-shot cron schedule visibility."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
PANELS_JS = ROOT / "static" / "panels.js"
STYLE_CSS = ROOT / "static" / "style.css"
I18N_JS = ROOT / "static" / "i18n.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node not on PATH")


def _cron_schedule_source() -> str:
    src = PANELS_JS.read_text(encoding="utf-8")
    start = src.find("function _cronScheduleKindForInput")
    if start < 0:
        pytest.fail("_cronScheduleKindForInput is missing")
    end = src.find("function _hasUnlimitedRepeat", start)
    if end < 0:
        pytest.fail("_cronScheduleKindForInput must stay near the cron schedule helpers")
    return src[start:end]


def _cron_schedule_save_source() -> str:
    src = PANELS_JS.read_text(encoding="utf-8")
    start = src.find("async function saveCronForm()")
    if start < 0:
        pytest.fail("saveCronForm is missing")
    end = src.find("// Back-compat aliases for any stale callers", start)
    if end < 0:
        pytest.fail("saveCronForm boundary marker is missing")
    return src[start:end]


def _run_node(script: str) -> str:
    proc = subprocess.run(
        [NODE, "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def test_cron_schedule_input_classifier_flags_agent_one_shot_forms():
    script = _cron_schedule_source() + r"""
const cases = {
  "30m": _cronScheduleKindForInput("30m"),
  "2h": _cronScheduleKindForInput("2h"),
  "1 day": _cronScheduleKindForInput("1 day"),
  "2026-05-11": _cronScheduleKindForInput("2026-05-11"),
  "2026-05-11T08:00": _cronScheduleKindForInput("2026-05-11T08:00"),
  "every 30m": _cronScheduleKindForInput("every 30m"),
  "Every 2h": _cronScheduleKindForInput("Every 2h"),
  "0 9 * * *": _cronScheduleKindForInput("0 9 * * *"),
  "not_a_schedule": _cronScheduleKindForInput("not_a_schedule"),
};
console.log(JSON.stringify(cases));
"""
    kinds = json.loads(_run_node(script))

    assert kinds["30m"] == "once"
    assert kinds["2h"] == "once"
    assert kinds["1 day"] == "once"
    assert kinds["2026-05-11"] == "once"
    assert kinds["2026-05-11T08:00"] == "once"
    assert kinds["every 30m"] == "interval"
    assert kinds["Every 2h"] == "interval"
    assert kinds["0 9 * * *"] == "cron"
    assert kinds["not_a_schedule"] == ""


def test_cron_schedule_preset_matching():
    script = _cron_schedule_source() + r"""
const cases = {
  hourly: _cronSchedulePresetIdForValue("every 1h"),
  hourlyCron: _cronSchedulePresetIdForValue("15 * * * *"),
  daily: _cronSchedulePresetIdForValue("30 7 * * *"),
  weekdays: _cronSchedulePresetIdForValue("5 22 * * 1-5"),
  weekly: _cronSchedulePresetIdForValue("45 8 * * 3"),
  monthly: _cronSchedulePresetIdForValue("10 6 15 * *"),
  empty: _cronSchedulePresetIdForValue(""),
  trimMatch: _cronSchedulePresetIdForValue("  30 7 * * *  "),
  custom: _cronSchedulePresetIdForValue("0 9 * * * 0"),
  shorthand: _cronSchedulePresetIdForValue("@daily"),
  invalidDaily: _cronSchedulePresetIdForValue("99 99 * * *"),
  invalidHourly: _cronSchedulePresetIdForValue("60 * * * *"),
  ambiguousSunday: _cronSchedulePresetIdForValue("0 9 * * 7"),
  invalidWeekly: _cronSchedulePresetIdForValue("0 9 * * 8"),
  invalidMonthDayZero: _cronSchedulePresetIdForValue("0 9 0 * *"),
  invalidMonthly: _cronSchedulePresetIdForValue("0 9 32 * *"),
};
console.log(JSON.stringify(cases));
"""
    cases = json.loads(_run_node(script))

    assert cases["hourly"] == "hourly"
    assert cases["hourlyCron"] == "hourly"
    assert cases["daily"] == "daily"
    assert cases["weekdays"] == "weekdays"
    assert cases["weekly"] == "weekly"
    assert cases["monthly"] == "monthly"
    assert cases["empty"] == "custom"
    assert cases["trimMatch"] == "daily"
    assert cases["custom"] == "custom"
    assert cases["shorthand"] == "custom"
    assert cases["invalidDaily"] == "custom"
    assert cases["invalidHourly"] == "custom"
    assert cases["ambiguousSunday"] == "weekly"
    assert cases["invalidWeekly"] == "custom"
    assert cases["invalidMonthDayZero"] == "custom"
    assert cases["invalidMonthly"] == "custom"


def test_cron_schedule_preset_controls_sync_raw_and_preset_paths():
    script = _cron_schedule_source() + r"""
const elements = {};
function $(id) { return elements[id]; }
function makeElement(initialValue = '') {
  return {
    value: initialValue,
    style: { display: '' },
    listeners: {},
    addEventListener(type, handler) {
      (this.listeners[type] || (this.listeners[type] = [])).push(handler);
    },
    dispatchEvent(eventType) {
      const handlers = this.listeners[eventType] || [];
      for (const handler of handlers) handler({ type: eventType, target: this });
    },
  };
}
function t(key) {
  const dict = {
    cron_schedule_preset_label: 'Preset',
    cron_schedule_preset_hourly: 'Hourly',
    cron_schedule_preset_daily: 'Daily',
    cron_schedule_preset_weekdays: 'Weekdays',
    cron_schedule_preset_weekly: 'Weekly',
    cron_schedule_preset_monthly: 'Monthly',
    cron_schedule_preset_custom: 'Custom',
  };
  return dict[key];
}
function esc(value) { return value == null ? '' : String(value); }

[
  'cronFormSchedule',
  'cronFormSchedulePreset',
  'cronFormSchedulePresetParams',
  'cronFormScheduleHourField',
  'cronFormScheduleMinuteField',
  'cronFormScheduleWeekdayField',
  'cronFormScheduleMonthDayField',
  'cronFormScheduleHour',
  'cronFormScheduleMinute',
  'cronFormScheduleWeekday',
  'cronFormScheduleMonthDay',
].forEach((id) => {
  elements[id] = makeElement();
});
elements.cronFormScheduleOnceWarning = { style: { display: 'none' } };
elements.cronFormSchedulePresetParams.style.display = 'none';

_initCronSchedulePresetControls();

function snapshot() {
  return {
    preset: elements.cronFormSchedulePreset.value,
    schedule: elements.cronFormSchedule.value,
    paramsDisplay: elements.cronFormSchedulePresetParams.style.display,
    hourFieldDisplay: elements.cronFormScheduleHourField.style.display,
    minuteFieldDisplay: elements.cronFormScheduleMinuteField.style.display,
    weekdayFieldDisplay: elements.cronFormScheduleWeekdayField.style.display,
    monthDayFieldDisplay: elements.cronFormScheduleMonthDayField.style.display,
    hour: elements.cronFormScheduleHour.value,
    minute: elements.cronFormScheduleMinute.value,
    weekday: elements.cronFormScheduleWeekday.value,
    monthDay: elements.cronFormScheduleMonthDay.value,
    warning: elements.cronFormScheduleOnceWarning.style.display,
    kind: _cronScheduleKindForInput(elements.cronFormSchedule.value),
  };
}

elements.cronFormSchedule.value = '15 * * * *';
elements.cronFormSchedule.dispatchEvent('input');
const hourlySync = snapshot();

elements.cronFormSchedulePreset.value = 'hourly';
elements.cronFormSchedulePreset.dispatchEvent('change');
elements.cronFormScheduleMinute.value = '15';
elements.cronFormScheduleMinute.dispatchEvent('change');
const hourlyWrite = snapshot();

elements.cronFormSchedule.value = '30 7 * * *';
elements.cronFormSchedule.dispatchEvent('input');
const dailySync = snapshot();
elements.cronFormScheduleHour.value = '7';
elements.cronFormScheduleHour.dispatchEvent('change');
elements.cronFormScheduleMinute.value = '30';
elements.cronFormScheduleMinute.dispatchEvent('change');
const dailyWrite = snapshot();

elements.cronFormSchedule.value = '5 22 * * 1-5';
elements.cronFormSchedule.dispatchEvent('input');
const weekdaysSync = snapshot();

elements.cronFormSchedule.value = '45 8 * * 3';
elements.cronFormSchedule.dispatchEvent('input');
const weeklySync = snapshot();
elements.cronFormSchedule.value = '0 9 * * 7';
elements.cronFormSchedule.dispatchEvent('input');
const weeklyRawSundaySync = snapshot();
elements.cronFormScheduleWeekday.value = '3';
elements.cronFormScheduleWeekday.dispatchEvent('change');
elements.cronFormScheduleHour.value = '8';
elements.cronFormScheduleHour.dispatchEvent('change');
elements.cronFormScheduleMinute.value = '45';
elements.cronFormScheduleMinute.dispatchEvent('change');
const weeklyWrite = snapshot();

elements.cronFormSchedule.value = '10 6 15 * *';
elements.cronFormSchedule.dispatchEvent('input');
const monthlySync = snapshot();
elements.cronFormScheduleMonthDay.value = '15';
elements.cronFormScheduleMonthDay.dispatchEvent('change');
elements.cronFormScheduleHour.value = '6';
elements.cronFormScheduleHour.dispatchEvent('change');
elements.cronFormScheduleMinute.value = '10';
elements.cronFormScheduleMinute.dispatchEvent('change');
const monthlyWrite = snapshot();

elements.cronFormSchedule.value = '30 7 * * *';
elements.cronFormSchedule.dispatchEvent('input');
const dailyAfterMonthlySync = snapshot();

elements.cronFormSchedulePreset.value = 'monthly';
elements.cronFormSchedulePreset.dispatchEvent('change');
elements.cronFormScheduleHour.value = '99';
elements.cronFormScheduleMinute.value = '-8';
elements.cronFormScheduleMonthDay.value = '99';
elements.cronFormScheduleMonthDay.dispatchEvent('change');
const normalizedMonthlyWrite = snapshot();

elements.cronFormSchedule.value = '@daily';
elements.cronFormSchedule.dispatchEvent('input');
const shorthandCustom = snapshot();

elements.cronFormSchedule.value = 'advanced: cron expression';
elements.cronFormSchedule.dispatchEvent('input');
const unsupportedCustom = snapshot();

elements.cronFormSchedulePreset.value = 'custom';
elements.cronFormSchedulePreset.dispatchEvent('change');
const customSelectionPreserved = snapshot();

console.log(JSON.stringify({
  hourlySync,
  hourlyWrite,
  dailySync,
  dailyWrite,
  weekdaysSync,
  weeklySync,
  weeklyRawSundaySync,
  weeklyWrite,
  monthlySync,
  monthlyWrite,
  dailyAfterMonthlySync,
  normalizedMonthlyWrite,
  shorthandCustom,
  unsupportedCustom,
  customSelectionPreserved,
}));
"""
    result = json.loads(_run_node(script))

    assert result["hourlySync"]["preset"] == "hourly"
    assert result["hourlySync"]["schedule"] == "15 * * * *"
    assert result["hourlySync"]["paramsDisplay"] == ""
    assert result["hourlySync"]["hourFieldDisplay"] == "none"
    assert result["hourlySync"]["minuteFieldDisplay"] == ""
    assert result["hourlySync"]["kind"] == "cron"
    assert result["hourlyWrite"]["schedule"] == "15 * * * *"
    assert result["hourlyWrite"]["kind"] == "cron"

    assert result["dailySync"]["preset"] == "daily"
    assert result["dailySync"]["schedule"] == "30 7 * * *"
    assert result["dailySync"]["hourFieldDisplay"] == ""
    assert result["dailySync"]["minuteFieldDisplay"] == ""
    assert result["dailySync"]["weekdayFieldDisplay"] == "none"
    assert result["dailySync"]["monthDayFieldDisplay"] == "none"
    assert result["dailyWrite"]["schedule"] == "30 7 * * *"
    assert result["dailyWrite"]["kind"] == "cron"

    assert result["weekdaysSync"]["preset"] == "weekdays"
    assert result["weekdaysSync"]["schedule"] == "5 22 * * 1-5"
    assert result["weekdaysSync"]["hourFieldDisplay"] == ""
    assert result["weekdaysSync"]["minuteFieldDisplay"] == ""
    assert result["weekdaysSync"]["weekdayFieldDisplay"] == "none"
    assert result["weekdaysSync"]["monthDayFieldDisplay"] == "none"

    assert result["weeklySync"]["preset"] == "weekly"
    assert result["weeklySync"]["schedule"] == "45 8 * * 3"
    assert result["weeklySync"]["weekdayFieldDisplay"] == ""
    assert result["weeklySync"]["monthDayFieldDisplay"] == "none"
    assert result["weeklyRawSundaySync"]["preset"] == "weekly"
    assert result["weeklyRawSundaySync"]["schedule"] == "0 9 * * 7"
    assert result["weeklyRawSundaySync"]["weekday"] == "0"
    assert result["weeklyWrite"]["schedule"] == "45 8 * * 3"
    assert result["weeklyWrite"]["kind"] == "cron"

    assert result["monthlySync"]["preset"] == "monthly"
    assert result["monthlySync"]["schedule"] == "10 6 15 * *"
    assert result["monthlySync"]["monthDayFieldDisplay"] == ""
    assert result["monthlySync"]["weekdayFieldDisplay"] == "none"
    assert result["monthlyWrite"]["schedule"] == "10 6 15 * *"
    assert result["monthlyWrite"]["kind"] == "cron"

    assert result["dailyAfterMonthlySync"]["preset"] == "daily"
    assert result["dailyAfterMonthlySync"]["schedule"] == "30 7 * * *"
    assert result["dailyAfterMonthlySync"]["hour"] == "7"
    assert result["dailyAfterMonthlySync"]["minute"] == "30"
    assert result["dailyAfterMonthlySync"]["monthDayFieldDisplay"] == "none"

    assert result["normalizedMonthlyWrite"]["schedule"] == "0 23 31 * *"
    assert result["normalizedMonthlyWrite"]["hour"] == "23"
    assert result["normalizedMonthlyWrite"]["minute"] == "0"
    assert result["normalizedMonthlyWrite"]["monthDay"] == "31"
    assert result["normalizedMonthlyWrite"]["kind"] == "cron"

    assert result["shorthandCustom"]["preset"] == "custom"
    assert result["shorthandCustom"]["schedule"] == "@daily"
    assert result["shorthandCustom"]["paramsDisplay"] == "none"

    assert result["unsupportedCustom"]["preset"] == "custom"
    assert result["unsupportedCustom"]["schedule"] == "advanced: cron expression"
    assert result["unsupportedCustom"]["paramsDisplay"] == "none"

    assert result["customSelectionPreserved"]["preset"] == "custom"
    assert result["customSelectionPreserved"]["schedule"] == "advanced: cron expression"
    assert result["customSelectionPreserved"]["paramsDisplay"] == "none"


def test_cron_schedule_raw_warning_listener_survives_missing_preset_params():
    script = _cron_schedule_source() + r"""
const elements = {};
function $(id) { return elements[id]; }
function makeElement(initialValue = '') {
  return {
    value: initialValue,
    style: { display: '' },
    listeners: {},
    addEventListener(type, handler) {
      (this.listeners[type] || (this.listeners[type] = [])).push(handler);
    },
    dispatchEvent(eventType) {
      const handlers = this.listeners[eventType] || [];
      for (const handler of handlers) handler({ type: eventType, target: this });
    },
  };
}
elements.cronFormSchedule = makeElement();
elements.cronFormSchedulePreset = makeElement('custom');
elements.cronFormScheduleOnceWarning = { style: { display: 'none' } };

_initCronSchedulePresetControls();
elements.cronFormSchedule.value = '30m';
elements.cronFormSchedule.dispatchEvent('input');

console.log(JSON.stringify({
  warning: elements.cronFormScheduleOnceWarning.style.display,
  inputListeners: (elements.cronFormSchedule.listeners.input || []).length,
  presetChangeListeners: (elements.cronFormSchedulePreset.listeners.change || []).length,
}));
"""
    result = json.loads(_run_node(script))

    assert result["warning"] == ""
    assert result["inputListeners"] == 1
    assert result["presetChangeListeners"] == 1


def test_cron_schedule_custom_selection_preserves_raw_schedule_exactly():
    script = _cron_schedule_source() + r"""
const elements = {};
function $(id) { return elements[id]; }
function makeElement(initialValue = '') {
  return {
    value: initialValue,
    style: { display: '' },
    listeners: {},
    addEventListener(type, handler) {
      (this.listeners[type] || (this.listeners[type] = [])).push(handler);
    },
    dispatchEvent(eventType) {
      const handlers = this.listeners[eventType] || [];
      for (const handler of handlers) handler({ type: eventType, target: this });
    },
  };
}
function t(key) {
  const dict = {
    cron_schedule_preset_label: 'Preset',
    cron_schedule_preset_hourly: 'Hourly',
    cron_schedule_preset_daily: 'Daily',
    cron_schedule_preset_weekdays: 'Weekdays',
    cron_schedule_preset_weekly: 'Weekly',
    cron_schedule_preset_monthly: 'Monthly',
    cron_schedule_preset_custom: 'Custom',
  };
  return dict[key];
}
function esc(value) { return value == null ? '' : String(value); }

[
  'cronFormSchedule',
  'cronFormSchedulePreset',
  'cronFormSchedulePresetParams',
  'cronFormScheduleHourField',
  'cronFormScheduleMinuteField',
  'cronFormScheduleWeekdayField',
  'cronFormScheduleMonthDayField',
  'cronFormScheduleHour',
  'cronFormScheduleMinute',
  'cronFormScheduleWeekday',
  'cronFormScheduleMonthDay',
].forEach((id) => {
  elements[id] = makeElement();
});
elements.cronFormScheduleOnceWarning = { style: { display: 'none' } };
elements.cronFormSchedulePresetParams.style.display = 'none';

_initCronSchedulePresetControls();

elements.cronFormSchedule.value = 'advanced: cron expression';
elements.cronFormSchedule.dispatchEvent('input');
elements.cronFormSchedulePreset.value = 'custom';
elements.cronFormSchedulePreset.dispatchEvent('change');

console.log(JSON.stringify({
  preset: elements.cronFormSchedulePreset.value,
  schedule: elements.cronFormSchedule.value,
  paramsDisplay: elements.cronFormSchedulePresetParams.style.display,
}));
"""
    result = json.loads(_run_node(script))

    assert result["preset"] == "custom"
    assert result["schedule"] == "advanced: cron expression"
    assert result["paramsDisplay"] == "none"


def test_cron_form_surfaces_one_shot_warning_copy_markers_and_preset_markup():
    panels = PANELS_JS.read_text(encoding="utf-8")
    style = STYLE_CSS.read_text(encoding="utf-8")
    i18n = I18N_JS.read_text(encoding="utf-8")

    assert "id=\"cronFormScheduleOnceWarning\"" in panels
    assert "id=\"cronFormSchedulePreset\"" in panels
    assert "id=\"cronFormSchedulePresetParams\"" in panels
    assert "id=\"cronFormScheduleHour\"" in panels
    assert "id=\"cronFormScheduleMinute\"" in panels
    assert "id=\"cronFormScheduleWeekday\"" in panels
    assert "id=\"cronFormScheduleMonthDay\"" in panels
    assert "cron_schedule_once_warning" in panels
    assert "_cronSchedulePresetIdForValue" in panels
    assert "_cronSchedulePresetOptionHtml" in panels
    assert "_initCronSchedulePresetControls" in panels
    assert "addEventListener('input', _syncCronSchedulePresetAndWarning" in panels
    assert "addEventListener('change', _syncCronSchedulePresetAndWarning" in panels
    assert "addEventListener('change', _applyCronSchedulePresetSelection" in panels
    assert ".cron-once-warning" in style
    assert ".cron-schedule-preset-shell" in style
    assert ".cron-schedule-preset-params" in style
    assert ".cron-schedule-preset-field" in style
    assert ".cron-schedule-preset-time-hint" in style
    assert "cron_schedule_time_hint" in panels
    assert "fields: ['minute']" in panels
    assert "fields: ['hour', 'minute']" in panels
    assert "fields: ['hour', 'minute', 'weekday']" in panels
    assert "fields: ['hour', 'minute', 'monthDay']" in panels
    assert "Duration forms like '30m' run once" in i18n


def test_cron_form_save_payload_still_uses_visible_raw_schedule_only():
    save_block = _cron_schedule_save_source()
    panels = PANELS_JS.read_text(encoding="utf-8")

    assert "cronFormSchedulePreset" not in save_block
    assert "const schedule=schEl.value.trim();" in save_block
    assert "const updates = {job_id: _editingCronId, schedule, profile: profile, toast_notifications: toastNotifications}" in panels


def test_cron_form_i18n_has_preset_keys():
    i18n = I18N_JS.read_text(encoding="utf-8")
    required_keys = [
        "cron_schedule_preset_label",
        "cron_schedule_preset_hourly",
        "cron_schedule_preset_daily",
        "cron_schedule_preset_weekdays",
        "cron_schedule_preset_weekly",
        "cron_schedule_preset_monthly",
        "cron_schedule_preset_custom",
    ]

    for key in required_keys:
        assert i18n.count(key) >= 14
