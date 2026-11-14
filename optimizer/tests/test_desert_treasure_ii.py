"""Seeded DTII replay: independent medallions, one-time deposits and lamps."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
Q = 'quest.desert_treasure_ii_the_fallen_empire'
CLAIM = 'claim.desert_treasure_ii.ancient_vault'
LAMP = 'reward.dt2.ancient_lamp'
BRANCHES = ('vardorvis', 'leviathan', 'duke', 'whisperer')


class DesertTreasureIITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / 'schemas')
        cls.tables = CatalogValidator(load_catalog(ROOT / 'data/manifest.json', contracts), contracts).tables
        cls.profile = read_json(ROOT / 'data/profiles/main-baseline.json')
        cls.actions = {x['id']: x for x in read_json(ROOT / 'data/catalog/desert-treasure-ii/actions.json')}

    def seed(self, *, dt1=True, secrets=True, levels=True, soul_runes=2):
        state = {**self.profile['initial_state']}
        state['xp_tenths'] = {
            name: 100000000 if levels else 0 for name in state['xp_tenths']
        }
        state['completed_action_ids'] = [
            'quest.enakhras_lament.complete',
            'quest.temple_of_the_eye.complete',
            'quest.the_garden_of_death.complete',
            'quest.below_ice_mountain.complete',
            'miniquest.his_faithful_servants.complete',
        ]
        state['flags'] = {
            **state.get('flags', {}),
            'flag.quest.desert_treasure_i.complete': dt1,
            'flag.quest.secrets_of_the_north.complete': secrets,
        }
        state['inventory'] = {
            **state['inventory'],
            'item.death_rune': 8,
            'item.chaos_rune': 16,
            'item.blood_rune': 2,
            'item.soul_rune': soul_runes,
            'item.fire_rune': 2,
            'item.air_rune': 3,
            'item.water_rune': 4,
            'item.pestle_and_mortar': 1,
            'item.tinderbox': 1,
        }
        state['counters'] = {**state['counters'], 'token.quest_points': 100}
        state['location_id'] = 'location.dt2.vault'
        return RouteState(self.tables, self.profile['policies'], state)

    def apply(self, state, action_id):
        record = self.tables['actions'][action_id]
        initial = state.snapshot()
        # Focused seeded replay: travel topology is tested separately; putting
        # the player at the action's tile isolates mechanics from global routing.
        initial['location_id'] = record['start_location_id']
        state = RouteState(self.tables, self.profile['policies'], initial)
        step = {
            'kind': 'action',
            'action_id': action_id,
            'modeled_seconds': record['duration']['expected_seconds'],
        }
        if 'planned_outcome' in record:
            step['planned_outcome'] = record['planned_outcome']
        return state.apply(step, action_id)

    def run_route(self, state, branch_order=BRANCHES, *, stop_after=None):
        # Stage order in the draft collection is intro, four branches, finale.
        ids = list(self.actions)
        branch_ranges = {}
        for branch in BRANCHES:
            begin = f'{Q}.ask_elissa' if branch == 'vardorvis' else (
                f'{Q}.enter_scar' if branch == 'leviathan' else (
                    f'{Q}.reach_ghorrock' if branch == 'duke' else f'{Q}.descend_lassar'
                )
            )
            end = f'{Q}.deposit_{branch}_medallion'
            branch_ranges[branch] = ids[ids.index(begin):ids.index(end) + 1]
        intro = ids[:ids.index(f'{Q}.ask_elissa')]
        tail = ids[ids.index(f'{Q}.return_with_four_medallions'):-1]
        route = intro + [a for branch in branch_order for a in branch_ranges[branch]] + tail + [CLAIM]
        for action in route:
            if action == stop_after:
                return state
            state = self.apply(state, action)
        return state

    def test_all_four_medallions_and_full_replay(self):
        state = self.run_route(self.seed())
        snapshot = state.snapshot()
        self.assertEqual(snapshot['counters']['token.quest_points'], 105)
        self.assertEqual(snapshot['counters']['counter.dt2.vault_medallions'], 4)
        self.assertEqual(snapshot['inventory']['item.dt2.ring_of_shadows'], 1)
        self.assertEqual(snapshot['inventory'].get('item.dt2.golem_cell', 0), 0)
        for branch in BRANCHES:
            self.assertEqual(snapshot['inventory'].get(f'item.dt2.medallion_{branch}', 0), 0)
        self.assertTrue(snapshot['flags']['unlock.dt2.scar_essence_mine'])
        self.assertIn(CLAIM, snapshot['completed_action_ids'])
        instances = [r for r in snapshot['held_rewards'] if r['reward_id'] == LAMP]
        self.assertEqual(len(instances), 3)
        with self.assertRaises(DataError):
            self.apply(state, CLAIM)

    def test_medallion_paths_can_be_completed_in_other_order(self):
        state = self.run_route(self.seed(), tuple(reversed(BRANCHES)))
        self.assertIn(Q + '.complete', state.snapshot()['completed_action_ids'])
        self.assertEqual(state.snapshot()['counters']['counter.dt2.vault_medallions'], 4)

    def test_prerequisites_are_hard_gates(self):
        for missing in (self.seed(dt1=False), self.seed(secrets=False), self.seed(levels=False)):
            with self.assertRaises(DataError):
                self.apply(missing, Q + '.select_ancients')
        required = self.actions[Q + '.select_ancients']['requirements']['requirements']
        skills = {r['skill_id']: r['minimum_level'] for r in required if r['kind'] == 'skill'}
        self.assertEqual(skills, {
            'skill.magic': 75, 'skill.firemaking': 75, 'skill.thieving': 70,
            'skill.herblore': 62, 'skill.runecraft': 60, 'skill.construction': 60,
        })
        self.assertFalse(any(r.get('boostable', False) for r in required if r['kind'] == 'skill'))

    def test_burst_runes_and_duke_supplies_are_debited(self):
        before = self.run_route(self.seed(), stop_after=Q + '.cast_blood_burst')
        with self.assertRaises(DataError):
            self.apply(self.run_route(self.seed(soul_runes=0), stop_after=Q + '.cast_shadow_burst'),
                       Q + '.cast_shadow_burst')
        after = self.apply(before, Q + '.cast_blood_burst')
        self.assertEqual(after.snapshot()['inventory'].get('item.blood_rune', 0), 0)
        self.assertEqual(after.snapshot()['inventory']['item.death_rune'], 6)
        self.assertEqual(
            self.actions[Q + '.mix_duke_poison']['consumes'],
            [{'item_id': 'item.dt2.arder_mushroom', 'quantity': 3},
             {'item_id': 'item.dt2.musca_mushroom', 'quantity': 3}],
        )

    def test_quest_fails_before_all_four_deposits(self):
        state = self.run_route(self.seed(), stop_after=Q + '.deposit_whisperer_medallion')
        self.assertEqual(state.snapshot()['counters']['counter.dt2.vault_medallions'], 3)
        with self.assertRaises(DataError):
            self.apply(state, Q + '.return_with_four_medallions')
        with self.assertRaises(DataError):
            self.apply(state, Q + '.complete')

    def test_lamp_rules_and_registry_are_one_time(self):
        lamp = self.tables['xp_rewards'][LAMP]
        self.assertEqual(lamp['minimum_level'], 60)
        self.assertEqual(lamp['amount']['xp_tenths'], 1000000)
        self.assertEqual(lamp['selection_count'], 1)
        self.assertTrue(lamp['retainable'])
        self.assertIn('skill.prayer', lamp['eligible_skills'])
        registry = next(x for x in read_json(ROOT / 'data/raw/build-242/reward-registry.json')['entries']
                        if x['id'] == CLAIM)
        self.assertEqual(registry['status'], 'collected')
        self.assertEqual(registry['package']['quantity'], 3)
        self.assertEqual(registry['producer_action_id'], CLAIM)

    def test_main_graph_has_reversible_local_passages(self):
        graph = defaultdict(set)
        for e in self.tables['travel_edges'].values():
            graph[e['from_location_id']].add(e['to_location_id'])
        for a, b in (
            ('location.nardah.rug_merchant', 'location.dt2.vault'),
            ('location.temple_of_the_eye.entrance', 'location.dt2.scar'),
            ('location.northern.weiss_prison', 'location.dt2.ghorrock'),
            ('location.ice_mountain.oracle', 'location.dt2.lassar'),
        ):
            self.assertIn(b, graph[a])
            self.assertIn(a, graph[b])
        self.assertNotIn('location.dt2.vault', graph['location.dt2.stranglewood'])
        seen = {'location.nardah.rug_merchant'}
        queue = deque(seen)
        while queue:
            for destination in graph[queue.popleft()]:
                if destination not in seen:
                    seen.add(destination)
                    queue.append(destination)
        self.assertIn('location.dt2.azzanadra', seen)


if __name__ == '__main__':
    unittest.main()
