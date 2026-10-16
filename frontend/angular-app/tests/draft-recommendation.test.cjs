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
const exportsObject = {};
vm.runInNewContext(compiled, {
  exports: exportsObject,
  require: (name) => name === '@angular/core' ? { Component: () => () => {} } : {},
  setTimeout
});

function setup() {
  const requests = [];
  const component = new exportsObject.AppComponent({
    post: (url, body) => ({ subscribe: (callbacks) => requests.push({ url, body, ...callbacks }) })
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

test('empty available pool has an explicit state and makes no provider request', () => {
  const { component, requests } = setup();
  component.draftEntries = [];
  component.loadRecommendation();
  assert.match(component.recommendationError, /No available prospects/);
  assert.equal(requests.length, 0);
});
