const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/app/app.component.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, experimentalDecorators: true }
}).outputText;
function componentClass(timers = { setTimeout, clearTimeout }) {
  const exportsObject = {};
  vm.runInNewContext(compiled, {
    exports: exportsObject,
    require: (name) => name === '@angular/core' ? { Component: () => () => {}, ViewChild: () => () => {} } : {},
    ...timers
  });
  return exportsObject.AppComponent;
}

function setup(timers) {
  const requests = [];
  const Component = componentClass(timers);
  const component = new Component({
    post: (url, body) => ({ subscribe: (callbacks) => requests.push({ method: 'POST', url, body, ...callbacks }) }),
    get: (url) => ({ subscribe: (callbacks) => requests.push({ method: 'GET', url, ...callbacks }) }),
    put: (url, body) => ({ subscribe: (callbacks) => requests.push({ method: 'PUT', url, body, ...callbacks }) })
  });
  component.accessToken = 'test-only';
  component.draftEntries = ['a', 'b'].map((id) => ({ player_id: id, name: id }));
  component.draftState = {
    draft_run: { id: 'draft-1', status: 'drafting', controlled_team_id: 'team-1' },
    current_team_id: 'team-1', current_pick_number: 1, picks: []
  };
  component.draftId = 'draft-1';
  const suggestion = {
    draft_run_id: 'draft-1', team_id: 'team-1', pick_number: 1,
    recommended: { player_id: 'a' }, alternatives: [{ player_id: 'b' }]
  };
  return { component, requests, suggestion };
}

test('recommendation and advisory selection never submit a pick', () => {
  const { component, requests, suggestion } = setup();
  component.loadRecommendation();
  assert.equal(component.recommendationLoading, true);
  requests[0].next(suggestion);
  assert.equal(component.recommendationLoading, false);
  assert.equal(component.recommendation, suggestion);
  component.chooseRecommendation('b');
  assert.equal(component.draftSelectedPlayerId, 'b');
  assert.equal(requests.length, 1);
  component.submitDraftPick();
  assert.equal(requests[1].url, 'http://localhost:8000/api/drafts/draft-1/picks');
  assert.equal(requests[1].body.player_id, 'b');
  assert.equal(component.recommendation, null);
});

test('selected players and responses for the wrong pick are rejected', () => {
  for (const invalidation of ['selected', 'wrong-pick', 'wrong-team']) {
    const { component, requests, suggestion } = setup();
    component.loadRecommendation();
    if (invalidation === 'selected') component.draftState.picks.push({ player_id: 'a' });
    if (invalidation === 'wrong-pick') suggestion.pick_number = 2;
    if (invalidation === 'wrong-team') suggestion.team_id = 'team-2';
    requests[0].next(suggestion);
    assert.equal(component.recommendation, null);
    assert.match(component.recommendationError, /no longer current/);
  }
});

test('advancement clears recommendations and ignores late responses', () => {
  const { component, requests, suggestion } = setup();
  component.loadRecommendation();
  component.advanceDraft('draft-1');
  requests[0].next(suggestion);
  assert.equal(component.recommendation, null);
  assert.equal(component.recommendationLoading, false);
});

test('failure clears the result, supports retry, and leaves manual picks available', () => {
  const { component, requests, suggestion } = setup();
  component.loadRecommendation();
  requests[0].next(suggestion);
  component.loadRecommendation();
  assert.equal(component.recommendation, null);
  requests[1].error({ error: { detail: 'Provider unavailable' } });
  assert.equal(component.recommendationLoading, false);
  assert.equal(component.recommendationError, 'Provider unavailable');
  component.chooseRecommendation('b');
  component.submitDraftPick();
  assert.equal(requests[2].body.player_id, 'b');
});

test('logout and completed drafts ignore recommendations', () => {
  const { component, requests, suggestion } = setup();
  component.loadRecommendation();
  component.logout();
  requests[0].next(suggestion);
  assert.equal(component.recommendation, null);
  const completed = setup();
  completed.component.draftState.draft_run.status = 'completed';
  completed.component.loadRecommendation();
  assert.equal(completed.requests.length, 0);
});

test('unconfigured AI shows an informational notice and leaves manual drafting available', () => {
  const { component, requests } = setup();
  component.loadRecommendation();
  requests[0].error({
    status: 503, error: { detail: { code: 'recommendation_not_configured' } }
  });
  assert.equal(component.recommendationLoading, false);
  assert.equal(component.recommendationError, null);
  assert.match(component.recommendationNotice, /not enabled yet/);
  assert.equal(component.draftBusy, false);
  component.chooseRecommendation('b');
  component.submitDraftPick();
  assert.equal(requests[1].body.player_id, 'b');
  assert.equal(component.recommendationNotice, null);
});

test('draft template hides internal pick sources and distinguishes unavailable AI from errors', () => {
  const template = fs.readFileSync(path.join(__dirname, '../src/app/app.component.html'), 'utf8');
  assert.doesNotMatch(template, /pick\.selection_source|draft-pick-source/);
  assert.match(template, /\*ngIf="recommendationNotice" role="status"/);
  assert.match(template, /\*ngIf="!recommendationNotice" class="text-button"/);
  assert.match(template, /\*ngIf="recommendationError" class="draft-error" role="alert"/);
});

test('empty available pool has an explicit state and makes no provider request', () => {
  const { component, requests } = setup();
  component.draftEntries = [];
  component.loadRecommendation();
  assert.match(component.recommendationError, /No available prospects/);
  assert.equal(requests.length, 0);
});

test('reviewed projections are labeled honestly and existing draft basis stays pinned', () => {
  const { component } = setup();
  component.selectedTeamId = 'team-1';
  component.teams = [{ id: 'team-1', draft_order_basis: 'projected-one-pick-per-team' }];
  component.draftState.draft_run.order_basis = 'legacy-unreviewed';
  assert.match(component.draftOrderLabel, /Sample\/unreviewed/);
  component.draftState.draft_run.order_basis = 'projected-one-pick-per-team';
  assert.match(component.draftOrderLabel, /Projected draft order/);
  assert.match(component.draftOrderLabel, /traded ownership is not modeled/);
  component.draftState = null;
  assert.match(component.draftOrderLabel, /Projected draft order/);
  component.teams[0].draft_order_basis = 'seeded-sample';
  assert.match(component.draftOrderLabel, /not the official NFL order/);
});

test('team needs load in priority order, omit zero scores, and ignore stale responses', () => {
  const { component, requests } = boardSetup();
  component.loadBoard();
  const needsRequest = requests.find((request) => request.url.includes('/needs?'));
  assert.ok(needsRequest);
  assert.match(needsRequest.url, /team-1\/needs\?draft_year=2027/);
  needsRequest.next([
    { position_code: 'QB', need_score: 90 },
    { position_code: 'WR', need_score: 80 },
    { position_code: 'EDGE', need_score: 75 },
    { position_code: 'RB', need_score: 0 },
    { position_code: 'QB', need_score: 70 }
  ]);
  assert.deepEqual(Array.from(component.teamNeeds), ['QB', 'WR', 'ED']);

  component.selectedTeamId = 'team-2';
  component.loadTeamNeeds();
  const stale = needsRequest;
  stale.next([{ position_code: 'TE', need_score: 100 }]);
  assert.deepEqual(Array.from(component.teamNeeds), []);
  requests.at(-1).next([{ position_code: 'CB', need_score: 100 }]);
  assert.deepEqual(Array.from(component.teamNeeds), ['CB']);
});

test('team needs appear above the board title without exposing their scores', () => {
  const template = fs.readFileSync(path.join(__dirname, '../src/app/app.component.html'), 'utf8');
  assert.match(template, /class="team-needs" aria-label="Team needs"/);
  assert.match(template, /<span \*ngFor="let position of teamNeeds">\{\{ position \}\}<\/span>/);
  assert.doesNotMatch(template, /\{\{[^}]*need_score/);
});

const sourceBoard = {
  board: { id: 50, version: 1 },
  entries: [
    { player_id: 'pff-a', first_name: 'Source', last_name: 'Candidate', position: 'WR',
      college_name: 'Ohio State', rank_position: 1, score: 90, source_rank: 2,
      source_name: 'pff-big-board', is_projected: true }
  ]
};

function boardSetup() {
  const state = setup();
  state.component.draftId = null;
  state.component.draftState = null;
  state.component.selectedTeamId = 'team-1';
  return state;
}

test('copying loads persisted personal prospects and saving sends their exact IDs', () => {
  const { component, requests } = boardSetup();
  component.copyBoard();
  assert.match(requests[0].url, /team-1\/board\/copy.*replace_existing=false/);
  assert.equal(component.boardActionEnabled, false);
  component.copyBoard();
  assert.equal(requests.length, 1);
  requests[0].next({ board_id: 50, version: 1 });
  assert.match(requests[1].url, /board_type=personal/);
  requests[1].next(sourceBoard);
  assert.equal(component.boardMode, 'personal');
  assert.equal(component.entries[0].name, 'Source Candidate');
  assert.equal(component.entries[0].source, 'pff-big-board');
  assert.equal(component.entries[0].sourceRank, 2);
  assert.equal(component.entries[0].projected, true);
  component.saveBoard();
  const saveRequest = requests.find((request) => request.method === 'PUT');
  assert.ok(saveRequest);
  assert.deepEqual(Array.from(saveRequest.body.player_ids), ['pff-a']);
});

test('reordering a personal board autosaves and serializes changes made during a save', () => {
  const { component, requests } = boardSetup();
  component.boardMode = 'personal';
  component.boardId = 50;
  component.entries = [
    { player_id: 'p1', name: 'One', rank: 1 },
    { player_id: 'p2', name: 'Two', rank: 2 },
    { player_id: 'p3', name: 'Three', rank: 3 }
  ];
  component.moveEntry(2, -1);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].method, 'PUT');
  assert.deepEqual(Array.from(requests[0].body.player_ids), ['p1', 'p3', 'p2']);
  assert.equal(component.savingBoard, true);

  component.moveEntry(1, -1);
  assert.equal(requests.length, 1);
  requests[0].next({ version: 2 });
  assert.equal(requests.length, 2);
  assert.deepEqual(Array.from(requests[1].body.player_ids), ['p3', 'p1', 'p2']);
  requests[1].next({ version: 3 });
  assert.equal(component.boardVersion, 3);
  assert.equal(component.boardDirty, false);
  assert.equal(component.saved, true);
});

test('failed board autosave shows the error and supports a manual retry', () => {
  const { component, requests } = boardSetup();
  component.boardMode = 'personal';
  component.boardId = 50;
  component.entries = [
    { player_id: 'p1', name: 'One', rank: 1 },
    { player_id: 'p2', name: 'Two', rank: 2 }
  ];
  component.moveEntry(1, -1);
  requests[0].error({ error: { detail: 'Database unavailable' } });
  assert.equal(component.boardSaveFailed, true);
  assert.equal(component.boardDirty, true);
  assert.equal(component.boardActionLabel, 'Retry save');
  assert.match(component.error, /Database unavailable/);

  component.completeBoardAction();
  assert.equal(requests.length, 2);
  assert.deepEqual(Array.from(requests[1].body.player_ids), ['p2', 'p1']);
  requests[1].next({ version: 2 });
  assert.equal(component.boardDirty, false);
  assert.equal(component.boardSaveFailed, false);
});

test('existing custom board requires explicit confirmation and cancellation never writes', () => {
  const { component, requests } = boardSetup();
  component.copyBoard(true);
  assert.equal(requests.length, 0);
  component.copyBoard();
  requests[0].error({ status: 409 });
  assert.equal(component.confirmingBoardCopy, true);
  assert.equal(requests.length, 1);
  component.cancelBoardCopy();
  component.copyBoard(true);
  assert.equal(requests.length, 1);
  component.copyBoard();
  requests[1].error({ status: 409 });
  component.copyBoard(true);
  assert.match(requests[2].url, /replace_existing=true/);
  requests[2].next({ board_id: 51, version: 4 });
  requests[3].next({ ...sourceBoard, board: { id: 51, version: 4 } });
  assert.equal(component.boardVersion, 4);
});

test('failed copy leaves the current board intact and exposes the API error', () => {
  const { component, requests } = boardSetup();
  component.entries = [{ player_id: 'existing' }];
  component.copyBoard();
  requests[0].error({ status: 400, error: { detail: 'Default board has no prospects' } });
  assert.equal(component.entries[0].player_id, 'existing');
  assert.equal(component.error, 'Default board has no prospects');
  assert.equal(component.loading, false);
});

test('late copy and board loads cannot replace another team or signed-out view', () => {
  const { component, requests } = boardSetup();
  component.loadBoard();
  component.selectedTeamId = 'team-2';
  component.onTeamChange();
  requests[0].next(sourceBoard);
  assert.equal(component.entries.length, 0);
  requests.find((request) => request.url.includes('team-2/board?')).next({ board: null, entries: [] });
  component.copyBoard();
  component.logout();
  requests.find((request) => request.url.includes('/board/copy')).next({ board_id: 50, version: 1 });
  assert.equal(component.boardMode, 'default');
  assert.equal(component.entries.length, 0);
  assert.equal(component.loading, false);
  assert.equal(requests.filter((request) => request.url.includes('/board/copy')).length, 1);
});

function clock() {
  let now = 0;
  let id = 0;
  const pending = new Map();
  return {
    setTimeout(callback, delay) { pending.set(++id, { callback, at: now + delay }); return id; },
    clearTimeout(timer) { pending.delete(timer); },
    tick(ms) {
      now += ms;
      for (const [timer, task] of [...pending]) {
        if (task.at <= now) { pending.delete(timer); task.callback(); }
      }
    },
    get pending() { return pending.size; }
  };
}

function draftState(count, currentTeam = 'team-3', status = 'drafting') {
  return {
    draft_run: { id: 'draft-1', status, controlled_team_id: 'team-1' },
    current_team_id: currentTeam, current_pick_number: count + 1,
    picks: Array.from({ length: count }, (_, index) => ({ player_id: `picked-${index}` })),
    trades: []
  };
}

test('automated picks default to a full 2000ms pause and stop on the user turn', () => {
  const timer = clock();
  const { component, requests } = setup(timer);
  component.advanceDraft('draft-1');
  assert.match(requests[0].url, /auto-simulate\?max_picks=1$/);
  requests[0].next(draftState(1));
  assert.equal(component.draftState.picks.length, 1);
  assert.equal(component.draftBusy, true);
  timer.tick(1999);
  assert.equal(requests.length, 1);
  timer.tick(1);
  assert.equal(requests.length, 2);
  timer.tick(10000);
  assert.equal(requests.length, 2, 'no overlapping request while server is responding');
  requests[1].next(draftState(2, 'team-1'));
  assert.equal(component.draftBusy, false);
  assert.match(requests[2].url, /recommendation$/);
  assert.equal(timer.pending, 0);
});

test('each selectable speed waits its exact duration without overlapping requests', () => {
  for (const delay of [3000, 2000, 1000]) {
    const timer = clock();
    const { component, requests } = setup(timer);
    component.setDraftSpeed(delay);
    component.advanceDraft('draft-1');
    requests[0].next(draftState(1));
    timer.tick(delay - 1);
    assert.equal(requests.length, 1);
    timer.tick(1);
    assert.equal(requests.length, 2);
    timer.tick(10000);
    assert.equal(requests.length, 2);
  }
});

test('speed changes replace a pending pause and do not invalidate in-flight requests', () => {
  const timer = clock();
  const { component, requests } = setup(timer);
  component.advanceDraft('draft-1');
  component.setDraftSpeed(3000);
  assert.equal(requests.length, 1);
  requests[0].next(draftState(1));
  timer.tick(500);
  component.setDraftSpeed(1000);
  assert.equal(timer.pending, 1);
  timer.tick(999);
  assert.equal(requests.length, 1);
  timer.tick(1);
  assert.equal(requests.length, 2);
  component.setDraftSpeed(2000);
  assert.equal(timer.pending, 0);
  requests[1].next(draftState(2));
  timer.tick(1999);
  assert.equal(requests.length, 2);
  timer.tick(1);
  assert.equal(requests.length, 3);
  requests[2].next(draftState(3, 'team-1'));
  component.setDraftSpeed(3000);
  assert.equal(timer.pending, 0);
});

test('pick team logos use supplied team data and names survive missing or failed logos', () => {
  const { component } = setup();
  component.teams = [
    { id: 'team-1', name: 'Test team', logo_url: 'https://example.test/team.png' },
    { id: 'team-2', name: 'Other team', logo_url: '' }
  ];
  assert.equal(component.draftTeamLogo('team-1'), 'https://example.test/team.png');
  assert.equal(component.draftTeamLogo('team-2'), null);
  assert.equal(component.draftTeamLogo('unknown'), null);
  component.failedDraftTeamLogos.add('team-1');
  assert.equal(component.draftTeamLogo('team-1'), null);
  assert.equal(component.teamName('team-1'), 'Test team');
  const template = fs.readFileSync(path.join(__dirname, '../src/app/app.component.html'), 'utf8');
  assert.match(template, /draftTeamLogo\(pick.team_id\)/);
  assert.match(template, /failedDraftTeamLogos.add\(pick.team_id\)/);
  assert.doesNotMatch(template, /candidate.projected/);
  assert.doesNotMatch(template, /prospect-notice|Player inclusion does not confirm draft eligibility/);
  assert.match(template, /ngModelChange\)="setDraftSpeed\(\$event\)"/);
  assert.match(template, /<option \*ngFor="let speed of draftSpeeds" \[ngValue\]="speed\.delayMs">\{\{ speed\.label \}\}<\/option>/);
  assert.doesNotMatch(template, /speed\.delayMs \/ 1000/);
});

test('a user pick pauses before the next automatic selection; completion leaves the recap', () => {
  const timer = clock();
  const { component, requests } = setup(timer);
  component.draftSelectedPlayerId = 'a';
  component.submitDraftPick();
  requests[0].next(draftState(1));
  timer.tick(1999);
  assert.equal(requests.length, 1);
  timer.tick(1);
  assert.equal(requests.length, 2);
  requests[1].next(draftState(32, '', 'completed'));
  assert.equal(component.draftBusy, false);
  assert.equal(component.draftState.picks.length, 32);
  assert.equal(timer.pending, 0);
  timer.tick(10000);
  assert.equal(requests.length, 2);
});

test('pacing cancels on logout and destroy, and ignores late responses', () => {
  for (const action of ['logout', 'ngOnDestroy']) {
    const timer = clock();
    const { component, requests } = setup(timer);
    component.advanceDraft('draft-1');
    requests[0].next(draftState(1));
    assert.equal(timer.pending, 1);
    component[action]();
    assert.equal(timer.pending, 0);
    timer.tick(3000);
    assert.equal(requests.length, 1);
    const late = setup(clock());
    late.component.advanceDraft('draft-1');
    late.component[action]();
    late.requests[0].next(draftState(2));
    assert.notEqual(late.component.draftState?.picks.length, 2);
  }
});

test('failed single-pick advancement stops pacing and retries explicitly', () => {
  const timer = clock();
  const { component, requests } = setup(timer);
  component.advanceDraft('draft-1');
  requests[0].error({ error: { detail: 'Service unavailable' } });
  assert.equal(component.draftBusy, false);
  assert.equal(component.draftError, 'Service unavailable');
  timer.tick(3000);
  assert.equal(requests.length, 1);
  component.simulateToUserPick();
  requests[1].next(draftState(32, '', 'completed'));
  assert.equal(component.draftError, null);
  assert.equal(timer.pending, 0);
});

test('pick log metadata comes from the draft pool, including players absent from the personal board', () => {
  const { component } = setup();
  component.draftEntries = component.mapDraftEntries([{
    player_id: 'pool-only', first_name: 'Real', last_name: 'Candidate', position: 'EDGE',
    college_name: 'Ohio State', college_logo_url: 'https://example.test/college.png'
  }], []);
  assert.equal(component.draftPlayerName('pool-only'), 'Real Candidate');
  const details = component.draftPlayerDetails('pool-only');
  assert.equal(details.position, 'EDGE');
  assert.equal(details.school, 'Ohio State');
  assert.equal(details.schoolLogoUrl, 'https://example.test/college.png');
  details.schoolLogoUrl = null;
  assert.equal(component.draftPlayerDetails('pool-only').school, 'Ohio State');
  assert.equal(component.draftPlayerDetails('unknown'), undefined);
  assert.equal(component.draftPlayerName('unknown'), 'unknown');
  const preferred = component.mapDraftEntries([{
    player_id: 'pool-only', position: 'OT', college_name: 'Texas',
    college_logo_url: 'https://example.test/updated.png'
  }], component.draftEntries);
  assert.equal(preferred[0].position, 'OT');
  assert.equal(preferred[0].school, 'Texas');
  assert.equal(preferred[0].schoolLogoUrl, 'https://example.test/updated.png');
});

test('the pick log follows new selections without overriding manual scrolling between picks', () => {
  const { component } = setup();
  const list = { scrollTop: 0, scrollHeight: 1200 };
  component.draftPickList = { nativeElement: list };
  component.setDraftState(draftState(10));
  component.ngAfterViewChecked();
  assert.equal(list.scrollTop, 1200);
  list.scrollTop = 50;
  component.ngAfterViewChecked();
  assert.equal(list.scrollTop, 50);
  component.setDraftState(draftState(11));
  component.ngAfterViewChecked();
  assert.equal(list.scrollTop, 1200);
});
